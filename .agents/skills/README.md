# Project development skills

Ponytail complements the existing Graphify setup: Graphify locates relationships;
Ponytail guides implementation and review. Repository policy lives in the root
`AGENTS.md`, which is currently ignored by this repository's `.gitignore`.

## Installed snapshot

- Source: https://github.com/DietrichGebert/ponytail
- Commit: `09c434ab73ca43761c5d8b0c5d341926c2fba710`
- Installed: 2026-10-23
- Skills: `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`
- Upstream skill files are unmodified. Their MIT license is in `PONYTAIL-LICENSE.txt`.
- Installation includes instructions only, with no lifecycle hooks or runtime dependencies.

## Workflow

1. Use Graphify to find the relevant code, then verify the current source and callers.
2. Use Ponytail's `full` level for the smallest complete implementation, preserving
   Design First, Evaluation First, ADRs, architectural boundaries, and required tests.
3. Review non-trivial task changes with `ponytail-review`; use `ponytail-audit` for
   requested module or repository audits and `ponytail-debt` for shortcut reports.
4. Run the appropriate checks and `graphify update .` after code changes.

Codex discovers repository skills from `.agents/skills/`. They are available on
the next turn. Explicit invocation examples:

```text
$ponytail full
$ponytail-review review the evaluation changes
$ponytail-audit audit src/rastin_ai/evaluation
$ponytail-debt
```

Plain-language requests work too. Responses follow the user's language. Reviews
and audits report findings without applying unrelated fixes. A skill-only install
uses instructions for mode selection; it does not provide hook-managed mode state
or the Claude Code band. Changing the default level means updating `AGENTS.md`.

To update, review the upstream diff against the pinned commit before replacing
the skill files, then update the commit recorded here and retain the license.
