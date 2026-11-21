//! Observed interval statistics and approved daily risk estimates.
use super::{pct, Interval, RiskRange};
use crate::decimal;
use bigdecimal::ToPrimitive;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

const MIN_DAILY: usize = 60;
const MAX_DAILY: usize = 252;
const ANNUAL_SESSIONS: f64 = 252.0;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Series {
    basis: String,
    source: String,
    rows: Vec<Session>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Session {
    date: NaiveDate,
    portfolio_index: Option<String>,
    vuag_index: Option<String>,
    bank_rate_pct: Option<String>,
    portfolio_value_gbp: Option<String>,
}

#[derive(Serialize)]
struct Measure {
    key: &'static str,
    value: Option<String>,
    n: usize,
    reason: Option<&'static str>,
    tail_n: Option<usize>,
    value_gbp: Option<String>,
    signed_loss_pct: Option<String>,
}

fn price(value: &Option<String>) -> Option<f64> {
    let x = decimal(value.as_deref()?).ok()?.to_f64()?;
    (x.is_finite() && x > 0.0).then_some(x)
}

fn rate(value: &Option<String>) -> Option<f64> {
    let x = decimal(value.as_deref()?).ok()?.to_f64()? / 100.0;
    (x.is_finite() && x > -1.0).then(|| x.ln_1p() / ANNUAL_SESSIONS)
}

fn validated(input: &serde_json::Value) -> Option<Series> {
    let series: Series = serde_json::from_value(input.clone()).ok()?;
    if series.basis != "approved_gbp_session_total_return_v1"
        || series.source.trim().is_empty()
        || series.source.len() > 256
        || series.source.chars().any(char::is_control)
        || !(2..=367).contains(&series.rows.len())
        || series
            .rows
            .windows(2)
            .any(|rows| rows[0].date >= rows[1].date)
    {
        return None;
    }
    for row in &series.rows {
        let prices = [
            &row.portfolio_index,
            &row.vuag_index,
            &row.portfolio_value_gbp,
        ];
        if prices
            .into_iter()
            .any(|value| value.is_some() && price(value).is_none())
            || row.bank_rate_pct.is_some() && rate(&row.bank_rate_pct).is_none()
        {
            return None;
        }
    }
    Some(series)
}

fn average(xs: &[f64]) -> f64 {
    xs.iter().sum::<f64>() / xs.len() as f64
}
fn variance(xs: &[f64]) -> f64 {
    let mu = average(xs);
    xs.iter().map(|x| (x - mu).powi(2)).sum::<f64>() / (xs.len() - 1) as f64
}
fn covariance(xs: &[f64], ys: &[f64]) -> f64 {
    let (mx, my) = (average(xs), average(ys));
    xs.iter()
        .zip(ys)
        .map(|(x, y)| (x - mx) * (y - my))
        .sum::<f64>()
        / (xs.len() - 1) as f64
}

fn formatted(x: f64, places: usize) -> String {
    let value = format!("{x:.places$}");
    let trimmed = value.trim_end_matches('0').trim_end_matches('.');
    if trimmed == "-0" {
        "0".to_owned()
    } else {
        trimmed.to_owned()
    }
}

fn measure(
    key: &'static str,
    n: usize,
    required: &'static str,
    compute: impl FnOnce() -> Option<f64>,
) -> Measure {
    let value = (n >= MIN_DAILY)
        .then(compute)
        .flatten()
        .filter(|x| x.is_finite());
    let reason = if value.is_some() {
        None
    } else if n < MIN_DAILY {
        Some(required)
    } else {
        Some("undefined")
    };
    Measure {
        key,
        n,
        value: value.map(|x| formatted(x, 6)),
        reason,
        tail_n: None,
        value_gbp: None,
        signed_loss_pct: None,
    }
}

fn tail(
    losses: &[f64],
    q: f64,
    var_key: &'static str,
    es_key: &'static str,
    nav: Option<f64>,
) -> [Measure; 2] {
    let n = losses.len();
    let mut var = measure(var_key, n, "need_portfolio", || None);
    let mut es = measure(es_key, n, "need_portfolio", || None);
    if n >= MIN_DAILY {
        let rank = q * (n - 1) as f64;
        let floor = rank.floor() as usize;
        let cutoff = losses[floor] + (losses[rank.ceil() as usize] - losses[floor]) * rank.fract();
        let first = losses.partition_point(|loss| *loss < cutoff);
        let tail = &losses[first..];
        for (metric, estimate) in [
            (&mut var, Some(cutoff)),
            (&mut es, (tail.len() >= 2).then(|| average(tail))),
        ] {
            metric.tail_n = Some(tail.len());
            metric.reason = if estimate.is_some() {
                None
            } else {
                Some("need_tail")
            };
            if let Some(loss) = estimate {
                metric.signed_loss_pct = Some(formatted(loss, 6));
                metric.value = Some(formatted(loss.max(0.0), 6));
                metric.value_gbp = nav.map(|value| formatted(value * loss.max(0.0) / 100.0, 2));
            }
        }
    }
    [var, es]
}

pub(super) fn calculate(
    intervals: &[Interval],
    range: &RiskRange,
    input: Option<&serde_json::Value>,
) -> serde_json::Value {
    let mut eligible = 0;
    let mut losses = 0;
    let mut worst = None;
    for interval in intervals {
        if let Some(growth) = &interval.growth {
            eligible += 1;
            if growth < &1 {
                losses += 1;
                if worst.is_none_or(|prior: &Interval| Some(growth) < prior.growth.as_ref()) {
                    worst = Some(interval);
                }
            }
        }
    }
    let observed = serde_json::json!({
        "eligible":eligible, "requested":intervals.len(), "loss_intervals":losses,
        "worst":worst.map(|row| serde_json::json!({"return_pct":row.growth.as_ref().map(pct),
                "start_at":row.start_at,"end_at":row.end_at})),
    });

    let series = input.and_then(validated);
    let mut portfolio = Vec::new();
    let mut excess = Vec::new();
    let mut matched_portfolio = Vec::new();
    let mut matched_vuag = Vec::new();
    let mut regression_portfolio = Vec::new();
    let mut regression_vuag = Vec::new();
    let mut losses = Vec::new();
    let (mut first_date, mut last_date, mut nav) = (None, None, None);
    if let Some(series) = &series {
        let in_range = &series.rows[series.rows.partition_point(|row| row.date < range.start)
            ..series.rows.partition_point(|row| row.date <= range.end)];
        let bounded = &in_range[in_range.len().saturating_sub(MAX_DAILY + 1)..];
        for rows in bounded.windows(2) {
            let (a, b) = (&rows[0], &rows[1]);
            let (Some(first), Some(last)) = (price(&a.portfolio_index), price(&b.portfolio_index))
            else {
                continue;
            };
            let ratio = last / first;
            let p = ratio.ln();
            if !p.is_finite() {
                continue;
            }
            first_date.get_or_insert(a.date);
            last_date = Some(b.date);
            nav = price(&b.portfolio_value_gbp);
            portfolio.push(p);
            losses.push((1.0 - ratio) * 100.0);
            let rf = rate(&a.bank_rate_pct);
            if let Some(rf) = rf {
                excess.push(p - rf);
            }
            if let (Some(first), Some(last)) = (price(&a.vuag_index), price(&b.vuag_index)) {
                let v = (last / first).ln();
                if v.is_finite() {
                    matched_portfolio.push(p);
                    matched_vuag.push(v);
                    if let Some(rf) = rf {
                        regression_portfolio.push(p - rf);
                        regression_vuag.push(v - rf);
                    }
                }
            }
        }
    }
    let a = ANNUAL_SESSIONS.sqrt();
    let n = portfolio.len();
    let m = matched_portfolio.len();
    let r = regression_portfolio.len();
    let correlation = |x: &[f64], y: &[f64]| {
        let denominator = (variance(x) * variance(y)).sqrt();
        (denominator > 0.0).then(|| (covariance(x, y) / denominator).clamp(-1.0, 1.0))
    };
    let beta = || {
        let var = variance(&regression_vuag);
        (var > 0.0).then(|| covariance(&regression_portfolio, &regression_vuag) / var)
    };
    let mut measures = vec![
        measure("volatility", n, "need_portfolio", || {
            Some(variance(&portfolio).sqrt() * a * 100.0)
        }),
        measure("sharpe", excess.len(), "need_rate", || {
            let sd = variance(&excess).sqrt();
            (sd > 0.0).then(|| average(&excess) / sd * a)
        }),
        measure("sortino", excess.len(), "need_rate", || {
            let downside = (excess.iter().map(|x| x.min(0.0).powi(2)).sum::<f64>()
                / excess.len() as f64)
                .sqrt();
            (downside > 0.0).then(|| average(&excess) / downside * a)
        }),
        measure("beta", r, "need_regression", beta),
        measure("jensen_alpha", r, "need_regression", || {
            beta().map(|b| {
                (average(&regression_portfolio) - b * average(&regression_vuag))
                    * ANNUAL_SESSIONS
                    * 100.0
            })
        }),
        measure("r_squared", r, "need_regression", || {
            correlation(&regression_portfolio, &regression_vuag).map(|r| r * r)
        }),
        measure("correlation", m, "need_vuag", || {
            correlation(&matched_portfolio, &matched_vuag)
        }),
        measure("tracking_error", m, "need_vuag", || {
            let active: Vec<_> = matched_portfolio
                .iter()
                .zip(&matched_vuag)
                .map(|(p, v)| p - v)
                .collect();
            Some(variance(&active).sqrt() * a * 100.0)
        }),
    ];
    losses.sort_by(f64::total_cmp);
    measures.extend(tail(&losses, 0.95, "var95", "es95", nav));
    measures.extend(tail(&losses, 0.99, "var99", "es99", nav));
    let state = match (&series, &input) {
        (Some(_), _) => "approved_series",
        (None, Some(_)) => "invalid_series",
        _ => "awaiting_approved_series",
    };
    serde_json::json!({
        "observed": observed, "daily_state": state,
        "source": series.as_ref().map(|s| &s.source), "minimum_daily":MIN_DAILY,
        "daily_start":first_date,"daily_end":last_date, "measures":measures,
    })
}
