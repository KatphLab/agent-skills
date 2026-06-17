---
name: pr-comment-review
description: >
  Review whether the latest commits in a PR address all review comments. Use this
  whenever the user gives a PR number and asks to check if review comments are
  resolved, verify review responses, compare commits against reviewer feedback,
  or asks "did this commit fix the comments?" / "check if PR feedback was
  addressed." This skill should be used for any comment-resolution review on a
  GitHub PR.
---

# PR Comment Resolution Review

Given a GitHub PR number, verify that the latest commits on the PR branch
address every review-comment raised on the PR.  The review is line‑sensitive:
each comment is mapped back to the code region it targeted, and the current file
state at that region is examined for resolution.

## Required tools

- `gh` CLI (authenticated for the repo)
- `git`

If either is missing, halt.

## Workflow

### 1. Resolve the repository

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
GH_REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null)
```

If either command fails there is no valid git repo or `gh` is not
authenticated — halt and tell the user.

### 2. Fetch pull request metadata

```bash
gh -R "$GH_REPO" pr view <PR_NUMBER> --json number,title,url,state,headRefName,headRefOid,baseRefName,baseRefOid
```

Save as `pr.json`.  Extract:
- `headRefName`   — the branch the PR targets
- `headRefOid`    — the SHA the PR currently points at
- `baseRefOid`    — the branch the PR is merging into

### 3. Match worktree to PR branch — **halt on mismatch**

```bash
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_HEAD=$(git rev-parse HEAD)
```

- `CURRENT_BRANCH` must equal `headRefName` (unless detached; see below).
- `CURRENT_HEAD` must equal `headRefOid`.

If `CURRENT_BRANCH` is `HEAD` (detached), skip the branch‑name check and
verify only HEAD SHA equality.  Note the detached state in output.

**If there is any mismatch, halt here.**  Tell the user:
- Current branch / HEAD
- Expected branch / HEAD (from the PR)
- "Switch to the correct worktree and re‑run."

Also check for a dirty working tree (`git status --porcelain`).  If dirty,
warn the user that line‑number accuracy may be affected, but do **not** halt —
the user may be mid‑edit.

### 4. Fetch review comments

Reviews come from two API endpoints.  Fetch both:

**Review decisions** (APPROVED / CHANGES_REQUESTED):
```bash
gh api repos/{owner}/{repo}/pulls/<NUMBER>/reviews \
  --jq '.[] | {author: .user.login, state, body}'
```

**Inline review comments** — these carry the `original_line` field that
pinpoints which line in the original file the comment was attached to:
```bash
gh api repos/{owner}/{repo}/pulls/<NUMBER>/comments \
  --jq '.[] | {author: .user.login, body, path, original_line, side, diff_hunk}'
```

**Only process comments that are actionable** — skip:
- Comments from the PR author (unless they are self‑review notes).
- Comments with empty bodies.
- Comments from bots (dependabot, coverage, etc.) unless they flag issues.

If there are zero actionable comments, report that and stop — nothing to
review.

### 5. Identify the commits to inspect

By default, inspect **all commits on the PR branch since the PR was opened**
that are not in the base branch:

```bash
git log --oneline <baseRefOid>..HEAD
```

If the user explicitly says "check the **last commit**" or "check since the
review," narrow to only those commits.

Show the full diff of the identified commits:
```bash
git show <commit-range>   # or individual commits
```

### 6. Map each comment to its code and check resolution

For **every** inline review comment:

1. **Resolve the file path** — the `path` field from the API is the path
   relative to the repo root.  Verify it exists in the current tree.

2. **Find the target line** — the `original_line` field tells you which line
   in the **original** (base) file the comment was placed on.  Use git to
   inspect that version of the file:

   ```bash
   git show <baseRefOid>:<path> | sed -n '<line-5>,<line+5>p'
   ```

   Show 5 lines of context around the target so you understand exactly what
   the reviewer was looking at.

   **Important**: the line number in `original_line` refers to the version of
   the file at the time the review was submitted, not the current HEAD.
   Always resolve against that base commit.  If the file was added in the PR
   (didn't exist in base), use the first commit where it was introduced.

3. **Compare with the current file** — read the current version of the file
   at the corresponding region and see what changed.  If the file was
   restructured, find the semantically equivalent code.

4. **Judge resolution** — for each comment, answer: is the concern addressed?
   Mark it as **RESOLVED**, **PARTIALLY**, or **NOT RESOLVED**, with a brief
   explanation that references the specific line(s) and code.

### 7. Produce the report

Output a structured table in the conversation:

```
## PR #<NUMBER> — Comment Resolution Review

PR branch: `<headRefName>`  |  HEAD: `<headRefOid>`  |  Worktree: ✅ match

Commits inspected: <range or list>

### Review summary
<author> — <CHANGES_REQUESTED | APPROVED> (<N> inline comments)

| # | Author | Original Line | File | Comment (abbreviated) | Status |
|---|--------|--------------|------|----------------------|--------|
| 1 | @user  | 308          | engine.py | "spec doesn't use abs" | ✅ RESOLVED |
| 2 | @user  | 369          | engine.py | "make threshold configurable" | ⚠️ PARTIALLY |
| 3 | @user  | 475          | engine.py | "missing proximity check" | ✅ RESOLVED |

### Unresolved / partially resolved
<For each comment that is not fully resolved:
- The exact snippet of the comment
- What the original code looked like (with context)
- What the current code looks like
- Why it is not fully resolved
- A suggested fix
>
```

The table must include **every** actionable comment.  Do not skip resolved
items — the user needs to see a complete picture.

### Key principles

- **Line numbers are the primary lens.**  Every comment maps to an
  `original_line`.  Always read the code around that line before judging.
- **Use the git history, not heuristics.**  Compare the base version of the
  file against the current version.  Do not guess what the reviewer meant.
- **Be precise in unresolved reports.**  Quote the exact comment text, show
  both old and new code, and suggest a concrete fix.
- **A partial fix is still a finding.**  Mark it PARTIALLY and explain what
  remains.
