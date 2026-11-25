"""The finance estimate matches ventur.com.mt/loan-calculator; checklists follow the applicant."""

import pytest

from app.modules.deals.finance_rules import (
    ApplicantType,
    EstimateError,
    MaritalStatus,
    Rates,
    checklist_for,
    estimate,
)

VENTUR = Rates(annual_rate_bp=650, onboarding_fee_bp=400, yearly_fee_bp=100)


def test_the_estimate_matches_the_website() -> None:
    # Website: price 16500, deposit 3000, 5 years -> net 13500, interest 4387.50, fee 675,
    # onboarding 540, total 19102.50, monthly 318.375 -> EUR 318.38.
    e = estimate(VENTUR, price_cents=1_650_000, deposit_cents=300_000, term_months=60)
    assert e.net_loan_cents == 1_350_000
    assert (e.interest_cents, e.yearly_fee_cents, e.onboarding_fee_cents) == (
        438_750,
        67_500,
        54_000,
    )
    assert (e.total_cents, e.monthly_cents) == (1_910_250, 31_838)


def test_half_years_zero_deposit_and_early_payoff() -> None:
    e = estimate(VENTUR, price_cents=999_999, deposit_cents=0, term_months=42, payoff_months=24)
    # net 9999.99, years 3.5: interest 2274.997725, fee 349.99965, onboarding 399.9996
    assert e.total_cents == 1_302_499  # 13024.986975 -> 13024.99
    assert e.monthly_cents == 31_012  # 310.11873... -> 310.12
    # saved = (interest + fee) - net x 7.5% x 2 = 2624.997375 - 1499.9985 = 1124.998875
    assert e.payoff_saving_cents == 112_500


@pytest.mark.parametrize(
    ("price", "deposit", "months", "message"),
    [
        (0, 0, 60, "more than zero"),
        (100_000, -1, 60, "negative"),
        (100_000, 100_000, 60, "less than the price"),
        (100_000, 0, 0, "between"),
        (100_000, 0, 121 * 6, "between"),
        (100_000, 0, 13, "half years"),
    ],
)
def test_invalid_inputs_are_refused(price: int, deposit: int, months: int, message: str) -> None:
    with pytest.raises(EstimateError, match=message):
        estimate(VENTUR, price_cents=price, deposit_cents=deposit, term_months=months)


def test_checklists_follow_applicant_type_and_marriage() -> None:
    single = checklist_for(ApplicantType.MALTESE_RESIDENT, MaritalStatus.SINGLE)
    married = checklist_for(ApplicantType.MALTESE_RESIDENT, MaritalStatus.MARRIED)
    assert [i.label for i in single][:2] == ["ID Card", "Vehicle Licence"]
    assert len(married) == len(single) + 5
    assert {i.form_kind for i in single} == {None, "kyc", "ccr"}
    company = checklist_for(ApplicantType.COMPANY, MaritalStatus.MARRIED)
    assert not any(i.label.startswith("Spouse") for i in company)
    rental = next(
        i
        for i in checklist_for(ApplicantType.NON_MALTESE_RESIDENT, MaritalStatus.SINGLE)
        if i.label.startswith("Rental")
    )
    assert rental.required is False
    assert all(i.key.startswith("fin_") and len(i.key) <= 40 for i in married)
