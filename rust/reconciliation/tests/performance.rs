use axis_reconciliation::performance::calculate_json;
use chrono::{Days, NaiveDate};
use serde_json::{json, Value};

fn request() -> Value {
    let first = NaiveDate::from_ymd_opt(2025, 12, 1).unwrap();
    let days: Vec<_> = (0..90).map(|i| {
        let date = first.checked_add_days(Days::new(i)).unwrap();
        json!({"date":date,"status":"observed","total_value":"100", "captured_at":format!("{date}T16:00:00+00:00")})
    }).collect();
    json!({
        "days":days,
        "coverage":{
            "start_at":"2025-01-01T00:00:00+00:00",
            "end_at":"2026-02-28T19:00:00+00:00",
            "completed_at":"2026-02-28T20:00:00+00:00"
        },
        "events":[],
    })
}

fn calculate(req: &Value) -> Value {
    serde_json::from_str(&calculate_json(&req.to_string()).unwrap()).unwrap()
}

fn event(kind: &str, amount: &str, at: &str, reference: &str) -> Value {
    json!({"kind":kind,"amount":amount,"at":at,"reference":reference,"currency":"GBP"})
}

#[test]
fn timed_external_flows_and_income() {
    let mut req = request();
    req["days"][88]["total_value"] = json!("100");
    req["days"][89]["total_value"] = json!("123");
    req["events"] = json!([
        event("DEPOSIT", "20", "2026-02-28T04:00:00+00:00", "test-funding"),
        event(
            "LENDING_INTEREST",
            "1",
            "2026-02-28T05:00:00+00:00",
            "test-income"
        ),
    ]);
    let report = calculate(&req);
    assert_eq!(report["latest_eligible"]["return_pct"], "2.727273");
    assert_eq!(report["latest_eligible"]["net_external_flow"], "20");
    assert_eq!(report["latest_eligible"]["external_flow_count"], 1);
    assert_eq!(report["funding"].as_array().unwrap().len(), 1);
    assert_eq!(report["month_to_date"]["return_pct"], "2.727273");
    assert_eq!(report["year_to_date"]["return_pct"], "2.727273");

    req["days"][89]["total_value"] = json!("82");
    req["events"] = json!([event(
        "WITHDRAW",
        "-20",
        "2026-02-28T04:00:00+00:00",
        "test-out"
    )]);
    assert_eq!(calculate(&req)["latest_eligible"]["return_pct"], "2.222222");
}

#[test]
fn gaps_and_unverified_input_block_returns() {
    let mut req = request();
    req["days"][84]["status"] = json!("missing");
    req["events"] = json!([
        event(
            "TRANSFER",
            "7",
            "2026-02-28T15:00:00+00:00",
            "test-ambiguous"
        ),
        event("DEPOSIT", "9", "2026-02-27T16:00:00+00:00", "test-boundary"),
        event("WITHDRAW", "9", "2026-02-25T17:00:00+00:00", "test-sign"),
    ]);
    let report = calculate(&req);
    let periods = &report["intervals"];
    assert_eq!(periods[83]["reason"], "missing_valuation");
    assert_eq!(periods[86]["reason"], "unclassified_or_unsupported_funding");
    assert_eq!(periods[87]["reason"], "funding_valuation_order_unknown");
    assert_eq!(periods[88]["return_pct"], Value::Null);
    assert_eq!(report["longest_valuation"]["days"], 84);
    assert_eq!(report["longest_eligible"]["intervals"], 83);
    assert_eq!(report["month_to_date"]["return_pct"], Value::Null);
    req["events"] = json!([]);
    req["coverage"]["end_at"] = json!("2026-02-28T10:00:00+00:00");
    assert_eq!(
        calculate(&req)["intervals"][88]["reason"],
        "funding_coverage_unverified"
    );
    req["coverage"]["end_at"] = json!("2026-02-28T16:05:00+00:00");
    req["days"][88]["total_value"] = json!("0");
    assert_eq!(
        calculate(&req)["intervals"][88]["reason"],
        "nonpositive_account_value"
    );
}

