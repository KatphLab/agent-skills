---
name: review-closure-gate
description: Use when repeated code reviews keep finding new issues, review fixes churn across multiple sessions, superspec.review/code-reviewer is being rerun, or a team needs deterministic closure of prior findings before another fresh audit.
---

# Review Closure Gate

## Overview

Fresh reviewers are good at discovery; they are bad at proving closure unless you give them state. Use this skill to turn repeated `requesting-code-review` / code-reviewer / `superspec.review` runs into a deterministic closure gate.

**Core principle:** Close the known list first. New discovery starts only after every previous finding is closed, rejected, or explicitly carried forward with evidence.

**REQUIRED SUB-SKILL:** Use `requesting-code-review` for the actual reviewer dispatch. This skill wraps it with scope control and closure accounting; it does not replace it.

## When to Use

Use this when:

- The user says reviews keep finding new issues after each fix pass.
- Running `superspec.review`, `code-reviewer`, or `requesting-code-review` more than once on the same feature.
- A review produced Critical/Important findings and the next task is “fix all” or “run review again”.
- Specs, tasks, or test plans changed during review remediation.
- You need to prove convergence, not collect another open-ended finding list.

Do not use this for a first exploratory review with no prior findings. Use `requesting-code-review` directly.

## Closure-First Workflow

### 1. Pin the review scope

Record these before reading code:

```text
Feature/spec path:
Implementation paths:
Test paths:
Source/spec support paths:
Excluded paths:
Review baseline:
```

Never rely on “latest feature” defaults during remediation. If scope changed since the previous review, say so before comparing findings.

### 2. Load the canonical ledger

Use one ledger per feature, preferably:

```text
specs/<feature>/checklists/review-closure-ledger.md
```

If prior findings are scattered (`review.md`, `.pi/review/`, `.specify/.../checklist-review.md`, PR comments), consolidate them into the ledger before fixing or reviewing.

### 3. Close prior findings before new discovery

For every open finding, verify and update:

```text
ID:
Status: open | closed | rejected | carried-forward
Original issue:
Spec reference:
Code reference:
Test reference:
Closure evidence:
Verification command/result:
Reason if rejected/carried-forward:
```

A finding is not closed by “tests pass”. It closes only when the specific old failure is impossible and a targeted test or explicit rationale proves it.

### 4. Reject weak closure evidence

Weak evidence patterns:

| Weak evidence                 | Required replacement                    |
| ----------------------------- | --------------------------------------- |
| `action is not ADD_POSITION`  | exact action/state/reason asserted      |
| “QA passed” only              | targeted regression plus QA             |
| “field exists”                | validator/behavior using the field      |
| “config constant exists”      | non-stub differentiated values verified |
| “reviewer did not mention it” | explicit closure row                    |

### 5. Run new discovery only after closure

Now use `requesting-code-review` / code-reviewer with the pinned scope and ledger. The prompt must tell the reviewer:

```text
First validate closure rows. Do not search for new issues until all open prior findings are assessed. Classify any new finding as one of:
- missed-before
- introduced-by-fix
- new-spec-or-scope
- different-review-scope
- confidence-promoted
```

### 6. Report convergence

End with this summary:

```text
Prior open findings: N
Closed: N
Rejected: N
Carried forward: N
New findings: N
New-finding causes: missed-before / introduced-by-fix / new-spec-or-scope / different-review-scope / confidence-promoted
Converging? yes/no, with reason
Next action:
```

## Code-Reviewer Prompt Add-on

Append this to the normal code-reviewer request:

```text
Closure discipline:
- Review scope is pinned to <scope>.
- Load and assess <ledger path> first.
- For each open finding, decide closed/rejected/carried-forward with evidence.
- Do not start fresh discovery until prior findings are accounted for.
- For every new finding, classify cause: missed-before, introduced-by-fix, new-spec-or-scope, different-review-scope, or confidence-promoted.
- Reject broad negative tests as closure evidence; require exact contract assertions.
- Final output must include convergence counts.
```

## Common Mistakes

| Mistake                                         | Fix                                                       |
| ----------------------------------------------- | --------------------------------------------------------- |
| Rerunning review without scope                  | Pin feature/spec/code/test paths first                    |
| Treating optional review files as durable state | Consolidate into one ledger                               |
| Fixing new issues before old closure            | Close or carry forward old findings first                 |
| Letting spec edits silently change target       | create a new baseline and classify as `new-spec-or-scope` |
| Counting passing tests as closure               | require targeted old-failure evidence                     |
| Using different reviewer shards each run        | keep a fixed reviewer matrix for closure cycles           |

## Minimal Ledger Template

```markdown
# Review Closure Ledger: <feature>

## Baseline

- Feature/spec path:
- Implementation paths:
- Test paths:
- Source/spec support paths:
- Excluded paths:

## Findings

### <ID>. <title>

- Status: open
- First seen:
- Severity/confidence:
- Spec reference:
- Code reference:
- Required behavior:
- Closure evidence:
- Verification:
- Notes:
```
