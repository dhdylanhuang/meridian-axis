# Financial calculation contracts

Status: ADOPTED definitions unless labelled PROPOSED/OPEN. Implement as pure functions with docstrings, units, dated inputs, eligibility and meaningful offline examples. This document defines application methods, not a claim of regulatory certification.

## Common result contract

Every material result carries value, unit/currency, as-of/session date, method/version, input revisions, window/frequency where relevant, observation count, coverage and quality. Availability is one of `available`, `provisional`, `insufficient_data`, `unsupported`, `not_applicable` or `failed`. Quality warnings can coexist with an available descriptive result. A missing result has a reason and no numeric placeholder.

Distinguish realised economic PnL, unrealised economic PnL, broker-reported PnL and tax gains. These fields must never share a misleading generic `return` or `cost` name in the calculation API.

## Valuation and allocation

Let `q_i` be signed quantity, `p_i` a compatible unadjusted listing price, `u_i` its unit multiplier (for example 0.01 for pence to pounds), and `x_i` GBP per one unit of quote currency. Then `MV_i = q_i × p_i × u_i × x_i`. GBP/GBP is exactly 1. Preserve both listing amount and the exact FX observation. Unsupported leverage, shorting or liability types produce limitations rather than an accidental long-only calculation.

`NAV = sum(security MV) + sum(GBP cash balances) − supported liabilities`.

No explicit cash history means securities value can be shown, but not silently presented as reconciled total NAV. A missing price must not make that holding disappear from the denominator. Report valued coverage, last-good age and incomplete NAV state; block dependent trusted weights where material inputs are absent.

Holding weight is `MV_i / NAV`. Group weight is sum of its holding values divided by the same NAV. For a group-internal concentration view, renormalise its holdings to the group's securities value and label that denominator. NAV≤0 makes ordinary allocation/risk ratios unavailable. Cash contributes to portfolio allocation but is excluded from risky-asset correlation.

Group market value, supported cost, PnL and dividends are additive over eligible members/events. Group return is calculated from consistent aggregate wealth/cash-flow inputs; never sum or take an unweighted average of holding returns. Include closed-position income/realised events in historical attribution under their effective classification, even when current held count is zero.

## Quantities, costs and dividends

Quantity comes from replayed accepted events plus explicitly supported opening positions and corporate actions. A broker snapshot is a reconciliation source, not an extra acquisition. Cost methods have names: broker cost, economic tracking cost and HMRC allowable cost. Section 104 matching is described in [tax](tax.md) as deferred work, not an initial cost column or stage gate.

For the initial economic tracking view, average acquisition cost including supported acquisition fees may be used as a labelled ADOPTED management-cost method. Disposals release proportional management cost. Its realised PnL is proceeds net of supported disposal fees minus released management cost; this differs from future-acquisition tax matching. Unknown pre-opening cost means unavailable cost/PnL, even if quantity and price are known.

Dividend income is the sum of normalised payment events over an explicit interval, preserving gross, withholding and net only when supported. Retained dividends remain internal cash income. Reinvestment is a dividend event plus an acquisition; do not count it as an external contribution. Baseline cumulative dividends are historical observations, not cash events. Accumulating-fund distributions require separate source-supported treatment; do not fabricate cash receipts.

Total-return amount for a position must reconcile realised/unrealised economic PnL, income, fees and transfers on one stated basis. Total-return percentage with purchases and sales requires a dated return method; `(value − cost)/cost` is only labelled simple unrealised gain ratio.

## Portfolio performance and external cash flows

The portfolio boundary is the owner's included accounts. Deposits/withdrawals across that boundary are external flows. Buys/sells, retained income and FX conversion within it are internal. Transfers between included accounts net to zero; transfers to an excluded account cross the boundary. Distinguish genuine contribution, withdrawal and unknown transfer direction.

**Exact TWR:** split at every external cash flow when consistent immediately-before/after valuations exist. Compute each flow-free subperiod return and chain `product(1+r)−1`. Do not label daily snapshots plus unknown-timed flows as exact TWR.

