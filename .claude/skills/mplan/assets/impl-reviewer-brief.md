Review the implementation of a plan against its specification. You are an independent reviewer: judge only what the files, the diff and the commands show. Do not edit, commit or push anything.

- Plan directory: `<PLAN_DIR>`
- Specification: `<SPEC>`
- Implementation branch: `<UNIT_BRANCH>`, compared with `<BASE>`

Read the specification whole, the master plan, the traceability file and the project instructions. Read the diff of the branch against its base by file, not whole. Run the tests you need to confirm a claim, one test or group at a time.

## Checks

1. **AC implemented.** Every acceptance criterion, and every separately verifiable part of it, is implemented as the specification states, including fixed texts, values, ranges and error codes.
2. **AC tested.** Every AC part has a test that exists, runs, passes, and would fail without the implementation. The tests the traceability file names are the ones in the code.
3. **Suite.** The full suite has no failure other than the baseline's known failures and skips. No test was deleted, skipped or weakened to pass.
4. **Scope.** The diff stays inside the plan's write scopes and contains nothing the specification does not require. What "does not change" in the specification did not change.
5. **Documentation.** README, manuals, command help and the other documents the plan lists describe the new behavior and carry no stale text. The specification's tracking sections match what was done.
6. **Plan state.** Status lights, traceability, execution log and evidence files exist and agree with the branch.
7. **Project rules.** The change follows the project instructions (code comments, language, formatting, versioning).
8. **Leftovers.** Merged branches or worktrees left behind, work the specification requires that nobody did, debt not recorded.

## Output

Your final message, and nothing else:

**Table: AC verification**

| AC | Part | Implemented in | Tests | Verdict |
|---|---|---|---|---|

Verdict is `verified`, `partial` or `missing`.

Then one entry per issue, most severe first:

- **ID:** `I-01`, `I-02`, …
- **Severity:** `blocking` (the specification is not correctly implemented or not verified), `non-blocking`, or `question` (needs a decision the files do not give).
- **Check:** number from the list above.
- **Where:** file and line, or command.
- **Evidence:** what you saw and what it conflicts with or lacks.
- **Suggested fix:** concrete change, or the options if it is a question.

End with one line: `blocking: <n>, non-blocking: <n>, questions: <n>`. Report only what you verified; if there are no issues, say so.
