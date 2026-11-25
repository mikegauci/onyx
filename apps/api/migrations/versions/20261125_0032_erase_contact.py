"""Erase a contact (data protection tools, part 1).

- ``crm_contacts.erased_at``: when the contact was erased.
- ``app_erasing(rel)``: true only while ``app_erase_contact`` runs, as the schema owner, with
  the transaction marked as an erasure. The append-only and frozen-version guards gain this one
  exception; the app and worker roles can never satisfy it (they are not the table owner).
- ``app_erase_contact(contact, request_id)`` (SECURITY DEFINER, executable by ``onyx_app``):
  owners only, in the bound tenant. Redacts the person everywhere, keeps amounts, dates, numbers
  and suppressions, records one audit entry with ids only, and returns the stored file ids of
  the person's deal documents so the API deletes the objects.

The downgrade restores the original guards and drops the function and column.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db.rls import APP_ROLE, WORKER_ROLE

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERASING = """
CREATE FUNCTION app_erasing(rel oid) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public
AS $$
    SELECT coalesce(current_setting('onyx.erasing', true), '') = 'on'
       AND current_user = (SELECT pg_get_userbyid(c.relowner) FROM pg_class c WHERE c.oid = rel)
$$
"""
BYPASS = "    IF public.app_erasing(TG_RELID) THEN RETURN NEW; END IF;\n"

GUARDS_BEFORE = {
    "crm_activities_append_only": """
BEGIN
    RAISE EXCEPTION 'crm_activities is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
""",
    "inbox_append_only": """
BEGIN
    RAISE EXCEPTION '% is append-only (% blocked)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
""",
    "deal_events_append_only": """
BEGIN
    RAISE EXCEPTION 'deal_events is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
""",
    "quotations_version_frozen": """
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'quotations_versions cannot be deleted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status = 'draft' THEN
        RETURN NEW;
    END IF;
    IF OLD.status = 'approved' AND NEW.status = 'superseded'
        AND (to_jsonb(NEW) - 'status' - 'updated_at') = (to_jsonb(OLD) - 'status' - 'updated_at')
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'quotation version % is frozen (%)', OLD.version, OLD.status
        USING ERRCODE = 'insufficient_privilege';
END;
""",
    "outbound_draft_guard": """
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'outbound drafts cannot be deleted'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status NOT IN ('pending', 'approved') THEN
        RAISE EXCEPTION 'outbound draft is % and cannot change', OLD.status
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status = 'sent' AND OLD.status <> 'approved' THEN
        RAISE EXCEPTION 'only an approved outbound draft can be sent'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.current_revision < OLD.current_revision THEN
        RAISE EXCEPTION 'outbound draft revisions only move forward'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
