---
name: prism-review
description: Execute a GitHub issue-driven specification review workflow. Use this skill whenever the user gives a GitHub issue number and asks to review implementation against specs, Zoho workflow/spec links, related PRs, or branch code. This skill should be used for multi-step PR reviews that require gh CLI issue/PR lookup, worktree selection, downloading spec PDFs, pdftotext conversion, logic-reviewer subagents, reviewer subagents, and a final GitHub-ready review summary.
---

# GitHub Issue Spec Review

Use this skill to turn a GitHub issue number into a structured single-module review of the related PR/branch against the specification documents linked from the issue.

The goal is not a general code review. The goal is to verify whether the implementation matches the spec: workflows, formulas, thresholds, states, edge cases, validation rules, side effects, and output schemas. Keep all findings traceable to both the spec and code.

## Inputs

Expected user input: a GitHub issue number, optionally with repo/worktree hints.

If the issue number is missing or ambiguous, ask for it before proceeding.

## Required tools and assumptions

- `gh` CLI is installed and authenticated for the repository.
- `git` is available.
- `python` is available.
- `pdftotext` is available for PDF-to-text conversion.
- `logic-reviewer` and `reviewer` subagents are available.
- The repository may use git worktrees; do not assume the current directory is the right checkout.

If a required tool is missing, halt with a short explanation and the exact command/tool that failed.

## Directory layout

Create and use this structure under the resolved repository/worktree root:

```text
.pi/review/
  review-context.json     # manifest: repo, issue, PR, branch, SHAs, spec metadata
  issue.json
  pr.json
  changed-files.txt
  spec/
    spec-manifest.json    # source URL, filename, sha256, issue, PR, download time
    *.pdf
    *.txt
  logic-findings-high/
    *.md
  logic-findings-medium/
    *.md
  logic-findings-high-coverage.md    # spec coverage checklist
  logic-findings-medium-coverage.md  # spec coverage checklist
  review/
    *.md
  final-summary.md
```

Use stable, readable filenames. For individual findings, prefer `NN-short-kebab-title.md`, for example `01-missing-validation-for-empty-state.md`.

## Workflow

### 0. Resolve repository and worktree root

Before running any `gh` command or creating any artifact, resolve the target repository and worktree.

1. Get the repository root and top-level path:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
```

2. Determine the GitHub repository identifier:

```bash
GH_REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
```

3. From this point forward, prefix every `gh` command with `-R "$GH_REPO"` so that commands are repo-pinned regardless of worktree or subdirectory.

4. Verify `.pi/review/` is gitignored:

```bash
if ! git check-ignore -q .pi/review/; then
  GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
  grep -qx '.pi/review/' "$GIT_COMMON_DIR/info/exclude" 2>/dev/null || echo '.pi/review/' >> "$GIT_COMMON_DIR/info/exclude"
fi
```

This uses `git-common-dir` (correct for both normal repos and worktrees) and avoids duplicate entries.

5. Create `.pi/review/` if it does not exist:

```bash
mkdir -p .pi/review
```

5. Verify `gh` is authenticated for this repo:

```bash
gh auth status -R "$GH_REPO" || halt "gh is not authenticated for $GH_REPO"
```

Do not proceed until the repository identity is resolved and `gh` is confirmed authenticated.

### 1. Resolve issue and verify branch

1. Fetch issue details and save as validated JSON:

```bash
gh -R "$GH_REPO" issue view <ISSUE_NUMBER> --json number,title,body,url,state,labels,assignees,comments > .pi/review/issue.json.tmp
python3 -m json.tool .pi/review/issue.json.tmp > /dev/null && mv .pi/review/issue.json.tmp .pi/review/issue.json
```

If the temp file is empty or invalid JSON, halt and report the `gh` error.

2. Get the current branch and HEAD SHA:

```bash
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_HEAD=$(git rev-parse HEAD)
```

3. Check for a dirty working tree:

```bash
git status --porcelain
```

If dirty, report the uncommitted changes and ask the user to stash or commit before re-running. Do not proceed with a dirty tree — line numbers in findings will be unreliable.

4. Verify the branch aligns with the issue:
   - If `CURRENT_BRANCH` is `HEAD` (detached HEAD state), warn the user and ask them to check out the feature branch for this issue before proceeding.
   - Otherwise, confirm with the user that `CURRENT_BRANCH` is the correct branch for issue #<ISSUE_NUMBER>. If the issue body or title references a branch name, verify it matches.

If the user confirms the branch is wrong, halt and ask them to switch to the correct branch and re-run.

Do not review code from the wrong branch or commit. Do not attempt to switch branches or create new worktrees.

### 3. Download and convert spec documents

The issue body/comments and PR body/comments should contain Zoho workflow/spec links.

1. Extract all Zoho document links from:
   - `.pi/review/issue.json` (issue body and comments)
   - `.pi/review/pr.json` (PR body)
   - `.pi/review/pr-comments.txt` (PR comments/review discussion)

2. Classify each extracted link:
   - **Required**: directly referenced as the spec for the module under review, or the only spec link available.
   - **Optional**: supplementary, duplicate, or not clearly related to the PR's module.
   - **Ambiguous**: cannot determine relevance from context.

If any link's classification is ambiguous, ask the user to confirm before proceeding.

3. Load or initialize the spec manifest at `.pi/review/spec/spec-manifest.json`:

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

4. For each required link, check the manifest for an existing entry matching the same source URL, issue number, and PR number. If found and both the PDF and text file exist, reuse them without re-downloading. If not found or metadata does not match, download the document.

5. Download missing documents to `.pi/review/spec/`. Use the original filename from the URL when possible. If a stable filename is not available, use `spec-01.pdf`, `spec-02.pdf`, etc.

6. Validate each downloaded file before trusting it:

```bash
# Check HTTP success and content
file .pi/review/spec/<file>.pdf | grep -q "PDF" || echo "NOT A VALID PDF"

