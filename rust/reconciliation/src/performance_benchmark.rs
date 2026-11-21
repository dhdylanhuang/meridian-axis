//! Matched-date comparison to a reviewed VUAG GBP close series.

use super::{pct, round, Interval};
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
    pricing_at: String,
    price_gbp: String,
}

#[derive(Serialize)]
struct Match<'a> {
    start_date: NaiveDate,
    end_date: NaiveDate,
    portfolio_start_at: &'a Option<String>,
    portfolio_end_at: &'a Option<String>,
    portfolio_pct: &'a Option<String>,
    start_close: Option<&'a Close>,
    end_close: Option<&'a Close>,
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
        let priced = instant(&row.pricing_at).ok()?;
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

pub(super) fn compare(
    chart: &[Interval],
    data: Option<&serde_json::Value>,
    as_of: Option<&str>,
) -> serde_json::Value {
    let series = data
        .zip(as_of)
        .and_then(|(input, cutoff)| parse(input, cutoff));
    let state = match (&data, &series) {
        (None, _) => "awaiting_approved_series",
        (Some(_), None) => "invalid_series",
        (_, Some(_)) => "qualified_series",
    };
    let eligible = chart.iter().filter(|row| row.growth.is_some());
    let eligible_count = eligible.clone().count();
    let Some(series) = &series else {
        return serde_json::json!({"state":state,"eligible_intervals":eligible_count,"matched_intervals":0});
    };
    let index: BTreeMap<_, _> = series
        .rows
        .iter()
        .map(|price| (price.date, price))
        .collect();
    let comparisons: Vec<_> = eligible
        .map(|interval| {
            let start_close = index.get(&interval.start_date).copied();
            let end_close = index.get(&interval.end_date).copied();
            let mut row = Match {
                start_date: interval.start_date,
                end_date: interval.end_date,
                portfolio_start_at: &interval.start_at,
                portfolio_end_at: &interval.end_at,
                portfolio_pct: &interval.return_pct,
                start_close,
                end_close,
                benchmark_pct: None,
                difference_pp: None,
                reason: Some("missing_benchmark_close"),
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
                (start_close, end_close, &interval.growth)
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
        "source":series.source,
        "reviewed_at":series.reviewed_at,
        "basis":series.basis,
        "eligible_intervals":eligible_count,
        "matched_intervals":matched,
        "intervals":comparisons,
    })
}
