# Parallel PR reviews in your existing Orca workspace

## Run

From an Orca workspace terminal:

```sh
~/.local/bin/orca-pr-review 231 --agents omp,pi,antigravity,prime-agent
```

Omit the PR number to be prompted. `--repo /absolute/path` selects another existing
registered local workspace. `--remote upstream` selects a GitHub remote other than origin.
Install/enable/authenticate your chosen agents in **Settings → Agents** and authenticate `gh`.
**Orchestration does not need to be enabled.**

## What changed

The helper now calls Orca's native **agent.launch** API, not `orchestration worker-start`.
Each request includes the existing workspace, agent ID, and the entire short prompt:

```text
Review PR #231: https://github.com/OWNER/REPO/pull/231
Do a code review and explain whether it can be merged, including any blocking issues.
Do not change source code, switch branches, or merge/post anything.
Write your finished review to REPORT_PATH (temporary file, then rename).
End the report with Merge verdict: YES, NO, or UNCERTAIN (choose one).
```

There is **no orchestration worker preamble, task/dispatch ID, heartbeat, or worker_done**.
For argv-capable agents such as OMP, Pi and Prime Agent, Orca includes the prompt in the
startup command: it does not start an empty session and wait to inject a second command.
Providers without startup-prompt arguments still use Orca's readiness wait (up to 60 seconds)
and subsequent PTY prompt injection. Only report collection is independent of agent-state hooks.
OMP's startup-argument path is supported by the inspected Orca source, but live OMP delivery
has not been verified by this helper's installation checks.

All configured reviewers launch concurrently in the **same existing workspace**, each as a
fresh native Orca agent session. No workspaces/worktrees are created. Orca—not this helper—
resolves CLI executable names, configured launch arguments, permissions, models and accounts.
For example, use agent ID `antigravity`; Orca resolves its configured `agy` launcher.
Arguments/model options are not overridden by the helper.

The helper uses the authenticated local runtime Unix socket because the CLI currently does
not expose `agent.launch` for an existing workspace. Linux and macOS native local workspaces
are supported. SSH, WSL, paired runtimes and Windows are refused, never redirected locally.
Metadata is found using `ORCA_USER_DATA_PATH` or Orca's normal OS data directory. Runtime auth
credentials are read only in memory, never copied to the manifest or printed.

## Configure agents in Orca IDE

### Through Settings → Quick Commands

Add a **terminal command**, named **Parallel PR review**, scoped globally or to your project:

```sh
~/.local/bin/orca-pr-review --agents omp,pi,antigravity,prime-agent
```

Launch it from the tab bar/terminal Quick Commands menu and enter the PR number.
Edit `--agents` in that same settings UI whenever you want a different reviewer list.
The helper has no hard-coded reviewer allowlist; Orca validates installed/enabled IDs.

### Through Orca's file editor

Open `~/.config/orca-pr-review/config.json` and change its `agents` array:

```json
{
  "agents": ["omp", "pi", "antigravity", "prime-agent"]
}
```

A command without `--agents` reads this config at launch. `--agents` overrides it.
`--config /path/to/config.json` allows project-specific lists. The initial installed config
has not been overwritten; it retains your previous choices.

## Collection and results

Each run prints its unique report directory:

```text
~/.local/share/orca-pr-review/reports/OWNER--REPO/pr-N-TIMESTAMP-ID/
  manifest.json
  AGENT.md
  pr-N-review.md
```

Completion is based on the finished report file, **not agent hooks or terminal idle detection**.
The collector requires a final YES/NO/UNCERTAIN verdict and unchanged contents across two
observations. The prompt asks agents to write a temporary file and rename it when finished.
Sessions remain visible/open after reports arrive; the helper never closes or kills them.
A finished report is not proof that the agent process exited.

The combined Markdown includes each full review verbatim and a conservative recommendation:
any NO → NO; all valid YES reports → YES; missing/invalid/uncertain reviews → UNCERTAIN.
This is a review recommendation, not permission to merge or verification of CI status.
Reviews are not semantically deduplicated. PR commit metadata is recorded at launch, but
agents review the PR themselves; this does not certify a pinned snapshot. Prompt instructions
are not an OS sandbox. Other agents already running in the workspace are not altered.

## Timeout, interruption and resume

Default wait: 30 minutes. `--timeout 60` changes it. Timeout/Ctrl-C does not cancel sessions.
Launch receipts and operation IDs are saved before/after the launch wave. No launches are
blindly repeated after a lost response.

```sh
~/.local/bin/orca-pr-review --resume /absolute/path/to/report-directory
```

Resume collects existing sessions' reports. An unresolved launch is recovered only through
Orca's replay API using its exact original operation ID and parameters, so it cannot launch
a duplicate under a new identity. After a runtime restart, launch replay is skipped, but report
collection still works. Known sessions can be collected without connecting to Orca. Explicit
launch rejections are preserved in the manifest; inspect the error before starting a new run.
A `not-delivered` prompt receipt is preserved, not silently reinjected.

Old orchestration runs are **not resumed/restarted** by this version. Their existing agents
remain untouched. You can collect their available report files offline:

```sh
~/.local/bin/orca-pr-review --collect-only /absolute/path/to/report-directory
```

`--collect-only` scans every requested review file, including files arriving after a timeout
or lost launch receipt. It performs two observations a second apart without connecting to Orca.
Missing/invalid reports produce exit code 2, even if an older manifest recorded success.
`--output-dir /new/path` changes the destination of a new run; it must not already exist.

Exit code 0 for a review run means every requested review file was collected with a valid
verdict. It does **not** mean every verdict is YES. Exit code 2 means blocked/incomplete.

## Validation

```sh
~/.local/bin/orca-pr-review --doctor
```

Doctor authenticates to the actual local runtime and verifies native launch/replay API support;
it does not start agents. Provider logins are checked by Orca/provider at launch.
The simulated test suite has been removed. Doctor confirms API availability, not successful
provider startup or prompt delivery. No live review is launched by doctor.
