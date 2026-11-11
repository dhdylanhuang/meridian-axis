# Correlation module

Status: CONFIRMED key feature; ADOPTED method and reliability policies, with weekly defaults PROPOSED under Q12. Supports K01–K05 and A02.

## Inputs and meaning

Use approved daily total-return-compatible prices converted to GBP, never intraday quotes or unapproved `eod_poll` candidates. Include currently held nonzero risky positions and configured benchmark series. Cash, constants, nonpositive prices, unmapped listings and unsupported history are ineligible with explicit reasons and excluded-weight coverage.

Current-composition analytics describe the risk of today's holdings using historical market observations. They are not the realised historical return of the owner's changing portfolio. Freeze quantities/weights at a named as-of revision for the calculation. A reproducible result records the instruments, weights, price/FX revisions, setting/method version and sampling dates.

## Alignment pipeline

1. Validate listing/quote units, adjustment basis, date/time convention and compatible FX. Do not convert an already-GBP series twice.
2. Build a documented daily valuation grid from the relevant exchange/session calendars. Map source closes to session dates consistently; do not pretend London and Asian closes occurred simultaneously.
3. Carry forward a price only for a known market closure, up to **three consecutive valuation-grid observations**. Record every imputation. This is the ADOPTED interpretation of the brief's three-day limit; the UI explains the unit. Missing provider data on an open market is not automatically a holiday.
4. A longer gap or unknown closure flags the series and leaves missing observations. Preserve weekend/calendar metadata rather than blindly filling calendar days.
5. Form GBP prices using eligible FX at the valuation cutoff; a stale FX leg is a data-quality issue even with a current local close.
6. Calculate daily GBP log returns after alignment. Do not fill a missing return directly, and require the preceding eligible price.
7. Select the requested horizon and common eligible sample. Record original, imputed and complete counts.

The fill rule is a limited accommodation for closures. It does not remove timing bias. Weekly mode reduces some close-timing sensitivity and must remain visibly labelled.

## Horizons, frequency and reliability

| Control | Planned behaviour |
| --- | --- |
| Daily horizons | Last 30, 90 or 252 completed valuation-grid trading observations; require prior price |
| Weekly mode | Same calendar span as the selected daily horizon, aggregated to completed weekly endpoints; do not silently reinterpret 252 as 252 weeks |
| Weekly endpoint | Last common valuation-grid observation of the week; no incomplete current week by default |
| Daily reliability minimum | 60 actual aligned returns by default, as requested |
| Weekly reliability minimum | PROPOSED 20 completed weekly returns; Q12 must decide and label this separately |
| Descriptive short windows | A valid sample below reliability minimum is `insufficient_data` for reliable risk/alerts; an explicit descriptive view may show the coefficient, n and warning |
| Degenerate sample | Fewer than 3 observations, zero variance or invalid values: no coefficient |

A 30-day horizon cannot meet the default 60-day reliable minimum. This is intentional and visible, not patched by quietly lowering the minimum. Short-window descriptive estimates never drive correlation alerts. Synthetic tests may use reduced reliability thresholds explicitly.

## Matrix sample and PSD

The full matrix uses one shared complete-case return panel for its eligible universe. Record excluded instruments, exposure coverage and why the common sample shrank. Do not quietly drop whichever holding makes the result look better. Offer the user the eligible subset and its coverage before comparing it with a previous different universe.

Pairwise-complete covariance built from different dates can fail positive semidefiniteness. [pandas documentation](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.cov.html) explicitly warns about this. Therefore it cannot be the matrix used for eigenvalues, diversification ratios or shrinkage.

Raw Pearson correlation is derived from the common sample covariance. Check symmetry, unit diagonal, bounds and PSD with a scale-aware numerical tolerance (initial proposal 1e-10 for a correlation matrix). Zero-variance columns are excluded, not assigned a fabricated diagonal of 1. Singular matrices are allowed: PSD does not mean positive definite. Only round displayed values, not analytical inputs. Tiny numerical negatives may be clipped for a diagnostic after recording tolerance; materially invalid eigenvalues invalidate the result.

