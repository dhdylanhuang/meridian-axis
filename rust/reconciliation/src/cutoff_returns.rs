//! Returns for adjacent scheduled broker captures, with a separate approval policy.
use super::super::{growth, pct, CheckedEvent, Mark, RiskRange};
use super::{approved, statistics, Sample, MAX_DAILY};
use crate::{decimal, instant, text};
use bigdecimal::ToPrimitive;
use chrono::{DateTime, Datelike, FixedOffset, NaiveDate, Timelike, Weekday};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(in crate::performance) struct Capture {
    date: NaiveDate,
    target_at: String,
    captured_at: Option<String>,
    total_value_gbp: Option<String>,
    calendar_reviewed: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Approval {
    basis: String,
    effective_from: NaiveDate,
    effective_through: NaiveDate,
    reviewed_at: String,
    evidence: String,
}

fn utc(value: &str) -> Option<DateTime<FixedOffset>> {
    let at = instant(value).ok()?;
    (at.offset().local_minus_utc() == 0).then_some(at)
}

fn mark(row: &Capture, now: DateTime<FixedOffset>) -> Option<Mark> {
    let target = utc(&row.target_at)?;
    let captured = utc(row.captured_at.as_deref()?)?;
    if target.date_naive() != row.date
        || (
            target.hour(),
            target.minute(),
            target.second(),
            target.nanosecond(),
        ) != (22, 0, 0, 0)
        || captured > now
        || captured < target
        || (captured - target).num_milliseconds() >= 120_000
    {
        return None;
    }
    Some(Mark {
        time: captured,
        value: decimal(row.total_value_gbp.as_deref()?).ok()?,
    })
}

fn approval(raw: Option<&Value>, now: DateTime<FixedOffset>) -> Option<Approval> {
    let review: Approval = serde_json::from_value(raw?.clone()).ok()?;
    (review.basis == "trading212_fixed_cutoff_gbp_v1"
        && review.effective_from < review.effective_through
        && utc(&review.reviewed_at)? <= now
        && !review.evidence.trim().is_empty()
        && review.evidence.len() <= 256
        && !review.evidence.chars().any(char::is_control))
    .then_some(review)
}

pub(in crate::performance) fn calculate(
    observations: &[Capture],
    range: &RiskRange,
    as_of: Option<&str>,
    policy: Option<&Value>,
    covered: approved::Coverage,
    events: &[CheckedEvent],
) -> Option<Value> {
    let now = utc(as_of?)?;
    if observations.len() > 367
        || observations
            .windows(2)
            .any(|pair| pair[0].date >= pair[1].date)
        || observations.iter().any(|row| {
            row.date > now.date_naive()
                || matches!(row.date.weekday(), Weekday::Sat | Weekday::Sun)
                || (row.captured_at.is_some() != row.total_value_gbp.is_some())
        })
    {
        return None;
    }
    let policy_review = approval(policy, now);
    let approval_state = match (&policy_review, policy) {
        (Some(_), _) => "approved",
        (None, Some(_)) => "invalid_policy",
        _ => "awaiting_review",
    };
    let left = observations.partition_point(|row| row.date < range.start);
    let right = observations.partition_point(|row| row.date <= range.end);
    let rows = &observations[left.max(right.saturating_sub(MAX_DAILY + 1))..right];
    let marks: Vec<_> = rows.iter().map(|row| mark(row, now)).collect();
    let mut samples = Vec::new();
    let mut intervals = Vec::new();
    let mut latest = None;
    let mut current = None;
    for (i, pair) in rows.windows(2).enumerate() {
        let (start, end) = (&pair[0], &pair[1]);
        let result = if !start.calendar_reviewed || !end.calendar_reviewed {
            Err("calendar_unreviewed")
        } else {
            marks[i]
                .as_ref()
                .zip(marks[i + 1].as_ref())
                .ok_or("missing_cutoff_observation")
                .and_then(|(a, b)| growth(a, b, covered, events))
        };
        let factor = result.as_ref().ok().map(|(factor, _, _)| factor);
        approved::extend(
            &mut current,
            &mut latest,
            start.date,
            end.date,
            factor,
            None,
        );
        let accepted = factor.is_some()
            && policy_review.as_ref().is_some_and(|review| {
                review.effective_from <= start.date && end.date <= review.effective_through
            });
        if accepted {
            if let Some(portfolio_ratio) = factor
                .and_then(ToPrimitive::to_f64)
                .filter(|ratio| ratio.is_finite() && *ratio > 0.0)
            {
                samples.push(Sample {
                    start: start.date,
                    end: end.date,
                    portfolio_ratio,
                    vuag_ratio: None,
                    rate_pct: None,
                    nav: marks[i + 1].as_ref().and_then(|mark| mark.value.to_f64()),
                });
            }
        }
        intervals.push(json!({
            "start_date":start.date, "end_date":end.date,
            "return_pct":factor.map(pct), "reason":result.as_ref().err(),
            "external_flow_count":result.as_ref().ok().map(|row| row.2),
            "net_external_flow_gbp":result.as_ref().ok().map(|row| text(&row.1)),
            "approved":accepted,
        }));
    }
    let detail_start = intervals.len().saturating_sub(75);
    Some(json!({
        "basis":"trading212_fixed_cutoff_gbp_v1",
        "approval_state":approval_state,
        "latest": current.or(latest).map(approved::Stretch::report),
        "intervals":intervals[detail_start..],
        "approved_risk":policy_review.map(|_| statistics(samples)),
    }))
}
