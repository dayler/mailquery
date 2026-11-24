Review an implementation plan against its specification. You are an independent reviewer: judge only what the files say. Do not edit any file.

- Plan directory: `<PLAN_DIR>`
- Specification: `<SPEC>`

Read the specification whole, every file of the plan, and the project instructions. Open the code, tests and documents the plan cites to confirm they exist and say what the plan claims.

## Checks

1. **AC coverage.** Every acceptance criterion of the specification, and every separately verifiable part of it, is assigned to a milestone. Every condition of the requirement that changes behavior is covered by some milestone's scope.
2. **Test cases.** Every AC part has test cases that would fail if that part were not implemented, including the boundary and negative values the specification names. Expected results match the specification literally where it fixes text or numbers. Test IDs are unique and free, tests sit in files the milestone owns, and the command that runs them works with the existing suite.
3. **Contradictions.** Between the plan and the specification, between the plan and the project instructions, and between plan files: milestone table, dependency graph, waves, file ownership, traceability, briefs and decisions.
4. **Executability.** Each milestone can be done by an agent that reads only its brief and the rules file: its write scope contains every file its tasks and tests need; cited files, functions and line ranges exist; no file is owned by two milestones of the same wave; dependencies have no cycle and are integrated before they are used; gates are runnable commands.
5. **Impossible or blocking tasks.** Tasks that cannot be done as written, that depend on something outside the plan, or that wait on an undecided question.
6. **Open questions.** Anything the plan leaves undecided, and anything the specification leaves ambiguous that the plan resolves without recording a decision.
7. **Leftovers.** Work the specification requires that no milestone or orchestrator phase owns: documents to update, tracking sections, manual checks.

## Output

Your final message, and nothing else:

**Table: AC coverage**

| AC | Part | Milestone | Tests | Verdict |
|---|---|---|---|---|

Verdict is `covered`, `partial` or `missing`.

Then one entry per issue, most severe first:

- **ID:** `V-01`, `V-02`, …
- **Severity:** `blocking` (prevents implementing the plan correctly), `non-blocking`, or `question` (needs a decision the files do not give).
- **Check:** number from the list above.
- **Where:** file and heading or line.
- **Evidence:** what the file says and what it conflicts with or lacks.
- **Suggested fix:** concrete change, or the options if it is a question.

End with one line: `blocking: <n>, non-blocking: <n>, questions: <n>`. Report only what you verified in the files; if there are no issues, say so.
