# Repository rules

## Language

**Everything in the repository is written in English.** This covers source code, comments and docstrings, CLI help and any other user-facing text, configuration files and their documentation, example configuration files, `CLAUDE.md`, skills, scripts and workflows.

Exceptions:

- **README:** always kept in both English (`README.md`) and Spanish (`README.es.md`). Both files carry the same content; a change to one is applied to the other in the same change.
- **`docs/`:** may be written in Spanish for now.

## Tables and figures

**Every table, image, diagram, chart or other figure carries a title**, in chat answers and in every file or artifact written. The title goes on its own line right above the table or figure: `**Tabla: <title>**` in Spanish documents and `**Table: <title>**` in English ones. A table or figure that is added or modified gets its title in the same change.

## Source code comments

**Every comment and docstring in the source code describes what the code does. It never justifies the code by citing documents, tickets or any other project artifact, and never points the reader to them.**

A comment states behavior, inputs, outputs, invariants or side effects. It does not explain why a document, a ticket or a decision required the code, and it does not point the reader elsewhere.

Forbidden in comments and docstrings:

- Documents and their parts: PRD, specs, plans, roadmaps, threat models, annexes, interface documents, READMEs; section numbers, rows, points and examples of any of them.
- Requirement and decision IDs: functional and non-functional requirements, acceptance criteria, ADRs, change requests, design decisions.
- Planning and tracking: milestones, phases, contracts, plan decisions, test case IDs.
- Tickets and work items: Jira keys, GitHub/GitLab issue and PR numbers, bug IDs, Slack threads, emails, meeting notes, and links to any tracker or external resource.
- Document or spec versions used as a justification.

Scope: `src/`, `scripts/`, `pyproject.toml`, `.github/workflows/` and any other code that is not an automated test.

**Only exception:** automated tests (`tests/`) may cite requirement IDs from the PRD (`docs/prd/`) and test case IDs defined in `docs/tests/`, for traceability. They never cite plans, milestones or other planning IDs.

Example:

```python
# Bad:  Row 5 of PRD §12.11 (M08, AC-15, JIRA-123): only a driver that can materialize attachments may continue.
# Good: Only a driver that can materialize attachments may continue.
```

## Plans and permanent documents

Implementation plans, milestones, task lists and their evidence are temporary. They live only in `docs/plan/`. They are deleted only after the whole plan has been verified (its work, tests and evidence), a human reviewer has reviewed and approved it, and the incremental PRD / specification has been reconciled into the permanent PRD / specification. Until then, `docs/plan/` stays in the repository: deleting it is an explicit final step, never automatic and never a side effect of the implementation finishing.

The PRD lives in `docs/prd/`, one file per section, with `docs/prd/00-indice.md` as its entry point. A change reaches the PRD only through a change document in `docs/changes/`, reconciled unit by unit as the part "Cómo se concilia un cambio" of `docs/prd/00-indice.md` describes. A change document is deleted only on the owner's order, once all its units are reconciled.

Nothing outside `docs/plan/` cites a plan: not code, not tests, not permanent documents, not READMEs. Permanent documents describe the product as it is. Anything a plan produces that must outlive it is moved, before deletion, into the permanent document that owns it. Historical records are the only other place that may mention past plans, and only as events: a historical record may name a plan but never cite it as a requirement or a justification.

## Plan structure and delegated implementation

This section applies to every agent that writes or executes a plan in `docs/plan/` that delegates implementation to subagents. The protocol file, brief template, briefs, evidence, proposals and handoff notes live in `docs/plan/` and are deleted with the plan.

**Limits**

Rules reference these names. The plan's protocol file may override any of them in one block at its start; briefs may not.

| Limit | Default | Meaning |
|---|---|---|
| `whole-read-lines` | 300 | Longest file, in lines, read whole |
| `range-lines` | 200 | Longest range, in lines, read in one call |
| `output-lines` | 60 | Lines of long command output that enter the conversation |
| `final-message-lines` | 60 | Lines of a subagent's final message |
| `tool-call-budget` | 100 | Tool calls of a subagent session, every call included, before it hands off |
| `relaunch-split` | 2 | Relaunches of a milestone before its remaining work is split or its brief revised; a split part only gets a revised brief |
| `relaunch-stop` | 3 | Relaunches of a milestone or split part before relaunching it stops |

