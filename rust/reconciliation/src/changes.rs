//! Exact changes between two approved GBP broker observations.
use crate::exposures::{nonnegative, percent, portfolio_denominator};
use crate::{decimal, text, Error, Result};
use bigdecimal::BigDecimal;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

const METHOD: &str = "observed_portfolio_changes_v1";

#[derive(Deserialize)]
struct Request {
    start: Snapshot,
    end: Snapshot,
}

#[derive(Deserialize)]
struct Snapshot {
    #[serde(flatten)]
    capture: Capture,
    portfolio_value: Option<String>,
    invested_value: Option<String>,
    #[serde(default)]
    positions: Vec<Position>,
    #[serde(default)]
    cash: BTreeMap<String, Option<String>>,
    #[serde(default)]
    allocations: BTreeMap<String, Allocation>,
}

#[derive(Deserialize, Serialize)]
struct Capture {
    date: String,
    status: Status,
    observed_at: Option<String>,
    snapshot_id: Option<String>,
    account_captured_at: Option<String>,
    positions_captured_at: Option<String>,
}

#[derive(Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Status {
    Missing,
    Unavailable,
    Observed,
}

#[derive(Deserialize)]
struct Position {
    ticker: String,
    name: Option<String>,
    isin: Option<String>,
    quantity: Option<String>,
    current_value: Option<String>,
    account_currency: Option<String>,
}

#[derive(Deserialize)]
struct Allocation {
    classified: Amount,
    observed: Amount,
    buckets: Vec<Bucket>,
}

#[derive(Deserialize)]
struct Amount {
    value: Option<String>,
}

#[derive(Deserialize)]
struct Bucket {
    label: Option<String>,
    value: Option<String>,
    members: BTreeMap<String, Amount>,
}

#[derive(Serialize)]
struct Report {
    method: &'static str,
    source: &'static str,
    currency: &'static str,
    start: Endpoint,
    end: Endpoint,
    holdings: Vec<HoldingChange>,
    cash: Vec<Change>,
    top_five: Option<Change>,
    allocations: Vec<AllocationChange>,
}

#[derive(Serialize)]
struct Endpoint {
    #[serde(flatten)]
    capture: Capture,
    portfolio_denominator: Option<String>,
}

#[derive(Serialize)]
struct HoldingEnd {
    present: bool,
    name: Option<String>,
    isin: Option<String>,
    value: Option<String>,
    quantity: Option<String>,
    weight_pct: Option<String>,
}

#[derive(Serialize)]
struct HoldingChange {
    ticker: String,
    start: HoldingEnd,
    end: HoldingEnd,
    value_change: Option<String>,
    status: &'static str,
}

#[derive(Serialize)]
struct Change {
    label: Option<String>,
    start_value: String,
    end_value: String,
    value_change: String,
    start_weight_pct: String,
    end_weight_pct: String,
    weight_change_pp: String,
    members: Vec<Member>,
}

#[derive(Serialize)]
struct Member {
    ticker: String,
    start_value: Option<String>,
    end_value: Option<String>,
}

#[derive(Serialize)]
struct AllocationChange {
    dimension: &'static str,
    start_classified: Option<String>,
    end_classified: Option<String>,
    start_observed: Option<String>,
    end_observed: Option<String>,
    comparable: bool,
    buckets: Vec<Change>,
}

struct View<'a> {
    snapshot: &'a Snapshot,
    denominator: Option<BigDecimal>,
    positions: BTreeMap<&'a str, &'a Position>,
}

fn parsed(value: Option<&str>) -> Option<BigDecimal> {
    value.and_then(|value| decimal(value).ok())
}

impl Position {
    fn value(&self) -> Option<BigDecimal> {
        (self.account_currency.as_deref() == Some("GBP"))
            .then(|| nonnegative(self.current_value.as_deref()))
            .flatten()
    }
}

impl<'a> View<'a> {
    fn new(snapshot: &'a Snapshot) -> Result<Self> {
        if snapshot.positions.len() > 1024 {
            return Err(Error("changes_position_limit"));
        }
        let mut positions = BTreeMap::new();
        for position in &snapshot.positions {
            if parsed(position.quantity.as_deref()).is_some_and(|quantity| quantity == 0) {
                continue;
            }
            if positions
                .insert(position.ticker.as_str(), position)
                .is_some()
            {
                return Err(Error("changes_duplicate_position"));
            }
        }
        let denominator = portfolio_denominator(
            snapshot.portfolio_value.as_deref(),
            nonnegative(snapshot.invested_value.as_deref()).as_ref(),
        );
        Ok(Self {
            snapshot,
            denominator,
            positions,
        })
    }

