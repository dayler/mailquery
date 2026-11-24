---
name: mplan
description: Write the implementation plan for a specification file (change unit, requirement, PRD section or any document stating what to build) - master plan, one self-contained file per milestone, execution waves, integration batches, AC traceability and evidence protocol, ready for subagents - and validate a written plan with an independent reviewer (AC coverage, test cases, contradictions, open questions, impossible or blocking tasks), fixing what it finds - record the owner's approval - and implement a validated and approved plan (worktrees, per-test fix loop, single pull request, independent verification). Writing and checking a plan never change code, tests or product documentation. Use whenever the user asks to plan, prepare or break down the implementation of a spec or change unit, to validate, review or check a plan, or to implement or execute a written plan, even if they do not say "plan".
---

# mplan: implementation plan

- `/mplan <spec-file> [plan-dir]`: write the implementation plan for a specification (the rest of this file).
- `/mplan --check [plan-file-or-dir] [--review-rounds N] [--hitl on|off]`: validate a written plan. Read `references/check.md` and follow it instead of the planning steps below.
- `/mplan --approve [plan-file-or-dir]`: record the owner's approval of a validated plan. Read the "Approval" section of `references/check.md`.
- `/mplan --implement [plan-file-or-dir] [--merge on|off] [--test-retries N] [--review-rounds N] [--hitl on|off]`: implement a validated and approved plan. Read `references/implement.md` and follow it instead of the planning steps below.
- `/mplan --help` (also `-h` or `help`): print the help text below, in the user's language, and do nothing else.

Writing and checking a plan only plan: no code, test or product documentation changes. Only `--implement` changes them.

## Help text

```
mplan: implementation plans for a specification

/mplan <spec-file> [plan-dir]
    Write the plan: master plan, one brief per milestone, waves, batches,
    traceability and rules for subagents. Plans only; changes no code.
    plan-dir   where to write it (default: docs/plan/<spec-name>/)

/mplan --check [plan-file-or-dir] [--review-rounds N] [--hitl on|off]
    Review a written plan with an independent reviewer, fix the issues and
    leave it ready or blocked.
    plan       default: the plan of this conversation, or the only one found
    --review-rounds N
               re-validations after the first review, run only while
               blocking issues remain (default 2)
    --hitl     on: ask the user about open questions (default)
               off: write them to "Unresolved questions" in the master plan

/mplan --approve [plan-file-or-dir]
    Record your approval of a plan whose check verdict is ready. Only you
    can give it; a later check that changes the plan clears it.

/mplan --implement [plan-file-or-dir] [--merge on|off]
                   [--test-retries N] [--review-rounds N] [--hitl on|off]
    Implement a plan that is ready and approved: milestones in parallel
    git worktrees, tests run one by one and fixed locally before any push,
    one pull request, then an independent review of the implementation.
    Never touches main/master; leaves no merged branch behind.
    --merge    on: finish by merging the pull request into the integration
               branch (default); off: leave the pull request open
    --test-retries N
               fix-and-rerun attempts for one failing test (default 5)
    --review-rounds N
               re-verifications after the first review, run only while
               blocking issues remain (default 2)
    --hitl     as in --check

/mplan --help | -h
    Show this text.
```

## Parameters

- `SPEC`: first argument, or the specification file the user named. Ask for it if missing.
- `NAME`: `SPEC` file name without extension.
- `PLAN_DIR`: second argument; otherwise the project's plan location for `NAME`; otherwise `docs/plan/<NAME>/`. If it already holds a plan, ask before overwriting it.
- `BASE`: the branch the project integrates features into (project instructions; otherwise the default branch).
- `UNIT_BRANCH`: `feature/<NAME>`, created from `BASE`.

"AC" means an acceptance criterion of `SPEC`. If `SPEC` has no identifiable ACs, derive verifiable ones, give them IDs and record that as an open decision.

## Precedence

Project instructions (`CLAUDE.md` and what it references) govern plan layout, file split, file names, delegation rules, limits, language and formatting. When they prescribe a different file split, put the content required here in those files instead of duplicating it. Write the plan in the language the project uses for plan documents, otherwise in the language of `SPEC`.

## Templates

`assets/` holds the skeletons: `master-plan.md`, `milestone.md`, `rules.md` (subagent rules) and `companions.md` (traceability, decisions, execution log, evidence). Look first for the project's own templates (in the parent directory of `PLAN_DIR` or named by its instructions) and use each one found instead of the bundled one, adding any section this skill requires and the template lacks. Translate bundled headings to the plan's language and drop sections that do not apply. `MASTER-PLAN.md` and `M<NN>-<slug>.md` are fixed file names; companion files take the names in `master-plan.md`, translated to the plan's language, and every reference between plan files uses the names actually written.

## Constraints

- No rewrite of the product. Refactors that ease the implementation may be planned; each one is justified, narrowly scoped and behavior-preserving.
- No tags, releases or merges to the main branch unless the user orders it. The package version changes only as `SPEC` says.

## Before writing

