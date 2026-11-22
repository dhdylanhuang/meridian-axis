use axis_reconciliation::meridian::calculate_json;
use chrono::{Days, NaiveDate};
use serde_json::{json, Value};

fn input() -> Value {
    let first = "2025-01-01".parse::<NaiveDate>().unwrap();
    let mut grid = Vec::new();
    let mut levels = [Vec::new(), Vec::new(), Vec::new()];
    let mut flags = vec![false; 261];
    flags[210] = true;
    let mut prices = [100.0_f64; 3];
    for i in 0..=260 {
        let date = first.checked_add_days(Days::new(i as u64)).unwrap();
        grid.push(json!({"date":date,"cutoff_at":format!("{date}T16:00:00Z")}));
        let factor = ((i * i % 37) as f64 - 18.0) / 1000.0;
        prices[0] *= 1.0 + factor;
        prices[1] *= 1.0 + if i < 110 { -factor } else { factor * 1.1 };
        if i != 210 {
            prices[2] *= 1.0 - factor * 0.2 + ((i % 7) as f64 - 3.0) / 1000.0;
        }
        for (k, price) in prices.iter().enumerate() {
            levels[k].push(if k == 2 && (95..=131).contains(&i) {
                Value::Null
            } else {
                json!(format!("{price:.10}"))
            });
        }
    }
    let as_of = "2025-09-20T19:30:00Z";
    let positions: Vec<_> = [
        ("AAA", "300"),
        ("BBB", "200"),
        ("CCC", "300"),
        ("DDD", "100"),
    ]
    .iter()
    .map(|(ticker, value)| {
        json!({
            "ticker":ticker,"name":ticker,"current_value":value,
            "account_currency":"GBP","quantity":"1","instrument_type":"STOCK",
        })
    })
    .collect();
    json!({"snapshot":{
        "source":"trading212","basis":"broker_reported","currency":"GBP","total_value":"1000",
        "account_retrieval":{"retrieval_completed_at":as_of},
        "positions_retrieval":{"retrieval_completed_at":as_of},
        "cash_components":{"availableToTrade":"50"},
        "exposures":{"sectors":{"buckets":[{"label":"Industrials","members":{"AAA":{}}},
            {"label":"Technology","members":{"BBB":{},"CCC":{}}}]}},
        "positions":positions
    },"now":as_of,"window":90,"reviewed":{
        "basis":"reviewed_gbp_session_marks_v2","source":"Synthetic",
        "reviewed_at":"2025-09-20T19:00:00Z","calendar_evidence":"synthetic grid",
        "valuation_evidence":"synthetic values","sessions":grid,
        "holdings":{"as_of":"2025-09-20T16:00:00Z","evidence":"synthetic adjusted prices","instruments":[
            {"ticker":"AAA","weight_pct":"5","levels":levels[0],"imputed":vec![false; 261]},
            {"ticker":"BBB","weight_pct":"5","levels":levels[1],"imputed":vec![false; 261]},
            {"ticker":"CCC","weight_pct":"5","levels":levels[2],"imputed":flags}
        ]}
    }})
}
fn run(value: &Value) -> Value {
    serde_json::from_str(&calculate_json(&value.to_string()).unwrap()).unwrap()
}

#[test]
fn meridian_gate_reconciles_approved_capital_with_no_statistics() {
    let mut req = input();
    req["reviewed"] = Value::Null;
    let result = run(&req);
    assert_eq!(result["state"], "awaiting_approved_holding_series");
    assert_eq!(result["n"], 0);
    assert_eq!(result["excluded_pct"], "90");
    assert_eq!(result["cash_pct"], "5");
    assert_eq!(result["residual_pct"], "5");
    assert!(result["matrix"].is_null());
    req["reviewed"] = json!({"invalid":true});
    assert_eq!(run(&req)["state"], "reviewed_evidence_invalid");
}

#[test]
fn meridian_matrix_attribution_and_history_use_one_frozen_complete_panel() {
    let mut req = input();
    let result = run(&req);
    assert_eq!(result["state"], "available");
    assert_eq!(result["selected_cluster"], json!([0, 1]));
    assert_eq!(result["n"], 90);
    assert_eq!(result["covered_pct"], "80");
    assert_eq!(result["group_totals"][0]["capital"], "50");
    let risk = result["risk"].as_array().unwrap();
    assert!((risk.iter().map(|v| v.as_f64().unwrap()).sum::<f64>() - 100.0).abs() < 1e-10);
    assert!(risk[2].as_f64().unwrap() < 0.0);
    let matrix = result["matrix"].as_array().unwrap();
    for i in 0..3 {
        assert_eq!(matrix[i][i], 1.0);
        for j in 0..3 {
            assert_eq!(matrix[i][j], matrix[j][i]);
            assert!(matrix[i][j].as_f64().unwrap().abs() <= 1.0);
        }
    }
    let points = result["history"].as_array().unwrap();
    assert!(points[0]["rho"].as_f64().unwrap() < -0.9);
    assert!(points
        .iter()
        .any(|p| p["rho"].is_null() && p["excluded"].as_u64().unwrap() > 30));
    let last = points.last().unwrap();
    assert_eq!(last["rho"], matrix[0][1]);
    assert_eq!(last["n"], result["n"]);
    assert_eq!(last["imputed"], 2);

    req["pair"] = json!([0, 1]);
    req["pair_only"] = json!(true);
    assert!(run(&req)["history"]
        .as_array()
        .unwrap()
        .iter()
        .all(|p| p["rho"].is_number()));

    req["pair"] = Value::Null;
    req["pair_only"] = json!(false);
    req["window"] = json!(30);
    let short = run(&req);
    assert_eq!(short["descriptive"], true);
    assert_eq!(short["n"], 30);
    assert!(short["matrix"].is_array() && short["risk"].is_null());
}

#[test]
fn broker_cutoff_holding_levels_count_only_adjacent_returns_and_keep_basis_visible() {
    let mut req = input();
    let mut panel = json!({"dates":["2026-11-23","2026-11-24","2026-11-25","2026-11-26"],"levels":{
        "AAA":["10","11",null,"13"],"BBB":["20","18","19","21"]
    }});
    req["now"] = json!("2026-11-26T22:03:00Z");
    req["broker_cutoff"] = panel.clone();
    let partial = run(&req);
    assert_eq!(
        partial["price_basis"],
        "trading212_fixed_cutoff_gbp_price_v1"
    );
    assert_eq!(partial["n"], 1);
    assert_eq!(partial["scheduled"], 3);
    assert!(partial["matrix"].is_null());

    let dates = req["reviewed"]["sessions"]
        .as_array()
        .unwrap()
        .iter()
        .skip(8)
        .map(|r| &r["date"])
        .collect::<Vec<_>>();
    panel["dates"] = json!(dates);
    let rows = req["reviewed"]["holdings"]["instruments"]
        .as_array()
        .unwrap();
    let levels = |i: usize| &rows[i]["levels"].as_array().unwrap()[8..];
    panel["levels"] = json!({"AAA":levels(0),"BBB":levels(1),"CCC":levels(2)});
    req["broker_cutoff"] = panel;
    let full = run(&req);
    assert_eq!(full["state"], "available");
    assert_eq!(full["n"], 90);
    assert_eq!(
        full["history"].as_array().unwrap().last().unwrap()["imputed"],
        0
    );
}
