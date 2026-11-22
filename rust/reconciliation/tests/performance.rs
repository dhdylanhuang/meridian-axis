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
    req["days"][89]["vuag_mark"]["at"] = json!("2026-02-28T16:00:01Z");
    req["days"][87]["vuag_mark"] = json!({"at":"2026-02-26T16:00:01Z","price_gbp":"98"});
    let report = calculate(&req);
    let summary = &report["benchmark"]["latest_stretch"];
    assert_eq!(summary["intervals"], 2);
    assert_eq!(summary["portfolio_pct"], "3");
    assert_eq!(summary["benchmark_pct"], "3.316327");
    assert_eq!(summary["difference_pp"], "-0.316327");
}

#[test]
fn drawdown_uses_flow_adjusted_growth_and_resets_after_gaps() {
    let mut req = request();
    req["days"][84]["status"] = json!("missing");
    for (index, amount) in [
        (85, "100"),
        (86, "120"),
        (87, "108"),
        (88, "114"),
        (89, "100"),
    ] {
        req["days"][index]["total_value"] = json!(amount);
    }
    req["events"] = json!([event(
        "DEPOSIT",
        "20",
        "2026-02-25T04:00:00Z",
        "test-funding"
    )]);
    req["coverage"]["end_at"] = json!("2026-02-28T15:00:00Z");
    let report = calculate(&req);
    let drawdown = &report["drawdown"];
    assert_eq!(drawdown["start_at"], "2026-02-24T16:00:00+00:00");
    assert_eq!(drawdown["intervals"], 3);
    assert_eq!(drawdown["current_pct"], "5");
    assert_eq!(drawdown["worst_pct"], "10");
    assert_eq!(drawdown["worst_peak_at"], "2026-02-24T16:00:00+00:00");
    assert_eq!(drawdown["worst_trough_at"], "2026-02-26T16:00:00+00:00");
    assert_eq!(drawdown["later_unavailable_intervals"], 1);
    req["risk_range"] = json!({"start":"2026-02-26", "end":"2026-02-27"});
    let report = calculate(&req);
    assert_eq!(report["drawdown"]["intervals"], 1);
    assert_eq!(report["drawdown"]["current_pct"], "0");
    assert_eq!(report["drawdown"]["worst_pct"], "0");
    assert_eq!(report["drawdown"]["as_of"], "2026-02-27T16:00:00+00:00");
    req["coverage"] = Value::Null;
    assert!(calculate(&req)["drawdown"].is_null());
}

