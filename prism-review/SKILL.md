---
name: prism-review
description: Execute a GitHub issue-driven specification review workflow. Use this skill whenever the user gives a GitHub issue number and asks to review implementation against specs, Zoho workflow/spec links, related PRs, or branch code. This skill should be used for multi-step PR reviews that require gh CLI issue/PR lookup, worktree selection, downloading spec PDFs, pdftotext conversion, logic-reviewer subagents, reviewer subagents, and a final GitHub-ready review summary.
---

# GitHub Issue Spec Review

Turn a GitHub issue number into a single-module PR/branch review against linked specification documents. This is not a general code review: report only spec-vs-code mismatches, missing spec requirements, edge cases, validation rules, side effects, formulas, thresholds, states, workflows, and output/schema gaps. Every finding must be traceable to spec evidence and code evidence.

## Input

Expected input: GitHub issue number, optionally with repo/worktree hints. If the issue number is missing or ambiguous, ask before proceeding.

## Requirements

Required tools: authenticated `gh`, `git`, `python3`, `pdftotext`, and `logic-reviewer`/`reviewer` subagents. If any required command/tool fails, halt with the failed command/tool and a short explanation.

The repo may use worktrees. Do not assume the current directory is the target checkout. Do not switch branches, create worktrees, or review the wrong branch/commit.

## Review artifacts

Create all artifacts under the resolved repo/worktree root:

```text
.pi/review/
  review-context.json
  issue.json
  pr.json
  pr-comments.txt
  changed-files.txt
  spec/
    spec-manifest.json
    *.pdf
    *.txt
  logic-findings-high/*.md
  logic-findings-medium/*.md
  logic-findings-high-coverage.md
  logic-findings-medium-coverage.md
  review/*.md
  final-summary.md
```

Use stable filenames; for findings prefer `NN-short-kebab-title.md`.

## Workflow

### 0. Resolve repo and prepare workspace

Before any issue/PR fetch or artifact creation:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
GH_REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
gh auth status -R "$GH_REPO" || halt "gh is not authenticated for $GH_REPO"

if ! git check-ignore -q .pi/review/; then
  GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
  grep -qx '.pi/review/' "$GIT_COMMON_DIR/info/exclude" 2>/dev/null || echo '.pi/review/' >> "$GIT_COMMON_DIR/info/exclude"
