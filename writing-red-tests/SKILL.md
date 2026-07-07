---
name: writing-red-tests
description: Use when writing RED tests before implementation exists, especially when specifications exist but production code is missing or incomplete. This skill prevents vague overview tests by requiring every RED test to call the planned public API and assert concrete observable behavior.
---

# Writing RED Tests

## Overview

A RED test is an executable behavior specification for code that does not exist yet or does not yet satisfy the specification.

The test must be written as if the implementation already exists. It should call the planned public boundary and assert the output, error, state change, event, or serialized result required by the spec.

A RED test is not a planning note, overview check, placeholder, import smoke test, framework validation test, or coverage filler.

## Core Rule

Every RED test must answer this in code:

> When the planned public API is called with this input, what exact observable result should happen?

> If the test does not call the planned public API or assert a concrete observable result, it is not a RED test.

## Required Pattern

For each RED test:

1. Import the planned public API at module level.
2. Name the behavior from the specification.
3. Arrange realistic input from the spec.
4. Call the planned function, class method, endpoint handler, parser, reducer, service, or component boundary.
5. Assert the exact observable result.
6. Ensure the test would fail if the implementation were missing or behaviorally wrong.
7. Do not hide missing implementation behind dynamic imports, `hasattr`, broad mocks, TODOs, or generic assertions.

A missing module, missing class, or missing function at collection time is acceptable RED if that public API is part of the specification.

## RED Test Worth Gate

Before writing the test, answer:

> What specification requirement does this test make executable?

> What future implementation bug should make this test fail?

Write the test only when both answers are clear.

Do not write the test when the answer is only:

- The module exists.
- The class initializes.
- The function can be imported.
- The object has some attributes.
- No exception is raised.
- The implementation will be filled in later.
- The test describes the feature but does not exercise it.
- The test checks framework behavior instead of product behavior.

## What Good RED Looks Like

A good RED test may fail because the import does not exist yet:

```py
from capital_allocation.contracts.lifecycle import build_cycle_schedule


def test_monthly_cycle_uses_start_day_and_generates_expected_periods():
    schedule = build_cycle_schedule(
        cycle_type="monthly",
        start_date="2026-01-15",
        periods=3,
    )

    assert schedule == [
        {"period_start": "2026-01-15", "period_end": "2026-02-14"},
        {"period_start": "2026-02-15", "period_end": "2026-03-14"},
        {"period_start": "2026-03-15", "period_end": "2026-04-14"},
    ]
```

This is valid RED because it names and calls the planned public API and asserts the specified output.

## What Bad RED Looks Like

```py
def test_monthly_cycle_schedule_exists():
    # TODO: implement once build_cycle_schedule exists
    assert True
```

This is not a RED test. It cannot fail for the missing behavior.

```py
def test_lifecycle_module_has_cycle_support():
    import capital_allocation.contracts.lifecycle as lifecycle

    assert hasattr(lifecycle, "CycleInput")
```

This tests surface shape, not behavior. The implementation can still be completely absent.

```py
def test_monthly_cycle_overview():
    spec = {
        "cycle_type": "monthly",
        "start_date": "2026-01-15",
        "periods": 3,
    }

    assert spec["cycle_type"] == "monthly"
```

This only tests the test data. It does not call the implementation.

## Hypothetical API Rule

When the spec describes behavior but the implementation does not exist, look for existing reasonable API or invent the smallest reasonable public API that the implementation should expose.

Prefer names that match the product language in the spec.

Then write the test against that API.

Example:

Spec:

> For a quarterly cycle, generate period boundaries aligned to the supplied start date.

Acceptable RED test:

```py
from capital_allocation.contracts.lifecycle import build_cycle_schedule


def test_quarterly_cycle_generates_aligned_period_boundaries():
    schedule = build_cycle_schedule(
        cycle_type="quarterly",
        start_date="2026-01-10",
        periods=2,
    )

    assert schedule == [
        {"period_start": "2026-01-10", "period_end": "2026-04-09"},
        {"period_start": "2026-04-10", "period_end": "2026-07-09"},
    ]
```