**ADOPTED fallback:** Modified Dietz for a daily period with trustworthy flow timestamps: `r = (V_end − V_start − sum(F_j)) / (V_start + sum(w_j F_j))`, where positive F enters the portfolio and `w_j` is the fraction of the period remaining after that flow. Label this a cash-flow-adjusted approximation. If timestamps are only dates, a configurable convention is required (Q06); no silent midpoint or end-of-day choice.

Daily, MTD, calendar-YTD and since-inception results chain compatible available period returns. Since inception begins at supported inception, not the first convenient downloaded close. Missing observations, nonpositive denominators and unsupported flows make the affected interval unavailable or explicitly partial. Monthly Excel totals alone cannot establish these return series. Use GBP investor returns; local security performance is a separate diagnostic.

Portfolio drawdown uses a flow-adjusted wealth index, not raw NAV inflated by deposits. Current holding risk can use total-return security series independently of portfolio ownership history, with that distinction labelled.

### Observed Modified Dietz

`modified_dietz_observed_v1` uses GBP Trading 212 account values at their actual
account capture times. Each interval requires two approved captures on adjacent
UTC snapshot dates. Capture time determines elapsed-time weights. Each result
shows its observed start and end. Exact decimal arithmetic uses microsecond
elapsed weights and rounds division and chained growth to 24 decimal places.
Displayed percentages are rounded to six decimal places.

The private evidence read uses the newest successful completed Trading 212
transaction traversal as of the History read. It checks recorded page count,
sequence, digests and traversal completion. Repeated identical references count
once. Its conservative coverage starts at the earliest returned transaction and
ends at the first page's retrieval start. Days outside those bounds have
unverified funding coverage. Provider-available history does not establish
account-lifetime or independent statement coverage.

A positive GBP deposit or negative GBP withdrawal supplies a timed external
cash flow. Retained dividends, cash or lending interest and fees remain in
account performance. Transfers, unknown cash types, non-GBP or incompatible
funding signs block intersecting intervals. A qualifying external transaction
at exactly a valuation timestamp also blocks that interval because ordering
is unknown. A missing UTC date, unusable capture, nonpositive account value
or invalid weighted capital prevents the affected result.

The latest eligible pair and longest usable 90-day stretch report their actual
dates. Month-to-date and year-to-date chain through the latest eligible date in
the respective period, with prior period-end and every intervening valuation
required. Today can be provisional. The 90-day chart does not cap the internal
year-boundary check. A scheduled non-capture date breaks the chain under the
initial UTC-date convention.

### VUAG GBP benchmark proxy

Compare eligible observed daily returns to the GBP London Stock Exchange
listing of Vanguard S&P 500 UCITS ETF (VUAG, ISIN IE00BFMXXD54). The input is
a reviewed split-adjusted series of market closes for the accumulating share
class. Dividends are retained in the fund and receive no separate adjustment.
The ETF proxies the S&P 500 through an investable fund with market prices and
fund expenses. The chosen series represents the fund share.

Both dates must have a portfolio observation and a qualified GBP close.
Each portfolio account capture must also fall on the UTC date of its respective
benchmark endpoint. The comparison is provisional and shows both capture
times and benchmark price times. The benchmark return is the closing price
ratio less one. Difference is portfolio return less benchmark return in
percentage points, calculated before display rounding. A missing endpoint
stays blank. The dashboard does not bridge gaps to infer a daily result.

When a reviewed close series is absent, History uses the per-share GBP
`current_price` of the exact Trading 212 listing `VUAGl_EQ` from the same
approved daily snapshots as account value. A reported ISIN must agree with
IE00BFMXXD54. Older snapshots can qualify by exact broker listing and GBP support.
Both dates need a valid stored position mark and an eligible portfolio return.
A capture outside its UTC date leaves a gap. The visible timestamp is holdings
retrieval completion. Quote age, exchange-close status and split adjustments
are unverified. The broker series uses price ratios within that source only.

