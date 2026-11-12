# Product requirements

Status: CONFIRMED scope with explicitly identified ADOPTED interpretations. Baseline: 11 November 2026. See [decisions](decisions-and-questions.md) for unresolved choices.

## Purpose and user model

Great Dyke Meridian replaces a manually maintained Excel portfolio tracker with a private, dense monitoring application. AXIS is the summary view. The owner and a partner use distinct logins with equal full editing rights to access one owner's single Trading 212 Stocks and Shares ISA. Do not build separate roles, beneficial owners, investment portfolios or tenant billing. The planning goal is £100,000 by 2030; the original 30 April 2030 target date remains the active date unless revised.

Optimise for readable financial tables, dependable imports, explainable calculations and visible data quality. The desired visual direction is a dark Koyfin/Bloomberg-style terminal. There is no marketing site, trade execution or autonomous investment advice.

## Requirements and destinations

| ID | Requirement | Contract / delivery gate |
| --- | --- | --- |
| P01 | One Trading 212 ISA; two equal full-editor logins; localhost first | Security; Stage 2 |
| P02 | Cloudflare + Supabase PostgreSQL hosted target; retain Python/FastAPI/SQLAlchemy where runtime qualification passes; React, Vite, Tailwind/ECharts; SQLite local tooling only | Owner-approved platform amendment; architecture / Stage 0H |
| P03 | GBP values, performance and risk; retain FX used | Data model and calculations; Stage 2 |
| D01 | Trading 212 Public API v0 is primary; Demo default, explicit Live setting; HTTP Basic key/secret | Integration; Stage 0/1 |
| D02 | Read account summary, positions, historical fills/orders, dividends and cash events; cursor pagination and bounded retries | Integration; Stage 1 |
| D03 | Scheduled and manual sync, logged and idempotent across overlapping history | Imports; Stage 1/2 |
| D04 | CSV fallback and enrichment; UTF-8-sig; verified headers; Total rows excluded; dividends-gained semantics | Imports; Stage 0/1 |
| D05 | Excel baseline provenance `excel_migration`; reconcile source totals within £0.01 | Workbook baseline; Stage 1 |
| D06 | Editable ticker mapping; unmapped instruments produce warnings without destroying evidence | Data model; Stage 1/2 |
| G01 | One current group per listing; verified export group context, conflict review and Unassigned warnings; Slice is ticker in the inspected snapshot | Imports and data model; Stage 1 |
| G02 | Rename, merge and reassign with audit; preserve raw labels and manual overrides | Imports; Stage 1/2 |
| G03 | Group exposure, aggregation, correlation, attribution and risk | Calculations and correlation; Stages 2/4/5 |
| C01 | Derived quantity, costs, value, unrealised/realised PnL, dividends and return | Calculations and tax; Stages 2/3 |
| C02 | Holding and group weights; configurable holding RAG | Calculations and UI; Stage 2/5 |
| C03 | Daily, MTD, YTD, since-inception and time-weighted performance with explicit flows | Calculations; Stage 3 |
| T01 | DEFERRED: HMRC same-day, following-30-day and Section 104 matching; worked tests; transaction-date GBP costs/proceeds | Tax; optional later phase |
| T02 | DEFERRED: UK taxable-gain summaries and allowance settings | Tax; optional later phase, no balance trigger |
| R01 | Sharpe, Sortino, drawdown dates, historical VaR 95/99 and Expected Shortfall | Calculations; Stage 4 |
| R02 | Beta/Jensen alpha against VUAG and IWDA proxies, R-squared and observation count | Calculations; Stage 4 |
| R03 | Top-5/10, HHI and effective holdings, overall and within groups | Calculations; Stage 4 |
| R04 | Evidence-based ETF/stock overlap and currency exposures, including underlying revenue currency where available | Calculations; Stage 4/5 |
| R05 | Market -10/-20%, tech, GBP +/-5%, custom holding/group stress scenarios | Calculations; Stage 5 |
| F01 | £100,000 portfolio goal by 30 April 2030; editable pessimistic/base/optimistic scenarios and monthly contributions | Calculations; Stage 3; Q05 |
| F02 | Preserve and reconcile legacy Excel projection behaviour separately from active model | Workbook and calculations; Stage 3 |
| X01 | Holding/group/currency contribution, market/residual split, trade statistics; tax summary deferred | Calculations; Stage 5; Q10 |
| K01 | Dedicated GBP log-return correlation module; daily and weekly; 30/90/252 trading-day horizons | Correlation; Stage 4 |
| K02 | Alignment, bounded holiday fill, minimum overlap, counts and reliability | Correlation; Stage 4 |
| K03 | Raw and Ledoit-Wolf covariance/correlation; PSD checks and visible difference | Correlation; Stage 4 |
| K04 | Holding matrix, group matrix, rolling pair drilldown and benchmark views | Correlation and UI; Stage 4/5 |
| K05 | Average pair correlation, eigenvalue effective bets, diversification ratio and high-correlation pairs | Correlation; Stage 4 |
| L01 | Held instruments, benchmarks and needed FX only; 60-second requested quote interval during relevant sessions | Polling; Stage 2/5 |
| L02 | Exchange calendars, holidays, half-days, background execution and graceful shutdown | Polling; Stage 2 |
| L03 | Intraday observations, original/GBP values, 90-day configurable retention; daily data indefinite | Polling and data model; Stage 2/5 |
| L04 | Source, fetch/quote times, delay/stale state; last-good values on failure; SSE updates | Polling and UI; Stage 2/5 |
| L05 | Provisional session-close candidate, daily-source reconciliation and >0.5% discrepancy log | Polling; Stage 2/5 |
| A01 | Configurable alerts; each group drawdown >=10%; portfolio rolling two-trading-day peak-to-trough drawdown >=2%; other move/weight/VaR/data/import/thesis/grouping rules retained | Alerts; Stage 5 |
| A02 | Correlation alert rules, including held-pair 90-day threshold default 0.85 | Alerts and correlation; Stage 4/5 |
| A03 | Intraday valuation alerts, durable crossing state, re-arm after recovery and acknowledgement | Alerts; Stage 5 |
| U01 | All nine tabs: AXIS, GROUPS, EXPOSURES, CORRELATION, HOLDINGS, RISK, TRANSACTIONS, ATTRIBUTION, HISTORY | API/UI; Stage 2 then Stage 5 |
| U02 | Dated instrument/group thesis notes, optional review dates | Data model and UI; Stage 5 |
| S01 | Hashed passwords, secure HttpOnly sessions, CSRF, env secrets and audit | Security; Stage 1/2 |
| S02 | Append-only audit for logins, changes, imports, group operations and settings | Security/data model; Stage 1 onward |
| O01 | Backup and verified restore, local run instructions and upgrade procedure | Operations; Stage 1 then Stage 5 |
| O02 | Later remote access through Tailscale or Cloudflare Tunnel/Access | Operations; Stage 6, deferred |
| QA01 | Offline fixtures, pytest calculations, mocked HTTP/clock; network tests optional | Testing; every implementation stage |
| QA02 | Small cohesive files, completed stage gates, reproducible evidence and documented assumptions | Agent workflow; every stage |