# Check minimum size (reject empty/truncated files)
MIN_SIZE=1024
FILE_SIZE=$(stat -f%z .pi/review/spec/<file>.pdf 2>/dev/null || stat -c%s .pi/review/spec/<file>.pdf)
[ "$FILE_SIZE" -ge "$MIN_SIZE" ] || echo "FILE TOO SMALL"
```

If a downloaded file fails validation, halt and report the URL and failure reason. Do not proceed with untrusted spec files.

7. Update `spec-manifest.json` with each successfully downloaded file's metadata, including sha256 checksum.

8. Convert every validated PDF that lacks a corresponding text file:

```bash
pdftotext -layout .pi/review/spec/<file>.pdf .pi/review/spec/<file>.txt
```

9. Validate each `.txt` file:

```bash
# Non-empty
[ -s .pi/review/spec/<file>.txt ] || echo "EMPTY"

# Check for HTML/login page indicators (Zoho auth wall)
grep -qiE '<html|<head>|<body>|login|sign.in|password' .pi/review/spec/<file>.txt && echo "SUSPECTED HTML - NOT SPEC TEXT"
```

If any required document's text file fails validation, halt and report. The review depends on accurate spec text.

If any required Zoho document cannot be downloaded or converted, halt here. Report the failed URL/file and do not proceed to code review.

### 4. Define the review scope as a single module

Before starting subagent reviews, determine the module under review from the issue title/body, PR files, branch name, and spec. A "single module review" means the final output should be scoped around one coherent feature/module rather than listing unrelated repo-wide issues.

If the PR touches several unrelated modules and the intended module is unclear, ask the user to choose the module before continuing.

Prepare a concise context packet for subagents:

- Issue number, title, and URL
- PR number, title, URL, and branch
- Module scope
- Spec text file paths
- Relevant changed files from `.pi/review/changed-files.txt` (verify each file exists locally; report missing files)
- Instruction to produce only spec-vs-code findings with spec sections and code references

### 5. Run two parallel logic reviews

Spawn two `logic-reviewer` subagents against the same module and spec context, but keep their work independent:

1. One high-complexity review.
2. One medium-complexity review.

Launch both in the same parallel subagent call. Do not run one first, wait for its files, then start the other; that lets the later reviewer see the earlier review and defeats independence.

Build two role-specific task packets. Each packet may include only the shared context packet, spec text paths, relevant code paths, and that subagent's own output paths. Do not include the other reviewer's output directory, coverage file, findings, or summary in the task packet.

Ask each logic reviewer to compare implementation against the spec and write one markdown file per finding.

High-complexity output directory:

```text
.pi/review/logic-findings-high/
```

Medium-complexity output directory:

```text
.pi/review/logic-findings-medium/
```

Before spawning subagents, create and clear the output directories:

```bash
mkdir -p .pi/review/logic-findings-high .pi/review/logic-findings-medium
rm -f .pi/review/logic-findings-high/*.md .pi/review/logic-findings-medium/*.md
rm -f .pi/review/logic-findings-high-coverage.md .pi/review/logic-findings-medium-coverage.md
```

Also require each logic reviewer to produce a spec coverage checklist alongside its findings. Give each reviewer only its own coverage path:

```text
# high-complexity reviewer only
.pi/review/logic-findings-high-coverage.md

# medium-complexity reviewer only
.pi/review/logic-findings-medium-coverage.md
```

The coverage checklist should list every major spec section/requirement considered, with one of:

- `COVERED — finding file: <filename>` (a discrepancy was found)
- `VERIFIED — no discrepancy found` (the code matches the spec for this requirement)
- `SKIPPED — not in module scope` (explicitly out of scope)
- `UNCERTAIN — could not determine` (needs human review)

This ensures that a missed requirement is visible, not silently absent.

Each finding file should use this structure:

```markdown
# <Finding title>

## Category

<Logic mismatch | Missing requirement | Edge case | Validation | Data mapping | State/workflow | Formula/threshold | Output/schema | Security/spec compliance | Other>

## Severity

<Critical | High | Medium | Low>

## Spec reference

- Document: <spec txt/pdf name>
- Section/page/heading: <specific location>
- Requirement: <quoted or tightly paraphrased requirement>

## Code reference

- File: <path>
- Lines: <line range>
- Implementation: <brief description of current behavior>

## Issue

<Explain the discrepancy between spec and code.>

## Impact

<Explain user/business/system impact.>

## Suggested PR review comment

<Concise GitHub-ready comment.>
```

Tell subagents not to create aggregate summaries in the findings folders; one file per finding keeps the next review step clean.

Independence guardrail for each logic-reviewer prompt:

- Treat the other reviewer's artifacts as forbidden input, not context.
- Do not read, list, grep, summarize, or compare against `.pi/review/logic-findings-high/`, `.pi/review/logic-findings-medium/`, `.pi/review/logic-findings-high-coverage.md`, or `.pi/review/logic-findings-medium-coverage.md`, except for your own assigned output directory/coverage file when writing results.
- If you accidentally see another reviewer's finding or coverage file, ignore it and state this in your completion note.
- Base findings only on the issue/PR context, spec text, changed-file list, and code files.

This independence only applies to the two logic-reviewer passes. The later reviewer pass intentionally reads both sets of validated findings.

### 6. Validate subagent outputs and run reviewer pass

After each logic-reviewer subagent completes, validate its output before proceeding:

1. Check that the output directory contains at least one `.md` file (or that the subagent explicitly recorded zero findings in its coverage checklist).
2. Verify each finding file has the required sections: Category, Severity, Spec reference, Code reference, Issue, Impact, Suggested PR review comment.
3. Verify each Spec reference and Code reference contains non-placeholder content (no empty `<>` fields).
4. Verify file timestamps are from the current run (not stale from a previous iteration).

If validation fails, halt and report which files are malformed. Do not feed malformed findings to the reviewer.

Then spawn a `reviewer` subagent with medium complexity to review the validated logic findings, not to redo the whole code review from scratch.

Inputs:

- `.pi/review/logic-findings-high/*.md`
- `.pi/review/logic-findings-medium/*.md`
- `.pi/review/logic-findings-high-coverage.md`
- `.pi/review/logic-findings-medium-coverage.md`
- Spec text files
- Relevant code files

Output directory:

```text
.pi/review/review/
```

Before spawning the reviewer, create and clear the output directory:

```bash
mkdir -p .pi/review/review
rm -f .pi/review/review/*.md
```

Ask the reviewer to:

- Deduplicate overlapping findings.
- Reject findings that are not supported by both spec and code references.
- Tighten categories and severity.
- Improve GitHub-ready review comments.
- Preserve one markdown file per accepted finding.
- Include exact spec section/page/heading and code file/line references.
- Note any spec requirements from the coverage checklists that were marked UNCERTAIN or that both logic reviewers marked as VERIFIED but the reviewer suspects may have issues.

Each reviewer output file must use this structure:

```markdown
# <Finding title>

## Category

<Logic mismatch | Missing requirement | Edge case | Validation | Data mapping | State/workflow | Formula/threshold | Output/schema | Security/spec compliance | Other>

## Severity

<Critical | High | Medium | Low>

## Spec reference

- Document: <spec txt/pdf name>
- Section/page/heading: <specific location>
- Requirement: <quoted or tightly paraphrased requirement>

## Code reference

- File: <path>
- Lines: <line range>
- Implementation: <brief description of current behavior>

## Issue

<Explain the discrepancy between spec and code.>

## Impact

<Explain user/business/system impact.>

## Suggested PR review comment

<Concise GitHub-ready comment.>
```

### 7. Main-agent final review and summary

After the reviewer subagent finishes:

#### 7a. Re-verify PR head has not changed

```bash
CURRENT_PR_HEAD=$(gh -R "$GH_REPO" pr view <PR_NUMBER> --json headRefOid -q '.headRefOid')
SAVED_PR_HEAD=$(python3 -c "import json; print(json.load(open('.pi/review/pr.json'))['headRefOid'])")
```

If `CURRENT_PR_HEAD` differs from `SAVED_PR_HEAD`, halt and report that new commits were pushed during the review. Ask the user whether to re-run with the updated HEAD or proceed with the stale (but documented) state.

#### 7b. Review findings

Personally review all accepted findings in `.pi/review/review/*.md` against the spec and code. Do not blindly trust subagent output.

For each finding:

1. Confirm the spec reference exists and supports the claim.
2. Confirm the code reference exists and line numbers are accurate.
3. Confirm the issue is in the selected module scope.
4. Merge duplicates if any remain.
5. Remove unsupported, vague, or non-actionable findings.

#### 7c. Verify spec coverage

Read both coverage checklists (`logic-findings-high-coverage.md` and `logic-findings-medium-coverage.md`).

For any requirement marked:

- `UNCERTAIN` — attempt to verify yourself. If still uncertain, include in the final summary under "Review notes" as an unresolved item.
- `SKIPPED` — confirm it is genuinely out of module scope. If not, flag it.
- `VERIFIED` by both reviewers — spot-check a few to build confidence, but do not re-review all of them.

This catches the case where both logic reviewers missed or incorrectly cleared a requirement.

#### 7d. Create final summary

Create one final document:

```text
.pi/review/final-summary.md
```

Use this structure:

````markdown
# PR Spec Review Summary

## Review target

- Issue: #<number> — <title>
- PR: #<number> — <title>
- Branch: <branch>
- PR head SHA: <headRefOid>
- Module: <module>
- Spec documents: <list with URLs and filenames>

## Executive summary

<Brief summary of whether the implementation matches the spec and the most important gaps.>

## Spec coverage

- Total spec requirements considered: <N>
- Requirements with findings: <N>
- Requirements verified with no discrepancy: <N>
- Requirements out of scope: <N>
- Requirements uncertain/unresolved: <N>

## Findings ready for GitHub PR review

### 1. <Finding title>

- Category: <category>
- Severity: <severity>
- Spec reference: <document + section/page/heading>
- Code reference: `<file>:<line-range>`

```suggestion-comment
<GitHub-ready PR review comment. It should be specific, actionable, and mention the expected behavior from the spec.>
```
````

### 2. <Finding title>

...

## Findings considered but excluded

<Optional. List rejected/merged findings briefly if useful.>

## Unresolved spec requirements

<List any requirements marked UNCERTAIN that could not be resolved.>

## Review notes

<Any constraints, missing documents, ambiguous spec language, stale-commit warnings, or assumptions.>

```

The final summary is the only place to produce the single consolidated review. Keep it focused on issues that can be put directly into a GitHub PR review.

## Quality bar

A finding is acceptable only when it has all of the following:

- A clear mismatch between spec and implementation.
- A specific spec reference: document plus section/page/heading or quoted requirement.
- A specific code reference: file plus line range.
- A category and severity.
- A concise, actionable GitHub-ready comment.
- Relevance to the selected module.

Avoid:

- Style-only comments unless the spec explicitly requires the style/format.
- Repo-wide cleanup suggestions unrelated to the module.
- Findings based only on assumptions or unstated requirements.
- Findings without line numbers.
- Repeating the same issue across multiple files unless each instance needs its own PR comment.

## When to halt

Halt and ask/report instead of continuing when:

- The issue number is missing.
- `gh` cannot fetch the issue or the fetch produces invalid/empty JSON.
- No related PR/branch can be identified.
- Multiple related PRs are plausible and the user has not chosen one.
- The current worktree branch does not match the PR branch.
- The current HEAD SHA does not match the PR head SHA.
- The working tree is dirty (uncommitted changes).
- Required Zoho spec documents cannot be downloaded or fail validation (not a PDF, too small, HTML/auth wall detected).
- PDF conversion fails or produces empty/unusable text.
- The downloaded spec file does not match the manifest (wrong file, checksum mismatch).
- A required spec link's classification is ambiguous and the user has not confirmed.
- The PR appears to cover multiple unrelated modules and the intended module is unclear.
- Subagent output files are malformed or missing required sections.
- New commits were pushed to the PR head during the review.

When halting, include what you tried and the next piece of information needed from the user.
```
