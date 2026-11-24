# M<NN> — <title>

- **Spec:** `<SPEC>` (<completes it, or contributes without completing it alone>).
- **Wave / batch:** <n> / <n>. **Batch branch:** `feature/<NAME>-batch-<n>`. **Milestone branch:** `feature/<NAME>-m<NN>`, created from the tip of the batch branch.
- **Base commit:** (given by the orchestrator at launch; copy it here in your first commit). **Suite baseline:** (given by the orchestrator at launch, with known failures and skips; copy it here).
- **Depends on:** <milestones and what it uses from each>. **Used by:** <milestones>.
- **ACs:** <IDs and the part covered>.

## Objective

<one or two sentences>

## Scope

<what it does>

## Out of scope

<what it does not do and which milestone does it>

## Write scope

<exact files; always this file, `<PLAN_DIR>/work/M<NN>-handoff.md` and `<PLAN_DIR>/work/M<NN>-proposals.md`; never a shared document>

## Specification

Ranges of `<SPEC>` at commit `<reference commit>` (heading and lines):

<list>

## Code entry points

<file, function and line at commit `<reference commit>`; if the line moved, find it by name>

## Prior refactors

<none, or which ones and why; each one behavior-preserving>

## Applicable decisions

<IDs from the plan's decisions file, copied with their text>

## Phases

**Table: Phases of M<NN>**

| Phase | Tasks | Status |
|---|---|---|
| 1 | … | ⚪ |

## Tests

<new groups with their cases and next free IDs, tests that change, file and command>

## Documentation

<README, manuals, command help and other documents it updates; or "none">

## Spec updates

<tracking rows, consumer documents, checklist items and deviations it contributes to; the orchestrator applies them>

## Gates

<commands>

## Raw evidence data

Those in the "Raw evidence" section of the plan's rules file, plus: <milestone-specific data>.

## Definition of Done

<verifiable list>

## Progress log

**Table: Progress log of M<NN>**

| Date | Phase | Note |
|---|---|---|
