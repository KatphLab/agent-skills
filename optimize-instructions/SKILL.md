---
name: optimize-instructions
description: Use when asked to optimize, tighten, simplify, clean up, or rewrite markdown instruction files, prompts, system prompts, agent docs, skill docs, slash commands, or markdown workflows in place.
hide: true
---

# Optimize Instructions

Optimize only the named markdown instruction file(s), in place. Preserve behavior while making instructions shorter, clearer, and easier for agents to execute. Critique only when explicitly requested.

## Workflow

1. **Confirm targets**
   - If no path is named, ask for one before doing anything else.
   - If multiple paths are named, process each file independently and write each back in place.

2. **Read each target fully**
   - Preserve frontmatter, metadata, placeholders (`$ARGUMENTS`, `{previous}`), paths, command names, variables, output formats, command semantics, safety rules, permission boundaries, destructive-action warnings, edge cases, fallbacks, dependencies, and environment assumptions.
   - Before editing, identify the file's purpose, user outcome, constraints, decision branches, interaction model, and output contract.

3. **Rewrite for execution**
   - Make role, goal, decision order, ambiguity handling, dependency checks, user interaction, and output requirements explicit.
   - Prefer operational steps over explanation, motivation, style advice, or critique.
   - Separate requirements from preferences.
   - Keep only content that improves correct execution.

4. **Remove noise without changing scope**
   - Collapse duplication, redundant examples, unnecessary formatting, unresolved variants, speculative alternatives, TODOs, and non-operative style rules.
   - Do not invent requirements, broaden scope, or add steps unless required to preserve intent under ambiguity.

5. **Report briefly**
   - Name updated file(s).
   - Summarize the main cleanup.
   - Do not paste large rewrites, alternatives, or detailed reports unless requested.
