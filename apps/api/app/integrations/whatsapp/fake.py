"""An in-memory WhatsApp provider for local and e2e runs. Settings refuse it when deployed.

Nothing leaves the process. Sends are recorded and get a fake message id; the template list
is whatever was set on ``templates`` (one approved utility template by default).
"""

import uuid
from collections.abc import Sequence

from app.integrations.whatsapp import OutgoingWhatsApp, TemplateInfo

DEFAULT_TEMPLATES = (
    TemplateInfo(
        provider_id="1000000000000001",
        name="follow_up",
        language="en",
        category="utility",
        status="approved",
        body="Hello {{1}}, this is a follow-up about your enquiry. Reply here to continue.",
        param_count=1,
        supported=True,
    ),
)


class FakeWhatsAppProvider:
    name = "fake"

    def __init__(self, templates: Sequence[TemplateInfo] = DEFAULT_TEMPLATES) -> None:
        self.sent: list[OutgoingWhatsApp] = []
        self.templates = list(templates)

    async def send(self, message: OutgoingWhatsApp) -> str:
        self.sent.append(message)
        return f"wamid.fake-{uuid.uuid4().hex}"

    async def list_templates(self, waba_id: str) -> Sequence[TemplateInfo]:
        del waba_id
        return list(self.templates)
