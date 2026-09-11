---
name: pruning-unit-tests
description: Use when reviewing, pruning, or approving unit tests for production suites; when tests look brittle, implementation-focused, mock-heavy, coverage-driven, obsolete after TDD, or disconnected from product behavior.
hide: true
---

# Pruning Unit Tests

## Overview

A production test suite is executable specification, not a development diary. Keep tests that constrain real behavior. Delete or rewrite tests that constrain how the current code happens to be written.

Bad tests are not harmless: they block refactors, reward mock choreography, and create false confidence while missing real regressions.

## The Production Test Gate

For every questionable test, answer this in one sentence:

> If this test fails in CI, which user-visible behavior, public API contract, business rule, error path, or invariant might be broken?

Decision:

- Clear behavior or contract answer: keep it, or strengthen it if the assertion is weak.
- Answer names a private method, helper, mock call, call order, component structure, file layout, coverage target, or discarded implementation: rewrite or delete it.
- No clear answer: it does not belong in production testing.
- The expected behavior changed intentionally: update the test to the new contract or delete the obsolete one.
- The failure might expose a real bug: stop pruning and debug before deleting.

## Triage Table

| Classification | Action | Examples |
| --- | --- | --- |
| Preserve | Keep as-is or make the name/assertion clearer | Public API contract, business rule, error handling, invariant, regression for a real bug |
| Rewrite | Keep the behavioral intent, replace implementation assertions | Mock call counts, private helper calls, broad snapshots, internal state checks |
| Delete | Remove from production suite | Coverage filler, duplicate with no new branch, framework/library behavior, obsolete TDD scaffold, test of a mock/test helper |
| Investigate | Do not edit yet | Ambiguous product contract, failing test that may indicate a bug, unclear ownership |

## Delete Criteria

Delete when at least one is true and no unique behavior remains:

- The test only proves that code is shaped a certain way: helper called, dependency invoked, branch name used, class instantiated.
- The test asserts mock behavior instead of system behavior.
- The test verifies a framework, language feature, or library guarantee instead of your logic.
- The test was created during TDD for an abandoned design and no longer maps to accepted behavior.
- The test exists only to raise coverage numbers.
- Another test already covers the same branch, edge case, and invariant with clearer behavioral assertions.
- The test would fail during a safe refactor while no user/API behavior changed.

Coverage policy is not a reason to keep garbage. If deleting a bad test drops required coverage for real logic, replace it with a real behavior test.

## Rewrite Patterns

| Bad test checks | Better test checks |
| --- | --- |
| `toHaveBeenCalledWith(...)` on an internal collaborator | Returned value, persisted state, emitted event, rendered role/text, or external side effect |
| Private helper output | Public API behavior over inputs that exercise that helper |
| Large snapshot | Specific semantic contract: accessible text, state transition, serialized output, validation error |
| Exact algorithm steps | Required observable result, ordering only if ordering is part of the contract |
| Mock component/test double exists | Parent behavior visible to the user or caller |
| Old TDD scaffold | Current accepted behavior, or nothing if the behavior was abandoned |

## Example

<Bad>

```ts
test('calls normalize before save', async () => {
  const normalize = vi.spyOn(service as any, 'normalize');

  await service.createUser({ email: ' Alice@Example.COM ' });

  expect(normalize).toHaveBeenCalledWith(' Alice@Example.COM ');
  expect(repo.save).toHaveBeenCalled();
});
```

This pins private structure and collaborator choreography. A safe refactor can break it without changing behavior.
</Bad>

<Good>

```ts
test('stores email in canonical form', async () => {
  await service.createUser({ email: ' Alice@Example.COM ' });

  await expect(repo.findByEmail('alice@example.com')).resolves.toMatchObject({
    email: 'alice@example.com',
  });
});
```

This protects the contract: users can be found by canonical email. The implementation can change freely.
</Good>

## Pruning Workflow

1. Identify the behavior each test claims to protect. If you cannot state it, mark it delete/investigate.
2. Check the current accepted contract from code, API usage, requirements, or nearby behavioral tests.
3. Classify each test: preserve, rewrite, delete, investigate.
4. Delete only tests with no unique behavior. Rewrite brittle tests that protect real behavior.
5. Avoid changing production code during pruning unless investigation finds a real bug; then switch to bug-fix workflow.
6. Run the targeted test command for every changed suite. If tests were rewritten, verify they fail when the protected behavior is broken if practical.

## Red Flags

- Test name says only `works`, `renders`, `calls handler`, `initializes`, `coverage`, or `snapshot`.
- Mock setup is larger than the behavior being asserted.
- The strongest assertion is a mock call count or call order.
- Assertions mention private fields, private methods, internal component names, generated IDs, or exact file structure.
- The test fails when a mock is removed, but not when real behavior is broken.
- The test documents what TDD tried before the design changed.
- The test is kept because “it already exists” or “coverage needs it.”

## Reporting Format

When pruning or reviewing tests, report concrete decisions:

```markdown
## Unit test pruning
- Deleted: `path/to/test.ts` / `test name` — no production behavior; only asserted mock call order.
- Rewritten: `path/to/test.ts` / `test name` — now asserts persisted canonical email instead of private helper call.
- Preserved: `path/to/test.ts` / `test name` — protects validation error contract for empty email.
- Investigate: `path/to/test.ts` / `test name` — ambiguous contract; failure may indicate a product bug.

Verification: `<targeted command>` — observed result.
```

## Common Mistakes

- Deleting an annoying failing test without checking whether it found a real regression.
- Keeping a brittle test because it once helped during TDD.
- Replacing implementation assertions with snapshots instead of behavior assertions.
- Treating “unit” as “mock everything.” Use real collaborators when they make the behavior clearer and are cheap/deterministic.
- Preserving duplicate tests because deleting them feels risky. Risk comes from losing behavior coverage, not from lowering test count.

## Bottom Line

A production unit test earns its place by catching a real behavior regression. If it cannot name the behavior, rewrite it or remove it.