Do not replace this with a weaker test just because `build_cycle_schedule` does not exist yet. The missing symbol is the correct RED failure.

## Required Assertion Types

Use one or more concrete assertions:

- Exact return value.
- Specific error type and message/error code.
- State persisted in a fake/in-memory repository.
- Emitted event payload.
- Rendered user-visible text or role.
- Serialized JSON/dict output.
- No side effect after rejection.

Avoid vague assertions:

- `assert result is not None`
- `assert len(result) > 0`
- `assert isinstance(result, dict)` unless the schema is also asserted.
- `assert function`
- `assert object`
- `assert True`
- `with pytest.raises(Exception)`
- `mock.assert_called()`
- Snapshot without semantic checks.

## Error Path Pattern

Bad:

```py
def test_invalid_cycle_errors():
    with pytest.raises(Exception):
        build_cycle_schedule(cycle_type="weekly")
```

Good:

```py
from capital_allocation.contracts.lifecycle import build_cycle_schedule, CycleValidationError


def test_unsupported_cycle_type_returns_product_error_code():
    with pytest.raises(CycleValidationError) as exc:
        build_cycle_schedule(
            cycle_type="weekly",
            start_date="2026-01-15",
            periods=3,
        )

    assert exc.value.code == "unsupported_cycle_type"
    assert "weekly" in str(exc.value)
```

## Existing-Code Versus Missing-Code Rule

When implementation exists:

- Import the real public API.
- Call it directly.
- Assert behavior from the specification.

When implementation does not exist:

- Import the planned public API at module level.
- Call it as if implemented.
- Assert the required behavior.
- Allow collection/import failure as RED only if the missing API is the planned public boundary.

Do not use fallback code like this:

```py
try:
    from app.feature import planned_function
except ImportError:
    planned_function = None
```

This hides the RED failure.

## Mocking Rule

Do not mock the unit under test.

Only mock:

- External I/O.
- Time/randomness.
- Network/database/filesystem when not using a cheap fake.
- Expensive services.
- Failure modes that cannot be produced with real deterministic inputs.

A RED test that mocks the planned implementation and then asserts the mock was called is invalid.

## Spec-to-Test Checklist

For every requirement in the spec, extract:

- Public boundary to call.
- Input example.
- Expected output/error/side effect.
- Edge case or invalid case.
- Observable invariant.

Then write tests for the smallest meaningful set of behaviors.

Do not write one broad overview test for an entire feature. Split by behavior.

## Review Checklist

Before committing a RED test, verify:

- It imports the planned public API at module level.
- It calls the API under test.
- It asserts concrete behavior from the spec.
- It would fail with no implementation.
- It would fail with an incorrect implementation.
- It would pass after a correct implementation, regardless of private structure.
- It does not assert only existence, initialization, mocks, snapshots, or framework behavior.
- It does not test its own fixture data.

## Anti-Patterns to Reject

| Bad pattern                 | Why it is wrong              | Replacement                          |
| --------------------------- | ---------------------------- | ------------------------------------ |
| `assert True`               | No behavior coverage         | Call planned API and assert output   |
| `hasattr(module, "X")`      | Shape check only             | Exercise `X` through public behavior |
| `assert result is not None` | Allows broken outputs        | Assert exact result or schema        |
| Import inside test          | Hides collection-time RED    | Import public API at module level    |
| Mock planned function       | Tests the mock, not behavior | Call planned function                |
| One overview test           | Does not pin requirements    | One test per behavior                |
| Snapshot-only test          | Locks incidental output      | Assert semantic fields/text          |
| Framework validation test   | Tests dependency, not app    | Assert app error contract            |
| Test data assertion         | Tests the test setup         | Pass data into implementation        |

## Bottom Line

A RED test must be a failing executable version of the specification.

If the implementation is missing, the test should still call the planned public API and assert the behavior the implementation must eventually satisfy.

If the test can pass without the implementation, delete it.