    fn holding(&self, ticker: &str) -> HoldingEnd {
        let position = self.positions.get(ticker);
        let value = position.map_or_else(|| Some(BigDecimal::default()), |row| row.value());
        HoldingEnd {
            present: position.is_some(),
            name: position.and_then(|row| row.name.clone()),
            isin: position.and_then(|row| row.isin.clone()),
            quantity: position.map_or_else(
                || Some("0".into()),
                |row| parsed(row.quantity.as_deref()).as_ref().map(text),
            ),
            weight_pct: value
                .as_ref()
                .zip(self.denominator.as_ref())
                .map(|(v, d)| percent(v, d)),
            value: value.as_ref().map(text),
        }
    }

    fn top_five(&self) -> Option<BTreeMap<String, Amount>> {
        let mut ranked = self
            .positions
            .iter()
            .map(|(&ticker, row)| row.value().map(|value| (ticker, value)))
            .collect::<Option<Vec<_>>>()?;
        ranked.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(b.0)));
        Some(
            ranked
                .into_iter()
                .take(5)
                .map(|(ticker, value)| {
                    (
                        ticker.to_owned(),
                        Amount {
                            value: Some(text(&value)),
                        },
                    )
                })
                .collect(),
        )
    }

    fn complete_values(&self) -> bool {
        self.positions.values().all(|row| row.value().is_some())
    }
}

fn holdings(start: &View, end: &View) -> Vec<HoldingChange> {
    let tickers: BTreeSet<_> = start.positions.keys().chain(end.positions.keys()).collect();
    let mut ranked: Vec<_> = tickers
        .into_iter()
        .map(|&ticker| {
            let start = start.holding(ticker);
            let end = end.holding(ticker);
            let status = match (&start.quantity, &end.quantity) {
                _ if start
                    .isin
                    .as_ref()
                    .zip(end.isin.as_ref())
                    .is_some_and(|(a, b)| a != b) =>
                {
                    "identity_conflict"
                }
                _ if !start.present => "added",
                _ if !end.present => "closed",
                (Some(a), Some(b)) if a != b => "quantity_changed",
                (Some(_), Some(_)) => "quantity_unchanged",
                _ => "quantity_unavailable",
            };
            let delta = if status == "identity_conflict" {
                None
            } else {
                parsed(end.value.as_deref())
                    .zip(parsed(start.value.as_deref()))
                    .map(|(b, a)| b - a)
            };
            let change = HoldingChange {
                ticker: ticker.to_owned(),
                start,
                end,
                status,
                value_change: delta.as_ref().map(text),
            };
            (delta.map(|value| value.abs()), change)
        })
        .collect();
    ranked.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.ticker.cmp(&b.1.ticker)));
    ranked.into_iter().map(|(_, row)| row).collect()
}

fn members(
    start: Option<&BTreeMap<String, Amount>>,
    end: Option<&BTreeMap<String, Amount>>,
) -> Vec<Member> {
    let tickers: BTreeSet<_> = start
        .into_iter()
        .flat_map(|rows| rows.keys())
        .chain(end.into_iter().flat_map(|rows| rows.keys()))
        .collect();
    let value = |rows: Option<&BTreeMap<String, Amount>>, ticker: &str| {
        rows.and_then(|rows| rows.get(ticker))
            .and_then(|row| row.value.clone())
    };
    tickers
        .into_iter()
        .map(|ticker| Member {
            ticker: ticker.clone(),
            start_value: value(start, ticker),
            end_value: value(end, ticker),
        })
        .collect()
}

fn change(
    label: Option<String>,
    start: BigDecimal,
    end: BigDecimal,
    denominators: (&BigDecimal, &BigDecimal),
    members: Vec<Member>,
) -> Change {
    let start_pct = percent(&start, denominators.0);
    let end_pct = percent(&end, denominators.1);
    let weight_delta = decimal(&end_pct).expect("formatted percent")
        - decimal(&start_pct).expect("formatted percent");
    Change {
        label,
        start_value: text(&start),
        end_value: text(&end),
        value_change: text(&(end - start)),
        start_weight_pct: start_pct,
        end_weight_pct: end_pct,
        weight_change_pp: text(&weight_delta),
        members,
    }
}