#[test]
fn daily_risk_uses_only_approved_aligned_samples() {
    use chrono::{Datelike, Weekday};
    let mut req = request();
    req["risk_range"] = json!({"start":"2025-12-01","end":"2026-02-28"});
    req["days"][89]["total_value"] = json!("90");
    let no_daily = calculate(&req);
    assert_eq!(
        no_daily["metrics"]["observed"]["worst"]["return_pct"],
        "-10"
    );
    assert_eq!(
        no_daily["metrics"]["daily_state"],
        "awaiting_approved_series"
    );
    let mut rows: Vec<_> = req["days"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
        .filter_map(|(i, day)| {
            let date: NaiveDate = day["date"].as_str().unwrap().parse().unwrap();
            if matches!(date.weekday(), Weekday::Sat | Weekday::Sun) {
                return None;
            }
            let index = (1_000 + i % 7 * (i % 3 + 1)).to_string();
            Some(
                json!({"date":date,"portfolio_index":index,"vuag_index":index,
                    "portfolio_at":format!("{date}T17:00:00Z"),"vuag_at":format!("{date}T16:35:00Z"),
                    "portfolio_value_gbp":"1000"}),
            )
        })
        .collect();
    let final_row = rows.last_mut().unwrap();
    final_row["portfolio_index"] = json!("950");
    final_row["vuag_index"] = json!("950");
    req["risk_daily"] = json!({"basis":"approved_gbp_session_total_return_v1","source":"Synthetic approved data","rows":rows});
    let report = calculate(&req);
    let entries = report["metrics"]["measures"].as_array().unwrap();
    let entry = |key| entries.iter().find(|row| row["key"] == key).unwrap();
    assert!(
        entry("volatility")["value"]
            .as_str()
            .unwrap()
            .parse::<f64>()
            .unwrap()
            > 0.0
    );
    assert!(entry("sharpe")["value"].is_string());
    assert_eq!(
        report["metrics"]["bank_rate"]["verified_through"],
        "2026-11-21"
    );
    assert!(entry("sortino")["value"].is_string());
    assert_eq!(entry("beta")["value"], "1");
    assert_eq!(entry("jensen_alpha")["value"], "0");
    assert_eq!(entry("r_squared")["value"], "1");
    assert_eq!(entry("tracking_error")["value"], "0");
    assert!(entry("var95")["value_gbp"].is_string());
    assert!(entry("es95")["value_gbp"].is_string());
    assert_eq!(entry("es99")["reason"], "need_tail");

    req["risk_daily"]["rows"][1]["vuag_index"] = Value::Null;
    req["risk_daily"]["rows"][1]["vuag_at"] = Value::Null;
    let sparse = calculate(&req);
    let sparse = sparse["metrics"]["measures"].as_array().unwrap();
    assert_eq!(
        sparse
            .iter()
            .find(|row| row["key"] == "correlation")
            .unwrap()["n"],
        entry("correlation")["n"].as_u64().unwrap() - 2
    );
    assert_eq!(
        sparse.iter().find(|row| row["key"] == "sharpe").unwrap()["n"],
        entry("sharpe")["n"].as_u64().unwrap()
    );
}

fn approved_request() -> Value {
    use chrono::{Datelike, Weekday};
    let mut req = request();
    req["risk_range"] = json!({"start":"2025-12-01","end":"2026-02-28"});
    req["risk_as_of"] = json!("2026-02-28T23:30:00Z");
    let rows: Vec<_> = req["days"].as_array().unwrap().iter().map(|row| {
        row["date"].as_str().unwrap().parse::<NaiveDate>().unwrap()
    }).filter(|date| !matches!(date.weekday(), Weekday::Sat | Weekday::Sun))
      .enumerate().map(|(index, date)| {
        let level = (1000 + (index * index % 37) + 15 * usize::from(index > 31)).to_string();
        json!({"date":date,"cutoff_at":format!("{date}T16:00:00Z"),
            "portfolio_value_gbp":level,"portfolio_at":format!("{date}T16:00:00Z"),
            "vuag_index":level,"vuag_close_at":format!("{date}T15:30:00Z"),"vuag_at":format!("{date}T15:30:00Z")})
    }).collect();
    let levels: Vec<_> = rows.iter().map(|row| row["vuag_index"].clone()).collect();
    let mut no_marks = levels.clone();
    no_marks.fill(Value::Null);
    req["risk_daily"] = json!({"basis":"reviewed_gbp_session_marks_v2","source":"Synthetic session archive",
        "reviewed_at":"2026-02-28T23:00:00Z", "calendar_evidence":"test-calendar", "valuation_evidence":"test-nav",
        "benchmark_evidence":"test-permitted-gbp-series", "sessions":rows,
        "holdings":{"as_of":"2026-02-27T16:00:00Z","evidence":"test-composition-and-prices","instruments":[
            {"ticker":"AAA","weight_pct":"40","levels":levels},
            {"ticker":"BBB","weight_pct":"30","levels":levels},
            {"ticker":"CCC","weight_pct":"10","levels":no_marks},
        ]}
    });
    req
}

#[test]
fn reviewed_returns_use_timed_external_flows_and_preserve_scheduled_gaps() {
    let mut req = approved_request();
    req["risk_daily"]["sessions"][1]["portfolio_value_gbp"] = json!("1110");
    req["events"] = json!([event(
        "DEPOSIT",
        "100",
        "2025-12-02T04:00:00Z",
        "test-approval-funding"
    )]);
    req["risk_daily"]["sessions"][4]["portfolio_value_gbp"] = Value::Null;
    req["risk_daily"]["sessions"][4]["portfolio_at"] = Value::Null;
    let metrics = &calculate(&req)["metrics"];
    let approved = &metrics["session_performance"];
    assert_eq!(approved["rows"][0]["portfolio_pct"], "0.952381");
    assert_eq!(approved["rows"][0]["net_external_flow_gbp"], "100");
    for index in [3, 4] {
        assert_eq!(
            approved["rows"][index]["reason"],
            "missing_session_valuation"
        );
    }
    assert_eq!(approved["latest_portfolio"]["start_date"], "2025-12-08");
    assert!(approved["latest_matched"]["spread_pp"].is_string());
    assert_eq!(metrics["daily_coverage"]["portfolio"], 62);

    req["coverage"] = Value::Null;
    let metrics = &calculate(&req)["metrics"];
    assert_eq!(
        metrics["session_performance"]["rows"][0]["reason"],
        "funding_coverage_unverified"
    );
    assert_eq!(metrics["daily_coverage"]["portfolio"], 0);

    req["risk_daily"]["sessions"][1]["portfolio_at"] = json!("2025-12-02T16:00:01Z");
    assert!(axis_reconciliation::risk_sessions::audit_json(
        req["risk_daily"].to_string().as_bytes(),
        "2026-02-28T23:30:00Z"
    )
    .is_err());
    assert_eq!(calculate(&req)["metrics"]["daily_state"], "invalid_series");
}

#[test]
fn reviewed_session_risk_and_holding_pairs_use_their_declared_samples() {
    let mut req = approved_request();
    let metrics = &calculate(&req)["metrics"];
    assert_eq!(metrics["daily_coverage"]["portfolio"], 64);
    let measures = metrics["measures"].as_array().unwrap();
    let entry = |key| measures.iter().find(|row| row["key"] == key).unwrap();
    for key in ["volatility", "sharpe", "sortino", "var95", "es95"] {
        assert!(entry(key)["value"].is_string(), "{key}");
    }
    assert_eq!(entry("tracking_error")["value"], "0");
    assert_eq!(entry("beta")["value"], "1");
    let correlation = &metrics["holding_correlation"];
    assert_eq!(correlation["n"], 64);
    assert_eq!(
        correlation["pairs"][0],
        json!({"first":"AAA","second":"BBB","correlation":"1"})
    );
    assert_eq!(correlation["included_weight_pct"], "70");
    assert_eq!(correlation["excluded"][0]["ticker"], "CCC");

    for (instrument, mark) in [(0, 2), (0, 5), (1, 8), (1, 11)] {
        req["risk_daily"]["holdings"]["instruments"][instrument]["levels"][mark] = Value::Null;
    }
    let correlation = &calculate(&req)["metrics"]["holding_correlation"];
    assert_eq!(correlation["n"], 56);
    assert_eq!(correlation["state"], "insufficient_common_sample");
    assert_eq!(correlation["pairs"], json!([]));
}

#[test]
fn qualification_reports_real_sample_gates_without_exposing_source_rows() {
    use axis_reconciliation::risk_sessions::audit_with_funding;

    let req = approved_request();
    let manifest = req["risk_daily"].to_string();
    let cutoff = req["risk_as_of"].as_str().unwrap();
    let awaiting = audit_with_funding(manifest.as_bytes(), cutoff, None).unwrap();
    assert_eq!(
        awaiting["readiness"]["portfolio_and_benchmark"]["portfolio"],
        0
    );
    assert_eq!(
        awaiting["readiness"]["isa_gap_reasons"]["funding_coverage_unverified"],
        64
    );
    assert_eq!(
        awaiting["readiness"]["holding_correlation"]["common_returns"],
        64
    );

    let evidence = json!({"coverage":req["coverage"], "events":req["events"]});
    let verified = audit_with_funding(
        manifest.as_bytes(),
        cutoff,
        Some(evidence.to_string().as_bytes()),
    )
    .unwrap();
    assert_eq!(
        verified["readiness"]["portfolio_and_benchmark"]["portfolio"],
        64
    );
    assert_eq!(
        verified["readiness"]["daily_risk"]["volatility"]["available"],
        true
    );
    assert_eq!(verified["readiness"]["daily_risk"]["beta"]["eligible"], 64);
    let receipt = verified.to_string();
    assert!(!receipt.contains("AAA"));
    assert!(!receipt.contains("2026-"));
    assert!(!receipt.contains("Synthetic session archive"));

    let future = json!({"coverage":{
        "start_at":"2025-12-01T16:00:00Z","end_at":"2026-02-27T16:00:00Z",
        "completed_at":"2026-03-01T00:00:00Z"
    },"events":[]});
    assert!(audit_with_funding(
        manifest.as_bytes(),
        cutoff,
        Some(future.to_string().as_bytes())
    )
    .is_err());
}

fn cutoff_mark(date: &str, amount: Option<&str>) -> Value {
    json!({"date":date,"target_at":format!("{date}T22:00:00Z"),"calendar_reviewed":true,
        "captured_at":amount.map(|_| format!("{date}T22:00:10Z")),"total_value_gbp":amount})
}

#[test]
fn automatic_cutoff_returns_use_funding_and_keep_approval_separate() {
    let mut req = approved_request();
    req["cutoff_as_of"] = req["risk_as_of"].clone();
    req["cutoff_marks"] = json!([
        cutoff_mark("2025-12-01", Some("100")),
        cutoff_mark("2025-12-02", Some("121")),
        cutoff_mark("2025-12-03", None),
        cutoff_mark("2025-12-04", Some("130")),
        cutoff_mark("2025-12-05", Some("133")),
    ]);
    req["events"] = json!([event(
        "DEPOSIT",
        "20",
        "2025-12-02T10:00:10Z",
        "cutoff-funding"
    )]);
    let preapproval = calculate(&req);
    let report = &preapproval["metrics"]["cutoff_returns"];
    assert_eq!(report["intervals"][0]["return_pct"], "0.909091");
    assert_eq!(report["intervals"][0]["external_flow_count"], 1);
    assert_eq!(
        report["intervals"][1]["reason"],
        "missing_cutoff_observation"
    );
    assert_eq!(
        report["intervals"][2]["reason"],
        "missing_cutoff_observation"
    );
    assert_eq!(report["latest"]["sessions"], 1);
    assert!(report["approved_risk"].is_null());

    req["cutoff_approval"] = json!({"basis":"trading212_fixed_cutoff_gbp_v1",
        "effective_from":"2025-12-04","effective_through":"2026-12-31",
        "reviewed_at":"2026-02-28T20:00:00Z","evidence":"synthetic-reviewed-policy"});
    let metrics = &calculate(&req)["metrics"];
    assert_eq!(
        metrics["daily_coverage"],
        preapproval["metrics"]["daily_coverage"]
    );
    let report = &metrics["cutoff_returns"];
    assert_eq!(report["intervals"][0]["approved"], false);
    assert_eq!(report["intervals"][3]["approved"], true);
    assert_eq!(report["approved_risk"]["daily_coverage"]["portfolio"], 1);
    assert_eq!(report["approved_risk"]["daily_coverage"]["shortfall"], 59);
    assert!(report["approved_risk"]["measures"][0]["value"].is_null());

    req["coverage"] = Value::Null;
    let report = &calculate(&req)["metrics"]["cutoff_returns"];
    assert_eq!(
        report["intervals"][0]["reason"],
        "funding_coverage_unverified"
    );
    assert!(report["intervals"][0]["return_pct"].is_null());

    req["cutoff_approval"]["reviewed_at"] = json!("2026-03-01T00:00:00Z");
    let report = &calculate(&req)["metrics"]["cutoff_returns"];
    assert_eq!(report["approval_state"], "invalid_policy");
    assert!(report["approved_risk"].is_null());
}
