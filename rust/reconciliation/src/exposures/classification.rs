use super::Exposure;
use crate::{decimal, text};
use bigdecimal::BigDecimal;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Deserialize)]
pub(super) struct Classification {
    pub(super) sector: Option<SourcedWeights>,
    pub(super) issuer_domicile: Option<SourcedWeights>,
    pub(super) fund_markets: Option<SourcedWeights>,
    pub(super) non_equity: Option<NonEquity>,
}

#[derive(Deserialize)]
pub(super) struct NonEquity {
    source: Evidence,
    label: NonEquityKind,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum NonEquityKind {
    Gold,
    FixedIncome,
}

#[derive(Deserialize)]
pub(super) struct SourcedWeights {
    source: Evidence,
    weights: BTreeMap<String, String>,
}

#[derive(Clone, Deserialize, Serialize)]
struct Evidence {
    url: String,
    as_of: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    regulatory_report: Option<bool>,
}

#[derive(Serialize)]
pub(super) struct Allocation {
    classified: Exposure,
    observed: Exposure,
    buckets: Vec<Bucket>,
    sources: BTreeMap<String, Evidence>,
}

#[derive(Serialize)]
struct Bucket {
    label: Option<String>,
    #[serde(flatten)]
    exposure: Exposure,
    members: BTreeMap<String, Contribution>,
}

#[derive(Serialize)]
struct Contribution {
    value: Option<String>,
    holding_pct: String,
}

#[derive(Default)]
struct Amounts {
    total: Option<BigDecimal>,
    members: BTreeMap<String, Contribution>,
}

#[derive(Default)]
pub(super) struct AllocationBuilder {
    buckets: BTreeMap<Option<String>, Amounts>,
    sources: BTreeMap<String, Evidence>,
    classified: Option<BigDecimal>,
    observed: Option<BigDecimal>,
}

impl Evidence {
    fn eligible(&self, date: NaiveDate, max_age: i64) -> bool {
        let Ok(source_date) = NaiveDate::parse_from_str(&self.as_of, "%Y-%m-%d") else {
            return false;
        };
        let max_age = if max_age == 120 && self.regulatory_report == Some(true) {
            180
        } else {
            max_age
        };
        (0..=max_age).contains(&(date - source_date).num_days())
            && self.url.starts_with("https://")
            && self.url.len() <= 512
            && !self.url.chars().any(char::is_whitespace)
    }
}

impl SourcedWeights {
    fn eligible_weights(&self, date: NaiveDate, max_age: i64) -> Option<Vec<(&str, BigDecimal)>> {
        if !self.source.eligible(date, max_age)
            || self.weights.is_empty()
            || self.weights.len() > 64
        {
            return None;
        }
        let entries: Option<Vec<_>> = self
            .weights
            .iter()
            .map(|(label, value)| {
                if label.is_empty() || label.len() > 80 || label.chars().any(char::is_control) {
                    return None;
                }
                let weight = decimal(value)
                    .ok()
                    .filter(|weight| weight > &0 && weight <= &100)?;
                Some((label.as_str(), weight * BigDecimal::new(1.into(), 2)))
            })
            .collect();
        entries.filter(|entries| entries.iter().map(|(_, weight)| weight).sum::<BigDecimal>() <= 1)
    }
}

impl AllocationBuilder {
    fn record(
        &mut self,
        label: Option<String>,
        ticker: &str,
        amount: Option<&BigDecimal>,
        weight: &BigDecimal,
    ) {
        let row = self.buckets.entry(label).or_default();
        row.members.insert(
            ticker.to_owned(),
            Contribution {
                value: amount.map(text),
                holding_pct: text(&(weight * 100_i32)),
            },
        );
        if let Some(amount) = amount {
            *row.total.get_or_insert_with(BigDecimal::default) += amount;
        }
    }

    pub(super) fn add_non_equity(
        &mut self,
        ticker: &str,
        value: Option<&BigDecimal>,
        evidence: &NonEquity,
        date: NaiveDate,
    ) -> bool {
        if !evidence.source.eligible(date, 550) {
            return false;
        }
        let label = match evidence.label {
            NonEquityKind::Gold => "Outside equity sectors · Gold",
            NonEquityKind::FixedIncome => "Outside equity sectors · Bonds",
        };
        self.sources
            .insert(ticker.to_owned(), evidence.source.clone());
        if let Some(value) = value {
            *self.observed.get_or_insert_with(BigDecimal::default) += value;
        }
        self.record(Some(label.to_owned()), ticker, value, &BigDecimal::from(1));
        true
    }

    pub(super) fn add(
        &mut self,
        ticker: &str,
        value: Option<&BigDecimal>,
        evidence: Option<&SourcedWeights>,
        date: NaiveDate,
        max_age: i64,
    ) {
        if let Some(value) = value {
            *self.observed.get_or_insert_with(BigDecimal::default) += value;
        }
        let Some((evidence, weights)) = evidence.and_then(|source| {
            source
                .eligible_weights(date, max_age)
                .map(|weights| (source, weights))
        }) else {
            self.record(None, ticker, value, &BigDecimal::from(1));
            return;
        };
        self.sources
            .insert(ticker.to_owned(), evidence.source.clone());
        let mut remaining = BigDecimal::from(1);
        for (label, weight) in weights {
            let amount = value.map(|value| value * &weight);
            remaining -= &weight;
            if let Some(amount) = &amount {
                *self.classified.get_or_insert_with(BigDecimal::default) += amount;
            }
            self.record(Some(label.to_owned()), ticker, amount.as_ref(), &weight);
        }
        if remaining > 0 {
            let amount = value.map(|value| value * &remaining);
            self.record(None, ticker, amount.as_ref(), &remaining);
        }
    }

    pub(super) fn finish(self, exposure: &impl Fn(Option<&BigDecimal>) -> Exposure) -> Allocation {
        let mut buckets: Vec<_> = self.buckets.into_iter().collect();
        buckets.sort_by(|a, b| {
            b.0.is_some()
                .cmp(&a.0.is_some())
                .then_with(|| b.1.total.cmp(&a.1.total))
                .then_with(|| a.0.cmp(&b.0))
        });
        let classified = self.classified.or_else(|| {
            buckets
                .iter()
                .any(|(_, row)| row.total.is_some())
                .then(BigDecimal::default)
        });
        Allocation {
            classified: exposure(classified.as_ref()),
            observed: exposure(self.observed.as_ref()),
            buckets: buckets
                .into_iter()
                .map(|(label, row)| Bucket {
                    label,
                    exposure: exposure(row.total.as_ref()),
                    members: row.members,
                })
                .collect(),
            sources: self.sources,
        }
    }
}
