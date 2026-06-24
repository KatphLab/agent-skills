---
name: prism-review
description: Execute a specification review workflow. Use this skill whenever the user provides specification documents and code to review implementation against specs.
---

# Spec Review

This is not a general code review: report only spec-vs-code mismatches, missing spec requirements, edge cases, validation rules, side effects, formulas, thresholds, states, workflows, and output/schema gaps. Every finding must be traceable to spec evidence and code evidence.

## Input

Expected input: specification document paths and code/module paths to review. If either is missing or ambiguous, ask before proceeding.

## Requirements

Required tools: `git` and `logic-reviewer`/`reviewer` subagents. If any required command/tool fails, halt with the failed command/tool and a short explanation.

## Review artifacts

Create all artifacts under the resolved repo root:

```text
.pi/review/
  logic-findings-high/*.md
  logic-findings-medium/*.md
  logic-findings-high-coverage.md
  logic-findings-medium-coverage.md
  review/*.md
  final-summary.md
```

Use stable filenames; for findings prefer `NN-short-kebab-title.md`.

## Workflow

### 0. Prepare workspace

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

if ! git check-ignore -q .pi/review/; then
  GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
  grep -qx '.pi/review/' "$GIT_COMMON_DIR/info/exclude" 2>/dev/null || echo '.pi/review/' >> "$GIT_COMMON_DIR/info/exclude"
