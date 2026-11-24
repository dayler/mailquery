Skeletons of the master plan's companion files and of the evidence file. Each block below is one file.

---

# Traceability — <NAME>

**Table: AC → milestone → tests → status**

| AC | Part | Milestone | Tests | Status |
|---|---|---|---|---|
| … | … | M01 | … | ⚪ |

---

# Decisions, risks and owner answers — <NAME>

## Open decisions

- **D-01 (<blocks phase n | does not block>).** <what is undecided, why, what it holds back>

## Applied decisions

- **D-02.** <decision taken while planning and its reason>

## Risks

- **R-01. <name>.** <risk>. Mitigation: <mitigation>.

## Owner answers

<date, question, answer; or "None yet.">

---

# Execution log — <NAME>

Filled when each milestone and batch closes, and on every relaunch.

**Table: Execution log**

| Date | Milestone or batch | Previous → new status | Suite result | Evidence | HITL / notes |
|---|---|---|---|---|---|

---

# Evidence — M<NN> <title>

Written by the orchestrator from the subagent's raw data.

- **Full suite:** <command, final count, commit>
- **Milestone groups alone:** <command and count per group>
- **Goldens:** <created or updated and why, or "none">
- **New tests:** <IDs and the AC each covers>
- **Diff:** <`git diff --check` and `git diff --stat` against the batch base>
- **Coverage:** <touched modules>
- **Risks, accepted debt, HITL decisions, pending items:** <list or "none">
