# Sources and evidence register

Review baseline: **11 November 2026**. Links are primary sources. Provider/library behaviour and tax rules can change; verify the relevant source again before implementation changes that depend on it. No Bank Rate value is asserted. ISA guidance below distinguishes annual subscriptions from portfolio value.

## Owner sources

| ID | Source | What it establishes / limits |
| --- | --- | --- |
| SRC01 | [Archived original brief](context/original-brief.md) | Initial product scope; active resolutions are in product requirements |
| SRC02 | [Integration/polling amendment](context/integration-amendment.md) | API-primary revision and detailed intraday requirements; archival contradictions are resolved in active contracts |
| SRC03 | Explicit clarification: two logins, one owner's portfolio | User model, not two owners |
| SRC04 | Owner's local portfolio workbook | Read-only evidence; public-safe methods in [workbook baseline](workbook-baseline.md); exact hash/values stay local |
| SRC05 | Documentation request and owner answers | One ISA; equal edit rights; £100,000 goal; tax deferred; recovery re-arm; 10% group and 2% two-trading-day portfolio peak-to-trough alerts; July date unknown; repository public |
| SRC06 | Local holdings CSV | Verified [CSV contract](csv-contract.md); raw rows/digest/filename stay private |
| SRC07 | Three local Trading 212 PDF statements | Read-only [structural/coverage inspection](statement-source-contract.md); no private values/paths/digests published or complete-history claim |

The archived brief/amendment are historical source material, not active instructions to a future agent to build everything immediately. One real holdings CSV was inspected later in the same baseline; its schema is in [CSV contract](csv-contract.md). Execution-history CSV and authenticated broker responses remain uninspected.

## Broker integration

| Source | Reviewed use |
| --- | --- |
| [Trading 212 official API reference](https://docs.trading212.com/api) | Basic authentication, Demo/Live, pagination and account-wide rate limits |
| [Requested OpenAPI YAML](https://docs.trading212.com/_bundle/api.yaml) | Directly downloaded and parsed on 11 November 2026; structurally equal to JSON; hashes, field matrix and limits in [Stage 0 verification](stage-0-source-verification.md) |
| [Official linked OpenAPI JSON](https://docs.trading212.com/_bundle/api.json?download=) | Downloaded and compared with YAML: OpenAPI 3.0.1 / API v0, 17 paths / 38 schemas; no authenticated coverage claim |
| [Positions](https://docs.trading212.com/api/positions/getpositions.md) | Held-position price/currency fields and quote-timestamp limitation |
| [Historical orders](https://docs.trading212.com/api/historical-events/orders_1.md) | Separate fill/order identities, executed quantities and event kinds |
| [Dividends](https://docs.trading212.com/api/historical-events/dividends.md) | Payment/reference and amount-currency semantics |
| [Cash transactions](https://docs.trading212.com/api/historical-events/transactions.md) | Separate cash-event family and references |
| [Exchange schedules](https://docs.trading212.com/api/instruments/exchanges.md) | Working-schedule/time-event metadata to evaluate for calendars |
| [CSV export help](https://helpcentre.trading212.com/hc/en-us/articles/360016898917-Can-I-export-the-trading-data-from-my-account) | History and pie-information exports are distinct; does not verify owner's actual headers |

No live API call, credential, current balance or minute-level freshness guarantee is evidenced by these references. Absence of a route in the reviewed specification is a capability limit to recheck, not proof that the provider will never add one.

## Financial and numerical references

| Source | Reviewed use |
| --- | --- |
| [HMRC share-identification order](https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51555) | Same-day, qualifying following-30-day and Section 104 priority |
| [HMRC Section 104 holding](https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51575) | Pool quantity/allowable expenditure and acquisition costs |
| [Section 104 legislation](https://www.legislation.gov.uk/ukpga/1992/12/section/104) | Owner/capacity/security-class pooling scope; recheck current consolidated text |
| [HMRC tax on share disposals](https://www.gov.uk/tax-sell-shares) | Account-wrapper applicability, including ISA exclusions |
| [Accumulation-unit expenditure legislation](https://www.legislation.gov.uk/ukpga/1992/12/part/III/chapter/III/2023-03-01) | Dated legislation illustrating adjustment scope; **reverify current text before implementing fund-tax rules** |
| [yfinance download contract](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html) | Explicit adjustment, action, timezone and repair configuration |
| [pandas covariance](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.cov.html) | Missing-data covariance may not be PSD |
| [Ledoit-Wolf estimator](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.ledoit_wolf.html) | Covariance shrinkage estimator contract |

Sharpe/Sortino, quantiles, annualisation, effective bets and attribution conventions in the calculation documents are explicit application-method decisions. They are not presented as the only possible industry definitions. Do not attach a citation to a formula that the cited page does not support.

ISA clarification: [GOV.UK ISA rules](https://www.gov.uk/individual-savings-accounts/how-isas-work) describes tax-free investment income/gains and the annual subscription allowance. Tax-engine deferral follows the owner's scope decision, not an account-value threshold.

## Engineering references

| Source | Reviewed use |
| --- | --- |
| [SQLite type affinity](https://www.sqlite.org/datatype3.html) | Avoid implicit floating-point coercion of precise ledger decimals |
| [SQLite backup interface](https://www.sqlite.org/backup.html) | Consistent backup approach rather than an unsafe live-file copy |
| [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) | Application resource/scheduler lifecycle |
| [APScheduler 3.x guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) | Reference scheduler lifecycle/concurrency; version not selected yet |
| [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) | Session token/cookie handling |
| [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) | Explicit CSRF/Origin controls |
| [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) | Argon2id password-hash choice and maintained parameters |

## Reverification record

For an implementation task, record source URL/date, spec or fixture digest when relevant, scope inspected, observed changes and tests affected. Do not claim authenticated field coverage from a schema alone. Do not silently change a financial contract when an upstream library changes its default.

### 12 November 2026 recovery and broker recheck

The direct public Trading 212 YAML was downloaded again: **61,831 bytes**, SHA-256 `f2cda2ad99b9a22663c78a7b9187099c829df2fec655ea7f017236e11105c433`, unchanged from the 11 November contract. Official API documentation still specifies key/secret Basic authentication, per-account limits and whole-path/null-terminated pagination. No authenticated broker response has been inspected.

Official Supabase CLI recovery/Free backup guidance and PostgreSQL 17 dump/password-free-role references were rechecked for the [hosted recovery qualification](hosted-recovery.md). Actual testing found that native migration history needs an explicit data export beyond the CLI's default; the corrected archive restored with matching controls. This observation is independent of generic provider documentation.
