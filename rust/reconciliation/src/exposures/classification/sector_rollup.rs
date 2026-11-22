use super::{Allocation, Bucket, Contribution};
use crate::exposures::{nonnegative, percent, Exposure, Weights};
use crate::{decimal, text, Error, Result};
use bigdecimal::BigDecimal;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

/// Broad reporting crosswalk for reviewed source categories. Unknown labels retain
/// their identity so an unfamiliar manager category does not invent coverage.
fn broad_sector(label: &str) -> &str {
    match label {
        "ICB · Technology"
        | "Baillie Gifford · Technology"
        | "J.P. Morgan · Technology – Semi & Hardware"
        | "J.P. Morgan · Technology – Software" => "Information Technology",
        "ICB · Telecommunications"
        | "Baillie Gifford · Telecommunications"
        | "J.P. Morgan · Media" => "Communication Services",
        "ICB · Basic Materials"
        | "Baillie Gifford · Basic Materials"
        | "J.P. Morgan · Basic Industries" => "Materials",
        "ICB · Financials"
        | "Baillie Gifford · Financials"
        | "J.P. Morgan · Banks"
        | "J.P. Morgan · Financial Services"
        | "J.P. Morgan · Insurance" => "Financials",
        "ICB · Industrials"
        | "Baillie Gifford · Industrials"
        | "J.P. Morgan · Industrial Cyclical" => "Industrials",
        "ICB · Consumer Discretionary"
        | "Baillie Gifford · Consumer Discretionary"
        | "J.P. Morgan · Retail"
        | "J.P. Morgan · Automobiles & Auto Parts" => "Consumer Discretionary",
        "ICB · Health Care"
        | "Baillie Gifford · Healthcare"
        | "J.P. Morgan · Pharmaceutical/Medical Technology"
        | "J.P. Morgan · Health Services & Systems" => "Health Care",
        "ICB · Real Estate" | "J.P. Morgan · Property" => "Real Estate",
        "ICB · Consumer Staples" | "Baillie Gifford · Consumer Staples" => "Consumer Staples",
        "ICB · Energy" | "Baillie Gifford · Energy" | "J.P. Morgan · Energy" => "Energy",
        "ICB · Utilities" | "Baillie Gifford · Utilities" | "J.P. Morgan · Utilities" => {
            "Utilities"
        }
        _ => label,
    }
}

#[derive(Default)]
struct AggregatedBucket {
    value: Option<BigDecimal>,
    members: BTreeMap<String, AggregatedMember>,
}

#[derive(Default)]
struct AggregatedMember {
    value: Option<BigDecimal>,
    holding_pct: BigDecimal,
    labels: BTreeSet<String>,
}

fn add_value(total: &mut Option<BigDecimal>, value: Option<&str>) -> Result<()> {
    if let Some(value) = value {
        let amount = decimal(value)?;
        if amount < 0 {
            return Err(Error("sector_rollup_invalid"));
        }
        *total.get_or_insert_with(BigDecimal::default) += amount;
    }
    Ok(())
}

#[derive(Deserialize)]
struct Input {
    sectors: Allocation,
    portfolio_denominator: Option<String>,
    invested_denominator: Option<String>,
}

