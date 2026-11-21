//! Observed account returns. Broker marks and completed funding evidence are inputs.
use crate::{currency, decimal, identity, instant, text, Error, Result};
use bigdecimal::{BigDecimal, RoundingMode};
use chrono::{DateTime, Datelike, FixedOffset, NaiveDate};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[path = "performance_benchmark.rs"]
mod benchmark;

#[path = "performance_drawdown.rs"]
mod drawdown;

#[path = "performance_risk.rs"]
mod risk;

#[derive(Deserialize)]
pub struct Request {
    days: Vec<Day>,
    coverage: Option<Coverage>,
    events: Vec<Event>,
    benchmark: Option<serde_json::Value>,
    benchmark_as_of: Option<String>,
    risk_range: Option<RiskRange>,
    risk_daily: Option<serde_json::Value>,
    risk_as_of: Option<String>,
}

#[derive(Deserialize)]
struct RiskRange {
    start: NaiveDate,
    end: NaiveDate,
}

#[derive(Deserialize)]
struct Day {
    date: NaiveDate,
    status: String,
    total_value: Option<String>,
    captured_at: Option<String>,
    vuag_mark: Option<benchmark::BrokerMark>,
}

#[derive(Deserialize, Serialize)]
struct Coverage {
    start_at: String,
    end_at: String,
    completed_at: String,
}

#[derive(Deserialize, Serialize)]
struct Event {
    reference: String,
    kind: String,
    currency: String,
    amount: String,
    at: String,
}

#[derive(Serialize)]
struct Funding<'a> {
    #[serde(flatten)]
    event: &'a Event,
    signed_gbp: bool,
}

struct CheckedEvent<'a> {
    row: &'a Event,
    time: DateTime<FixedOffset>,
    amount: BigDecimal,
}

impl CheckedEvent<'_> {
    fn signed_gbp(&self) -> bool {
        self.row.currency == "GBP"
            && match self.row.kind.as_str() {
                "DEPOSIT" => self.amount > 0,
                "WITHDRAW" => self.amount < 0,
                _ => false,
            }
    }

    fn internal(&self) -> bool {
        matches!(
            self.row.kind.as_str(),
            "FEE" | "INTEREST_ON_FREE_CASH" | "LENDING_INTEREST"
        )
    }
}

#[derive(Serialize)]
struct Interval {
    start_date: NaiveDate,
    end_date: NaiveDate,
    start_at: Option<String>,
    end_at: Option<String>,
    reason: Option<&'static str>,
    return_pct: Option<String>,
    external_flow_count: Option<usize>,
    net_external_flow: Option<String>,
    #[serde(skip)]
    growth: Option<BigDecimal>,
}

#[derive(Serialize)]
struct Stretch {
    start_date: NaiveDate,
    end_date: NaiveDate,
    days: usize,
}

#[derive(Serialize)]
struct Summary {
    reason: Option<&'static str>,
    start_date: Option<NaiveDate>,
    end_date: Option<NaiveDate>,
    intervals: usize,
    return_pct: Option<String>,
}

struct Mark {
    time: DateTime<FixedOffset>,
    value: BigDecimal,
}

fn mark(day: &Day) -> Result<Option<Mark>> {
    if day.status != "observed" {
        return Ok(None);
    }
    Ok(Some(Mark {
        time: instant(
            day.captured_at
                .as_deref()
                .ok_or(Error("performance_mark_invalid"))?,
        )?,
        value: decimal(
            day.total_value
                .as_deref()
                .ok_or(Error("performance_mark_invalid"))?,
        )?,
    }))
}

fn round(value: &BigDecimal, scale: i64) -> BigDecimal {
    value.with_scale_round(scale, RoundingMode::HalfEven)
}

fn pct(growth: &BigDecimal) -> String {
    text(&round(&((growth - 1) * 100), 6))
}

