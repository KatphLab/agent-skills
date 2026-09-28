---
name: optimizing-data-contracts
description: Use when an existing Python data contract is overvalidated, slow, memory-heavy, awkward at call sites, or represented by Pydantic, dataclass, TypedDict, NamedTuple, Enum, Literal, or primitive containers without a clear boundary need.
---

# Optimizing Data Contracts

## Overview

Use the least runtime machinery that satisfies every required contract behavior. Optimize semantics first and measured cost second: never remove required validation, schema, serialization, immutability, or runtime identity to win a constructor benchmark.

**REQUIRED BACKGROUND:** Use `writing-data-contracts` for field types, optionality, validation, and contract invariants.

**REQUIRED REFERENCE:** Read [representation-guide.md](representation-guide.md) before recommending a representation change.

## Audit Before Changing

For each type, inspect its constructors and consumers, then record:

1. **Trust:** Can raw, external, persisted, or version-skewed data reach construction?
2. **Runtime work:** Must construction parse, coerce, reject, normalize, or enforce invariants?
3. **Integration:** Is JSON Schema, model serialization, framework discovery, or public export required?
4. **Runtime shape:** Do callers require attributes, a real `dict`, or a real `tuple`?
5. **Semantics:** Is it a value object, mutable state, structural mapping, positional tuple, reusable domain value, discriminator, or bitmask?
6. **Cost:** Is construction or memory measured as material? How often is it built, validated, copied, and serialized?
7. **Compatibility:** Do callers depend on equality, hashing, unpacking, `isinstance`, pattern matching, pickling, enum primitive comparison, or omitted keys?

No measured problem and no semantic mismatch means no migration. A cheaper type is not automatically a better contract.

## Decision Order

1. Keep **Pydantic `BaseModel`** when runtime validation/parsing, business invariants, JSON Schema, model serialization, or framework model APIs are required. Validate once at the boundary.
2. Otherwise use a **stdlib dataclass** for an attribute-based record. Default to `frozen=True, slots=True` for immutable internal results; use mutability only when state transitions are intentional. Add `kw_only=True` when positional construction is not part of the API.
3. Use **`TypedDict`** only when runtime values must remain ordinary dictionaries and static key checking is sufficient.
4. Use **`NamedTuple`** only when tuple behavior itself—unpacking, indexing, or tuple interoperability—is required.
5. Choose **`Literal`** for small local value sets and discriminators; choose an **enum** for reusable runtime domain identity. Do not wrap a one-use `Literal` in an enum for uniform style. Choose `Flag` only for an actual bitmask, not merely because values can form a set.
6. Use **`NewType`** for trusted internal scalar identity checked statically; use a type alias only for readability.

## Quick Reference

| Required behavior                                      | Best default                               |
| ------------------------------------------------------ | ------------------------------------------ |
| Untrusted input, runtime rejection, schema, model dump | Pydantic `BaseModel`                       |
| Trusted internal attribute record                      | `@dataclass(frozen=True, slots=True)`      |
| Deliberately mutable internal state                    | Mutable slotted dataclass                  |
| Plain-dict interoperability, static shape only         | `TypedDict`                                |
| Positional tuple contract                              | `NamedTuple`                               |
| One-use closed values or union tag                     | `Literal[...]`                             |
| Reusable textual domain/wire vocabulary                | `StrEnum`                                  |
| Reusable nominal domain, primitive equality unwanted   | `Enum`                                     |
| Numeric wire value without arithmetic semantics        | `Enum` with integer values                 |
| Required integer substitutability                      | `IntEnum`—rare                             |
| Intrinsic bitmask operations                           | `Flag`; `IntFlag` only for integer interop |
| Conceptual permission set, not a bitmask               | `frozenset[Permission]`                    |
| Static scalar distinction, no runtime checks           | `NewType`                                  |

## Example: Validate Once, Compute Cheaply

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["quote"]
    side: Side
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotePoint:
    price: Decimal
    quantity: Decimal


def calculate(request: QuoteRequest, price: Decimal) -> QuotePoint:
    # The boundary already established valid types; the hot-path result does no parsing.
    return QuotePoint(price=price, quantity=request.quantity)
```

Do not convert every nested boundary model into a dataclass after validation. Convert only records repeatedly constructed or retained in trusted code when profiling or semantics justify the extra mapping step.

## Migration and Verification

Migrate all callers in one cutover; do not leave adapters or dual representations. Verify the behavior the old type supplied: invalid input rejection, schema, JSON shape, required/omittable keys, equality, hashing, mutation, pattern matching, tuple/dict interoperability, and pickling where relevant.

When performance motivated the change, benchmark the real path before and after with equivalent work. Comparing validated Pydantic construction to an unvalidated dataclass is invalid unless validation is provably unnecessary on that path.

## Common Mistakes

| Mistake                                | Correction                                                                                                       |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| “Internal” means trusted               | Trace every construction path; persisted and message data remain boundary data.                                  |
| `TypedDict` validates dictionaries     | It is static typing; use Pydantic when runtime rejection is required.                                            |
| `NamedTuple` is a faster dataclass     | Choose it only for required tuple semantics; benchmark costs separately.                                         |
| Every closed set deserves an enum      | Use `Literal` for local tags; enum identity must earn its runtime API.                                           |
| “The architect wants enums everywhere” | Uniform selection criteria beat uniform representation; do not invent enum identity for a one-use `Literal`.     |
| Every combinable set deserves `Flag`   | Use `Flag` only when bitmask algebra or protocol encoding is intrinsic.                                          |
| `slots=True` proves optimization       | It removes the instance dictionary; measure the application-level effect.                                        |
| `model_construct()` is fast Pydantic   | It skips validation and can create invalid models; use only with proven trusted data and a benchmark.            |
| Pydantic dataclass is a compromise     | It still performs validation but lacks the full `BaseModel` API; use it only for required dataclass integration. |

## Red Flags

Stop if the proposal removes boundary validation, treats annotations as runtime checks, changes `dict`/tuple/enum equality accidentally, wraps a one-use `Literal` in an enum for uniformity, introduces `IntEnum` or `IntFlag` for convenience, uses `__post_init__` to rebuild validation, duplicates boundary and internal models without measured need, or claims a speed/memory win without exercising the real path.