**Plan documents**

- A plan never tells a subagent to read the master plan or a whole specification, catalog or interface document.
- Master plan: only milestones, dependencies, file ownership and the launch protocol. Traceability, owner answers, decisions, risks and the execution log go in separate files.
- Protocol file: one file with every subagent rule not in `CLAUDE.md` (branches and worktrees, evidence checklist, redaction, per-shell command and log redirection forms, the plan's log directory, the list of shared documents, limit overrides).
- Brief: one per milestone or split part, built from the plan's template, with only what that work needs: objective; write scope (exact files, or directories and globs for new tests and fixtures; always the evidence, proposal and handoff files; never a shared document); specification, catalog and interface ranges (heading plus line range at the baseline commit); next free test IDs; code entry points (file and function); baseline commit with known failures and skips; applicable decisions and owner answers; gate commands; log directory.
- The protocol file and briefs are concise: no background, history, examples or text already in `CLAUDE.md`; a brief also omits what the protocol file or the specification says.
- The launch protocol hands each subagent its brief and the protocol file. The subagent reads `CLAUDE.md` (unless the harness already loaded it), the protocol file and its brief whole, regardless of length, then the ranges the brief cites; anything else under the reading rule.

**Reading and output (every agent bound by this section)**

- A file of up to `whole-read-lines` lines may be read whole; when its length is unknown, the first read is a range. Longer files are located by search and read in ranges of at most `range-lines`; further consecutive ranges are read only while the task needs the rest of the same section or function. Searches are bounded by path, glob or result count.
- Potentially long command output (test suites, coverage, builds, full diffs, unbounded shell searches) goes to a log in the plan's log directory (for a subagent, the one in its brief), which is outside every checkout or ignored by git. At most `output-lines` lines enter the conversation: for tests, the summary line and one line per failing test (with more failures than fit, their count and the first ones); otherwise, the last lines. Details are read from the log in ranges. A gate passes when its exit code is zero or when its summary lists no failure other than the known failures and skips recorded in the brief; gate results come from the exit code or the summary line, never from truncated output. Short output, such as a single test case, `git status` or `git diff --stat`, enters directly; runs of more than one test module are never verbose (`-v`) in the conversation.
- Logs are scratch: the agent copies into the evidence file what the evidence needs.

**Subagent**

- To hand off, the subagent finishes the current edit, writes a short handoff note (done, pending, next command, open failures), commits everything (work-in-progress commits with failing tests are allowed on the feature branch) and returns.
- When it needs to write outside its write scope, it hands off and names the file and the required change in its final message. Changes to a shared document are proposals, never out-of-scope returns.
- It commits its evidence and its proposals for shared documents on its feature branch.
- After about `tool-call-budget` tool calls it starts no new work and hands off. The budget does not apply when only the final gate run and the evidence remain; a failing final gate is handed off.
- Its final message is an index of at most `final-message-lines` lines: proposed status, commit range and count, suite counts, coverage of touched modules, and the paths of its evidence, proposal and handoff files; a field that does not apply yet is stated as "not run". A blocking contradiction is summarized; its details and anything that does not fit go to the evidence file. The message never pastes those files.

**Orchestrator**

- The orchestrator is the only writer of shared documents and applies the proposals at integration.
- It verifies subagent work with the gates, `git diff --stat` and targeted searches.
- After an out-of-scope return it makes the change itself, widens the scope or chooses an alternative, and records the resolution in the brief; it never relaunches with a brief that does not reflect it.
- It relaunches in the same worktree and branch with the current brief plus the handoff note. Every launched subagent relocates stale line ranges by heading or function search. Split parts run one after another in that worktree.
- It counts every relaunch, whatever its cause, and records it in the execution log. After `relaunch-split` relaunches of a milestone it splits the remaining work or revises the brief. A split part's first launch is not a relaunch, its relaunches count only toward that part, and it is never split again. After `relaunch-stop` relaunches of a milestone or split part, or after a budget handoff with no change outside its handoff note, it stops relaunching that milestone or part: it finishes that work itself, or marks it blocked with the reason and reports it to the owner. Parts that depend on a blocked milestone or part are marked blocked with the same reason and reported; they are not launched. Remaining parts that do not depend on it continue.
