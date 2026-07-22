# Python Data Representation Guide

Choose by required behavior. Performance breaks ties only after profiling with equivalent work.

## Record Representations

### Pydantic `BaseModel`

**Use when:** data crosses a trust boundary; construction must parse or reject; scalar or cross-field invariants apply; JSON Schema, model serialization, discriminated unions, or framework model discovery is required.

**Strengths:** runtime validation, declarative constraints, precise errors, schema generation, nested parsing, controlled serialization.

**Costs:** validation and model construction work, dependency/runtime machinery, copying or coercion where configured. `frozen=True` prevents reassignment but does not recursively freeze mutable children.

**Rules:** validate once at ingress. Prefer strict concrete types, forbidden extras, immutable fields, discriminated unions, and `model_validate_json()` for JSON. Instantiate a `TypeAdapter` once, not per call. Do not replace required validation with `model_construct()`; on simple models it may not be faster, so profile it.

### Standard-library dataclass

**Use when:** a trusted internal record needs named attributes but no parsing, runtime validation, schema, or Pydantic APIs.

**Strengths:** direct Python construction, clear value-object semantics, generated equality/repr, methods, inheritance, keyword-only fields, and optional slots.

**Costs:** annotations are not enforced. `frozen=True` is shallow immutability; mutable children remain mutable. `slots=True` affects inheritance and omits weak-reference support unless requested.

**Configuration:**
- Immutable result/value object: `@dataclass(frozen=True, slots=True)`.
- Add `kw_only=True` when field order must not become a caller contract.
- Mutable dataclass only for deliberate mutable state; do not pretend state is a value object.
- Avoid `unsafe_hash=True`; make fields genuinely immutable instead.
- Never validate in `__post_init__`. If construction can reject input, use Pydantic.

### Pydantic dataclass

**Use when:** an existing integration specifically requires dataclass identity/APIs while construction still needs Pydantic validation.

**Strengths:** dataclass-compatible shape plus Pydantic validation; can be wrapped in `TypeAdapter` for dump/schema operations.

**Costs:** it does not remove validation latency and lacks the direct `BaseModel` method surface. It creates a hybrid convention that callers must understand.

**Default:** prefer direct `BaseModel` for boundary contracts and stdlib dataclass for trusted records. Do not choose the hybrid merely as a compromise.

### `TypedDict`

**Use when:** trusted values must be actual dictionaries because callers use key access, `**kwargs`, JSON-shaped mappings, or a library requires `dict`; static key/value checking is enough.

**Strengths:** zero wrapper object; runtime values are normal dicts; expresses required and `NotRequired` keys; works with `Unpack` for keyword arguments.

**Costs:** no runtime validation, parsing, immutability, nominal identity, methods, or `isinstance` checks. Dict allocation may use more memory than a slotted record. `ReadOnly` is a static restriction, not runtime freezing.

**Rules:** omission and `None` are distinct; use `NotRequired[T]` only for real omission. Do not use `total=False` as a shortcut for partial data. At a measured high-throughput boundary that must return dicts, `TypeAdapter[TypedDict]` can validate and generate schema, but use it only when model identity/APIs are unnecessary and focused tests cover the adapter. A public semantic record remains a `BaseModel` by default.

### `NamedTuple`

**Use when:** tuple identity and positional behavior are requirements—unpacking, indexing, compatibility with tuple APIs, or a stable positional protocol.

**Strengths:** immutable tuple representation with field names; compact; natural destructuring.

**Costs:** exposes indexing, length, concatenation, positional construction, and tuple-compatible equality whether wanted or not. Field order becomes API, and evolution is brittle.

**Default:** if callers only use attributes, choose a frozen slotted dataclass. Never select `NamedTuple` from a presumed speed advantage without a benchmark.

### Plain `dict`, `tuple`, and aliases

Use plain containers for short-lived local plumbing with no independent semantics. A type alias improves readability but creates neither runtime identity nor stronger static distinction. Reusable semantic records need a named representation. Do not hide an unknown heterogeneous payload behind `dict[str, object]` or `Any`.

## Closed Domains and Scalars

### `Literal`

**Use when:** a small closed set is local to one or a few signatures, or a field is a discriminated-union tag such as `Literal["created"]`.

**Strengths:** no wrapper value; precise type narrowing; Pydantic turns it into runtime validation and schema when used inside a model.

**Costs:** outside a runtime validator it is static only; no namespace, iteration, metadata, methods, or nominal identity. Large/repeated Literals drift.

Promote to an enum when the vocabulary becomes reusable domain language.

### `Enum` and `StrEnum`

Use an enum for a governed, reusable domain vocabulary that benefits from member names, iteration, runtime membership, identity, methods, or metadata.

- `StrEnum`: choose when wire values are strings and string interoperability is intentional. Members compare as strings, so it provides weaker runtime separation.
- `Enum` with string values: choose when raw-string equality must not succeed and serialization can explicitly use `.value` or framework encoding.
- `Enum` with integer values: choose for numeric wire codes when arithmetic and equality with integers are forbidden.

Do not invent an enum for a one-use discriminator. Preserve governed values exactly; never use `auto()` for externally stable wire values.

A style preference for “enums everywhere” does not establish reusable domain identity. Do not create `Literal[SomeEnum.MEMBER]` or a companion enum solely to satisfy uniformity; use the raw literal unless an independently reused vocabulary earns the enum.

### `IntEnum`, `Flag`, and `IntFlag`

- `IntEnum`: only when the domain intentionally requires integer substitutability or a legacy numeric API. Arithmetic can return plain integers and erode type identity.
- `Flag`: only when bitwise combination is intrinsic and unknown-bit behavior is specified. Confirm that accepted combinations and generated schema agree.
- `IntFlag`: only when both bitmask behavior and integer interoperability are required by a protocol. It leaks integer behavior most strongly.
- `frozenset[Permission]`: prefer when the domain is simply a set of named permissions and the wire form is names/arrays rather than an integer bitmask.

“Values can be combined” is insufficient evidence for `Flag`.

### `NewType`, type aliases, and `Annotated`

- `NewType`: use for trusted internal scalars such as distinct IDs when static nominal separation is valuable and runtime validation is not. At runtime it returns the underlying value; it cannot enforce format/range and operations may erase the distinction.
- Type alias: use only to shorten or name a structural type. It is equivalent to the underlying type.
- `Annotated`: attach reusable constraint/metadata to a base type. It becomes runtime enforcement only when a consumer such as Pydantic interprets the metadata.

At untrusted boundaries, use concrete domain types and Pydantic constraints rather than treating these annotations as validators.

## Optimization Rules

1. Remove duplicate validation, not required validation. Boundary data is validated even if another service allegedly validated it.
2. Separate boundary and internal forms only when lifecycle or profiling justifies conversion; duplicate models increase mapping and drift risk.
3. Benchmark end-to-end work: parse, validate, construct, retain, access, and serialize. Compare equivalent guarantees.
4. Prefer concrete collection annotations when the concrete shape is known; abstract `Sequence`/`Mapping` can add validation work.
5. Avoid repeated adapters, wrap validators, and revalidation inside trusted loops before changing the representation.
6. Audit every behavioral dependency before cutover: constructors, methods, exports, schema, serialization, equality, hashing, mutation, unpacking, pattern matching, reflection, and persisted pickle paths.
