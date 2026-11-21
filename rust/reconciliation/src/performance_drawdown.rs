//! Drawdown on the most recent uninterrupted flow-adjusted return chain.
use super::{round, Interval};
use crate::text;
use bigdecimal::BigDecimal;
use serde::Serialize;

#[derive(Serialize)]
pub(super) struct Report<'a> {
    method: &'static str,
    start_at: &'a str,
    as_of: &'a str,
    intervals: usize,
    current_pct: String,
    current_peak_at: &'a str,
    worst_pct: String,
    worst_peak_at: Option<&'a str>,
    worst_trough_at: Option<&'a str>,
    later_unavailable_intervals: usize,
}

pub(super) fn calculate(intervals: &[Interval]) -> Option<Report<'_>> {
    let last = intervals.iter().rposition(|row| row.growth.is_some())?;
    let first = intervals[..last]
        .iter()
        .rposition(|row| row.growth.is_none())
        .map_or(0, |gap| gap + 1);
    let start_at = intervals[first].start_at.as_deref()?;
    let mut peak_at = start_at;
    let mut wealth = BigDecimal::from(1);
    let mut peak = wealth.clone();
    let mut current = BigDecimal::from(0);
    let mut worst = current.clone();
    let mut worst_peak_at = None;
    let mut worst_trough_at = None;
    for row in &intervals[first..=last] {
        let at = row.end_at.as_deref()?;
        wealth = round(&(wealth * row.growth.as_ref()?), 24);
        if wealth > peak {
            peak = wealth.clone();
            peak_at = at;
        }
        current = (BigDecimal::from(1) - &wealth / &peak) * 100;
        if current > worst {
            worst = current.clone();
            worst_peak_at = Some(peak_at);
            worst_trough_at = Some(at);
        }
    }

    Some(Report {
        method: "observed_flow_adjusted_drawdown_v1",
        start_at,
        as_of: intervals[last].end_at.as_deref()?,
        intervals: last - first + 1,
        current_pct: text(&round(&current, 6)),
        current_peak_at: peak_at,
        worst_pct: text(&round(&worst, 6)),
        worst_peak_at,
        worst_trough_at,
        later_unavailable_intervals: intervals.len() - 1 - last,
    })
}