## Return series and risk conventions

Risk uses approved daily data; default horizon 252 observations. For a positive GBP total-return series `P_t`, simple return is `P_t/P_(t−1)−1`; log return `l_t = log(P_t/P_(t−1))`. Require one extra price observation. An adjusted series and explicit dividends cannot both supply the same return component. The adapter records adjustment basis; raw valuation closes remain separate.

ADOPTED annualisation factor: A=252 for daily and 52 for weekly. Use effective-dated UK Bank Rate as the requested risk-free proxy, not a promise of attainable cash return. Convert an annual rate R to period log rate `log(1+R)/A`, retaining source and rate convention. Historical rates apply by effective date; never apply tomorrow's rate to yesterday. A constant editable fallback is labelled, dated and audited.

| Measure | Adopted method | Edge cases / disclosure |
| --- | --- | --- |
| Sharpe | `sqrt(A) × mean(e_t)/sd(e_t, ddof=1)`, where e is log return minus period log risk-free | Insufficient n or zero volatility: unavailable; disclose log-return convention |
| Sortino | `sqrt(A) × mean(l_t−m_t) / sqrt(mean(min(l_t−m_t,0)^2))` | m is explicit minimum acceptable log return, default risk-free proxy; downside denominator uses all eligible periods; zero downside is undefined |
| Max drawdown | Running peak of compounded wealth W; `D_t=W_t/max(W_0..W_t)−1`; minimum D with peak/trough dates | Display positive loss magnitude with dated negative series; use earliest tied peak/trough consistently |
| Current drawdown | Latest W relative to its preceding running peak | Record peak date and latest eligible date; no forced recovery date |
| Historical VaR | One-period simple loss samples `L=−expm1(l)`; empirical 0.95/0.99 quantile using linear interpolation | Store signed quantile; headline nonnegative loss `max(0,q)`; show n and tail support, not guaranteed maximum loss |
| Expected Shortfall | Mean of observed L values at/above the selected VaR quantile | Record confidence, realised tail count and tie/interpolation rule; not Gaussian or annualised by sqrt(time) |
| VaR/ES GBP | Loss fraction times matching current NAV | Same horizon and basis; stale NAV warning; no implicit multi-day scaling |
| Beta/Jensen alpha | OLS `portfolio_excess_log = a + beta × benchmark_excess_log + residual` separately for each proxy | Common dates, n, R² and benchmark; A×a is annualised log alpha, `expm1(A×a)` labelled compounded alpha |
| Regression edge cases | Benchmark variance>0 and sufficient rank/sample | Do not regress against synthetic zeros or give beta=0 for missing observations |

Low tail sample support must be visible, especially 99% VaR over one year. A numerically available quantile is not automatically reliable. Configure minimum observations and tail-count warnings independently. Estimate outputs only for supported samples; no probability-of-safety claims.

## Concentration, overlap and currency

For nonnegative weights on an explicitly named denominator: top-k=sum largest min(k,n), `HHI=sum(w_i²)`, `effective_holdings=1/HHI`. Within-group values use group-normalised weights. For an overall securities-only diagnostic, exclude cash and renormalise; provide the separate NAV allocation view. Do not compare HHI values with different denominators as if identical.

Two funds' constituent overlap can use `sum(min(a_k,b_k))` over normalised underlying weights on a common as-of date. Portfolio exposure to underlying name k is direct holding exposure plus each fund's portfolio weight times its supported constituent weight. Missing constituents and stale look-through reduce reported coverage; never renormalise missing fund weight away without disclosure. High correlation is a separate warning, not measured common holdings. The VNRG/VUAG ~19% statement is unverified; a dated, defined fixture is required before testing that number.

Listing-currency allocation groups current GBP values by listing currency. It does not claim currency hedging or underlying economic exposure. Underlying revenue currency requires dated sourced percentages with coverage; country of listing is not a proxy. A fund's reporting currency is not automatically the listing currency or revenue currency.

### Approved broker snapshot exposure

