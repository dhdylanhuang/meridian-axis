use axis_reconciliation::{reconcile, Request};
use serde_json::{json, Value};
use std::io::Write;
use std::process::{Command, Stdio};

fn scope() -> Value {
    json!({"account_id":"synthetic-isa", "environment":"demo"})
}
fn event(reference: &str, amount: &str) -> Value {
    json!({"scope":scope(), "reference":reference, "provider_type":"DEPOSIT", "currency":"GBP",
        "amount":amount, "occurred_at":"2026-01-02T10:00:00Z", "observed_at":"2026-01-03T00:00:00Z",
        "source_id":"synthetic-source", "revision_id":null, "revision":0, "digest":"a".repeat(64),
        "sign_basis":{"state":"verified_signed_amount", "evidence_id":"synthetic-sign-evidence"}})
}
fn balance(amount: &str, at: &str) -> Value {
    json!({"scope":scope(),"currency":"GBP","amount":amount,"at":at,"source_id":"synthetic-statement","basis":"statement_cash"})
}
fn request(events: Vec<Value>) -> Value {
    json!({"schema_version":1,"scope":scope(),"cutoff":"2026-01-03T00:00:00Z", "observations":events,
        "opening_cash":[],"closing_cash":[],"broker_cash":null})
}
fn report(value: Value) -> Value {
    serde_json::to_value(reconcile(serde_json::from_value(value).unwrap()).unwrap()).unwrap()
}

#[test]
fn revisions_replace_once_and_exact_cash_rollforward_matches_independent_control() {
    let old = event("deposit", "1");
    let mut revised = old.clone();
    revised["amount"] = json!("2.000000000000000000000000000000000001");
    revised["revision"] = json!(1);
    revised["revision_id"] = json!("revision-1");
    revised["source_id"] = json!("revised-source");
    revised["digest"] = json!("b".repeat(64));
    let mut fee = event("fee", "-0.5");
    fee["provider_type"] = json!("FEE");
    let mut input = request(vec![old.clone(), old, revised, fee]);
    input["opening_cash"] = json!([balance("10", "2026-01-01T00:00:00Z")]);
    input["closing_cash"] = json!([balance(
        "11.500000000000000000000000000000000001",
        "2026-01-03T00:00:00Z"
    )]);
    let result = report(input);
    assert_eq!(result["records"].as_array().unwrap().len(), 2);
    assert_eq!(
        result["records"][0]["evidence"].as_array().unwrap().len(),
        3
    );
    assert_eq!(result["records"][0]["selected_revision_id"], "revision-1");
    assert_eq!(
        result["cash"][0]["known_signed_movements"],
        "1.500000000000000000000000000000000001"
    );
    assert_eq!(result["cash"][0]["unexplained_difference"], "0");
    assert_eq!(result["cash"][0]["state"], "matches_known_events_only");
    assert_eq!(result["availability"], "provisional");
}

#[test]
fn unknown_signs_and_broker_components_never_manufacture_cash() {
    let mut row = event("withdrawal", "50");
    row["provider_type"] = json!("WITHDRAW");
    row["sign_basis"] = json!({"state":"unverified"});
    let mut input = request(vec![row]);
    input["broker_cash"] = json!({"currency":"GBP","available_to_trade":"20","in_pies":"3",
        "reserved_for_orders":"1","at":"2026-01-03T00:00:00Z","snapshot_id":"snapshot"});
    let result = report(input);
    assert_eq!(result["records"][0]["state"], "unverified_sign_review");
    assert!(result["records"][0]["cash_delta"].is_null());
    assert!(result["cash"][0]["replayed_cash"].is_null());
    assert!(result["cash"][0]["unexplained_difference"].is_null());
    assert_eq!(result["cash"][0]["state"], "insufficient_data");
    assert_eq!(result["broker_cash"]["available_to_trade"], "20");
}

