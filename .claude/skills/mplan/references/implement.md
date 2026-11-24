# Plan implementation

Implement a validated plan as its orchestrator, verify the result with an independent reviewer and finish at the final pull request. The plan's own files (master plan, rules file, briefs) and the project instructions govern how; this file adds what they do not say and wins only on the rules marked "always".

## Parameters

- **Plan:** a plan file or its directory, resolved as in `references/check.md`. `PLAN_DIR`, `SPEC`, `BASE` and `UNIT_BRANCH` are the ones the master plan names.
- **`--merge on|off`:** whether the work ends by merging the final pull request into `BASE`. Default `on`.
- **`--test-retries N`:** fix-and-rerun attempts for one failing test. Default 5.
- **`--review-rounds N`:** re-verifications of the implementation after the first review. Default 2.
- **`--hitl on|off`:** whether to ask the user. Default `on`.

Arguments win over defaults stated in the project instructions, which win over the defaults above.

## Preconditions

Stop and report, changing nothing, unless all hold:

- The master plan's plan verdict is ready and "Unresolved questions" is empty. If the plan was never checked, say so and name `/mplan --check`.
- The master plan records the owner's approval. If it does not, say so and name `/mplan --approve`; never approve it yourself.
- `SPEC` is ready to implement under the project's rules (for example, approved).
- The working tree of `BASE` is clean and up to date with its remote.

## Always

- Never commit, merge or push to `main` or `master`, with any flag or instruction in the plan.
- Nothing is pushed before it passes locally.
- No tags and no releases unless the user orders them.

## Execution

1. **Follow the plan.** Run the phases, waves and batches in the order the master plan gives, with its launch protocol, branch names, gates, evidence and status-light rules. Keep the milestone table, traceability, execution log and `SPEC` tracking sections in step with the work.
2. **Parallelize with worktrees.** Milestones of the same wave with disjoint write scopes run at the same time, one subagent and one git worktree each, outside the repository. Milestones with overlapping files run in sequence.
3. **Test loop (each milestone, locally).** Run the milestone's unit tests and automated test cases one at a time. When one fails, fix it and re-run only that test, up to `test-retries` times, then go on to the next test; a failure never triggers a run of the whole suite. A test still failing after `test-retries` attempts is recorded with its output, the milestone goes 🔴 and the remaining tests still run. The full suite runs once, at the milestone gate, after every test of the milestone passes alone; a regression it shows is fixed with the same loop on the failing test.
4. **Integrate.** Milestone into batch, batch into `UNIT_BRANCH`, and the single pull request from `UNIT_BRANCH` to `BASE`, as the plan's batch protocol says. Push only what passed its local gate. Use the CLI of the project's host (`gh`, `glab` or equivalent).
5. **Blocked work.** A milestone that cannot be finished is marked 🔴 with the reason; milestones that depend on it are not launched; the rest continue. Contradictions or gaps in the plan are questions: with `--hitl on` ask the user and record the answer in the decisions file; with `--hitl off` write them to "Unresolved questions" and treat the affected milestones as blocked.

## Verification

If any milestone ended 🔴, skip the review: the implementation verdict is blocked. Otherwise, when every milestone is 🟢 and the pull request is open, and before any merge:

1. Run the review loop of `references/check.md` (review, triage, fix, questions, re-verify while blocking issues remain, up to `review-rounds`), with `assets/impl-reviewer-brief.md`, its placeholders filled in, as the reviewer's brief. Fixes here may change code, tests and documents on `UNIT_BRANCH`, each one through the test loop above and pushed to the same pull request.
2. Record the implementation verdict, with its date and the reviews run, in the "Validation" section of the master plan and in the execution log: **verified** when the last review has no accepted blocking issue left unfixed and no question is unresolved; **blocked** otherwise.

## Finish

- **Verdict verified:** run the closing steps the project requires on `UNIT_BRANCH` (for example, reconciling the specification into the requirements document) and confirm the full CI matrix is green on the pull request. Then, with `--merge on`, merge the pull request into `BASE` and confirm `BASE` is green; with `--merge off`, leave the pull request open and report its URL.
- **Verdict blocked:** no closing steps and no merge, with any value of `--merge`. Leave the pull request open, if one exists, and report its URL.
- **Cleanup.** No merged branch stays behind, locally or on the remote: delete milestone and batch branches once merged, and `UNIT_BRANCH` once its pull request is merged. Remove every worktree and prune. Check with `git branch --merged` and its remote equivalent. Unmerged branches are kept and listed in the report.

## Report

Shown in the chat when the work ends or stops:

- Implementation verdict, reviews run and the limit.
- Milestones with their final status; batches integrated; pull request URL and state; CI runs used versus the plan's budget.
- Tests that needed fixes, with attempts used; tests still failing, with their output.
- Issues fixed, rejected and still open, blocking first; questions answered and unresolved.
- Branches and worktrees removed; branches kept and why.
- What was not done.
