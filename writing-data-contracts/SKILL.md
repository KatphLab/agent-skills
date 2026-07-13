---
name: writing-data-contracts
description: Use when adding or revising Python request, response, event, configuration, persistence, or calculation-result contracts, especially under contracts modules or when field types, optionality, monetary precision, nested payloads, or Pydantic validation are undecided.
---

# Writing Data Contracts

## Overview

A data contract makes every accepted state explicit and every impossible state unrepresentable. Model domain meaning—not the legacy container shape.

Use `Engines/capital_allocation/contracts/` for naming, `StrEnum`, `Decimal`, immutability, docstring, and export conventions. Do not copy `base.py`, inherit its classes, or reproduce its freezing and generic-input machinery.

## Contract Recipe

1. Read the specification, callers, and neighboring contracts. Reuse existing enums and models; never create a second vocabulary.
2. Classify the boundary, then choose the model form.
3. Give every semantic record a named model. Do not hide an unknown record behind a type alias.
4. Choose the narrowest domain type for every field.
5. Encode scalar constraints declaratively with Pydantic.
6. Add a validator only for a specified cross-field or business invariant that Pydantic cannot express.
7. Add module/public docstrings, `__all__`, package exports, and focused contract tests.

Compatibility pressure does not weaken a new contract. Migrate callers cleanly; do not preserve weak types through adapters, aliases, shared bases, or deprecated paths.

## Choose the Model Form

| Contract role | Form |
|---|---|
| API, ingestion, serialization, persistence, event, or untrusted input | Direct Pydantic `BaseModel` with `ConfigDict(frozen=True, extra="forbid", strict=True)` |
| Trusted internal calculation result with no parsing or runtime validation | `@dataclass(frozen=True, slots=True)` |
| Internal record requiring parsing, schema generation, or validation | Pydantic model; do not recreate Pydantic in `__post_init__` |

Standard dataclasses must not define validation in `__post_init__`. If construction can reject data or one field constrains another, use Pydantic.

Never introduce a shared contract base merely to centralize three config flags.

## Type Rules

| Meaning | Type |
|---|---|
| Money, ratios, governed exact numerics | `Decimal`, with `Field` precision/range/finiteness constraints |
| Closed text domain, status, mode, reason, source | Existing or new `StrEnum` |
| Identifier | Existing domain ID type or `UUID`; constrained `str` only for genuinely open identifiers |
| Date/time | `date` or Pydantic `AwareDatetime` as required |
| Semantic record | Named nested Pydantic model or dataclass |
| Ordered collection | `tuple[T, ...]`, optionally constrained with `Field` |
| Dynamic keyed domain | Named `Mapping[KeyEnum, ValueType]` alias or wrapper only when map semantics are intrinsic |

Never use `Any`, `object`, bare `dict`, bare `list`, opaque `dict[str, ...]`, or list fields. A typed alias does not make an opaque dictionary a contract. Prefer named nested records; use a typed `Mapping` only for a genuinely dynamic homogeneous map.

Do not invent enum members, fields, defaults, or invariants. Derive them from the specification, existing contracts, and callers. If a required closed vocabulary is unavailable, identify that missing domain decision; do not silently fall back to `str` or an opaque payload.

Never add placeholder imports, imaginary types, or unresolved aliases to make a draft appear complete. If missing domain definitions prevent a real contract, report the exact blocker and provide no “shippable” or “compilable” placeholder.

## Optionality

`T | None` means absence or null is a real domain state—not that a caller may be lazy.

- Required and nullable: `value: T | None`.
- Omittable and nullable: `value: T | None = None`.
- Required with a default: `enabled: bool = False`; this is not optional.
- Empty collection as a valid state: `items: tuple[T, ...] = ()`; this is not optional.
- Conditional absence: use `T | None` only when another domain state truly permits absence, then enforce that relationship with one model validator.

Do not mark fields optional for partial construction, future data, test convenience, or because one caller lacks the value.

## Validation Boundary

Use Pydantic first:

- Concrete types: `UUID`, `StrEnum`, `Decimal`, `date`, `AwareDatetime`, `StrictBool`.
- `Annotated`, `Field`, and `StringConstraints`: bounds, positivity, length, pattern, decimal precision, and `allow_inf_nan=False`.
- Model configuration: strict input, frozen instances, forbidden extras.