fn growth(
    start: &Mark,
    end: &Mark,
    covered: Option<(DateTime<FixedOffset>, DateTime<FixedOffset>)>,
    events: &[CheckedEvent],
) -> std::result::Result<(BigDecimal, BigDecimal, usize), &'static str> {
    let duration = (end.time - start.time)
        .num_microseconds()
        .filter(|duration| *duration > 0)
        .ok_or("capture_order_invalid")?;
    if start.value <= 0 || end.value <= 0 {
        return Err("nonpositive_account_value");
    }
    if !covered.is_some_and(|(first, through)| first <= start.time && through >= end.time) {
        return Err("funding_coverage_unverified");
    }
    let mut flow = BigDecimal::from(0);
    let mut weighted = &start.value * duration;
    let mut count = 0;
    for event in events
        .iter()
        .filter(|event| start.time <= event.time && event.time <= end.time)
    {
        if event.internal() {
            continue;
        }
        if !event.signed_gbp() {
            return Err("unclassified_or_unsupported_funding");
        }
        if event.time == start.time || event.time == end.time {
            return Err("funding_valuation_order_unknown");
        }
        let remaining = (end.time - event.time)
            .num_microseconds()
            .ok_or("capture_order_invalid")?;
        flow += &event.amount;
        weighted += &event.amount * remaining;
        count += 1;
    }
    if weighted <= 0 {
        return Err("nonpositive_weighted_capital");
    }
    // Multiply both sides of the Dietz fraction by elapsed microseconds. The
    // weights stay exact until the single decimal division.
    let gain = (&end.value - &start.value - &flow) * duration;
    if &weighted + &gain <= 0 {
        return Err("nonpositive_growth");
    }
    Ok((round(&((&weighted + gain) / weighted), 24), flow, count))
}

fn longest_span(eligible: impl IntoIterator<Item = bool>) -> Option<(usize, usize)> {
    let mut current_start = 0;
    let mut best = None;
    for (i, available) in eligible.into_iter().enumerate() {
        if !available {
            current_start = i + 1;
        } else if best.is_none_or(|(start, end)| i - current_start >= end - start) {
            best = Some((current_start, i));
        }
    }
    best
}

fn summarize(intervals: &[Interval], start: NaiveDate, end: NaiveDate) -> Summary {
    let mut result = Summary {
        reason: Some("period_boundary_unavailable"),
        start_date: Some(start),
        end_date: Some(end),
        intervals: 0,
        return_pct: None,
    };
    let Some(first) = intervals.iter().position(|row| row.start_date == start) else {
        return result;
    };
    let Some(last) = intervals.iter().position(|row| row.end_date == end) else {
        return result;
    };
    if last < first {
        return result;
    }
    let mut product = BigDecimal::from(1);
    for row in &intervals[first..=last] {
        let Some(value) = &row.growth else {
            result.reason = row.reason;
            return result;
        };
        product = round(&(product * value), 24);
        result.intervals += 1;
    }
    result.reason = None;
    result.return_pct = Some(pct(&product));
    result
}

