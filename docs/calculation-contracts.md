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