## Resolutions of conflicting wording

| Original / later wording | Active interpretation | Evidence status |
| --- | --- | --- |
| CSV is the ongoing primary source | API primary, CSV fallback and missing-field enrichment | CONFIRMED later amendment |
| Single-user but two people | Two application users, one owner's portfolio | CONFIRMED clarification |
| Exclude Total, but place Total in Unassigned | Total is a source control row, never a holding or cash balance | ADOPTED correctness resolution |
| Slice is the group and every transaction has it | In the inspected snapshot Slice is ticker; Total-row Name is group context. Preserve raw fields; transaction labels are nullable and history needs a different format | VERIFIED snapshot; history OPEN |
| Instruments have group_id and membership is separate | Membership records are authoritative; a group_id may only be a cache | ADOPTED design |
| Cost basis uses daily closes | Executed trade/FX facts drive cost basis; daily closes drive risk series | ADOPTED correctness resolution |
| Last poll is daily close | Last eligible poll is provisional, never silently an approved risk input | ADOPTED quality rule |
| Reconcile against next day's close | Compare the same session's closing price retrieved later | ADOPTED correctness resolution |
| Once per session and re-arm | One event per excursion; re-arm after recovery; portfolio drawdown is the largest peak-to-trough fall within two trading days | CONFIRMED owner decision; Q08 resolved |
| Authentication Stage 5, but build now | Security and audit foundations precede usable financial UI | ADOPTED dependency order |
| Reproduce workbook exactly | Preserve source facts and legacy cases; do not carry known formula defects into active calculations | ADOPTED migration policy |

## Exclusions and deferred evidence

No order placement, modification, cancellation, pie targets, pie RAG, pie projections or pie management. Group alerts aggregate holdings; they are not broker-pie features. No subscriptions, multi-tenancy or public access in the local release.

Underlying ETF exposures, revenue-currency breakdowns, historical pre-opening basis, corporate actions and tax adjustments need evidence. They are requested capabilities, not permission to invent missing data. Complete implementation must either provide supported results or expose the specific unavailable state and limitation. A deferred feature is not silently dropped from the roadmap.

The owner confirms one ISA and defers the tax engine from the initial release. T01/T02 remain documented as optional later work, not initial stage gates. Portfolio value passing £20,000 is not a tax-engine activation rule. Current cost/PnL use clearly labelled management methods. GitHub is public: actual portfolio amounts/source files/notes remain local; only synthetic examples are published.

## Broker figures clarification — 12 November 2026

For the first financial snapshot, use Trading 212 reported account total/cash and per-position value/cost/PnL as authoritative source figures. Do not substitute reconstructed totals. Full ledger reconciliation is not a gate for displaying that broker snapshot. Keep source/as-of labels, exact decimals, missing states, account identity checks, immutable evidence and duplicate/atomicity controls. Calculated performance, risk and other analytics retain separate method/input labels; broker PnL is management reporting and is not HMRC output. See DC21/DC22 and the imports contract.