fn allocation(
    dimension: &'static str,
    start: &View,
    end: &View,
    denominators: Option<(&BigDecimal, &BigDecimal)>,
    complete: bool,
) -> AllocationChange {
    let a = start.snapshot.allocations.get(dimension);
    let b = end.snapshot.allocations.get(dimension);
    let coverage = |allocation: Option<&Allocation>| {
        allocation
            .map(|row| (row.classified.value.clone(), row.observed.value.clone()))
            .unwrap_or_default()
    };
    let (start_classified, start_observed) = coverage(a);
    let (end_classified, end_observed) = coverage(b);
    let basis = a.zip(b).zip(denominators).filter(|_| complete);
    let mut buckets = Vec::new();
    if let Some(((a, b), denominators)) = basis {
        let mut pairs = BTreeMap::new();
        for bucket in &a.buckets {
            pairs.entry(bucket.label.clone()).or_insert((None, None)).0 = Some(bucket);
        }
        for bucket in &b.buckets {
            pairs.entry(bucket.label.clone()).or_insert((None, None)).1 = Some(bucket);
        }
        let bucket_value = |bucket: Option<&Bucket>| {
            bucket.map_or_else(
                || Some(BigDecimal::default()),
                |row| nonnegative(row.value.as_deref()),
            )
        };
        for (label, (a, b)) in pairs {
            if let Some((start, end)) = bucket_value(a).zip(bucket_value(b)) {
                buckets.push(change(
                    label,
                    start,
                    end,
                    denominators,
                    members(a.map(|r| &r.members), b.map(|r| &r.members)),
                ));
            }
        }
    }
    AllocationChange {
        dimension,
        start_classified,
        end_classified,
        start_observed,
        end_observed,
        comparable: basis.is_some(),
        buckets,
    }
}

pub fn calculate_json(input: &str) -> Result<String> {
    if input.len() > 1024 * 1024 {
        return Err(Error("input_size_limit"));
    }
    let Request { start, end } =
        serde_json::from_str(input).map_err(|_| Error("request_invalid"))?;
    let a = View::new(&start)?;
    let b = View::new(&end)?;
    let denominators = a.denominator.as_ref().zip(b.denominator.as_ref());
    let mut holdings_changes = Vec::new();
    let mut cash = Vec::new();
    let mut top_five = None;
    let mut allocations = Vec::new();
    if start.capture.status == Status::Observed && end.capture.status == Status::Observed {
        holdings_changes = holdings(&a, &b);
        let complete = a.complete_values() && b.complete_values();
        if let Some(denominators) = denominators {
            for key in ["availableToTrade", "inPies", "reservedForOrders"] {
                let value = |snapshot: &Snapshot| {
                    nonnegative(snapshot.cash.get(key).and_then(Option::as_deref))
                };
                if let Some((a, b)) = value(&start).zip(value(&end)) {
                    cash.push(change(Some(key.into()), a, b, denominators, Vec::new()));
                }
            }
            if let Some((a, b)) = a.top_five().zip(b.top_five()) {
                let sum = |rows: &BTreeMap<String, Amount>| {
                    rows.values()
                        .filter_map(|row| parsed(row.value.as_deref()))
                        .sum()
                };
                top_five = Some(change(
                    Some("Top five holdings".into()),
                    sum(&a),
                    sum(&b),
                    denominators,
                    members(Some(&a), Some(&b)),
                ));
            }
        }
        for dimension in ["sectors", "issuer_domiciles", "fund_markets"] {
            allocations.push(allocation(dimension, &a, &b, denominators, complete));
        }
    }
    let start_denominator = a.denominator.as_ref().map(text);
    let end_denominator = b.denominator.as_ref().map(text);
    let report = Report {
        method: METHOD,
        source: "trading212",
        currency: "GBP",
        start: Endpoint {
            capture: start.capture,
            portfolio_denominator: start_denominator,
        },
        end: Endpoint {
            capture: end.capture,
            portfolio_denominator: end_denominator,
        },
        holdings: holdings_changes,
        cash,
        top_five,
        allocations,
    };
    serde_json::to_string(&report).map_err(|_| Error("output_failed"))
}
