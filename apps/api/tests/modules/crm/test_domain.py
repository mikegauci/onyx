"""CRM domain rules without a database: identity normalisation, lead lifecycle, CSV parsing."""

import itertools

import pytest

from app.modules.crm.identity import IdentityError, normalise_email, normalise_phone
from app.modules.crm.importer import MAX_BYTES, MAX_ROWS, ImportFileError, parse_contacts_csv
from app.modules.crm.lifecycle import TRANSITIONS, allowed_transitions, can_transition
from app.modules.crm.models import LeadStatus

NEW, CONTACTED, QUALIFIED, WON, LOST = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
    LeadStatus.WON,
    LeadStatus.LOST,
)

# --- identity --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Anna@Example.TEST ", "anna@example.test"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_email_is_trimmed_and_lower_cased(raw: str | None, expected: str | None) -> None:
    assert normalise_email(raw) == expected


@pytest.mark.parametrize("raw", ["not-an-email", "a@", "@b.test", "a b@c.test"])
def test_invalid_email_is_rejected_without_echoing_it(raw: str) -> None:
    with pytest.raises(IdentityError) as exc:
        normalise_email(raw)
    assert raw not in str(exc.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2123 4567", "+35621234567"),  # 8 digits: Maltese
        ("+356 9912-3456", "+35699123456"),
        ("00356 (21) 23.45.67", "+35621234567"),
        ("+44 20 7946 0000", "+442079460000"),
        ("0044 20 7946 0000", "+442079460000"),
        ("", None),
        (None, None),
    ],
)
def test_phone_is_normalised_to_e164(raw: str | None, expected: str | None) -> None:
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "+0123456789", "phone", "+356 2123 4567 8901 2345"])
def test_invalid_phone_is_rejected(raw: str) -> None:
    with pytest.raises(IdentityError):
        normalise_phone(raw)


# --- lifecycle -------------------------------------------------------------------------------


def test_happy_path_and_reopen() -> None:
    path = [NEW, CONTACTED, QUALIFIED, WON]
    for current, target in itertools.pairwise(path):
        assert can_transition(current, target)
    for status in (NEW, CONTACTED, QUALIFIED):
        assert can_transition(status, LOST)
    assert can_transition(LOST, NEW)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (NEW, QUALIFIED),
        (NEW, WON),
        (CONTACTED, WON),
        (CONTACTED, NEW),
        (QUALIFIED, NEW),
        (WON, LOST),
        (WON, NEW),
        (LOST, WON),
        (NEW, NEW),
    ],
)
def test_other_transitions_are_refused(current: LeadStatus, target: LeadStatus) -> None:
    assert not can_transition(current, target)


def test_every_status_has_rules_and_won_is_terminal() -> None:
    assert set(TRANSITIONS) == set(LeadStatus)
    assert allowed_transitions(WON) == []


# --- CSV import ------------------------------------------------------------------------------

HEADER = "full_name,email,phone,company,notes,lead_title\n"


def test_valid_rows_are_parsed_and_normalised() -> None:
    parsed = parse_contacts_csv(
        "﻿Full Name,EMAIL,Phone,Company,Lead Title,Ignored\n"
        "Anna Abela,Anna@Lumen.example.test,2123 4567,Acme (test),Lamps,x\n"
        "\n"
        "Ben Bonello,,+356 9900 0000,,,\n"
    )
    assert parsed.total == 2
    assert parsed.errors == []
    first, second = parsed.rows
    assert (first.row, first.email, first.phone) == (2, "anna@lumen.example.test", "+35621234567")
    assert (first.company, first.lead_title) == ("Acme (test)", "Lamps")
    assert (second.row, second.email, second.phone) == (4, None, "+35699000000")


def test_row_errors_name_row_and_field_but_not_the_value() -> None:
    parsed = parse_contacts_csv(
        HEADER
        + ",a@x.test,,,,\n"  # no name
        + "Bad Email,secret-value,,,,\n"
        + "No Identity,,,,,\n"
        + "Bad Phone,,12,,,\n"
        + "Fine Row,ok@x.test,,,,\n"
    )
    errors = {(e.row, e.field) for e in parsed.errors}
    assert errors == {(2, "full_name"), (3, "email"), (4, "email"), (5, "phone")}
    assert all("secret-value" not in e.message for e in parsed.errors)
    assert [r.row for r in parsed.rows] == [6]


def test_over_long_cells_are_errors() -> None:
    parsed = parse_contacts_csv(HEADER + "x" * 201 + ",a@x.test,,,,\n")
    assert [(e.row, e.field) for e in parsed.errors] == [(2, "full_name")]


def test_duplicates_within_the_file_are_reported_against_the_first_row() -> None:
    parsed = parse_contacts_csv(
        HEADER
        + "Anna,anna@x.test,,,,\n"
        + "Anna Again,ANNA@x.test,,,,\n"
        + "Phone One,,2123 4567,,,\n"
        + "Phone Two,,+356 2123 4567,,,\n"
    )
    assert [r.row for r in parsed.rows] == [2, 4]
    assert parsed.file_duplicates == [(3, "email", 2), (5, "phone", 4)]


def test_formula_like_cells_are_kept_as_plain_text() -> None:
    parsed = parse_contacts_csv(HEADER + '"=HYPERLINK(""x"")",f@x.test,,,"+SUM(1)",\n')
    assert parsed.rows[0].full_name == '=HYPERLINK("x")'
    assert parsed.rows[0].notes == "+SUM(1)"


def test_skipped_duplicate_does_not_claim_its_other_identity() -> None:
    parsed = parse_contacts_csv(
        HEADER
        + "First,first@x.test,2123 4567,,,\n"
        + "Skipped,second@x.test,2123 4567,,,\n"
        + "Second,second@x.test,2123 4568,,,\n"
    )
    assert [r.row for r in parsed.rows] == [2, 4]
    assert parsed.file_duplicates == [(3, "phone", 2)]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ("email,phone\n", "full_name"),
        ("full_name,company\n", "email or a phone"),
        ("full_name,email,email\n", "Repeated"),
        ('full_name,email\n"unterminated,a@x.test\n', "not valid CSV"),
    ],
)
def test_file_level_errors(content: str, message: str) -> None:
    with pytest.raises(ImportFileError, match=message):
        parse_contacts_csv(content)


def test_row_and_size_limits() -> None:
    rows = "".join(f"P{i},p{i}@x.test,,,,\n" for i in range(MAX_ROWS + 1))
    with pytest.raises(ImportFileError, match="rows"):
        parse_contacts_csv(HEADER + rows)
    with pytest.raises(ImportFileError, match="larger"):
        parse_contacts_csv(HEADER + "x" * MAX_BYTES)