pub fn calculate_json(input: &str) -> Result<String> {
    if input.len() > 640 * 1024 {
        return Err(Error("performance_input_limit"));
    }
    let request: Request = serde_json::from_str(input).map_err(|_| Error("request_invalid"))?;
    if !(90..=367).contains(&request.days.len())
        || request.events.len() > 1024
        || request
            .days
            .windows(2)
            .any(|pair| pair[0].date.succ_opt() != Some(pair[1].date))
    {
        return Err(Error("performance_window_invalid"));
    }
    let covered = request
        .coverage
        .as_ref()
        .map(|coverage| {
            let start = instant(&coverage.start_at)?;
            let end = instant(&coverage.end_at)?;
            if start > end || end > instant(&coverage.completed_at)? {
                return Err(Error("performance_coverage_invalid"));
            }
            Ok((start, end))
        })
        .transpose()?;
    let marks = request.days.iter().map(mark).collect::<Result<Vec<_>>>()?;
    let mut events = Vec::with_capacity(request.events.len());
    let mut seen = BTreeSet::new();
    for row in &request.events {
        identity(&row.reference)?;
        currency(&row.currency)?;
        if !seen.insert(&row.reference) {
            return Err(Error("performance_duplicate_event"));
        }
        events.push(CheckedEvent {
            row,
            time: instant(&row.at)?,
            amount: decimal(&row.amount)?,
        });
    }
    events.sort_by(|a, b| {
        b.time
            .cmp(&a.time)
            .then(a.row.reference.cmp(&b.row.reference))
    });
    let chart_start = request.days.len() - 90;
    let first_chart_date = request.days[chart_start].date;
    let mut intervals = Vec::with_capacity(89);
    for (i, days) in request.days.windows(2).enumerate() {
        let mut row = Interval {
            start_date: days[0].date,
            end_date: days[1].date,
            start_at: days[0].captured_at.clone(),
            end_at: days[1].captured_at.clone(),
            reason: Some("missing_valuation"),
            return_pct: None,
            external_flow_count: None,
            net_external_flow: None,
            growth: None,
        };
        if let (Some(start), Some(end)) = (&marks[i], &marks[i + 1]) {
            match growth(start, end, covered, &events) {
                Ok((factor, flow, count)) => {
                    row.reason = None;
                    row.return_pct = Some(pct(&factor));
                    row.growth = Some(factor);
                    row.external_flow_count = Some(count);
                    row.net_external_flow = Some(text(&flow));
                }
                Err(reason) => row.reason = Some(reason),
            }
        }
        intervals.push(row);
    }
    let chart_intervals = &intervals[chart_start..];
    if let Some(range) = request.risk_range {
        let start = intervals
            .iter()
            .position(|row| row.start_date == range.start);
        let end = intervals.iter().position(|row| row.end_date == range.end);
        let (Some(first), Some(last)) = (start, end) else {
            return Err(Error("risk_range_invalid"));
        };
        if first > last {
            return Err(Error("risk_range_invalid"));
        }
        let selected = &intervals[first..=last];
        return serde_json::to_string(&serde_json::json!({
            "method": "modified_dietz_observed_v1",
            "drawdown": drawdown::calculate(selected),
            "metrics": risk::calculate(
                selected, &request.days[first..=last+1], &range,
                risk::Evidence { input: request.risk_daily.as_ref(), as_of: request.risk_as_of.as_deref(),
                                covered, events: &events },
            ),
        }))
        .map_err(|_| Error("performance_output_invalid"));
    }
    let funding: Vec<_> = events
        .iter()
        .filter(|event| !event.internal() && event.time.date_naive() >= first_chart_date)
        .map(|event| Funding {
            event: event.row,
            signed_gbp: event.signed_gbp(),
        })
        .collect();
    let latest = chart_intervals
        .iter()
        .rev()
        .find(|row| row.growth.is_some());
    let longest_valuation =
        longest_span(marks[chart_start..].iter().map(Option::is_some)).map(|(first, last)| {
            Stretch {
                start_date: request.days[chart_start + first].date,
                end_date: request.days[chart_start + last].date,
                days: last - first + 1,
            }
        });
    let longest_eligible = longest_span(chart_intervals.iter().map(|row| row.growth.is_some()))
        .map(|(first, last)| {
            summarize(
                chart_intervals,
                chart_intervals[first].start_date,
                chart_intervals[last].end_date,
            )
        });
    let end = request.days.last().expect("90-day window").date;
    let month_start = end
        .with_day(1)
        .and_then(|date| date.pred_opt())
        .ok_or(Error("date_invalid"))?;
    let year_start =
        NaiveDate::from_ymd_opt(end.year() - 1, 12, 31).ok_or(Error("date_invalid"))?;
    let eligible_end = latest.map_or(end, |row| row.end_date);
    let month_to_date = summarize(
        &intervals,
        month_start,
        if eligible_end > month_start {
            eligible_end
        } else {
            end
        },
    );
    let year_to_date = summarize(
        &intervals,
        year_start,
        if eligible_end > year_start {
            eligible_end
        } else {
            end
        },
    );
    serde_json::to_string(&serde_json::json!({
        "method": "modified_dietz_observed_v1",
        "funding_coverage": request.coverage,
        "funding": funding,
        "intervals": chart_intervals,
        "latest_eligible": latest,
        "longest_valuation": longest_valuation,
        "longest_eligible": longest_eligible,
        "month_to_date": month_to_date,
        "year_to_date": year_to_date,
        "drawdown": drawdown::calculate(chart_intervals),
        "benchmark": benchmark::compare(chart_intervals, &request.days[chart_start..], request.benchmark.as_ref(), request.benchmark_as_of.as_deref()),
    }))
    .map_err(|_| Error("performance_output_invalid"))
}
