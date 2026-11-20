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

#[test]
fn applies_dated_sources_and_preserves_fund_residual_and_missing_values() {
    let mut request = fixture();
    request["positions"] = json!([
        {"ticker":"D", "isin":"DIRECT", "instrument_type":"STOCK",
          "current_value":"40", "account_currency":"GBP"},
        {"ticker":"E", "isin":"FUND", "instrument_type":"ETF",
          "current_value":"150.00000000000000000001", "account_currency":"GBP"},
        {"ticker":"G", "isin":"METAL", "instrument_type":"ETF",
          "current_value":"35", "account_currency":"GBP"},
        {"ticker":"S", "isin":"STALE", "instrument_type":"ETF",
          "current_value":"1", "account_currency":"GBP"},
        {"ticker":"X", "instrument_type":"STOCK"},
    ]);
    let source = json!({"as_of":"2026-01-01","url":"https://example.test/review"});
    request["classifications"] = json!({
        "DIRECT": {
            "sector":{"source":source,"weights":{"Industrials":"100"}},
            "issuer_domicile":{"source":source,"weights":{"Country A":"100"}}
        },
        "FUND":{
            "sector":{"source":source,"weights":{"Industrials":"50","Utilities":"25"}},
            "fund_markets":{"source":source,"weights":{"Country A":"60"}}
        },
        "METAL":{"non_equity":{"label":"gold","source":source}},
        "STALE":{"fund_markets":{"source":{"as_of":"2024-01-01","url":"https://example.test/old"},
            "weights":{"Country A":"100"}}}
    });
    let result = report(request.clone());
    let sectors = &result["sectors"];
    assert_eq!(sectors["classified"]["value"], "152.5000000000000000000075");
    assert_eq!(sectors["buckets"][0]["label"], "Industrials");
    assert_eq!(
        sectors["buckets"][0]["members"]["E"]["value"],
        "75.000000000000000000005"
    );
    assert_eq!(sectors["buckets"][0]["members"]["E"]["holding_pct"], "50");
    assert_eq!(sectors["buckets"][1]["label"], "Utilities");
    assert_eq!(
        sectors["buckets"][2]["label"],
        "Outside equity sectors · Gold"
    );
    assert_eq!(sectors["buckets"][3]["value"], "38.5000000000000000000025");
    assert!(sectors["buckets"][3]["members"]["X"]["value"].is_null());
    assert_eq!(result["issuer_domiciles"]["classified"]["value"], "40");
    assert_eq!(
        result["fund_markets"]["classified"]["value"],
        "90.000000000000000000006"
    );
    assert_eq!(
        result["fund_markets"]["observed"]["value"],
        "151.00000000000000000001"
    );
    assert!(result["fund_markets"]["sources"]["S"].is_null());
    assert_eq!(
        result["fund_markets"]["sources"]["E"]["as_of"],
        "2026-01-01"
    );

    request["classifications"]["FUND"]["fund_markets"]["weights"]["Country B"] = json!("41");
    let overallocated = report(request);
    assert_eq!(overallocated["fund_markets"]["classified"]["value"], "0");
    assert_eq!(
        overallocated["fund_markets"]["buckets"][0]["value"],
        "151.00000000000000000001"
    );
}

#[test]
fn dated_regulatory_fund_report_can_extend_the_factsheet_window() {
    let mut request = fixture();
    request["positions"] = json!([{"ticker":"TRUST","isin":"FUND","instrument_type":"STOCK",
        "current_value":"100","account_currency":"GBP"}]);
    request["classifications"] = json!({"FUND":{"fund_markets":{
        "source":{"as_of":"2025-08-01","url":"https://example.test/report","regulatory_report":true},
        "weights":{"Region A":"100"}
    }}});
    let qualified = report(request.clone());
    assert_eq!(qualified["fund_markets"]["classified"]["value"], "100");
    assert!(qualified["issuer_domiciles"]["buckets"]
        .as_array()
        .unwrap()
        .is_empty());
    assert_eq!(
        qualified["fund_markets"]["sources"]["TRUST"]["regulatory_report"],
        true
    );

    request["classifications"]["FUND"]["fund_markets"]["source"]["regulatory_report"] =
        json!(false);
    assert_eq!(report(request)["fund_markets"]["classified"]["value"], "0");
}
