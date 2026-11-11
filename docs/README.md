# Documentation guide

Baseline: **11 November 2026**. Implementation is authorised; see current status for verified delivery.

This is the working specification for Great Dyke Meridian. Its purpose is to let an unfamiliar contributor implement a bounded task without reconstructing a conversation or inventing financial definitions.

## Reading routes

**Owner:** product requirements → workbook baseline → development stages → decisions and questions → status and handoff.

**Orchestrator:** current status → agent workflow → requirements → stage gates → architecture → relevant contracts → testing and acceptance.

**Backend/data agent:** architecture → data model → Trading 212 integration → imports and reconciliation → relevant calculations → security and operations.

**Analytics agent:** workbook baseline → calculation contracts → correlation → tax or attribution requirements → testing and acceptance.

**Frontend agent:** API and UI → product requirements → calculation availability states → alerts → security and operations. The browser must not create a parallel financial calculation engine.

## Authoritative homes

| Document | Owns |
| --- | --- |
| [Product requirements](product-requirements.md) | Scope, requirement IDs, exclusions and changes to the original brief |
| [Architecture](architecture.md) | Component responsibilities, dependency rules, runtime and proposed source tree |
| [Data model](data-model.md) | Identity, persistence, provenance, constraints and migrations |
| [Stage 0 verification](stage-0-source-verification.md) | Direct YAML/JSON comparison, field coverage and remaining source gates |
| [Local development](local-development.md) | Verified installation, migration, liveness and backup/restore commands |
| [Free hosting](hosting-options.md) | Persistent free compute and private access options, provider limits and owner dependencies |
| [Trading 212 integration](trading212-integration.md) | Provider coverage, authentication, pagination, identities and reconciliation |
| [Imports and reconciliation](imports-and-reconciliation.md) | File/sync lifecycle, atomicity, corrections and source precedence |
| [Workbook baseline](workbook-baseline.md) | Public-safe workbook structure, methods and defects; exact values stay local |
| [CSV contract](csv-contract.md) | Verified snapshot headers, ticker/group semantics, missing tokens and limits |
| [Calculation contracts](calculation-contracts.md) | Valuation, returns, risk, projections, attribution and edge cases |
| [Correlation](correlation.md) | Sampling, matrices, shrinkage, weighting, clustering and diagnostics |
| [Tax](tax.md) | Deferred matching scope and synthetic worked examples; not an initial gate |
| [Market data and polling](market-data-and-polling.md) | Price/FX semantics, scheduling, freshness and closing-data reconciliation |
| [API and UI](api-and-ui.md) | Application interface proposals, nine tabs, interaction and error states |
| [Alerts](alerts.md) | Rules, transitions, acknowledgement, re-arming and evaluation basis |
| [Security and operations](security-and-operations.md) | Access, secrets, configuration, backups, recovery and remote-access boundary |
| [Development stages](development-stages.md) | Ordered deliverables and exit gates |
| [Testing and acceptance](testing-and-acceptance.md) | Test evidence, fixture requirements and acceptance matrix |
| [Agent workflow](agent-workflow.md) | Task boundaries, ownership, parallel work, review and handoff |
| [Decisions and questions](decisions-and-questions.md) | Design status, owner questions and defaults awaiting confirmation |
| [Risk register](risk-register.md) | Material project risks and mitigations |
| [Source register](source-register.md) | Primary references, verification dates and evidence limitations |
| [Status and handoff](status-and-handoff.md) | Actual progress, outstanding work and next task |
| [Original brief](context/original-brief.md) | Historical brief with personal workbook filename redacted; current decisions supersede it |
| [Integration amendment](context/integration-amendment.md) | Owner's API-primary and polling revision, retained as historical source |

Templates: [task brief](templates/task-brief.md), [handoff](templates/handoff.md), [decision record](templates/decision-record.md).

## Status vocabulary

- **CONFIRMED:** explicitly requested or clarified by the owner.
- **VERIFIED:** observed in the workbook, repository or cited provider contract. It may still be dated or limited.
- **ADOPTED:** an engineering decision selected in this plan to make implementation coherent. It is not an assertion of owner preference and can be revised with evidence.
- **PROPOSED:** a recommendation that still needs a decision before dependent behaviour ships.
- **OPEN:** unresolved information or choice. Identify the tasks it actually blocks.
- **DEFERRED:** intentionally outside the current release or dependent on unavailable evidence; remains visible.

These labels describe evidence and decisions. Implementation has separate states: not started, in progress, verified and accepted. No feature is implemented merely because its specification is ADOPTED.

Requirement IDs such as `D01` belong to the product matrix. Owner questions use `Q01`; confirmed decisions use `DC01`, engineering decisions `DE01`, risks `RSK01` and sources `SRC01`. Keep these namespaces distinct in task briefs and handoffs.

## Change policy

Change a contract at its authoritative home, then update its consumers and tests. Use stable requirement and question IDs. Significant changes need a decision record with rationale and affected requirements. Do not copy large definitions across documents. A new document earns its place only when it owns a distinct decision or workflow.

When a source changes, retain the prior verification date and record what was rechecked. Do not silently replace historical workbook values with current broker values.
