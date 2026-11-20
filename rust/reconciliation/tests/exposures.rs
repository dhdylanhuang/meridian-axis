use axis_reconciliation::exposures::{calculate, Request};
use serde_json::{json, Value};

fn report(request: Value) -> Value {
    let request: Request = serde_json::from_value(request).unwrap();
    serde_json::to_value(calculate(request).unwrap()).unwrap()
}

fn fixture() -> Value {
    json!({
        "snapshot_id": "synthetic",
        "account_as_of": "2026-01-02T13:00:00Z",
        "positions_as_of": "2026-01-02T13:00:01Z",
        "currency": "GBP",
        "portfolio_value": "400",
        "invested_value": "300",
        "cash_components": {"availableToTrade": "70", "inPies": "30", "reservedForOrders": "29"},
        "positions": [
            {"ticker":"B", "current_value":"1.000000000000000000009", "account_currency":"GBP", "quote_currency":"USD"},
            {"ticker":"A", "current_value":"100.000000000000000000001", "account_currency":"GBP", "quote_currency":"USD"},
            {"ticker":"C", "current_value":"75", "account_currency":"GBP"},
        ]
    })
}

#[test]
fn uses_broker_controls_with_exact_amounts_and_independent_cash_components() {
    let result = report(fixture());
    assert_eq!(
        result["observed_holdings"],
        json!({"value":"176.00000000000000000001","portfolio_pct":"44","invested_pct":"58.67"})
    );
    assert_eq!(result["holdings"][0]["ticker"], "A");
    assert_eq!(result["holdings"][0]["portfolio_pct"], "25");
    assert_eq!(result["holdings"][0]["invested_pct"], "33.33");
    assert_eq!(result["quote_currencies"][0]["quote_currency"], "USD");
    assert_eq!(
        result["quote_currencies"][0]["value"],
        "101.00000000000000000001"
    );
    assert_eq!(result["quote_currencies"][1]["quote_currency"], Value::Null);
    assert_eq!(result["concentration"][1]["top"], 5);
    assert_eq!(result["concentration"][2]["position_count"], 3);
    assert_eq!(result["concentration"][2]["invested_pct"], "58.67");
    assert_eq!(
        result["cash_component_pct"],
        json!({
            "availableToTrade":"17.5","inPies":"7.5","reservedForOrders":"7.25"
        })
    );
}

#[test]
fn incompatible_values_and_denominators_are_visible_without_renormalizing() {
    let mut input = fixture();
    input["positions"][1]["current_value"] = Value::Null;
    input["positions"][2]["account_currency"] = json!("USD");
    let result = report(input.clone());
    assert_eq!(result["missing_values"], 2);
    assert_eq!(result["holdings"][0]["ticker"], "B");
    assert_eq!(result["holdings"][0]["invested_pct"], "0.33");
    assert_eq!(result["quote_currencies"][0]["missing_values"], 1);
    assert!(result["quote_currencies"][1]["value"].is_null());
    assert!(result["concentration"][0]["value"].is_null());

    input["portfolio_value"] = json!("299");
    assert!(report(input.clone())["portfolio_denominator"].is_null());
    input["invested_value"] = json!("0");
    let result = report(input);
    assert!(result["invested_denominator"].is_null());
    assert!(result["holdings"][0]["invested_pct"].is_null());
    assert_eq!(result["portfolio_denominator"], "299");
}

#[test]
fn limits_rank_to_requested_counts_and_rounds_half_up_once() {
    let mut input = fixture();
    input["positions"] = json!((1..=11)
        .map(|i| json!({
            "ticker":format!("S{i:02}"),"current_value":i.to_string(),"account_currency":"GBP"
        }))
        .collect::<Vec<_>>());
    input["cash_components"]["reservedForOrders"] = json!("0.02");
    let result = report(input);
    assert_eq!(result["concentration"][0]["value"], "11");
    assert_eq!(result["concentration"][1]["value"], "45");
    assert_eq!(result["concentration"][2]["value"], "65");
    assert_eq!(result["cash_component_pct"]["reservedForOrders"], "0.01");
}
