//! Matched-date comparison to observed VUAG GBP marks or reviewed closes.

use super::{pct, round, Day, Interval};
use crate::{decimal, instant, text};
use bigdecimal::BigDecimal;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Series {
    ticker: String,
    isin: String,
    currency: String,
    basis: String,
    source: String,
    reviewed_at: String,
    rows: Vec<Close>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Close {
    date: NaiveDate,
    #[serde(rename(deserialize = "pricing_at", serialize = "at"))]
    at: String,
    price_gbp: String,
}

#[derive(Serialize)]
struct Match<'a> {
    start_date: NaiveDate,
    end_date: NaiveDate,
    portfolio_start_at: &'a Option<String>,
    portfolio_end_at: &'a Option<String>,
    portfolio_pct: &'a Option<String>,
    start_mark: Option<&'a Close>,
    end_mark: Option<&'a Close>,
    benchmark_pct: Option<String>,
    difference_pp: Option<String>,
    reason: Option<&'static str>,
}

fn parse(input: &serde_json::Value, as_of: &str) -> Option<Series> {
    let cutoff = instant(as_of).ok()?;
    let data: Series = serde_json::from_value(input.clone()).ok()?;
    if data.ticker != "VUAG"
        || data.isin != "IE00BFMXXD54"
        || data.currency != "GBP"
        || data.basis != "split_adjusted_lse_market_close_accumulating"
        || data.source.trim().is_empty()
        || data.source.len() > 256
        || data.source.chars().any(char::is_control)
        || !(2..=367).contains(&data.rows.len())
    {
        return None;
    }
    let reviewed = instant(&data.reviewed_at).ok()?;
    if reviewed.offset().local_minus_utc() != 0
        || reviewed > cutoff
        || data.rows.windows(2).any(|row| row[0].date >= row[1].date)
    {
        return None;
    }
    for row in &data.rows {
        let priced = instant(&row.at).ok()?;
        if priced.offset().local_minus_utc() != 0
            || priced.date_naive() != row.date
            || priced > reviewed
            || decimal(&row.price_gbp).ok()? <= 0
        {
            return None;
        }
    }
    Some(data)
}

#[derive(Deserialize)]
pub(super) struct BrokerMark {
    at: String,
    price_gbp: String,
}

fn observed_marks(days: &[Day]) -> Vec<Close> {
    days.iter()
        .filter_map(|day| {
            let mark = day.vuag_mark.as_ref()?;
            let at = instant(&mark.at).ok()?;
            if day.status != "observed"
                || at.offset().local_minus_utc() != 0
                || at.date_naive() != day.date
                || decimal(&mark.price_gbp).ok()? <= 0
            {
                return None;
            }
            Some(Close {
                date: day.date,
                at: mark.at.clone(),
                price_gbp: mark.price_gbp.clone(),
            })
        })
        .collect()
}

pub(super) fn compare(
    chart: &[Interval],
    days: &[Day],
    data: Option<&serde_json::Value>,
    as_of: Option<&str>,
) -> serde_json::Value {
    let series = data
        .zip(as_of)
        .and_then(|(input, cutoff)| parse(input, cutoff));
    let eligible = chart.iter().filter(|row| row.growth.is_some());
    let eligible_count = eligible.clone().count();
    let observed;
    let (state, source, basis, reviewed_at, marks) = if let Some(series) = &series {
        (
            "qualified_series",
            series.source.as_str(),
            series.basis.as_str(),
            Some(series.reviewed_at.as_str()),
            series.rows.as_slice(),
        )
    } else {
        observed = observed_marks(days);
        if observed.is_empty() {
            let state = if data.is_some() {
                "invalid_series"
            } else {
                "awaiting_approved_series"
            };
            return serde_json::json!({"state":state,"eligible_intervals":eligible_count,"matched_intervals":0});
        }
        (
            "broker_observed",
            "Trading 212 holdings snapshots",
            "broker_observed_gbp_mark",
            None,
            observed.as_slice(),
        )
    };
    let index: BTreeMap<_, _> = marks.iter().map(|price| (price.date, price)).collect();
    let comparisons: Vec<_> = eligible
        .map(|interval| {
            let start_mark = index.get(&interval.start_date).copied();
            let end_mark = index.get(&interval.end_date).copied();
            let mut row = Match {
                start_date: interval.start_date,
                end_date: interval.end_date,
                portfolio_start_at: &interval.start_at,
                portfolio_end_at: &interval.end_at,
                portfolio_pct: &interval.return_pct,
                start_mark,
                end_mark,
                benchmark_pct: None,
                difference_pp: None,
                reason: Some(if state == "broker_observed" {
                    "missing_benchmark_mark"
                } else {
                    "missing_benchmark_close"
                }),
            };
            // The UTC capture date must match the session label at both ends. A
            // snapshot whose account capture crossed midnight is a different date.
            let capture_dates_match = interval
                .start_at
                .as_deref()
                .and_then(|value| instant(value).ok())
                .is_some_and(|value| value.date_naive() == interval.start_date)
                && interval
                    .end_at
                    .as_deref()
                    .and_then(|value| instant(value).ok())
                    .is_some_and(|value| value.date_naive() == interval.end_date);
            if !capture_dates_match {
                row.reason = Some("portfolio_capture_date_mismatch");
                return row;
            }
            if let (Some(first), Some(last), Some(portfolio)) =
                (start_mark, end_mark, &interval.growth)
            {
                let first_price = decimal(&first.price_gbp).expect("validated positive close");
                let last_price = decimal(&last.price_gbp).expect("validated positive close");
                let benchmark = round(&(last_price / first_price), 24);
                row.benchmark_pct = Some(pct(&benchmark));
                let spread: BigDecimal = (portfolio - &benchmark) * 100;
                row.difference_pp = Some(text(&round(&spread, 6)));
                row.reason = None;
            }
            row
        })
        .collect();
    let matched = comparisons
        .iter()
        .filter(|row| row.reason.is_none())
        .count();
    serde_json::json!({
        "state":state,
        "source":source,
        "reviewed_at":reviewed_at,
        "basis":basis,
        "eligible_intervals":eligible_count,
        "matched_intervals":matched,
        "intervals":comparisons,
    })
}