#[test]
fn longer_year_series_does_not_expand_chart_or_expose_old_transactions() {
    let mut req = request();
    let first = NaiveDate::from_ymd_opt(2025, 12, 31).unwrap();
    let days: Vec<_> = (0..=181).map(|i| {
        let date = first.checked_add_days(Days::new(i)).unwrap();
        json!({"date":date,"status":"observed","total_value":"100", "captured_at":format!("{date}T16:00:00+00:00")})
    }).collect();
    req["days"] = json!(days);
    req["coverage"]["end_at"] = json!("2026-06-30T18:00:00+00:00");
    req["coverage"]["completed_at"] = json!("2026-06-30T19:00:00+00:00");
    req["events"] = json!([event(
        "DEPOSIT",
        "20",
        "2026-01-21T13:00:00+00:00",
        "test-old"
    )]);
    let report = calculate(&req);
    assert_eq!(report["funding"].as_array().unwrap().len(), 0);
    assert_eq!(report["intervals"].as_array().unwrap().len(), 89);
    assert_eq!(report["year_to_date"]["intervals"], 181);
    assert_ne!(report["year_to_date"]["return_pct"], "0");
}

#[test]
fn benchmark_compares_matching_gbp_closes_and_leaves_gaps() {
    let mut req = request();
    req["days"][89]["total_value"] = json!("103");
    assert_eq!(
        calculate(&req)["benchmark"]["state"],
        "awaiting_approved_series"
    );
    req["benchmark_as_of"] = json!("2026-03-02T08:00:00Z");
    req["benchmark"] = json!({
        "ticker":"VUAG","isin":"IE00BFMXXD54","currency":"GBP",
        "basis":"split_adjusted_lse_market_close_accumulating",
        "source":"Synthetic closes","reviewed_at":"2026-03-01T18:00:00Z",
        "rows":[
            {"date":"2026-02-27","pricing_at":"2026-02-27T16:35:00Z","price_gbp":"100"},
            {"date":"2026-02-28","pricing_at":"2026-02-28T16:35:00Z","price_gbp":"102"}
        ]
    });
    let report = calculate(&req);
    let benchmark = &report["benchmark"];
    assert_eq!(benchmark["state"], "qualified_series");
    assert_eq!(benchmark["matched_intervals"], 1);
    let comparisons = benchmark["intervals"].as_array().unwrap();
    let latest = comparisons.last().unwrap();
    assert_eq!(latest["portfolio_pct"], "3");
    assert_eq!(latest["benchmark_pct"], "2");
    assert_eq!(latest["difference_pp"], "1");
    assert_eq!(latest["start_mark"]["at"], "2026-02-27T16:35:00Z");
    assert_eq!(comparisons[87]["reason"], "missing_benchmark_close");
    assert_eq!(comparisons[87]["benchmark_pct"], Value::Null);

    req["days"][89]["captured_at"] = json!("2026-02-27T23:58:00Z");
    let report = calculate(&req);
    assert_eq!(
        report["benchmark"]["intervals"][88]["reason"],
        "portfolio_capture_date_mismatch"
    );
    req["benchmark_as_of"] = json!("2026-02-28T23:00:00Z");
    let report = calculate(&req);
    assert_eq!(report["benchmark"]["state"], "invalid_series");
    assert_eq!(report["latest_eligible"]["return_pct"], "3");
}

#[test]
fn observed_broker_marks_compare_same_dates_without_mixing_sources() {
    let mut req = request();
    req["days"][89]["total_value"] = json!("103");
    req["days"][88]["vuag_mark"] = json!({"at":"2026-02-27T16:00:01Z","price_gbp":"100"});
    req["days"][89]["vuag_mark"] = json!({"at":"2026-02-28T16:00:01Z","price_gbp":"101.25"});
    let report = calculate(&req);
    let benchmark = &report["benchmark"];
    assert_eq!(benchmark["state"], "broker_observed");
    assert_eq!(benchmark["matched_intervals"], 1);
    assert_eq!(benchmark["intervals"][88]["benchmark_pct"], "1.25");
    assert_eq!(benchmark["intervals"][88]["difference_pp"], "1.75");
    assert_eq!(
        benchmark["intervals"][88]["end_mark"]["at"],
        "2026-02-28T16:00:01Z"
    );
    assert_eq!(
        benchmark["intervals"][87]["reason"],
        "missing_benchmark_mark"
    );

    req["days"][89]["vuag_mark"]["at"] = json!("2026-02-27T23:59:00Z");
    let report = calculate(&req);
    assert_eq!(report["benchmark"]["matched_intervals"], 0);
    assert_eq!(report["latest_eligible"]["return_pct"], "3");
}
