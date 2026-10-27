# Parallel PR reviews in Herdr

Herdr equivalent of `orca-pr-review`: independent parallel reviews, finding verification, an OMP recheck, and a minimal fix plan. Uses Python's standard library and Herdr's native CLI; no Orca runtime or orchestration API.

## Run

From a terminal inside the existing Herdr workspace:

```sh
python3 ~/.agents/skills/herdr-pr-review/review.py 231 \
  --agents omp,pi,codex \
  --consolidation-agent codex --planning-agent pi
```

Use a PR number or URL, or omit it to select the current branch's PR. `--repo /absolute/path` selects an existing local repository; `--remote upstream` selects a GitHub remote other than `origin`. Each agent's new tab uses that repository as its cwd in the caller's workspace. No workspaces, worktrees, clones, or branch switches are created.

Requires a running Herdr server, `HERDR_ENV=1` caller context, `git`, authenticated `gh`, and installed/authenticated interactive agent CLIs. Commands stay on the caller's Herdr server; the helper has no SSH/machine forwarding. Run it on the machine that owns the checkout and report files.

Use kinds from the installed `herdr agent start --help`, not Orca IDs or executable paths. For example, Herdr uses `agy`, not `antigravity`; `prime-agent` is not an installed Herdr kind. The helper does not translate aliases, override models/permissions, install agents, or answer approval dialogs. Agents use their own CLI settings.

Reviewer choices can instead come from `~/.config/herdr-pr-review/config.json`:

```json
{"agents": ["omp", "pi", "codex"]}
```

`--agents` overrides that file; `--config /path/to/config.json` selects another file. `--consolidation-agent` and `--planning-agent` are explicit for each new run. The genuine-findings recheck uses OMP, matching the Orca pipeline.

## Flow and reports

Each reviewer gets a fresh background tab. The helper captures the returned root pane ID, calls `herdr agent start`, waits for startup readiness, then submits the complete prompt once with `herdr agent prompt`. Reviewers launch concurrently. Focus stays in the caller's pane; existing agents are untouched.

Review prompts require independent, evidenced PR-code findings, forbid source changes/branch switches/merging/posting, and request a finished Markdown report written by temporary-file rename. Completion requires a review body, a final `Merge verdict: YES`, `NO`, or `UNCERTAIN`, and unchanged bytes in two observations one second apart. Lifecycle idle/done and terminal text are not completion evidence.

The helper prints the run directory:

```text
~/.local/share/herdr-pr-review/reports/OWNER--REPO/pr-N-TIMESTAMP-ID/
  manifest.json
  omp.md
  pi.md
  codex.md
  pr-N-review.md
  pr-N.consolidated.md
  pr-N.genuine.md
  pr-N.plan.md
```

The combined `pr-N-review.md` preserves each collected review verbatim and recommends NO if any reviewer says NO, YES if every reviewer says YES, otherwise UNCERTAIN. It is the initial review aggregate, not the downstream verified verdict.

When all reviews arrive:

1. All YES → stop: no actionable code findings.
2. Otherwise the consolidation agent deduplicates and verifies findings against code/callers.
3. OMP rechecks genuine findings, rejecting speculative or over-engineered demands.
4. The planning agent writes the smallest fix plan, not implementation code.

A YES at any verification stage stops the remaining stages. A missing/invalid report stops progress to subsequent stages. Downstream files exist only for stages that ran. Verification caveats alone do not count as defects; unresolved suspected code defects warrant UNCERTAIN.

Exit 0 means all required reports were collected, including an early YES stop. It does not mean all verdicts are YES. Exit 2 means blocked/incomplete. These are review recommendations, not merge authorization, CI certification, or proof of a pinned commit snapshot. Prompts are not an OS sandbox; agents share the existing checkout.

## Timeout and recovery

The default wait is 30 minutes per wave/stage. `--timeout 60` changes it. Timeout and Ctrl-C leave sessions open; no agents are killed or closed, even after completion. `--output-dir /new/path` chooses a new, non-existing report directory.

```sh
python3 ~/.agents/skills/herdr-pr-review/review.py --resume /absolute/report/directory
python3 ~/.agents/skills/herdr-pr-review/review.py --collect-only /absolute/report/directory
```

Resume waits for existing reviewer/stage reports and starts only untouched downstream stages, in the original Herdr session/workspace. Offline collection takes two observations and makes no Herdr calls; it returns 2 when required reports are still missing. Both modes use saved choices and collect reports even when a launch receipt was lost.

Herdr has no launch replay contract equivalent to Orca's. The helper saves agent identities before launching and pane IDs before starting agents. It never automatically repeats `agent start` or `agent prompt`, including after an ambiguous timeout or lost response. A failed startup or uncertain delivery may therefore require manual attention:

```sh
herdr agent get NAME_FROM_MANIFEST
herdr agent read NAME_FROM_MANIFEST --source visible
```

Inspect the pane/dialog before deciding whether work was submitted. Respond to approval dialogs deliberately; an unknown outcome is not permission to submit the same review twice. Existing Orca manifests are not inputs to this helper.

## Validation

```sh
python3 ~/.agents/skills/herdr-pr-review/review.py --doctor --agents omp,pi,codex
```

Doctor checks the actual caller workspace, installed agent-start CLI surface, reviewer configuration, and `gh` authentication. It does not launch reviewers or prove provider authentication/readiness.

Implementation smoke checks exercised CLI workflows with controlled Herdr/GitHub responses: all-YES early exit, the full verification/planning pipeline, each verification early exit, malformed reports, timeout with late-report resume, and lost startup receipts. Live Herdr checks exercised background tab/root-pane creation, shell command/output collection, and native OMP startup plus `/help` prompt submission. Temporary smoke tabs were closed. No provider-backed PR review was launched.

Native interface references: [agent automation](https://herdr.dev/docs/agent-automation/) and [CLI reference](https://herdr.dev/docs/cli-reference/).