1. Read `SPEC` whole: ACs, decisions and every tracking section it carries (reconciliation table, consumer documents, checklist or equivalents).
2. Check that `SPEC` is ready to implement under the project's rules (approved, committed, final IDs, no open questions). If it is not, plan anyway, record it as an open decision and mark the preparation phase 🔴 with the reason.
3. Review the code, the test suite (framework, layout, conventions, fixtures, how it runs), the CI workflow, the README, user manuals and command help texts.
4. Check that the baseline has unit tests and a suite that runs with one command; tests for the new ACs follow that scheme. If either is missing, or the infrastructure cannot test some kind of AC (for example, it depends on a real external system), stop and ask the user before planning tests: state what you found and the options, such as a preliminary milestone that adds the infrastructure.

## Master plan

`PLAN_DIR/MASTER-PLAN.md`. It coordinates and monitors milestones. The master plan and its companion files contain:

- Milestone table: status light, dependencies, ACs covered, link to the milestone file.
- Mermaid dependency graph and execution waves stating which milestones can run in parallel in subagents.
- File ownership per milestone.
- The master plan's own phases (for example preparation/refactor, implementation, integration, documentation, closing), each with a status light.
- Traceability matrix: AC → milestone → test(s) → status.
- Risks and open decisions. An ambiguous or untestable AC is an open decision that does not block the rest. Human-in-the-loop answers are recorded here.
- Subagent launch protocol: context received, deliverables, how status is reported, how status lights are updated.
- Batch protocol (below): batch table, integration budget and the integration, CI and evidence rules.
- Execution log, filled when each milestone and batch closes.
- "Validation" and "Unresolved questions" sections, filled by `/mplan --check` and `/mplan --implement`. No milestone is launched unless the plan verdict is ready, there are no unresolved questions and the owner approved the plan; the launch protocol states it.

## Milestone files

`PLAN_DIR/M<NN>-<slug>.md`, one per milestone, built from the milestone template and executable by a subagent that has read only that file and the rules file. Beyond what the template shows:

- Dependencies between milestones are allowed when necessary and always declared.
- No file is owned by two milestones of the same wave.
- Tests for each AC use the existing suite's framework, layout and conventions, with next free IDs and the command that runs them.
- Documentation updates cover README, user manuals, command help and any other affected documentation except the requirements document `SPEC` reconciles into.
- `SPEC` updates and raw evidence data are handed to the orchestrator as proposals; the subagent does not write them into shared documents.

## Batch protocol

Waves decide execution order and parallelism; batches decide how work is integrated.

1. **Batches.** Group milestones in batches of 3-4 (1 only when strictly necessary), ordered by dependency and area. Each batch has an integration branch created from `UNIT_BRANCH` and merged back with `--no-ff` when it closes. A batch opens only after the previous one is integrated.
2. **Branches and worktrees.** A milestone branch starts from the tip of its batch branch, never from `BASE`. One reusable worktree per active milestone, reset to the batch tip; none per attempt. Parallel milestones of a wave each use an isolated worktree and disjoint write scopes; overlapping files force sequential execution.
3. **Milestone integration.** When the milestone's local gate is green, the orchestrator merges it into the batch branch with `--no-ff`. No per-milestone PR, no waiting for CI. A milestone does not close with a red local suite, documentation debt or missing evidence.
4. **Single PR.** One PR from `UNIT_BRANCH` to `BASE`, updated when each batch closes. Fixes are pushed to the same PR. It merges only with the full matrix green.
5. **CI only on the PR.** The full matrix runs on the PR with `concurrency: cancel-in-progress` and a `timeout-minutes` fitted to the suite; pushes to milestone or batch branches do not trigger it. State the expected jobs and runs and compare them with a PR-per-milestone scenario. If the existing workflow already behaves this way, say so and plan no change.
6. **Evidence.** `PLAN_DIR/evidence/M<NN>.md`, written by the orchestrator from the subagent's raw data, with the content of the evidence skeleton. Evidence plus the milestone commits replace the per-milestone PR and CI.
7. **Gates.**
   - Milestone: local suite with no new failures against the baseline, milestone cases green alone, evidence written, status lights and `SPEC` tracking sections updated and consistent.
   - Batch: full matrix green on the PR, cumulative diff inside the write scopes, `--no-ff` integration, run URL in the execution log.
   - Phase: every AC with evidence, documentation free of stale references, read-only gates and host smoke tests green or skipped with a reason, `SPEC` tracking sections updated.
8. **Status ownership.** Only the orchestrator writes the master plan and `SPEC`. The subagent updates the phase lights of its own milestone file and proposes the transition; the orchestrator syncs the milestone table, traceability matrix and execution log when each milestone and batch closes.
9. **Defects and gaps.** A defect found after closing returns the milestone to 🟡 and is logged. Contradictions or gaps go back to the orchestrator before any improvisation; the HITL answer is recorded in the plan.

## Status lights

Define the legend once in the master plan and use it unchanged everywhere: ⚪ pending, 🟡 in progress, 🟢 done, 🔴 blocked. The protocol states who updates each light and when. At the end of this session every light is ⚪, except those blocked by a pending question or an unmet precondition, which are 🔴 with the reason.

## Delivery

Write the files in `PLAN_DIR`, then report:

- Milestones and their waves.
- Batch table and integration budget: PRs and matrix runs expected versus a PR per milestone.
- Proposed refactors.
- Questions pending the user's decision, if any.
- That the plan is not validated or approved yet, and the commands that check, approve and implement it.