## Shrinkage

Offer Ledoit-Wolf covariance on the same eligible complete return panel, then normalise its covariance to correlation. Report the estimator, shrinkage coefficient, sample and difference from the raw estimate. Do not apply it to an arbitrary incomplete correlation table or imply that it fixes missing evidence. [Estimator documentation](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.ledoit_wolf.html)

Raw and shrunk views must use the same universe/sample for comparison. Store which estimator drives diagnostic outputs and alert evaluations. Default estimator is raw sample covariance until the owner selects shrinkage; changing it is audited and creates a new analytical revision.

## Group indices

Freeze current within-group market-value weights w, normalised over eligible members. Construct each day's group **simple** return `r_g,t=sum(w_i × r_i,t)` and then log-transform `log(1+r_g,t)`. Do not take a weighted mean of log returns and call it exact group portfolio return. This defines a hypothetical constant-weight/rebalanced series; disclose that assumption.

ADOPTED completeness policy: a group needs all its required current members' eligible returns for a date. Do not silently reweight a missing member out. If coverage is incomplete, show the affected group as unavailable or an explicitly requested partial subgroup. Historical realised group indices would need historical holdings/weights and are a different feature.

## Views

1. **Holding matrix:** heatmap values and scale; global hierarchical clustering using distance `sqrt(2×(1−rho))` and average linkage, with deterministic tie handling. Display group annotations along axes. A separate group-order mode clusters within each group and can draw contiguous boundaries; global clustering cannot promise contiguous groups.
2. **Pair detail:** selected pair, rolling coefficient, n, exclusions and frequency. The matrix cell's sample is the same full-panel sample. An optional pair-specific rolling history can use a wider pair sample only when its differing basis is labelled.
3. **Group matrix:** complete group indices plus benchmark columns, showing frozen weight date and eligible coverage.
4. **Benchmark view:** holdings/groups versus each verified VUAG/IWDA proxy, sortable by coefficient, with 30/90/252-horizon rolling views and counts.
5. **Diagnostics:** pair averages, effective bets, diversification ratio and highest positive-correlated held pairs. Show estimator, universe and coverage alongside results.

## Diagnostic formulas

For n eligible holdings and a correlation matrix R:

- Average pairwise correlation = mean of `R_ij` for i<j, excluding diagonal; unweighted, labelled. For n<2 unavailable. Within-group average uses that subset.
- Correlation-based effective bets = `(sum(lambda))² / sum(lambda²)` using eigenvalues of R. It ranges 1..n for a valid matrix. This is an unweighted participation-ratio diagnostic, not `1/HHI` and not a claim that positions are economically independent.
- Diversification ratio = `sum(w_i sigma_i) / sqrt(wᵀ Sigma w)`, using matching sample/estimator and nonnegative risky-asset weights normalised excluding cash. Zero portfolio volatility or unsupported shorts makes it unavailable.
- Highest-correlated pairs include only two distinct positions both held. Positive correlation is co-movement risk; negative correlation is not ranked as duplication by absolute value.

The held-pair 90-day default alert threshold is 0.85. Pair-average, benchmark correlation and effective-bets thresholds remain configurable and require explicit values. Alerts require a reliable eligible result and a stable, disclosed universe; log sample/universe changes rather than treating them as ordinary market crossings.

## Tests and acceptance

Synthetic increasing/decreasing nonconstant series produce +1/−1; a constructed orthogonal sample produces zero within tolerance. Validate common-panel symmetry/diagonal/bounds/PSD, singular but valid matrices, shrinkage comparison on identical inputs, deterministic clustering and weighted-simple group returns.

Test 30-day unreliability at minimum 60; no alerts from insufficient samples; constant series excluded; holidays filled only to limit; open-market missing data not holiday-filled; weekly count labelled; missing group member not renormalised away; pair detail preserves sample identity; omitted cash and excluded exposure shown. The VNRG/VUAG overlap fixture belongs to look-through exposure tests once its evidence exists, not a fabricated correlation target.
