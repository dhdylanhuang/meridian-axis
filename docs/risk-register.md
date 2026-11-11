# Project risk register

Status: planning risks, not evidence that failures have occurred in an implemented app. Review at each stage gate; close only with concrete verification.

| ID | Risk / consequence | Priority | Mitigation / owner workstream | Gate evidence |
| --- | --- | --- | --- | --- |
| RSK01 | CSV assumed to contain execution IDs or grouping fields it lacks | Critical | Inspect actual exports; field matrix and fixtures; data integration | Stage 0 source contracts |
| RSK02 | API and CSV duplicate the same economic event | Critical | Event-kind identities, aliases and bidirectional import-order tests | Stage 1 idempotent replay |
| RSK03 | History/opening balances incomplete but tax/returns appear complete | Critical | Coverage and provisional states; explicit opening evidence | Stages 1/3 unsupported paths tested |
| RSK04 | Raw Total rows, broker snapshots or reinvested dividends double counted | Critical | Source/control separation, NAV/cash/quantity reconciliation | Stage 1/2 invariants |
| RSK05 | Incorrect listing, currency unit or FX direction scales value 100× | Critical | Verified symbol mapping, quote-unit metadata, conversion fixtures | Stage 2 mapping/GBP controls |
| RSK06 | Intraday/adjusted/provisional closes contaminate daily risk | High | Separate bases/selections; explicit adapter options; input eligibility | Stage 2/4 rejection tests |
| RSK07 | Future tax extension: following acquisitions alter earlier tax years | Deferred | Retain matching design; do not implement initially | Optional tax-phase tests |
| RSK08 | Provider limitations prevent promised minute-fresh quotes | High | Separate fetch/quote age and capability contract; alternative adapter only when justified | Stage 2 disclosure/last-good tests |
| RSK09 | Different pairwise samples create invalid covariance/eigenvalues | High | Common panel and PSD checks; exclusions/coverage visible | Stage 4 known/singular/missing-data cases |
| RSK10 | Current weights presented as historical realised group performance | High | Label hypothetical constant-weight indices; historical weights for attribution | Stage 4/5 basis checks |
| RSK11 | Spreadsheet defects become app acceptance targets | High | Preserve facts and legacy fixtures; independent correct formulas | Stage 1/3 baseline review |
| RSK12 | Multi-worker scheduler repeats requests/events or locks SQLite | High | One owner, no overlapping jobs, bounded short transactions | Stage 2 reload/restart tests |
| RSK13 | Credentials/portfolio data leak through logs, fixtures or repository | Critical | Environment secrets, redaction, safe evidence, runtime ignore rules | Stage 1/2 redaction and repository review |
| RSK14 | Login/CSRF/security deferred until financial UI is exposed | High | Security gate before usable financial endpoints | Stage 2 negative-path checks |
| RSK15 | Backups exist but cannot restore, or WAL file copied inconsistently | High | Consistent backup API and separate-path restore drill | Stage 1 then Stage 5 recovery |
| RSK16 | Multiple agents redefine contracts or overwrite shared files | High | Bounded write sets, single migration owner, integration review | Every task handoff |
| RSK17 | Scope overwhelms a local-model implementation | High | Small cohesive modules and vertical slices; no extra infrastructure | Stage-sized verified deliveries |
| RSK18 | Static look-through/currency evidence becomes stale or incomplete | Medium | Dated source/coverage, no inferred exposure claims | Stage 4/5 available/unavailable views |
| RSK19 | Retention deletes evidence behind daily closes or alerts | High | Durable selected observations/references before tick deletion | Stage 5 retention/replay tests |
| RSK20 | API beta contract or library defaults drift | High | Verify YAML, schema fixtures, explicit adapter options and versioned dependencies | Stage 0 plus adapter-change review |
| RSK21 | Two full-editor users silently overwrite each other's changes | Medium | Expected revisions, equal permissions and distinct audit/session identities | Stage 2/5 two-session tests |
| RSK22 | Date-only/irregular snapshots become invented month-end history | High | Original labels/date precision and notes retained | Stage 1 history fixture |

Priority reflects potential financial-integrity/privacy impact, not a quantified probability model. A limitation should appear in the UI where it affects results, not only in this register. Do not add unrelated infrastructure to mitigate hypothetical scale; measure before changing the architecture.