AXIS uses `broker_exposures_v1`. The position numerator is Trading 212
`positions[].walletImpact.currentValue` in the snapshot's primary currency.
The two denominators are the account summary's reported `totalValue` (portfolio)
and `investments.currentValue` (invested value). Neither is reconstructed. Both
must be positive for their respective percentages, and portfolio weights require
a nonnegative investment control no greater than the reported total. Account and
positions use their own retrieval completion times. The portfolio denominator
is a broker account control, without an assertion of reconciled NAV.

Rank supported nonnegative position amounts descending, with ticker breaking
ties. Largest, top five and top ten use the sum of the largest min(k, number of
positions) values, as money and as a percentage of each eligible denominator.
These measures are unavailable if any position value is absent or incompatible.
Individual and bucket percentages use the full broker controls even with
partial coverage. Known valued holdings and missing values remain visible. A
bucket with no usable values has no amount. Separate retrievals can produce a
difference between summed holdings and the reported investment control. Rust
sums exact decimal amounts and rounds percentages once, half up to two decimal
places. Amounts and percentages cross WASM and JSON as decimal strings.

Quote-currency buckets use Trading 212 instrument currency from positions, then
available, nonconflicting held-listing metadata as a fallback. Unclassified
quote currency is an explicit bucket. Currency buckets represent direct holdings
by quoted currency, with no underlying currency, geographic or fund look-through
claim. Classification extends the same approved projection with three sourced
allocations: broad equity sectors, direct-share issuer domicile (country of
incorporation), and underlying equity markets reported by fund managers.
Direct shares use a reviewed principal-business sector in the broad 11-sector
GICS naming scheme. Fund sector data is included where the manager categories
can be used on the same broad basis. ICB and manager-specific sector categories
use labelled rows because they differ from GICS-style sectors. Reported regional
weights keep their regional labels where country-level weights are unavailable.
Domicile and fund markets are independent
views because those country definitions differ. Fund market and sector estimates
apply published weights to the full broker position value. Manager tables may
exclude cash and derivatives under their stated basis. No residual is inferred
from a benchmark or added to a country. Verified gold and bond positions appear
outside the equity sector scope and do not contribute to the fund-market view.

The private catalogue is keyed by the approved Trading 212 instrument ISIN.
Position evidence takes precedence with a current broker catalogue fallback,
and a conflicting ISIN withholds the join. A fund breakdown is eligible at most
120 days after its evidence date, or 180 days for a sourced regulatory
annual or interim fund report. Issuer classifications and non-equity evidence
are eligible at most 550 days after that date. Future evidence is withheld.
Reviewed dimensions accept positive decimal percentage strings summing to at
most 100. Missing documents, unsupported fund portions, and any unsourced or rounding
remainder are unclassified. Preserve published decimal weights. If a rounded
table exceeds 100%, leave the smallest rounding-affected category in the
residual. Partial constituent coverage uses only sourced fund weights and
independently verified groups. Single-market equity share may use the
manager’s identification of its single market with the observed equity
sector subtotal. This preserves the unallocated fund portion. Exact value times the source percentage yields the
bucket contribution. No unclassified remainder is renormalized. Snapshot
allocations carry source URL and date once per holding and dimension, exact
constituent amounts, the original allocation share, and the classified and
observed values. Quote currency remains a separate listing-only allocation.

Available-to-trade, in-pies and reserved-for-orders cash each use the eligible
portfolio denominator. Shares are independent and may overlap. Total cash
allocation requires either an authoritative total cash control or verified
disjoint components. The approved projection carries the method, snapshot ID,
both cutoffs, primary currency, control amounts, measured coverage and outputs.
Older snapshots and compute failures leave broker figures usable.