fi
mkdir -p .pi/review
```

From here, prefix every `gh` command with `-R "$GH_REPO"`.

### 1. Resolve issue, PR, branch, and commit

1. Fetch and validate the issue:

```bash
gh -R "$GH_REPO" issue view <ISSUE_NUMBER> --json number,title,body,url,state,labels,assignees,comments > .pi/review/issue.json.tmp
python3 -m json.tool .pi/review/issue.json.tmp > /dev/null && mv .pi/review/issue.json.tmp .pi/review/issue.json
```

If output is empty/invalid, halt and report the `gh` failure.

2. Identify the related PR from issue body/comments, branch hints, linked PRs, or user-provided hints. If none or multiple plausible PRs are found, halt and ask the user to choose.

3. Save PR metadata, comments, changed files, and current checkout state:

```bash
gh -R "$GH_REPO" pr view <PR_NUMBER> --json number,title,body,url,state,headRefName,headRefOid,baseRefName,comments,reviews,files > .pi/review/pr.json.tmp
python3 -m json.tool .pi/review/pr.json.tmp > /dev/null && mv .pi/review/pr.json.tmp .pi/review/pr.json
gh -R "$GH_REPO" pr view <PR_NUMBER> --comments > .pi/review/pr-comments.txt
gh -R "$GH_REPO" pr diff <PR_NUMBER> --name-only > .pi/review/changed-files.txt
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_HEAD=$(git rev-parse HEAD)
git status --porcelain
```

If the tree is dirty, halt and ask the user to stash/commit; line numbers may be unreliable.

4. Verify checkout alignment:
   - If detached (`CURRENT_BRANCH=HEAD`), halt and ask the user to check out the feature branch.
   - Confirm `CURRENT_BRANCH` matches the PR head branch or user-confirmed branch.
   - Confirm `CURRENT_HEAD` matches `headRefOid` from `.pi/review/pr.json`.

Write `.pi/review/review-context.json` with repo, issue, PR, branch, head SHA, base branch, artifact paths, and timestamp.

### 2. Download and validate specs

Extract Zoho/spec links from `.pi/review/issue.json`, `.pi/review/pr.json`, and `.pi/review/pr-comments.txt`. Classify each as:

- `required`: directly referenced as the module spec or the only spec link available.
- `optional`: supplementary, duplicate, or unrelated to the module.
- `ambiguous`: relevance cannot be determined.

If any classification is ambiguous, ask the user before continuing.

Maintain `.pi/review/spec/spec-manifest.json`:

```json
{
  "specs": [
    {
      "source_url": "https://...",
      "filename": "spec-01.pdf",
      "sha256": "...",
      "issue_number": 123,
      "pr_number": 456,
      "download_time": "ISO8601",
      "classification": "required"
    }
  ]
}
```

For each required link, reuse an existing manifest entry only when `source_url`, issue, PR, PDF, and text file all match. Otherwise download to `.pi/review/spec/` using the original filename when stable, else `spec-01.pdf`, `spec-02.pdf`, etc.

Validate each PDF before trusting it:

```bash
file .pi/review/spec/<file>.pdf | grep -q "PDF" || echo "NOT A VALID PDF"
MIN_SIZE=1024
FILE_SIZE=$(stat -f%z .pi/review/spec/<file>.pdf 2>/dev/null || stat -c%s .pi/review/spec/<file>.pdf)
[ "$FILE_SIZE" -ge "$MIN_SIZE" ] || echo "FILE TOO SMALL"
```

Record sha256 metadata, then convert missing text files:

```bash
pdftotext -layout .pi/review/spec/<file>.pdf .pi/review/spec/<file>.txt
[ -s .pi/review/spec/<file>.txt ] || echo "EMPTY"
grep -qiE '<html|<head>|<body>|login|sign.in|password' .pi/review/spec/<file>.txt && echo "SUSPECTED HTML - NOT SPEC TEXT"
```

If a required PDF/download/text conversion fails validation, halt with the URL/file and reason.

### 3. Define single-module scope

Determine one coherent module from the issue title/body, PR files, branch, and spec. If the PR touches unrelated modules and scope is unclear, ask the user to choose before reviewing.

Prepare a context packet for subagents with:

- Issue/PR numbers, titles, URLs, branch, and head SHA.
- Module scope and assumptions.
- Spec text paths.
- Changed files from `.pi/review/changed-files.txt`; verify each exists locally.
- Instruction to report only spec-vs-code findings, including spec requirements missing from code.
- Instruction to validate every cited code line against the current checkout immediately before writing.

### 4. Run independent logic reviews

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

### 5. Validate logic outputs and run reviewer pass

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

### 6. Main-agent verification and final summary

Re-verify the PR head before using reviewer output:

```bash
CURRENT_PR_HEAD=$(gh -R "$GH_REPO" pr view <PR_NUMBER> --json headRefOid -q '.headRefOid')
SAVED_PR_HEAD=$(python3 -c "import json; print(json.load(open('.pi/review/pr.json'))['headRefOid'])")
```

If the head changed, halt and ask whether to re-run on the updated head or continue with the stale documented state.

Personally verify `.pi/review/review/*.md`; do not blindly trust subagents. For each accepted finding:

1. Confirm the spec reference exists and supports the claim.
2. Re-open cited code with line numbers and fix bad ranges before final reporting.
3. For missing implementations, use targeted searches and cite closest relevant files/functions or search evidence; do not invent line numbers.
4. Confirm module relevance, merge duplicates, and remove unsupported/vague/non-actionable items.

Read both coverage checklists. Verify `NOT_IMPLEMENTED`; investigate `UNCERTAIN`; confirm `SKIPPED` is out of scope; spot-check some requirements both reviewers marked `VERIFIED`.

Write `.pi/review/final-summary.md` using the final summary template below. It is the only consolidated review output and should be directly usable for GitHub PR review.

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

## Suggested PR review comment
<Concise GitHub-ready comment.>
```

## Final summary template

````markdown
# PR Spec Review Summary

## Review target
- Issue: #<number> — <title>
- PR: #<number> — <title>
- Branch: <branch>
- PR head SHA: <headRefOid>
- Module: <module>
- Spec documents: <URLs and filenames>

## Executive summary
<Whether implementation matches the spec and the most important gaps, including missing requirements.>

## Spec coverage
- Total spec requirements considered: <N>
- Requirements with findings: <N>
- Requirements not implemented: <N>
- Requirements verified with no discrepancy: <N>
- Requirements out of scope: <N>
- Requirements uncertain/unresolved: <N>

## Findings ready for GitHub PR review
<Group findings by Critical, High, Medium, Low. Omit empty severity groups.>

### <Severity>
#### <N>. <Finding title>
- Category: <category>
- Spec details: <document + section/page/heading + requirement + expected behavior>
- Code details: `<file>:<validated line-range>` — <current behavior, or "No implementation found" with search evidence>
- Discrepancy: <exact mismatch or missing implementation>
- Possible fix: <concrete implementation direction>

```suggestion-comment
<Specific, actionable GitHub-ready comment that mentions expected spec behavior.>
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
- Category, severity, spec details, code details, discrepancy, possible fix, impact, and a concise GitHub-ready comment.
- Relevance to the selected module.

Reject style-only comments unless required by the spec, repo-wide cleanup, assumptions/unstated requirements, findings without code evidence, and duplicate comments unless each instance needs a separate PR comment.

## Halt conditions

Halt and ask/report when:

- Issue number is missing.
- `gh` cannot fetch issue/PR data or returns empty/invalid JSON.
- No related PR/branch is found, or multiple PRs are plausible.
- Current branch/HEAD does not match the PR branch/head.
- Working tree is dirty.
- Required Zoho/spec documents cannot be downloaded, are invalid PDFs, are too small, hit an auth wall, fail checksum/manifest validation, or convert to empty/unusable text.
- A required spec link is ambiguous and unconfirmed.
- The PR spans unrelated modules and target scope is unclear.
- Subagent output is malformed, stale, unsupported, or missing required sections.
- New commits are pushed to the PR during review.

When halting, state what was tried and the exact next information/action needed from the user.

