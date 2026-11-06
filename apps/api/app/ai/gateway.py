"""The AI gateway: the only way application code calls a model.

One call, in order:

1. Resolve the workload's model and its configured price (unconfigured, unpriced or keyless
   means unavailable: fail closed, no provider call).
2. Reserve the worst-case cost in a short transaction as ``onyx_worker`` bound to the tenant,
   holding the tenant's budget row lock, so concurrent calls cannot overspend. No budget, or not
   enough left, records a ``budget_blocked`` event and refuses the call.
3. Call the provider with a per-attempt timeout and bounded retries for transient errors only.
   The output must validate against the caller's Pydantic schema.
4. Finalise the event once with the provider's token counts and the real cost.

The tenant id must come from server-side membership (``WorkspaceAccess``) or a verified
platform-admin lookup, never from input. Prompts and replies are never logged or stored.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dt_time
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, UsageLimits, capture_run_messages
from pydantic_ai.exceptions import (
    AgentRunError,
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelTimeoutError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
)
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import AIBudgetExceededError, AIProviderError
from app.ai.models import AIBudget, AIUsageEvent, UsageStatus
from app.ai.pricing import TokenPrice, estimate_input_tokens
from app.ai.providers import ModelFactory, ModelRef, build_model, price_for, resolve_model
from app.ai.redaction import error_kind, log_ai
from app.core.config import Settings
from app.core.db.context import worker_transaction
from app.core.logging import request_id_var

# Model requests per attempt: the first answer plus one retry when its output fails validation.
REQUESTS_PER_ATTEMPT = 2

# Transient provider failures worth another attempt. Quota, auth, bad requests are not.
RETRYABLE_ERRORS: tuple[type[ModelAPIError], ...] = (
    ModelRateLimitError,
    ModelUnavailableError,
    ModelServerError,
    ModelConnectionError,
    ModelRequestTimeout,
)


def period_start(now: datetime) -> date:
    """First day of the UTC month containing ``now``; budgets reset then."""
    return now.astimezone(UTC).date().replace(day=1)


def period_start_at(period: date) -> datetime:
    """The UTC instant a budget period starts."""
    return datetime.combine(period, dt_time.min, tzinfo=UTC)


@dataclass(frozen=True)
class AIUsage:
    event_id: uuid.UUID
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int
    attempts: int
    latency_ms: int


@dataclass(frozen=True)
class AIResult[T: BaseModel]:
    output: T
    usage: AIUsage


@dataclass
class _Outcome:
    status: UsageStatus
    output: Any = None
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 0
    error_kind: str | None = None


@dataclass(frozen=True)
class _Reservation:
    event_id: uuid.UUID | None  # None when the call was blocked
    reason: str | None = None
    alert: dict[str, int] | None = None


def _tokens(messages: list[ModelMessage]) -> tuple[int, int]:
    responses = [m for m in messages if isinstance(m, ModelResponse)]
    return (
        sum(r.usage.input_tokens for r in responses),
        sum(r.usage.output_tokens for r in responses),
    )


class AIGateway:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        model_factory: ModelFactory = build_model,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions = sessions
        self._settings = settings
        self._model_factory = model_factory
        self._sleep = sleep
        self._now = now

    async def run_structured[T: BaseModel](
        self,
        *,
        organization_id: uuid.UUID,
        workload: str,
        output_type: type[T],
        instructions: str,
        prompt: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> AIResult[T]:
        ref = resolve_model(self._settings, workload)
        price = price_for(self._settings, ref)
        model = self._model_factory(ref, self._settings)

        reserve = self.worst_case_cost_micros(price, output_type, instructions, prompt)
        fields = {"organization_id": organization_id, "workload": workload, "model": ref.ref}

        reservation = await self._reserve(organization_id, workload, ref, reserve, actor_user_id)
        if reservation.alert is not None:
            log_ai(
                logging.WARNING, "ai budget alert threshold reached", **fields, **reservation.alert
            )
        if reservation.event_id is None:
            log_ai(logging.WARNING, "ai call blocked by budget", **fields, status="budget_blocked")
            raise AIBudgetExceededError(reservation.reason)

        started = time.monotonic()
        outcome = await self._call(model, output_type, instructions, prompt)
        latency_ms = int((time.monotonic() - started) * 1000)
        cost = price.cost_micros(outcome.input_tokens, outcome.output_tokens)
        await self._finalise(organization_id, reservation.event_id, outcome, cost, latency_ms)

        usage = AIUsage(
            event_id=reservation.event_id,
            provider=ref.provider,
            model=ref.name,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            cost_usd_micros=cost,
            attempts=outcome.attempts,
            latency_ms=latency_ms,
        )
        log_ai(
            logging.INFO if outcome.status is UsageStatus.SUCCEEDED else logging.WARNING,
            "ai call finished",
            **fields,
            event_id=usage.event_id,
            status=outcome.status.value,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd_micros=cost,
            attempts=usage.attempts,
            latency_ms=latency_ms,
            error_kind=outcome.error_kind,
        )
        if outcome.status is not UsageStatus.SUCCEEDED:
            raise AIProviderError
        return AIResult(output=outcome.output, usage=usage)

    def worst_case_cost_micros(
        self, price: TokenPrice, output_type: type[BaseModel], instructions: str, prompt: str
    ) -> int:
        """The most one call may spend: every attempt and output retry at full length."""
        schema = json.dumps(output_type.model_json_schema())
        requests = REQUESTS_PER_ATTEMPT * self._settings.ai_max_attempts
        return price.cost_micros(
            estimate_input_tokens(instructions, prompt, schema) * requests,
            self._settings.ai_max_output_tokens * requests,
        )

    # --- budget --------------------------------------------------------------------------

    async def _reserve(
        self,
        organization_id: uuid.UUID,
        workload: str,
        ref: ModelRef,
        reserve: int,
        actor_user_id: uuid.UUID | None,
    ) -> _Reservation:
        period = period_start(self._now())
        values = {
            "organization_id": organization_id,
            "workload": workload,
            "provider": ref.provider,
            "model": ref.name,
            "actor_user_id": actor_user_id,
            "request_id": request_id_var.get(),
        }
        async with worker_transaction(self._sessions, organization_id) as (session, _):
            budget = await session.scalar(
                select(AIBudget)
                .where(AIBudget.organization_id == organization_id)
                .with_for_update()
            )
            spent = int(
                await session.scalar(
                    select(func.coalesce(func.sum(AIUsageEvent.cost_usd_micros), 0)).where(
                        AIUsageEvent.organization_id == organization_id,
                        AIUsageEvent.created_at >= period_start_at(period),
                    )
                )
                or 0
            )
            reason: str | None = None
            if budget is None:
                reason = "No AI budget is set for this workspace."
            elif spent + reserve > budget.monthly_limit_usd_micros:
                reason = None  # the default message: the monthly limit is reached
            else:
                event_id = await session.scalar(
                    insert(AIUsageEvent)
                    .values(**values, status=UsageStatus.RESERVED, cost_usd_micros=reserve)
                    .returning(AIUsageEvent.id)
                )
                if event_id is None:  # pragma: no cover - INSERT ... RETURNING always returns
                    raise RuntimeError("usage event was not created")
                alert = await self._maybe_alert(session, budget, period, spent + reserve)
                return _Reservation(event_id=event_id, alert=alert)

            await session.execute(
                insert(AIUsageEvent).values(
                    **values,
                    status=UsageStatus.BUDGET_BLOCKED,
                    cost_usd_micros=0,
                    finished_at=func.now(),
                )
            )
            return _Reservation(event_id=None, reason=reason)

    async def _maybe_alert(
        self, session: AsyncSession, budget: AIBudget, period: date, committed: int
    ) -> dict[str, int] | None:
        """Mark (once per month) that committed spend crossed the alert threshold."""
        limit = budget.monthly_limit_usd_micros
        if committed * 100 < limit * budget.alert_percent or budget.alerted_period == period:
            return None
        await session.execute(
            update(AIBudget)
            .where(AIBudget.organization_id == budget.organization_id)
            .values(alerted_period=period, updated_at=func.now())
        )
        return {
            "spent_usd_micros": committed,
            "limit_usd_micros": limit,
            "alert_percent": budget.alert_percent,
        }

    async def _finalise(
        self,
        organization_id: uuid.UUID,
        event_id: uuid.UUID,
        outcome: _Outcome,
        cost: int,
        latency_ms: int,
    ) -> None:
        async with worker_transaction(self._sessions, organization_id) as (session, _):
            await session.execute(
                update(AIUsageEvent)
                .where(
                    AIUsageEvent.id == event_id,
                    AIUsageEvent.organization_id == organization_id,
                    AIUsageEvent.status == UsageStatus.RESERVED,
                )
                .values(
                    status=outcome.status,
                    input_tokens=outcome.input_tokens,
                    output_tokens=outcome.output_tokens,
                    cost_usd_micros=cost,
                    attempts=outcome.attempts,
                    latency_ms=latency_ms,
                    error_kind=outcome.error_kind,
                    finished_at=func.now(),
                )
            )

    # --- provider call -------------------------------------------------------------------

    async def _call[T: BaseModel](
        self, model: Model, output_type: type[T], instructions: str, prompt: str
    ) -> _Outcome:
        settings = self._settings
        timeout = settings.ai_timeout_seconds
        model_settings = ModelSettings(
            max_tokens=settings.ai_max_output_tokens,
            request_timeout=timeout,
            max_retries=0,  # retries happen here, where they are counted and bounded
        )
        outcome = _Outcome(status=UsageStatus.PROVIDER_ERROR)
        for attempt in range(1, settings.ai_max_attempts + 1):
            outcome.attempts = attempt
            agent = Agent(
                model, output_type=output_type, instructions=instructions, retries={"output": 1}
            )
            retryable = False
            with capture_run_messages() as messages:
                try:
                    async with asyncio.timeout(timeout):
                        result = await agent.run(
                            prompt,
                            model_settings=model_settings,
                            usage_limits=UsageLimits(request_limit=REQUESTS_PER_ATTEMPT),
                        )
                    outcome.status, outcome.output, outcome.error_kind = (
                        UsageStatus.SUCCEEDED,
                        result.output,
                        None,
                    )
                except ModelAPIError as exc:
                    timed_out = isinstance(exc, ModelTimeoutError | ModelRequestTimeout)
                    outcome.status = (
                        UsageStatus.TIMEOUT if timed_out else UsageStatus.PROVIDER_ERROR
                    )
                    outcome.error_kind = error_kind(exc)
                    retryable = isinstance(exc, RETRYABLE_ERRORS)
                except TimeoutError as exc:
                    outcome.status, outcome.error_kind = UsageStatus.TIMEOUT, error_kind(exc)
                    retryable = True
                except (UnexpectedModelBehavior, AgentRunError) as exc:
                    # Output failed validation (after its one retry) or broke the request limit.
                    outcome.status, outcome.error_kind = UsageStatus.INVALID_OUTPUT, error_kind(exc)
                except Exception as exc:  # unexpected adapter failure: record it, never leak it
                    outcome.status, outcome.error_kind = UsageStatus.PROVIDER_ERROR, error_kind(exc)
                finally:
                    used_in, used_out = _tokens(messages)
                    outcome.input_tokens += used_in
                    outcome.output_tokens += used_out
            if outcome.status is UsageStatus.SUCCEEDED or not retryable:
                break
            if attempt < settings.ai_max_attempts:
                await self._sleep(settings.ai_retry_backoff_seconds * 2 ** (attempt - 1))
        return outcome
