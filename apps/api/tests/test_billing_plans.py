"""Plans must be internally consistent: every module's requirements are in the same plan."""

import pytest

from app.core.billing.plans import BASE_MODULES, PLANS, Plan
from app.core.modules.registry import REGISTRY


@pytest.mark.parametrize("plan", list(Plan))
def test_a_plans_modules_include_what_they_require(plan: Plan) -> None:
    modules = PLANS[plan].modules
    for module in modules:
        assert REGISTRY[module].requires <= modules, (plan, module)


def test_the_base_modules_are_consistent_and_in_every_plan() -> None:
    for module in BASE_MODULES:
        assert REGISTRY[module].requires <= BASE_MODULES
    for spec in PLANS.values():
        assert spec.modules >= BASE_MODULES
