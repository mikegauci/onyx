"""Errors the gateway raises. Messages are generic: no prompt, reply, key or provider text."""

from app.core.errors import AppError, ErrorCode, ServiceUnavailableError


class AIUnavailableError(ServiceUnavailableError):
    """No usable model: not configured, no key, or no price. Fail closed."""

    default_message = "AI is not available for this workspace right now."


class AIProviderError(ServiceUnavailableError):
    """The provider failed, timed out or returned output that did not validate."""

    default_message = "The AI provider could not complete the request. Try again later."


class AIBudgetExceededError(AppError):
    status_code = 429
    code = ErrorCode.BUDGET_EXCEEDED
    default_message = "This workspace has reached its AI spending limit for the month."
