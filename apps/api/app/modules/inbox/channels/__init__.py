"""Channel adapters: the only code that knows a provider's message format."""

from app.modules.inbox.channels.base import (
    ChannelAdapter,
    ChannelNotConnectedError,
    DeliveryResult,
    InboundMessage,
    InvalidInboundError,
    OutboundMessage,
    adapter_for,
)

__all__ = [
    "ChannelAdapter",
    "ChannelNotConnectedError",
    "DeliveryResult",
    "InboundMessage",
    "InvalidInboundError",
    "OutboundMessage",
    "adapter_for",
]
