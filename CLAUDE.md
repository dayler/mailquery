# Repository rules

## Language

**Everything in the repository is written in English.** This covers source code, comments and docstrings, CLI help and any other user-facing text, configuration files and their documentation, example configuration files, `CLAUDE.md`, skills, scripts and workflows.

Exceptions:

- **README:** always kept in both English (`README.md`) and Spanish (`README.es.md`). Both files carry the same content; a change to one is applied to the other in the same change.
- **`docs/`:** may be written in Spanish for now.

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

**Only exception:** automated tests (`tests/`) may cite requirement IDs from `docs/PRD.md` and test case IDs defined in `docs/TEST-CATALOG.md`, for traceability. They never cite plans, milestones or other planning IDs.

Example:

```python
# Bad:  Row 5 of PRD §12.11 (M08, AC-15, JIRA-123): only a driver that can materialize attachments may continue.
# Good: Only a driver that can materialize attachments may continue.
```

## Plans and permanent documents

Implementation plans, milestones, task lists and their evidence are temporary. They live only in `docs/plan/` and are deleted when the work is done.

Nothing outside `docs/plan/` cites them: not the code, not the tests, not `docs/` (PRD, interfaces, test catalog, roadmap, backlogs, known defects), not the READMEs. Permanent documents describe the product as it is. Anything a plan produces that must outlive it is moved into the permanent document it belongs to before the plan is deleted:

- Test case definitions go to `docs/TEST-CATALOG.md`.
- Open defects go to `docs/KNOWN-DEFECTS.md`; performance debt goes to `docs/PERFORMANCE-BACKLOG.md`.
- Pending product work goes to `docs/ROADMAP.md`.
- Product rules go to `docs/PRD.md`.

`docs/archive/` holds historical records and is the only other place that may mention past plans.