pub(crate) fn sector_rollup_json(input: &str) -> Result<String> {
    if input.len() > 512 * 1024 {
        return Err(Error("input_size_limit"));
    }
    let Input {
        mut sectors,
        portfolio_denominator,
        invested_denominator,
    } = serde_json::from_str(input).map_err(|_| Error("sector_rollup_invalid"))?;
    let positive = |value: Option<&str>| nonnegative(value).filter(|amount| amount > &0);
    let portfolio = positive(portfolio_denominator.as_deref());
    let invested = positive(invested_denominator.as_deref());
    let mut merged = BTreeMap::<Option<String>, AggregatedBucket>::new();
    for bucket in sectors.buckets {
        let key = bucket.label.as_deref().map(broad_sector).map(str::to_owned);
        let group = merged.entry(key).or_default();
        add_value(&mut group.value, bucket.exposure.value.as_deref())?;
        for (ticker, member) in bucket.members {
            let target = group.members.entry(ticker).or_default();
            add_value(&mut target.value, member.value.as_deref())?;
            target.holding_pct += decimal(&member.holding_pct)?;
            if let Some(label) = &bucket.label {
                target.labels.insert(label.clone());
            }
            target.labels.extend(member.source_labels);
        }
    }
    let mut ranked: Vec<_> = merged.into_iter().collect();
    ranked.sort_by(|(a, x), (b, y)| {
        b.is_some()
            .cmp(&a.is_some())
            .then_with(|| y.value.cmp(&x.value))
            .then_with(|| a.cmp(b))
    });
    let as_pct = |amount: Option<&BigDecimal>, denominator: Option<&BigDecimal>| {
        amount
            .zip(denominator)
            .map(|(value, basis)| percent(value, basis))
    };
    sectors.buckets = ranked
        .into_iter()
        .map(|(label, group)| {
            let members = group
                .members
                .into_iter()
                .map(|(ticker, member)| {
                    let source_labels = member.labels.into_iter().collect::<Vec<_>>();
                    let mapped = source_labels
                        .iter()
                        .any(|source| Some(source) != label.as_ref());
                    let contribution = Contribution {
                        value: member.value.as_ref().map(text),
                        holding_pct: text(&member.holding_pct),
                        source_labels: if mapped { source_labels } else { Vec::new() },
                    };
                    (ticker, contribution)
                })
                .collect();
            Bucket {
                label,
                exposure: Exposure {
                    value: group.value.as_ref().map(text),
                    weights: Weights {
                        portfolio_pct: as_pct(group.value.as_ref(), portfolio.as_ref()),
                        invested_pct: as_pct(group.value.as_ref(), invested.as_ref()),
                    },
                },
                members,
            }
        })
        .collect();
    serde_json::to_string(&sectors).map_err(|_| Error("output_failed"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    #[test]
    fn sector_rollup_merges_source_values_and_deduplicates_contributors() {
        let observed =
            json!({"value":"73.000000000000001", "portfolio_pct":"73", "invested_pct":"91.25"});
        let input = json!({
        "portfolio_denominator":"100", "invested_denominator":"80",
        "sectors":{"classified":{"value":"70"}, "observed":observed,
            "sources":{"FUND":{"url":"https://example.test/report", "as_of":"2026-09-01"}},
            "buckets":[
                {"label":"Information Technology","value":"10.000000000000001",
                    "members":{"STOCK":{"value":"10.000000000000001","holding_pct":"100"}}},
                {"label":"ICB · Technology","value":"25", "members":{"ETF":{"value":"25","holding_pct":"50"}}},
                {"label":"J.P. Morgan · Technology – Software","value":"12",
                    "members":{"FUND":{"value":"12","holding_pct":"12"}}},
                {"label":"J.P. Morgan · Technology – Semi & Hardware","value":"8",
                    "members":{"FUND":{"value":"8","holding_pct":"8"}}},
                {"label":"Baillie Gifford · Telecommunications","value":"5",
                    "members":{"TRUST":{"value":"5","holding_pct":"10"}}},
                {"label":"Outside equity sectors · Gold","value":"10","members":{}},
                {"label":null,"value":"3","members":{"UNMARKED":{"value":null,"holding_pct":"100"}}}
            ]}});
        let report: Value =
            serde_json::from_str(&sector_rollup_json(&input.to_string()).unwrap()).unwrap();
        let buckets = report["buckets"].as_array().unwrap();
        assert_eq!(buckets.len(), 4);
        let tech = &buckets[0];
        assert_eq!(tech["label"], "Information Technology");
        assert_eq!(tech["value"], "55.000000000000001");
        assert_eq!(tech["portfolio_pct"], "55");
        assert_eq!(tech["invested_pct"], "68.75");
        assert_eq!(tech["members"].as_object().unwrap().len(), 3);
        assert_eq!(tech["members"]["FUND"]["value"], "20");
        assert_eq!(tech["members"]["FUND"]["holding_pct"], "20");
        assert_eq!(
            tech["members"]["FUND"]["source_labels"],
            json!([
                "J.P. Morgan · Technology – Semi & Hardware",
                "J.P. Morgan · Technology – Software"
            ])
        );
        assert_eq!(buckets[1]["label"], "Outside equity sectors · Gold");
        assert_eq!(buckets[2]["label"], "Communication Services");
        assert_eq!(buckets[3]["label"], Value::Null);
        assert_eq!(buckets[3]["members"]["UNMARKED"]["value"], Value::Null);
        assert_eq!(report["observed"], observed);
        assert_eq!(report["sources"], input["sectors"]["sources"]);
    }
}
