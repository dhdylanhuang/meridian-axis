//! Deterministic direct-price shocks to eligible saved GBP holding values.
use crate::{decimal, instant, text, Error, Result};
use bigdecimal::BigDecimal;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Snapshot {
    source: String,
    basis: String,
    currency: String,
    total_value: String,
    account_retrieval: Capture,
    positions_retrieval: Capture,
    cash_components: CashComponents,
    positions: Vec<Position>,
}

#[derive(Deserialize)]
struct Capture {
    retrieval_completed_at: String,
}

#[derive(Deserialize)]
struct CashComponents {
    #[serde(rename = "availableToTrade")]
    available_to_trade: Option<String>,
}

#[derive(Deserialize)]
struct Position {
    ticker: String,
    name: Option<String>,
    instrument_type: Option<String>,
    account_currency: Option<String>,
    current_value: Option<String>,
    quantity: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    scenarios: [Scenario; 2],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Scenario {
    price_shock_pct: String,
    scope: Scope,
    basket: Vec<String>,
    overrides: Vec<Override>,
}

#[derive(Deserialize, Serialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Scope {
    All,
    Basket,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Override {
    ticker: String,
    price_shock_pct: String,
}

#[derive(Serialize)]
struct HoldingImpact {
    ticker: String,
    name: Option<String>,
    opening_value: String,
    shock_pct: String,
    impact: String,
    stressed_value: String,
    basis: &'static str,
}

#[derive(Serialize)]
struct ScenarioResult {
    scope: Scope,
    price_shock_pct: String,
    stressed_value: String,
    impact: String,
    impact_pct: Option<String>,
    covered_value: String,
    covered_pct: Option<String>,
    covered_holdings: usize,
    uncovered_value: String,
    unshocked_marked_value: String,
    holdings: Vec<HoldingImpact>,
}

#[derive(Serialize)]
struct Report {
    method: &'static str,
    availability: &'static str,
    source: &'static str,
    currency: &'static str,
    capture_time: String,
    holdings_capture_time: String,
    opening_value: String,
    known_cash: Option<String>,
    unreconciled_value: String,
    total_holdings: usize,
    unvalued_holdings: usize,
    ineligible_holdings: usize,
    scenarios: [ScenarioResult; 2],
}

struct MarkedPosition<'a> {
    position: &'a Position,
    value: BigDecimal,
    eligible: bool,
}

fn shock(input: &str) -> Result<BigDecimal> {
    let rate = decimal(input).map_err(|_| Error("shock_invalid"))?;
    if rate < -100 || rate > 1_000 {
        return Err(Error("shock_invalid"));
    }
    Ok(rate)
}

fn marked(position: &Position) -> Option<MarkedPosition<'_>> {
    if position.account_currency.as_deref() != Some("GBP") {
        return None;
    }
    let value = decimal(position.current_value.as_deref()?).ok()?;
    let eligible = value > 0
        && matches!(position.instrument_type.as_deref(), Some("STOCK" | "ETF"))
        && position
            .quantity
            .as_deref()
            .and_then(|quantity| decimal(quantity).ok())
            .is_some_and(|quantity| quantity > 0);
    Some(MarkedPosition {
        position,
        value,
        eligible,
    })
}

