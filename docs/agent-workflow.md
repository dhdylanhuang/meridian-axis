# Orchestration and multi-agent workflow

Status: ADOPTED working process for humans and authorised agents. Follow the platform's delegation rules; the presence of this document is not a requirement to spawn agents for every task.

## Optimise for less coordination

Prefer one contributor for a small change. Parallelise independent work after its contracts are stable, not two people inventing the same schema. A short correct patch with evidence is better than a broad rewrite followed by several integration cleanups.

The orchestrator owns scope, dependency ordering, integration and acceptance. The architect owns coherent boundaries and significant design decisions, not a separate approval queue for routine implementation. Contributors own bounded changes and honest evidence. A reviewer checks the actual diff and behaviour rather than accepting a handoff's claims.

## Start-of-task protocol

1. Read root AGENTS, current status, active stage and relevant contracts. Inspect actual files and working-tree changes.
2. State the task's requirement IDs, smallest useful outcome and dependent decisions.
3. Assign a clear write set and reviewer. Record which other tasks may run independently.
4. Freeze or explicitly coordinate shared interfaces before dependent agents begin.
5. Use [task brief](templates/task-brief.md). Do not delegate a vague instruction such as “build backend.”

A task brief is coordination, not a new system of user approvals. Work within already-authorised scope; ask only for missing information that materially determines behaviour or an action requiring authorisation.

## Safe work boundaries

| Workstream | Suitable independent ownership after contracts settle | Shared dependency / integration caution |
| --- | --- | --- |
| Broker adapter | HTTP parsing, pagination, mocked fixtures | Normalised event/identity DTO contract |
| CSV/Excel import | Format parsing and source reconciliation | Shared import service, source/economic identity and audit |
| Tax (deferred) | Optional later pure matching module and examples | Not an initial workstream/gate; requires a later owner request |
| Risk | Pure statistical modules and fixtures | Approved return-series/quality contract |
| Correlation | Alignment/matrix/group index modules and tests | Price/calendar/FX semantics and settings |
| Frontend | One feature area using agreed DTO fixtures | No duplicated formulas; API contract versions |
| Security/operations | Sessions, CSRF, backup/restore and runbook | App lifecycle/middleware and schema migrations |

Only one active owner edits each file. Serialise migration numbers, package manifests/lockfiles, app bootstrap, shared DTOs, root AGENTS and status updates. Shared filesystem agents must not use git reset/clean, broad formatting or bulk dependency upgrades to resolve overlap. If isolated worktrees are used later, the orchestrator merges and verifies each integration; do not assume worktree isolation exists.

## Communication and decisions

Report concrete findings and interface changes early. A dependency disagreement should become a concise proposed contract change, affected requirements and test consequences. Use [decision record](templates/decision-record.md) for a material change; routine implementation choices need no ceremony.

Do not rewrite established modules because a new task prefers a different style. Preserve user changes. If an agent notices an unrelated defect, record it and continue the bounded task unless it blocks correctness. No agent may quietly redefine a financial formula to make a test pass.

## Task completion and integration

Contributor delivers: changed files, outcome, exact verification commands/results, requirement coverage, migrations/backfills, known limits and remaining work. Use [handoff](templates/handoff.md). “Should work” is not a test result.

Orchestrator then:

1. Reviews diff and confirms file ownership/scope.
2. Checks contract consistency and security/privacy implications.
3. Runs relevant integration/reconciliation checks after combining changes.
4. Verifies UI states when presentation changed.
5. Updates stage evidence/status and unresolved decisions.
6. Reports what actually works, what remains unavailable and next task.

Do not claim the whole stage because a delegated component passes alone. No commits, pushes or deployments unless authorised by the owner. A local handoff does not require a commit.

## Context preservation

Authoritative financial definitions live in their domain documents; task notes link to them. Avoid copying whole specifications into every agent prompt. Give the agent its objective, constraints, paths and relevant anchors. Preserve original source evidence separately from proposed decisions and implementation state.

At a long-running handoff, update status with completed requirements, exact verification and next bounded task. Include unfinished edits and active ownership so another agent does not duplicate work. Do not record sensitive environment values, raw credentials or unnecessary account responses.

## Definition of done

A task is done when its behaviour meets the agreed acceptance criteria, relevant checks pass, changed contracts/status are accurate, no unrelated work was overwritten and the handoff identifies material limits. Documentation-only work is complete when requirements, links, status and evidence are internally consistent; it does not require inventing tests or application files.
