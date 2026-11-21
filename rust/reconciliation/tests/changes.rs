use axis_reconciliation::changes::calculate_json;
use serde_json::{json, Value};

fn position(ticker: &str, quantity: &str, value: &str) -> Value {
    json!({"ticker":ticker,"quantity":quantity,"current_value":value,"account_currency":"GBP"})
}

fn snapshot(date: &str, positions: Vec<Value>, sector: Value) -> Value {
    json!({
        "date": date, "status": "observed", "portfolio_value":"1000","invested_value":"900",
        "positions":positions,"cash":{"availableToTrade":"100"},"allocations":{"sectors":sector}
    })
}

fn sector(value: &str) -> Value {
    json!({
        "classified":{"value":value}, "observed":{"value":value},
        "buckets":[{"label":"Technology","value":value,"members":{"A_EQ":{"value":value}}}]
    })
}

#[test]
fn ranks_signed_changes_and_links_saved_contributions() {
    let report: Value = serde_json::from_str(&calculate_json(&json!({
        "start": snapshot("2026-11-19", vec![position("A_EQ","2","200.0001"),position("B_EQ","1","100")], sector("200.0001")),
        "end": snapshot("2026-11-20", vec![position("A_EQ","3","230"), position("C_EQ","2","50")], sector("230"))
    }).to_string()).unwrap()).unwrap();
    let rows = report["holdings"].as_array().unwrap();
    assert_eq!(
        rows.iter()
            .map(|row| row["ticker"].as_str().unwrap())
            .collect::<Vec<_>>(),
        ["B_EQ", "C_EQ", "A_EQ"]
    );
    assert_eq!(rows[0]["status"], "closed");
    assert_eq!(rows[0]["value_change"], "-100");
    assert_eq!(rows[0]["end"]["quantity"], "0");
    assert_eq!(rows[1]["status"], "added");
    assert_eq!(rows[1]["value_change"], "50");
    assert_eq!(rows[2]["status"], "quantity_changed");
    assert_eq!(rows[2]["value_change"], "29.9999");
    assert_eq!(rows[2]["end"]["weight_pct"], "23");
    assert_eq!(report["start"]["portfolio_denominator"], "1000");
    assert_eq!(report["top_five"]["weight_change_pp"], "-2");
    assert_eq!(report["cash"][0]["weight_change_pp"], "0");
    let sectors = &report["allocations"][0];
    assert_eq!(sectors["start_classified"], "200.0001");
    assert_eq!(sectors["buckets"][0]["weight_change_pp"], "3");
    assert_eq!(sectors["buckets"][0]["members"][0]["ticker"], "A_EQ");
    assert_eq!(report["allocations"][1]["comparable"], false);
}

#[test]
fn preserves_a_missing_endpoint_without_treating_it_as_an_empty_portfolio() {
    let report: Value = serde_json::from_str(
        &calculate_json(
            &json!({
                "start": {"date":"2026-11-19","status":"missing"},
                "end": snapshot("2026-11-20", vec![position("A_EQ","1","200")], sector("200"))
            })
            .to_string(),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(report["start"]["status"], "missing");
    assert_eq!(report["end"]["status"], "observed");
    assert_eq!(report["holdings"], json!([]));
    assert!(report["top_five"].is_null());
}
