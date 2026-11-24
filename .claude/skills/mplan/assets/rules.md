# Subagent rules — <NAME>

**Limits:** <the project's, or overrides>.

## Branches and worktrees

- Milestone branch: `feature/<NAME>-m<NN>`, created from the tip of its batch branch, never from `<BASE>`.
- Worktree: `<path outside the repository>`, one per active milestone, reset to the batch tip.
- The subagent does not merge, push or open PRs.

## Shared documents

Written only by the orchestrator; the subagent proposes changes in `work/M<NN>-proposals.md`:

- <master plan, this file, traceability, decisions, log, `evidence/`>
- `<SPEC>`
- <other project documents with a single writer>

## Log directory

`<path outside every checkout or ignored by git>`

## Command forms

<per shell: full suite with output redirected to a log, exit code, summary line and failing test lines; one test group alone; coverage; whitespace check and diff summary against the batch base>

## Raw evidence

Delivered by the subagent in its final message and in `work/M<NN>-proposals.md`:

- Command and summary line of the full suite, with the commit.
- Command and summary line of each milestone group run alone.
- Goldens created or changed and why, or "none".
- New tests with their ID and the AC they cover.
- Output of `git diff --check` and `git diff --stat` against the batch base.
- Coverage of the touched modules.
- Risks, accepted debt, decisions applied and pending items.

## Redaction

<what evidence and copied logs never contain>

## Tests

<framework, naming, isolation and platform conventions of the existing suite>