Do not hand-write validators for type checks, UUID/date parsing, enum membership, number bounds, finiteness, lengths, patterns, or collection length. Custom validators are reserved for specified relationships such as mutually dependent fields, exact reconciliation, exhaustive keyed-domain coverage, or state-transition rules. They must be small, typed, documented, and raise a precise `ValueError`.

## Example

```python
"""External capital-allocation order contracts."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from Engines.capital_allocation.contracts.enums import AllocationId

__all__ = [
    "AllocationLeg",
    "CancellationReason",
    "CapitalAllocationOrder",
    "ExecutionProvider",
    "OrderStatus",
    "ProviderReceipt",
]

PositiveMoney = Annotated[
    Decimal,
    Field(gt=Decimal("0"), allow_inf_nan=False, max_digits=24, decimal_places=6),
]


class OrderStatus(StrEnum):
    """Supported capital-allocation order states."""

    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


class CancellationReason(StrEnum):
    """Governed cancellation reason codes."""

    CLIENT_REQUEST = "CLIENT_REQUEST"
    RISK_REJECTION = "RISK_REJECTION"


class ExecutionProvider(StrEnum):
    """Configured execution providers."""

    PRIMARY_BROKER = "PRIMARY_BROKER"
    BACKUP_BROKER = "BACKUP_BROKER"


class AllocationLeg(BaseModel):
    """One exact allocation within an order."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    allocation_id: AllocationId
    notional: PositiveMoney


class ProviderReceipt(BaseModel):
    """Structured provider acknowledgement."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    provider: ExecutionProvider
    provider_order_id: UUID
    received_at: AwareDatetime


class CapitalAllocationOrder(BaseModel):
    """Complete immutable order accepted at the external boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    order_id: UUID
    status: OrderStatus
    legs: Annotated[tuple[AllocationLeg, ...], Field(min_length=1)]
    cancellation_reason: CancellationReason | None = None
    receipt: ProviderReceipt

    @model_validator(mode="after")
    def validate_cancellation(self) -> Self:
        """Require a reason exactly when the order is cancelled."""
        cancelled = self.status is OrderStatus.CANCELLED
        if cancelled != (self.cancellation_reason is not None):
            raise ValueError("cancellation reason must match cancelled status")
        return self
```

The validator exists only because cancellation is a cross-field domain invariant. Pydantic handles every scalar constraint.

## Verification

Test observable contract behavior:

- A realistic valid model constructs and serializes with the intended shape.
- Extra fields, wrong enum domains, float money, and invalid declarative constraints fail.
- Required fields cannot be omitted; nullable and omittable behavior matches the specification.
- Every custom business invariant fails on both sides of its boundary.
- Internal dataclasses are frozen/slotted and contain no mutable field types.

Run only the focused contract tests and repository formatter/linter commands allowed by local instructions.

## Common Mistakes

| Mistake or excuse | Required correction |
|---|---|
| “The wire shape already passes.” | Passing an opaque shape does not define a safe contract; migrate it. |
| “A type alias makes the dictionary typed.” | Replace semantic dictionaries with named models. |
| “Use the shared base for consistency.” | Subclass `BaseModel` directly; consistency comes from explicit local config. |
| “Float avoids breaking callers.” | Use `Decimal`; update producers and consumers together. |
| “Custom checks are safer.” | Use maintained Pydantic types and constraints; custom code only for business relationships. |
| “The field is not always present.” | Prove absence is a domain state before adding `None`. |
| “The enum values are probably these.” | Find the governed vocabulary; never guess a contract domain. |
| “It is only one `__post_init__` invariant.” | Construction-time rejection is runtime validation; choose Pydantic. |
| “A placeholder import makes the missing domain visible.” | A nonexistent type is not a contract; report the blocker without claiming completion. |

## Red Flags

Stop and redesign if a contract contains `Any`, `object`, `float` for exact values, free-form strings for closed domains, mutable or opaque collection fields, broad optionality, a custom scalar validator, validation in dataclass `__post_init__`, inheritance from `base.py`, placeholder domain types, or compatibility shims preserving those choices.
