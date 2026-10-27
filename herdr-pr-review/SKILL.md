---
name: herdr-pr-review
description: Run parallel PR reviews, verify findings, and produce a minimal fix plan in Herdr.
disable-model-invocation: true
---

# Herdr PR review

Run the bundled `review.py` inside a Herdr-managed pane, against an existing local repository. Read [README.md](README.md) for setup, report semantics, or recovery.

1. Resolve the requested PR and reviewer kinds from the user's request or `~/.config/herdr-pr-review/config.json`. Use Herdr kind names, such as `omp`, `pi`, `codex`, or `agy`; the installed `herdr agent start --help` lists supported kinds. The consolidation and planning roles require explicit choices. Ask for missing role choices rather than choosing models/providers for the user.
2. Run `python3 <this-skill-directory>/review.py --doctor --agents <kinds>` to check caller context and GitHub authentication. Provider installation, login, and approval dialogs remain provider responsibilities.
3. Start the helper, using the absolute path to this skill's `review.py`:

   ```sh
   python3 <this-skill-directory>/review.py <PR-number-or-URL> \
     --repo <existing-repository-path> --agents <comma-separated-kinds> \
     --consolidation-agent <kind> --planning-agent <kind>
   ```

   Omit the PR argument to review the current branch's PR. The helper opens a new background tab per agent in the caller's existing workspace. It neither creates checkouts nor changes branches. Reviewers run concurrently; consolidation, OMP recheck, and fix planning run sequentially only while findings remain.
4. Report the output directory and the last completed stage's findings/plan. Distinguish the initial combined recommendation from the verified findings. Exit 0 means the required reports arrived, not that merging is authorized or CI passed.

If interrupted, use `--resume <report-directory>` to collect existing reports and launch only untouched downstream stages. Use `--collect-only <report-directory>` for offline collection without any Herdr calls. Neither mode repeats a reviewer launch or prompt. For a startup/approval problem, inspect the saved agent name with `herdr agent get` and `herdr agent read --source visible`; ask the user before answering approval dialogs. Leave review sessions open.