#[test]
fn conflict_and_unknown_kinds_are_review_items_and_future_events_do_not_replay() {
    let old = event("conflict", "1");
    let mut conflict = old.clone();
    conflict["amount"] = json!("2");
    let mut unknown = event("unknown", "3");
    unknown["provider_type"] = json!("FUTURE_PROVIDER_TYPE");
    let mut future = event("future", "4");
    future["occurred_at"] = json!("2026-01-03T00:00:01Z");
    let result = report(request(vec![old, conflict, unknown, future]));
    let rows = result["records"].as_array().unwrap();
    assert_eq!(rows[0]["state"], "identity_conflict_review");
    assert_eq!(rows[1]["state"], "after_cutoff");
    assert_eq!(rows[2]["state"], "unsupported_type_review");
    assert!(rows.iter().all(|row| row["cash_delta"].is_null()));
}

#[test]
fn explicit_opening_excludes_prior_activity_and_currency_totals_stay_separate() {
    let mut before = event("at-opening", "100");
    before["occurred_at"] = json!("2026-01-01T00:00:00Z");
    let mut usd = event("usd", "3");
    usd["currency"] = json!("USD");
    let mut input = request(vec![before, event("gbp", "2"), usd]);
    input["opening_cash"] = json!([balance("10", "2026-01-01T00:00:00Z")]);
    input["closing_cash"] = json!([balance("13", "2026-01-03T00:00:00Z")]);
    let result = report(input);
    assert_eq!(result["cash"][0]["known_signed_movements"], "2");
    assert_eq!(result["cash"][0]["replayed_cash"], "12");
    assert_eq!(result["cash"][0]["unexplained_difference"], "1");
    assert_eq!(result["cash"][1]["currency"], "USD");
    assert_eq!(result["cash"][1]["known_signed_movements"], "3");
    assert!(result["cash"][1]["replayed_cash"].is_null());
}

#[test]
fn timestamps_order_by_instant_and_large_exact_values_do_not_round() {
    let mut old = event("same", "1");
    old["observed_at"] = json!("2026-01-03T01:00:00+02:00");
    let mut new = old.clone();
    new["observed_at"] = json!("2026-01-03T00:00:00Z");
    new["amount"] = json!("1e128");
    let result = report(request(vec![old, new]));
    assert_eq!(
        result["cash"][0]["known_signed_movements"],
        format!("1{}", "0".repeat(128))
    );
}

#[test]
fn scopes_precisions_and_control_basis_fail_closed() {
    for (field, value, expected) in [
        ("amount", json!("NaN"), "decimal_invalid"),
        ("amount", json!("1e129"), "decimal_precision_limit"),
        ("currency", json!("gbp"), "currency_invalid"),
        ("occurred_at", json!("2026-01-01"), "timestamp_invalid"),
    ] {
        let mut row = event("invalid", "1");
        row[field] = value;
        let error = reconcile(serde_json::from_value(request(vec![row])).unwrap()).unwrap_err();
        assert_eq!(error.0, expected);
    }
    let mut row = event("foreign", "1");
    row["scope"]["account_id"] = json!("other");
    assert_eq!(
        reconcile(serde_json::from_value(request(vec![row])).unwrap())
            .unwrap_err()
            .0,
        "scope_mismatch"
    );
    let mut input = request(vec![]);
    input["opening_cash"] = json!([balance("1", "2026-01-01T00:00:00Z")]);
    let mut closing = balance("1", "2026-01-03T00:00:00Z");
    closing["basis"] = json!("verified_total_cash");
    input["closing_cash"] = json!([closing]);
    assert_eq!(
        reconcile(serde_json::from_value(input).unwrap())
            .unwrap_err()
            .0,
        "cash_control_basis_mismatch"
    );
    let mut numeric = request(vec![event("float", "1")]);
    numeric["observations"][0]["amount"] = json!(1.1);
    assert!(serde_json::from_value::<Request>(numeric).is_err());
    let mut extra = request(vec![]);
    extra["guess_opening_balance"] = json!(true);
    assert!(serde_json::from_value::<Request>(extra).is_err());
}

#[test]
fn native_cli_emits_report_or_safe_error_without_echoing_input() {
    let binary = env!("CARGO_BIN_EXE_axis-reconciliation");
    let mut child = Command::new(binary)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(
            serde_json::to_string(&request(vec![event("cli", "2")]))
                .unwrap()
                .as_bytes(),
        )
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let report: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["method"], "cash_reconciliation_rust_v1");
    let mut child = Command::new(binary)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(b"sensitive-invalid-marker")
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    assert_eq!(output.stderr, b"request_invalid\n");
}