fn simulate(
    scenario: Scenario,
    opening: &BigDecimal,
    marked: &[MarkedPosition<'_>],
    eligible: &BTreeSet<&str>,
    residual: &BigDecimal,
) -> Result<ScenarioResult> {
    let rate = shock(&scenario.price_shock_pct)?;
    let basket: BTreeSet<_> = scenario.basket.iter().map(String::as_str).collect();
    if basket.len() != scenario.basket.len()
        || !basket.is_subset(eligible)
        || (scenario.scope == Scope::Basket && basket.is_empty())
        || (scenario.scope == Scope::All && !basket.is_empty())
    {
        return Err(Error("stress_basket_invalid"));
    }
    let mut overrides = BTreeMap::new();
    for entry in &scenario.overrides {
        let ticker = entry.ticker.as_str();
        if !eligible.contains(ticker)
            || (scenario.scope == Scope::Basket && !basket.contains(ticker))
            || overrides
                .insert(ticker, shock(&entry.price_shock_pct)?)
                .is_some()
        {
            return Err(Error("stress_override_invalid"));
        }
    }

    let mut impact = BigDecimal::from(0);
    let mut covered = BigDecimal::from(0);
    let mut unshocked = BigDecimal::from(0);
    let mut rows = Vec::new();
    let percent_factor = BigDecimal::new(1.into(), 2);
    for row in marked {
        let ticker = row.position.ticker.as_str();
        if !row.eligible || (scenario.scope == Scope::Basket && !basket.contains(ticker)) {
            unshocked += &row.value;
            continue;
        }
        let (applied, basis) = match overrides.get(ticker) {
            Some(override_rate) => (override_rate, "holding_override"),
            None => (&rate, "scenario"),
        };
        let change = &row.value * applied * &percent_factor;
        impact += &change;
        covered += &row.value;
        let holding = HoldingImpact {
            ticker: ticker.to_owned(),
            name: row.position.name.clone(),
            opening_value: text(&row.value),
            shock_pct: text(applied),
            impact: text(&change),
            stressed_value: text(&(&row.value + &change)),
            basis,
        };
        rows.push((change, holding));
    }
    rows.sort_by(|(a, left), (b, right)| a.cmp(b).then_with(|| left.ticker.cmp(&right.ticker)));
    Ok(ScenarioResult {
        scope: scenario.scope,
        price_shock_pct: text(&rate),
        stressed_value: text(&(opening + &impact)),
        impact_pct: decimal_percent(&impact, opening),
        impact: text(&impact),
        covered_pct: decimal_percent(&covered, opening),
        covered_value: text(&covered),
        covered_holdings: rows.len(),
        uncovered_value: text(&(&unshocked + residual)),
        unshocked_marked_value: text(&unshocked),
        holdings: rows.into_iter().map(|(_, row)| row).collect(),
    })
}

pub(crate) fn calculate_json(input: &str) -> Result<String> {
    #[derive(Deserialize)]
    struct Input {
        snapshot: Snapshot,
        assumptions: Request,
    }
    if input.len() > 640 * 1024 {
        return Err(Error("input_size_limit"));
    }
    let Input {
        snapshot,
        assumptions,
    } = serde_json::from_str(input).map_err(|_| Error("stress_request_invalid"))?;
    if snapshot.source != "trading212"
        || snapshot.basis != "broker_reported"
        || snapshot.currency != "GBP"
        || snapshot.positions.len() > 1024
    {
        return Err(Error("snapshot_unavailable"));
    }
    let opening = decimal(&snapshot.total_value).map_err(|_| Error("snapshot_unavailable"))?;
    if opening < 0 {
        return Err(Error("snapshot_unavailable"));
    }
    let capture_time = snapshot.account_retrieval.retrieval_completed_at;
    let holdings_capture_time = snapshot.positions_retrieval.retrieval_completed_at;
    instant(&capture_time)?;
    instant(&holdings_capture_time)?;
    let cash = snapshot
        .cash_components
        .available_to_trade
        .as_deref()
        .map(decimal)
        .transpose()?;
    let mut tickers = BTreeSet::new();
    if snapshot
        .positions
        .iter()
        .any(|row| !tickers.insert(row.ticker.as_str()))
    {
        return Err(Error("snapshot_unavailable"));
    }
    let marked: Vec<_> = snapshot.positions.iter().filter_map(marked).collect();
    let eligible: BTreeSet<_> = marked
        .iter()
        .filter(|row| row.eligible)
        .map(|row| row.position.ticker.as_str())
        .collect();
    let marked_total: BigDecimal = marked.iter().map(|row| &row.value).sum();
    let zero = BigDecimal::from(0);
    let residual = &opening - marked_total - cash.as_ref().unwrap_or(&zero);
    let [first, second] = assumptions.scenarios;
    let report = Report {
        method: "direct_isa_stress_v1",
        availability: if eligible.is_empty() {
            "insufficient_data"
        } else {
            "available"
        },
        source: "trading212",
        currency: "GBP",
        capture_time,
        holdings_capture_time,
        opening_value: text(&opening),
        known_cash: cash.as_ref().map(text),
        unreconciled_value: text(&residual),
        total_holdings: snapshot.positions.len(),
        unvalued_holdings: snapshot.positions.len() - marked.len(),
        ineligible_holdings: marked.len() - eligible.len(),
        scenarios: [
            simulate(first, &opening, &marked, &eligible, &residual)?,
            simulate(second, &opening, &marked, &eligible, &residual)?,
        ],
    };
    serde_json::to_string(&report).map_err(|_| Error("output_failed"))
}

fn decimal_percent(numerator: &BigDecimal, denominator: &BigDecimal) -> Option<String> {
    (denominator > &0).then(|| text(&((numerator * BigDecimal::from(100)) / denominator).round(4)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    fn run(custom: Value) -> Result<Value> {
        let input = json!({
            "snapshot": {
                "source": "trading212", "basis": "broker_reported", "currency": "GBP",
                "total_value": "1000",
                "account_retrieval": {"retrieval_completed_at": "2029-04-30T21:59:00Z"},
                "positions_retrieval": {"retrieval_completed_at": "2029-04-30T21:59:01Z"},
                "cash_components": {"availableToTrade": "100","reservedForOrders":"20"},
                "positions": [
                    {"ticker":"ALPHA","name":"Synthetic Alpha","quantity":"1","account_currency":"GBP",
                        "instrument_type":"STOCK","current_value":"500"},
                    {"ticker":"BETA","name":"Synthetic Beta","quantity":"1","account_currency":"GBP",
                        "instrument_type":"ETF","current_value":"300"},
                    {"ticker":"GAMMA","quantity":"1","account_currency":"GBP","current_value":null},
                    {"ticker":"DELTA","quantity":"1","account_currency":"GBP","current_value":"25"}
                ]
            },
            "assumptions": {"scenarios": [
                {"scope":"all","price_shock_pct":"-10","basket":[],"overrides":[]}, custom,
            ]}
        });
        Ok(serde_json::from_str(&calculate_json(&input.to_string())?).unwrap())
    }

    #[test]
    fn direct_price_shock_preserves_gbp_cash() {
        let report =
            run(json!({"scope":"all","price_shock_pct":"-20","basket":[],"overrides":[]})).unwrap();
        assert_eq!(report["known_cash"], "100");
        assert_eq!(report["opening_value"], "1000");
        assert_eq!(report["scenarios"][0]["stressed_value"], "920");
        assert_eq!(report["scenarios"][0]["impact_pct"], "-8");
        assert_eq!(report["scenarios"][1]["stressed_value"], "840");
    }

    #[test]
    fn specific_shock_replaces_basket_shock_and_impacts_tie() {
        let report = run(
            json!({"scope":"basket","price_shock_pct":"-20","basket":["ALPHA","BETA"],
            "overrides":[{"ticker":"BETA","price_shock_pct":"-5"}]}),
        )
        .unwrap();
        let result = &report["scenarios"][1];
        assert_eq!(result["holdings"][0]["ticker"], "ALPHA");
        assert_eq!(result["holdings"][0]["impact"], "-100");
        assert_eq!(result["holdings"][1]["impact"], "-15");
        assert_eq!(result["holdings"][1]["basis"], "holding_override");
        assert_eq!(result["impact"], "-115");
        assert_eq!(result["stressed_value"], "885");
    }

    #[test]
    fn shows_uncovered_and_unreconciled_value_separately() {
        let report =
            run(json!({"scope":"basket","price_shock_pct":"0","basket":["ALPHA"],"overrides":[]}))
                .unwrap();
        let result = &report["scenarios"][1];
        assert_eq!(report["unvalued_holdings"], 1);
        assert_eq!(report["ineligible_holdings"], 1);
        assert_eq!(report["unreconciled_value"], "75");
        assert_eq!(result["covered_value"], "500");
        assert_eq!(result["covered_pct"], "50");
        assert_eq!(result["unshocked_marked_value"], "325");
        assert_eq!(result["uncovered_value"], "400");
        assert_eq!(result["covered_holdings"], 1);
    }

    #[test]
    fn rejects_empty_basket_and_out_of_scope_override() {
        let empty = json!({"scope":"basket","price_shock_pct":"-10","basket":[],"overrides":[]});
        assert_eq!(run(empty).unwrap_err(), Error("stress_basket_invalid"));
        let outside = json!({"scope":"basket","price_shock_pct":"-10","basket":["ALPHA"],
            "overrides":[{"ticker":"BETA","price_shock_pct":"-1"}]});
        assert_eq!(run(outside).unwrap_err(), Error("stress_override_invalid"));
    }
}