""",
}
REVISION_GUARD_BEFORE = """
DECLARE
    state text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'outbound revisions are append-only (% blocked)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT status INTO state FROM outbound_drafts WHERE id = NEW.draft_id;
    IF state IS NOT NULL AND state NOT IN ('pending', 'approved') THEN
        RAISE EXCEPTION 'outbound draft is % and cannot get a new revision', state
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
"""


def _with_bypass(body: str) -> str:
    """The same guard, with the erasure exception as its first statement."""
    head, _, tail = body.partition("BEGIN\n")
    return f"{head}BEGIN\n{BYPASS}{tail}"


def _replace(name: str, body: str) -> str:
    return f"CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $${body}$$"


ERASE = """
CREATE FUNCTION app_erase_contact(p_contact uuid, p_request_id text)
RETURNS TABLE (removed_file uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    org uuid := public.app_current_organization_id();
    leads uuid[];
    convs uuid[];
    msgs uuid[];
    drafts uuid[];
    quotes uuid[];
    dls uuid[];
    calls uuid[];
    files uuid[];
BEGIN
    IF org IS NULL OR public.app_membership_role(org) IS DISTINCT FROM 'owner' THEN
        RAISE EXCEPTION 'owner required' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.crm_contacts WHERE organization_id = org AND id = p_contact
    ) THEN
        RAISE EXCEPTION 'contact not found' USING ERRCODE = 'P0002';
    END IF;
    PERFORM set_config('onyx.erasing', 'on', true);

    SELECT coalesce(array_agg(id), '{}') INTO leads FROM public.crm_leads
        WHERE organization_id = org AND contact_id = p_contact;
    SELECT coalesce(array_agg(DISTINCT c.id), '{}') INTO convs FROM public.inbox_conversations c
        WHERE c.organization_id = org AND (c.contact_id = p_contact OR EXISTS (
            SELECT 1 FROM public.inbox_participants p
            WHERE p.organization_id = org AND p.conversation_id = c.id
              AND p.contact_id = p_contact));
    SELECT coalesce(array_agg(id), '{}') INTO msgs FROM public.inbox_messages
        WHERE organization_id = org AND conversation_id = ANY (convs);
    SELECT coalesce(array_agg(id), '{}') INTO drafts FROM public.outbound_drafts
        WHERE organization_id = org AND conversation_id = ANY (convs);
    SELECT coalesce(array_agg(id), '{}') INTO quotes FROM public.quotations_quotes
        WHERE organization_id = org AND contact_id = p_contact;
    SELECT coalesce(array_agg(id), '{}') INTO dls FROM public.deals
        WHERE organization_id = org AND contact_id = p_contact;
    SELECT coalesce(array_agg(id), '{}') INTO calls FROM public.inbox_missed_calls
        WHERE organization_id = org AND conversation_id = ANY (convs);
    SELECT coalesce(array_agg(d.file_id), '{}') INTO files FROM public.deal_documents d
        WHERE d.organization_id = org AND d.deal_id = ANY (dls) AND d.file_id IS NOT NULL;

    UPDATE public.crm_contacts SET full_name = 'Erased contact', email = NULL, phone = NULL,
        notes = NULL, archived_at = coalesce(archived_at, now()), erased_at = now(),
        updated_at = now()
        WHERE organization_id = org AND id = p_contact;
    UPDATE public.crm_leads SET title = 'Erased lead', notes = NULL, lost_reason = NULL,
        updated_at = now()
        WHERE organization_id = org AND id = ANY (leads);
    UPDATE public.crm_activities SET body = NULL, details = '{}'::jsonb
        WHERE organization_id = org AND (subject_id = p_contact OR subject_id = ANY (leads));

    UPDATE public.inbox_conversations SET subject = 'Erased conversation',
        external_thread_ref = NULL, handoff_reason = NULL, updated_at = now()
        WHERE organization_id = org AND id = ANY (convs);
    UPDATE public.inbox_messages SET body = '[erased]'
        WHERE organization_id = org AND id = ANY (msgs);
    UPDATE public.inbox_events SET details = '{}'::jsonb
        WHERE organization_id = org AND conversation_id = ANY (convs);
    UPDATE public.inbox_participants SET display_name = NULL, address = NULL
        WHERE organization_id = org AND conversation_id = ANY (convs);
    UPDATE public.inbox_email_deliveries SET recipient = 'erased', detail = NULL
        WHERE organization_id = org AND message_id = ANY (msgs);
    UPDATE public.inbox_whatsapp_sends SET recipient = 'erased', detail = NULL
        WHERE organization_id = org AND conversation_id = ANY (convs);
    UPDATE public.inbox_missed_calls SET caller = NULL
        WHERE organization_id = org AND id = ANY (calls);

    UPDATE public.outbound_revisions SET body = '[erased]', template_params = '[]'::jsonb
        WHERE organization_id = org AND draft_id = ANY (drafts);
    UPDATE public.outbound_drafts SET rejection_reason = CASE
            WHEN rejection_reason IS NULL THEN NULL ELSE '[erased]' END
        WHERE organization_id = org AND id = ANY (drafts);

    UPDATE public.quotations_quotes SET title = 'Erased quote'
        WHERE organization_id = org AND id = ANY (quotes);
    UPDATE public.quotations_versions SET notes = NULL
        WHERE organization_id = org AND quote_id = ANY (quotes);

    UPDATE public.deals SET title = 'Erased deal',
        cancel_reason = CASE WHEN cancel_reason IS NULL THEN NULL ELSE '[erased]' END,
        updated_at = now()
        WHERE organization_id = org AND id = ANY (dls);
    UPDATE public.deal_events SET details = '{}'::jsonb
        WHERE organization_id = org AND deal_id = ANY (dls);
    UPDATE public.deal_documents SET file_id = NULL, file_deleted_at = now(),
        rejection_reason = NULL, updated_at = now()
        WHERE organization_id = org AND deal_id = ANY (dls) AND file_id IS NOT NULL;

    UPDATE public.tasks SET title = 'Follow-up (erased contact)'
        WHERE organization_id = org
          AND subject_id = ANY (ARRAY[p_contact] || leads || convs || dls || calls);

    INSERT INTO public.audit_entries (
        organization_id, actor_user_id, action, target_type, target_id, metadata, request_id
    ) VALUES (
        org, public.app_current_user_id(), 'privacy.contact_erased', 'contact', p_contact,
        jsonb_build_object(
            'conversations', cardinality(convs), 'messages', cardinality(msgs),
            'leads', cardinality(leads), 'quotes', cardinality(quotes),
            'deals', cardinality(dls), 'files', cardinality(files)
        ),
        p_request_id
    );
    PERFORM set_config('onyx.erasing', 'off', true);
    RETURN QUERY SELECT unnest(files);
END
$$
"""
SIGNATURE = "app_erase_contact(uuid, text)"


def upgrade() -> None:
    op.add_column("crm_contacts", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    # An erased contact keeps no email or phone.
    op.execute("ALTER TABLE crm_contacts DROP CONSTRAINT ck_crm_contacts_has_identity")
    op.execute(
        "ALTER TABLE crm_contacts ADD CONSTRAINT ck_crm_contacts_has_identity "
        "CHECK (email IS NOT NULL OR phone IS NOT NULL OR erased_at IS NOT NULL)"
    )
    op.execute(ERASING)
    # The guards call it under whichever role writes, so the app and worker roles need it;
    # nobody else (in particular not Supabase's Data API roles through PUBLIC).
    op.execute("REVOKE ALL ON FUNCTION app_erasing(oid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_erasing(oid) TO {APP_ROLE}, {WORKER_ROLE}")
    for name, body in GUARDS_BEFORE.items():
        op.execute(_replace(name, _with_bypass(body)))
    op.execute(_replace("outbound_revision_guard", _with_bypass(REVISION_GUARD_BEFORE)))
    op.execute(ERASE)
    op.execute(f"REVOKE ALL ON FUNCTION {SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {SIGNATURE}")
    for name, body in GUARDS_BEFORE.items():
        op.execute(_replace(name, body))
    op.execute(_replace("outbound_revision_guard", REVISION_GUARD_BEFORE))
    op.execute("DROP FUNCTION IF EXISTS app_erasing(oid)")
    op.execute("ALTER TABLE crm_contacts DROP CONSTRAINT ck_crm_contacts_has_identity")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM crm_contacts WHERE erased_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Erased contacts exist; downgrade by restoring a backup';
            END IF;
        END
        $$
        """
    )
    op.execute(
        "ALTER TABLE crm_contacts ADD CONSTRAINT ck_crm_contacts_has_identity "
        "CHECK (email IS NOT NULL OR phone IS NOT NULL)"
    )
    op.drop_column("crm_contacts", "erased_at")