Sources: [account summary](https://docs.trading212.com/api/accounts/getaccountsummary.md),
[open positions](https://docs.trading212.com/api/positions/getpositions.md),
[instrument catalogue](https://docs.trading212.com/api/instruments/instruments.md).

## Projections

The active model is portfolio-level only. Confirmed planning goal: **£100,000 by 2030**, retaining **30 April 2030** from the original brief. Workbook legacy date: 5 April 2030 and fixed 44 months. Preserve legacy reconciliation in [workbook baseline](workbook-baseline.md); do not create group projection objects to reproduce its interface.

For a fixed n-period case with end-period contribution c and monthly rate r: `FV=V0(1+r)^n+c((1+r)^n−1)/r`; at r=0 use `V0+n×c`. Beginning-period contributions multiply the contribution term by `(1+r)`. For active dated forecasts, iterate an explicit contribution schedule and growth periods, with a stated treatment of partial periods.

PROPOSED active annual assumption convention: effective annual growth converted with `r=(1+R)^(1/12)−1`. Legacy uses R/12 instead. Q05 now concerns only contribution timing, private opening NAV, partial periods and scenario rates; the £100,000 goal is settled. The workbook's private contribution schedule is historical input, not confirmation that deposits execute automatically. Scenario values must be editable and audited; no invented pessimistic/optimistic rates. No Monte Carlo or confidence claims are required.

## Attribution and trading statistics

ADOPTED first attribution step: reconciled GBP PnL amounts by dated holding/group, including income, fees, cash and explicit residuals. Reconcile to portfolio PnL before percentages or alpha/beta charts. Use historical quantities and effective memberships; today's holdings cannot explain disposed positions' history.

For local simple return r_L and quote-currency GBP return r_FX, total return is `r_L+r_FX+r_L×r_FX`. Report the interaction separately initially. Multi-period contribution requires a documented linking method (Q10); do not just sum daily percentage contributions.

A CAPM residual is an unexplained statistical component, not proof of skill. Market/residual attribution requires a selected benchmark, period, regression basis and reconciliation. Label the chosen proxy and keep descriptive PnL attribution separate from regression analysis.

Win/loss ratio, profit factor and average holding period need a defined economic episode/disposal policy, independent of HMRC matching. They are OPEN under Q10. Zero losses does not produce a finite invented profit factor, open positions are not closed wins, and future tax matches do not establish actual holding duration.

## Stress scenarios and RAG

Stress tests are deterministic hypothetical revaluations. Market shocks (-10/-20%) must state whether they directly shock selected securities or use beta; do not assume these are equivalent. Tech sell-off needs an explicit affected set/shock (Q11). Define GBP appreciation by quote direction: if quote currency costs 5% fewer GBP, multiply its GBP-per-unit FX by 0.95. Preserve the exact mathematical meaning shown in UI; do not ambiguously invert a 5% currency move. Apply overlapping holding/group shocks once using explicit precedence. Cash and hedges require supported treatment. Stress results are not forecasts.

Holding RAG is requested but its score/threshold meaning is OPEN (Q09). Until decided, display unavailable/configuration required rather than arbitrary red/amber/green investment recommendations. Group RAG and pie target status are excluded.

## Confirmed drawdown alert defaults

Every group has a configurable default 10% drawdown-from-running-peak alert. The portfolio has a configurable default 2% largest peak-to-trough decline within a rolling two-trading-day window. Both use compatible flow-adjusted wealth and re-arm after the measured condition recovers. The portfolio rule is not a two-day endpoint loss; see [alerts](alerts.md) for ordered observations, window memory and missing-data rules. These defaults do not define a holding RAG score or a tech shock.


## Reported cash activity summary

Owner DC25: cash now and historical receipts/withdrawals are distinct quantities.
For an explicit UTC period, sum latest nonconflicting source amounts once within
`(account, environment, source family, reference)`, separately by currency/category.
This descriptive reported total preserves provider signs; it does not establish
cash ledger economics, external contribution classification, gross/net dividend
semantics, returns, or what fraction remains in current cash. Missing coverage is
labelled; a missing category is unestablished rather than a synthetic zero. Rust
owns exact sums; Python validates and JavaScript displays strings without finance
arithmetic. Broker cash components stay independent.
