//! Observed interval statistics and approved daily risk estimates.
use super::{pct, CheckedEvent, Day, Interval, RiskRange};
use crate::risk_sessions::{self, Reviewed};
use crate::{decimal, instant};
use bigdecimal::ToPrimitive;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[path = "approved_performance.rs"]
mod approved;
#[path = "official_bank_rate.rs"]
mod bank_rate;
#[path = "holding_correlation.rs"]
mod holdings;

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
    portfolio_at: Option<String>,
    vuag_index: Option<String>,
    vuag_at: Option<String>,
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
        let timed = [
            (&row.portfolio_index, &row.portfolio_at),
            (&row.vuag_index, &row.vuag_at),
        ];
        if timed.into_iter().any(|(level, at)| {
            level.is_some() != at.is_some()
                || at.as_deref().is_some_and(|at| {
                    instant(at).map_or(true, |time| {
                        time.offset().local_minus_utc() != 0 || time.date_naive() != row.date
                    })
                })
        }) {
            return None;
        }
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

pub(super) struct Evidence<'a> {
    pub input: Option<&'a serde_json::Value>,
    pub as_of: Option<&'a str>,
    pub covered: approved::Coverage,
    pub events: &'a [CheckedEvent<'a>],
}

struct Sample {
    start: NaiveDate,
    end: NaiveDate,
    portfolio_ratio: f64,
    vuag_ratio: Option<f64>,
    rate_pct: Option<String>,
    nav: Option<f64>,
}

fn legacy_samples(series: &Series, range: &RiskRange) -> Vec<Sample> {
    let rows = &series.rows[series.rows.partition_point(|row| row.date < range.start)
        ..series.rows.partition_point(|row| row.date <= range.end)];
    rows[rows.len().saturating_sub(MAX_DAILY + 1)..]
        .windows(2)
        .filter_map(|rows| {
            let (a, b) = (&rows[0], &rows[1]);
            Some(Sample {
                start: a.date,
                end: b.date,
                portfolio_ratio: price(&b.portfolio_index)? / price(&a.portfolio_index)?,
                vuag_ratio: price(&b.vuag_index)
                    .zip(price(&a.vuag_index))
                    .map(|(b, a)| b / a),
                rate_pct: a.bank_rate_pct.clone(),
                nav: price(&b.portfolio_value_gbp),
            })
        })
        .collect()
}

pub(super) fn calculate(
    intervals: &[Interval],
    days: &[Day],
    range: &RiskRange,
    evidence: Evidence,
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
        "valuation_dates":days.iter().filter(|row| row.status == "observed").count(),
        "worst":worst.map(|row| serde_json::json!({"return_pct":row.growth.as_ref().map(pct),
                "start_at":row.start_at,"end_at":row.end_at})),
    });

    let reviewed = evidence
        .input
        .zip(evidence.as_of)
        .and_then(|(input, as_of)| {
            (input.get("basis").and_then(|field| field.as_str()) == Some(risk_sessions::BASIS))
                .then(|| Reviewed::parse(input, as_of).ok())
                .flatten()
        });
    let series = evidence.input.and_then(validated);
    let source = reviewed
        .as_ref()
        .map(|data| &data.source)
        .or_else(|| series.as_ref().map(|data| &data.source));
    let (samples, session_performance) = if let Some(data) = &reviewed {
        approved::calculate(data, range, evidence.covered, evidence.events)
    } else {
        (
            series
                .as_ref()
                .map(|series| legacy_samples(series, range))
                .unwrap_or_default(),
            serde_json::Value::Null,
        )
    };
    let holding_correlation = reviewed.as_ref().map_or_else(
        || serde_json::json!({"state":"awaiting_approved_holding_series"}),
        |data| holdings::calculate(data, range.start, range.end),
    );
    let mut portfolio = Vec::new();
    let mut excess = Vec::new();
    let mut matched_portfolio = Vec::new();
    let mut matched_vuag = Vec::new();
    let mut regression_portfolio = Vec::new();
    let mut regression_vuag = Vec::new();
    let mut losses = Vec::new();
    let (mut first_date, mut last_date, mut nav) = (None, None, None);
    for sample in samples {
        let ratio = sample.portfolio_ratio;
        let p = ratio.ln();
        if !p.is_finite() {
            continue;
        }
        first_date.get_or_insert(sample.start);
        last_date = Some(sample.end);
        nav = sample.nav;
        portfolio.push(p);
        losses.push((1.0 - ratio) * 100.0);
        let rf = bank_rate::opening_rate(sample.start)
            .map(|pct| (pct / 100.0).ln_1p() / ANNUAL_SESSIONS)
            .or_else(|| rate(&sample.rate_pct));
        if let Some(rf) = rf {
            excess.push(p - rf);
        }
        if let Some(v) = sample.vuag_ratio.map(f64::ln).filter(|v| v.is_finite()) {
            matched_portfolio.push(p);
            matched_vuag.push(v);
            if let Some(rf) = rf {
                regression_portfolio.push(p - rf);
                regression_vuag.push(v - rf);
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
    let state = match (source, evidence.input) {
        (Some(_), _) => "approved_series",
        (None, Some(_)) => "invalid_series",
        _ => "awaiting_approved_series",
    };
    serde_json::json!({
        "observed": observed, "daily_state": state,
        "source": source, "minimum_daily":MIN_DAILY,
        "session_performance":session_performance, "holding_correlation":holding_correlation,
        "daily_start":first_date,"daily_end":last_date, "measures":measures,
        "daily_coverage":{"portfolio":n,"vuag":m,"with_rate":excess.len(),
            "shortfall":MIN_DAILY.saturating_sub(n)},
        "bank_rate":{"source":bank_rate::SOURCE,"url":bank_rate::URL,
            "start_date":bank_rate::first_covered(),"verified_through":bank_rate::VERIFIED_THROUGH},
    })
}
