//! Admission of reviewed GBP session evidence shared by the offline check and WASM.
use crate::{decimal, instant, Error, Result};
use bigdecimal::{BigDecimal, ToPrimitive};
use chrono::{DateTime, FixedOffset, NaiveDate};
use serde::{Deserialize, Deserializer};
use serde_json::{json, Value};
use std::collections::BTreeSet;

pub(crate) const BASIS: &str = "reviewed_gbp_session_marks_v2";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Reviewed {
    pub basis: String,
    pub source: String,
    pub reviewed_at: String,
    calendar_evidence: String,
    valuation_evidence: String,
    benchmark_evidence: Option<String>,
    pub sessions: Vec<Session>,
    pub holdings: Option<Holdings>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Session {
    pub date: NaiveDate,
    pub cutoff_at: String,
    pub portfolio_value_gbp: Option<String>,
    portfolio_at: Option<String>,
    pub vuag_index: Option<String>,
    pub vuag_close_at: Option<String>,
    vuag_at: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Holdings {
    pub as_of: String,
    evidence: String,
    pub instruments: Vec<Instrument>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Instrument {
    pub ticker: String,
    pub weight_pct: String,
    #[serde(deserialize_with = "parse_levels")]
    pub levels: Vec<Option<f64>>,
}

fn label(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 256 && !value.chars().any(char::is_control)
}

pub(crate) fn level(value: &str) -> Option<f64> {
    let price = decimal(value).ok()?.to_f64()?;
    (price.is_finite() && price > 0.0).then_some(price)
}

fn parse_levels<'de, D: Deserializer<'de>>(
    source: D,
) -> std::result::Result<Vec<Option<f64>>, D::Error> {
    Vec::<Option<String>>::deserialize(source)?
        .into_iter()
        .map(|mark| {
            mark.as_deref()
                .map(|mark| {
                    level(mark).ok_or_else(|| serde::de::Error::custom("holding_level_invalid"))
                })
                .transpose()
        })
        .collect()
}

fn utc(value: &str) -> Result<DateTime<FixedOffset>> {
    instant(value)
        .ok()
        .filter(|time| time.offset().local_minus_utc() == 0)
        .ok_or(Error("session_timestamp_invalid"))
}

fn mark(
    value: Option<&str>,
    observed: Option<&str>,
    expected: Option<DateTime<FixedOffset>>,
) -> Result<()> {
    if let (Some(value), Some(at), Some(expected)) = (value, observed, expected) {
        if level(value).is_some() && utc(at)? == expected {
            return Ok(());
        }
    } else if value.is_none() && observed.is_none() {
        return Ok(());
    }
    Err(Error("session_mark_invalid"))
}

impl Reviewed {
    pub(crate) fn parse(input: &Value, as_of: &str) -> Result<Self> {
        let data: Self =
            serde_json::from_value(input.clone()).map_err(|_| Error("session_evidence_invalid"))?;
        let reviewed = utc(&data.reviewed_at)?;
        if data.basis != BASIS
            || reviewed > utc(as_of)?
            || !label(&data.source)
            || !label(&data.calendar_evidence)
            || !label(&data.valuation_evidence)
            || data
                .benchmark_evidence
                .as_deref()
                .is_some_and(|value| !label(value))
            || !(2..=367).contains(&data.sessions.len())
            || data
                .sessions
                .windows(2)
                .any(|rows| rows[0].date >= rows[1].date)
        {
            return Err(Error("session_evidence_invalid"));
        }
        for row in &data.sessions {
            let cutoff = utc(&row.cutoff_at)?;
            let close = row.vuag_close_at.as_deref().map(utc).transpose()?;
            if cutoff.date_naive() != row.date
                || cutoff > reviewed
                || close.is_some_and(|at| at.date_naive() != row.date || at > cutoff)
                || row.vuag_index.is_some() && data.benchmark_evidence.is_none()
            {
                return Err(Error("session_calendar_invalid"));
            }
            mark(
                row.portfolio_value_gbp.as_deref(),
                row.portfolio_at.as_deref(),
                Some(cutoff),
            )?;
            mark(row.vuag_index.as_deref(), row.vuag_at.as_deref(), close)?;
        }
        if let Some(holdings) = &data.holdings {
            holdings.validate(data.sessions.len(), reviewed)?;
        }
        Ok(data)
    }
}

impl Holdings {
    fn validate(&self, sessions: usize, reviewed: DateTime<FixedOffset>) -> Result<()> {
        if utc(&self.as_of)? > reviewed
            || !label(&self.evidence)
            || !(1..=128).contains(&self.instruments.len())
        {
            return Err(Error("holding_series_invalid"));
        }
        let mut weight = BigDecimal::default();
        let mut seen = BTreeSet::new();
        for row in &self.instruments {
            crate::identity(&row.ticker)?;
            let valid_weight = decimal(&row.weight_pct)
                .ok()
                .filter(|amount| amount > &0 && amount <= &100)
                .ok_or(Error("holding_weight_invalid"))?;
            weight += valid_weight;
            if !seen.insert(&row.ticker) || row.levels.len() != sessions {
                return Err(Error("holding_series_invalid"));
            }
        }
        if weight > 100 {
            return Err(Error("holding_weight_invalid"));
        }
        Ok(())
    }
}

/// Structural check only. The operator signs off the underlying source, calendar,
/// coverage and usage rights before supplying the private manifest.
pub fn audit_json(input: &[u8], as_of: &str) -> Result<Value> {
    audit_with_funding(input, as_of, None)
}

pub fn audit_with_funding(input: &[u8], as_of: &str, funding: Option<&[u8]>) -> Result<Value> {
    if input.len() > 512 * 1024 {
        return Err(Error("session_evidence_limit"));
    }
    let raw = serde_json::from_slice(input).map_err(|_| Error("session_evidence_invalid"))?;
    let data = Reviewed::parse(&raw, as_of)?;
    let readiness = crate::performance::session_readiness(&raw, &data, as_of, funding)?;
    Ok(json!({
        "validation": "passed",
        "scheduled_sessions": data.sessions.len(),
        "portfolio_marks": data.sessions.iter().filter(|row| row.portfolio_value_gbp.is_some()).count(),
        "benchmark_marks": data.sessions.iter().filter(|row| row.vuag_index.is_some()).count(),
        "holding_series": data.holdings.as_ref().map_or(0, |holdings| holdings.instruments.len()),
        "readiness": readiness,
    }))
}