fi
mkdir -p .pi/review
```

### 1. Define single-module scope

Determine one coherent module from the provided spec and code paths. If the scope spans unrelated modules and is unclear, ask the user to choose before reviewing.

Prepare a context packet for subagents with:

- Spec document paths and the module scope/assumptions.
- Code file paths under review; verify each exists locally.
- Instruction to report only spec-vs-code findings, including spec requirements missing from code.
- Instruction to validate every cited code line against the current checkout immediately before writing.

### 2. Run independent logic reviews

Create/clear outputs, then launch both logic reviewers in one parallel subagent call:

```bash
mkdir -p .pi/review/logic-findings-high .pi/review/logic-findings-medium
rm -f .pi/review/logic-findings-high/*.md .pi/review/logic-findings-medium/*.md
rm -f .pi/review/logic-findings-high-coverage.md .pi/review/logic-findings-medium-coverage.md
```

Run:

1. `logic-reviewer`, high complexity, output only to `.pi/review/logic-findings-high/` and `.pi/review/logic-findings-high-coverage.md`.
2. `logic-reviewer`, medium complexity, output only to `.pi/review/logic-findings-medium/` and `.pi/review/logic-findings-medium-coverage.md`.

Do not run them sequentially. Each prompt may include only the shared context packet, spec paths, relevant code paths, and that reviewer's own output paths. The other reviewer's directory and coverage file are forbidden input. If a reviewer accidentally sees the other's artifacts, it must ignore them and say so in its completion note.

Require one file per finding and no aggregate summaries in findings folders.

Coverage checklist statuses:

- `COVERED — finding file: <filename>`
- `NOT_IMPLEMENTED — finding file: <filename>`
- `VERIFIED — no discrepancy found`
- `SKIPPED — not in module scope`
- `UNCERTAIN — could not determine`

### 3. Validate logic outputs and run reviewer pass

Before proceeding, validate each logic-reviewer output:

1. Findings exist, or coverage explicitly records zero findings.
2. Each finding has all required sections from the finding template.
3. No placeholder/empty spec or code details remain.
4. Code line references include validation evidence and match current checkout behavior.
5. Files are from the current run, not stale.

If validation fails, halt and report malformed files. Do not feed malformed findings to the reviewer.

Create/clear reviewer output:

```bash
mkdir -p .pi/review/review
rm -f .pi/review/review/*.md
```

Spawn one medium-complexity `reviewer` subagent. Inputs: validated logic finding files, both coverage checklists, spec text files, and relevant code files. Ask it to deduplicate, reject unsupported claims, re-check line numbers, tighten category/severity/comments, preserve one markdown file per accepted finding, and keep missing-implementation findings when supported. It should also note `NOT_IMPLEMENTED`, `UNCERTAIN`, suspicious `VERIFIED`, or improperly `SKIPPED` coverage items.

### 4. Main-agent verification and final summary

Personally verify `.pi/review/review/*.md`; do not blindly trust subagents. For each accepted finding:

1. Confirm the spec reference exists and supports the claim.
2. Re-open cited code with line numbers and fix bad ranges before final reporting.
3. For missing implementations, use targeted searches and cite closest relevant files/functions or search evidence; do not invent line numbers.
4. Confirm module relevance, merge duplicates, and remove unsupported/vague/non-actionable items.

Read both coverage checklists. Verify `NOT_IMPLEMENTED`; investigate `UNCERTAIN`; confirm `SKIPPED` is out of scope; spot-check some requirements both reviewers marked `VERIFIED`.

Write `.pi/review/final-summary.md` using the final summary template below. It is the only consolidated review output.

## Finding template

Use this exact structure for logic-reviewer and reviewer finding files:

```markdown
# <Finding title>

## Category

<Logic mismatch | Missing requirement | Edge case | Validation | Data mapping | State/workflow | Formula/threshold | Output/schema | Security/spec compliance | Other>

## Severity

<Critical | High | Medium | Low>

## Spec details

- Document: <spec txt/pdf name>
- Section/page/heading: <specific location>
- Requirement: <quoted or tightly paraphrased requirement>
- Expected behavior: <what the spec says should happen>

## Code details

- File: <path>
- Lines: <validated line range, or "No implementation found" for missing requirements>
- Current behavior: <current behavior or absence>
- Line validation: <command used to verify, e.g. `nl -ba <file> | sed -n 'X,Yp'`>

## Discrepancy

<Exact spec/code mismatch, including unimplemented spec requirements.>

## Possible fix

<Concrete implementation or validation change.>

## Impact

<User/business/system impact.>

## Suggested review comment

<Concise actionable comment.>
```

## Final summary template

````markdown
# Spec Review Summary

## Review target

- Module: <module>
- Spec documents: <filenames>
- Code paths: <files reviewed>

## Executive summary

<Whether implementation matches the spec and the most important gaps, including missing requirements.>

## Spec coverage

- Total spec requirements considered: <N>
- Requirements with findings: <N>
- Requirements not implemented: <N>
- Requirements verified with no discrepancy: <N>
- Requirements out of scope: <N>
- Requirements uncertain/unresolved: <N>

## Findings

<Group findings by Critical, High, Medium, Low. Omit empty severity groups.>

### <Severity>

#### <N>. <Finding title>

- Category: <category>
- Spec details: <document + section/page/heading + requirement + expected behavior>
- Code details: `<file>:<validated line-range>` — <current behavior, or "No implementation found" with search evidence>
- Discrepancy: <exact mismatch or missing implementation>
- Possible fix: <concrete implementation direction>

```suggestion-comment
<Specific, actionable comment that mentions expected spec behavior.>
```

## Findings considered but excluded

<Optional. Rejected/merged findings if useful.>

## Unresolved spec requirements

<Any UNCERTAIN requirements that could not be resolved.>

## Review notes

<Constraints, missing documents, ambiguous spec language, stale-commit warnings, or assumptions.>
````

## Quality bar

Accept a finding only when it has:

- Clear spec/implementation mismatch, including spec requirements absent from code.
- Specific spec evidence: document plus section/page/heading or quoted requirement.
- Specific code evidence: file plus validated line range, or explicit `No implementation found` with search evidence.
- Line numbers verified against current checkout immediately before final reporting.
- Category, severity, spec details, code details, discrepancy, possible fix, impact, and a concise actionable comment.
- Relevance to the selected module.

Reject style-only comments unless required by the spec, repo-wide cleanup, assumptions/unstated requirements, findings without code evidence, and duplicate comments unless each instance needs a separate comment.

## Halt conditions

Halt and ask/report when:

- Spec or code paths are missing.
- The scope spans unrelated modules and target scope is unclear.
- `git` commands fail (cannot resolve repo, working tree is dirty).
- Subagent output is malformed, stale, unsupported, or missing required sections.
- The working tree or spec/code paths change during review.

When halting, state what was tried and the exact next information/action needed from the user.
