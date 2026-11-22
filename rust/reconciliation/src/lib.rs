//! Pure, read-only cash reconciliation. Provider signs are never inferred.
#[cfg(target_arch = "wasm32")]
mod wasm;

pub mod changes;
pub mod exposures;
pub mod meridian;
pub mod performance;
#[cfg(any(test, target_arch = "wasm32"))]
mod projections;
pub mod risk_sessions;
#[cfg(any(test, target_arch = "wasm32"))]
mod stress;
use bigdecimal::BigDecimal;
use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::str::FromStr;

pub const MAX_OBSERVATIONS: usize = 20_000;
pub const MAX_INPUT_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Environment {
    Demo,
    Live,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Scope {
    pub account_id: String,
    pub environment: Environment,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "snake_case", deny_unknown_fields)]
pub enum SignBasis {
    Unverified,
    VerifiedSignedAmount { evidence_id: String },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub scope: Scope,
    #[serde(default = "cash_family")]
    pub family: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub instrument_label: Option<String>,
    pub reference: String,
    pub provider_type: String,
    pub currency: String,
    pub amount: String,
    pub occurred_at: String,
    pub observed_at: String,
    pub source_id: String,
    pub revision_id: Option<String>,
    pub revision: u32,
    pub digest: String,
    pub sign_basis: SignBasis,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CashSignPolicy {
    StatementCheckedGbpV1,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BalanceBasis {
    StatementCash,
    VerifiedTotalCash,
    BrokerAvailableToTrade,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Balance {
    pub scope: Scope,
    pub currency: String,
    pub amount: String,
    pub at: String,
    pub source_id: String,
    pub basis: BalanceBasis,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrokerCash {
    pub currency: String,
    pub available_to_trade: Option<String>,
    pub in_pies: Option<String>,
    pub reserved_for_orders: Option<String>,
    pub at: String,
    pub snapshot_id: String,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub schema_version: u8,
    pub scope: Scope,
    pub cutoff: String,
    pub observations: Vec<Observation>,
    pub opening_cash: Vec<Balance>,
    pub closing_cash: Vec<Balance>,
    pub broker_cash: Option<BrokerCash>,
    #[serde(default)]
    pub cash_sign_policy: Option<CashSignPolicy>,
    #[serde(default)]
    pub activity_since: Option<String>,
    #[serde(default)]
    pub detail_query: Option<DetailQuery>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RecordState {
    KnownSignedMovement,
    UnverifiedSignReview,
    UnsupportedTypeReview,
    IdentityConflictReview,
    AfterCutoff,
    ReportedActivityOnly,
}

#[derive(Debug, Serialize)]
pub struct EconomicRecord {
    pub family: String,
    pub instrument_label: Option<String>,
    pub reference: String,
    pub provider_type: String,
    pub currency: String,
    pub reported_amount: String,
    pub cash_delta: Option<String>,
    pub occurred_at: String,
    pub state: RecordState,
    pub selected_source_id: String,
    pub selected_revision_id: Option<String>,
    pub sign_basis: SignBasis,
    pub evidence: Vec<Observation>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ComparisonState {
    InsufficientData,
    Difference,
    MatchesKnownEventsOnly,
}

#[derive(Debug, Serialize)]
pub struct CashComparison {
    pub currency: String,
    pub window_start: Option<String>,
    pub cutoff: String,
    pub opening: Option<Balance>,
    pub closing: Option<Balance>,
    pub known_signed_movements: String,
    pub replayed_cash: Option<String>,
    pub unexplained_difference: Option<String>,
    pub state: ComparisonState,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub included_movement_count: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub excluded_movement_count: Option<usize>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DetailQuery {
    pub category: String,
    pub currency: String,
    pub offset: usize,
    pub limit: usize,
}
#[derive(Debug, Serialize)]
pub struct ActivityEntry {
    pub family: String,
    pub reference: String,
    pub provider_type: String,
    pub amount: String,
    pub currency: String,
    pub occurred_at: String,
    pub instrument_label: Option<String>,
    pub source_id: String,
    pub revision_id: Option<String>,
    pub revision: u32,
    pub digest: String,
}
#[derive(Debug, Serialize)]
pub struct ActivityDetails {
    pub category: String,
    pub currency: String,
    pub offset: usize,
    pub limit: usize,
    pub total_count: usize,
    pub entries: Vec<ActivityEntry>,
}
fn activity_category(row: &EconomicRecord) -> &str {
    if row.family == "dividends" {
        "dividends"
    } else {
        match row.provider_type.as_str() {
            "DEPOSIT" => "deposits",
            "WITHDRAW" => "withdrawals",
            "FEE" => "fees",
            "TRANSFER" => "transfers",
            "INTEREST_ON_FREE_CASH" => "cash_interest",
            "LENDING_INTEREST" => "lending_interest",
            _ => "other",
        }
    }
}
fn cash_family() -> String {
    "transactions".to_owned()
}

#[derive(Debug, Serialize)]
pub struct ActivityTotal {
    pub currency: String,
    pub category: String,
    pub amount: String,
    pub event_count: usize,
}
#[derive(Debug, Serialize)]
pub struct ReportedActivity {
    pub since: String,
    pub cutoff: String,
    pub totals: Vec<ActivityTotal>,
    pub excluded_conflicts: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<ActivityDetails>,
}

fn reported_activity(
    records: &[EconomicRecord],
    since: &str,
    cutoff: &str,
    query: Option<&DetailQuery>,
) -> Result<ReportedActivity> {
    let start = instant(since)?;
    let end = instant(cutoff)?;
    if start > end {
        return Err(Error("balance_cutoff_invalid"));
    }
    let mut totals: BTreeMap<(String, String), (BigDecimal, usize)> = BTreeMap::new();
    let mut excluded = 0;
    for row in records {
        let at = instant(&row.occurred_at)?;
        if at < start || at > end {
            continue;
        }
        if row.state == RecordState::IdentityConflictReview {
            excluded += 1;
            continue;
        }
        let category = activity_category(row);
        let value = totals
            .entry((row.currency.clone(), category.to_owned()))
            .or_insert((BigDecimal::from(0), 0));
        value.0 += decimal(&row.reported_amount)?;
        value.1 += 1;
    }
    let details = if let Some(query) = query {
        currency(&query.currency)?;
        if query.limit == 0
            || query.limit > 50
            || query.offset > 1024
            || !matches!(
                query.category.as_str(),
                "deposits"
                    | "withdrawals"
                    | "fees"
                    | "transfers"
                    | "cash_interest"
                    | "lending_interest"
                    | "dividends"
                    | "other"
            )
        {
            return Err(Error("request_invalid"));
        }
        let mut selected: Vec<_> = records
            .iter()
            .filter(|row| {
                let at = instant(&row.occurred_at).expect("validated");
                row.currency == query.currency
                    && activity_category(row) == query.category
                    && row.state != RecordState::IdentityConflictReview
                    && at >= start
                    && at <= end
            })
            .collect();
        selected.sort_by_key(|row| {
            (
                std::cmp::Reverse(instant(&row.occurred_at).expect("validated")),
                row.family.clone(),
                row.reference.clone(),
            )
        });
        let total_count = selected.len();
        let entries = selected
            .into_iter()
            .skip(query.offset)
            .take(query.limit)
            .map(|row| {
                let evidence = row
                    .evidence
                    .iter()
                    .find(|e| {
                        e.source_id == row.selected_source_id
                            && e.revision_id == row.selected_revision_id
                    })
                    .expect("selected evidence");
                ActivityEntry {
                    family: row.family.clone(),
                    reference: row.reference.clone(),
                    provider_type: row.provider_type.clone(),
                    amount: text(&decimal(&row.reported_amount).expect("validated")),
                    currency: row.currency.clone(),
                    occurred_at: row.occurred_at.clone(),
                    instrument_label: row.instrument_label.clone(),
                    source_id: row.selected_source_id.clone(),
                    revision_id: row.selected_revision_id.clone(),
                    revision: evidence.revision,
                    digest: evidence.digest.clone(),
                }
            })
            .collect();
        Some(ActivityDetails {
            category: query.category.clone(),
            currency: query.currency.clone(),
            offset: query.offset,
            limit: query.limit,
            total_count,
            entries,
        })
    } else {
        None
    };
    Ok(ReportedActivity {
        details,
        since: since.to_owned(),
        cutoff: cutoff.to_owned(),
        totals: totals
            .into_iter()
            .map(
                |((currency, category), (amount, event_count))| ActivityTotal {
                    currency,
                    category,
                    amount: text(&amount),
                    event_count,
                },
            )
            .collect(),
        excluded_conflicts: excluded,
    })
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub method: &'static str,
    pub availability: &'static str,
    pub scope: Scope,
    pub cutoff: String,
    pub lifetime_coverage: &'static str,
    pub records: Vec<EconomicRecord>,
    pub cash: Vec<CashComparison>,
    pub broker_cash: Option<BrokerCash>,
    pub warnings: BTreeSet<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reported_activity: Option<ReportedActivity>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cash_sign_policy: Option<CashSignPolicy>,
}

/// Safe categories only; no input data appears in diagnostics.
#[derive(Debug, PartialEq, Eq)]
pub struct Error(pub &'static str);
type Result<T> = std::result::Result<T, Error>;

fn identity(value: &str) -> Result<()> {
    if value.trim().is_empty() || value.len() > 256 {
        return Err(Error("identity_invalid"));
    }
    Ok(())
}
fn currency(value: &str) -> Result<()> {
    if value.len() != 3 || !value.bytes().all(|b| b.is_ascii_uppercase()) {
        return Err(Error("currency_invalid"));
    }
    Ok(())
}
fn instant(value: &str) -> Result<DateTime<FixedOffset>> {
    DateTime::parse_from_rfc3339(value).map_err(|_| Error("timestamp_invalid"))
}
fn decimal(value: &str) -> Result<BigDecimal> {
    if value.len() > 256
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || b".+-eE".contains(&b))
    {
        return Err(Error("decimal_invalid"));
    }
    let amount = BigDecimal::from_str(value).map_err(|_| Error("decimal_invalid"))?;
    let (coefficient, scale) = amount.as_bigint_and_exponent();
    if scale.unsigned_abs() > 128
        || coefficient.to_str_radix(10).trim_start_matches('-').len() > 128
    {
        return Err(Error("decimal_precision_limit"));
    }
    Ok(amount)
}
fn text(value: &BigDecimal) -> String {
    value.normalized().to_plain_string()
}
fn supported(kind: &str) -> bool {
    matches!(
        kind,
        "DEPOSIT" | "WITHDRAW" | "FEE" | "TRANSFER" | "INTEREST_ON_FREE_CASH" | "LENDING_INTEREST"
    )
}
fn balances<'a>(
    rows: &'a [Balance],
    scope: &Scope,
    cutoff: &DateTime<FixedOffset>,
    closing: bool,
) -> Result<BTreeMap<String, &'a Balance>> {
    let mut result = BTreeMap::new();
    for row in rows {
        if &row.scope != scope {
            return Err(Error("scope_mismatch"));
        }
        identity(&row.source_id)?;
        currency(&row.currency)?;
        decimal(&row.amount)?;
        let stamp = instant(&row.at)?;
        if (closing && stamp != *cutoff) || (!closing && stamp >= *cutoff) {
            return Err(Error("balance_cutoff_invalid"));
        }
        if result.insert(row.currency.clone(), row).is_some() {
            return Err(Error("duplicate_balance"));
        }
    }
    Ok(result)
}

fn effective_sign_basis(row: &Observation, request: &Request) -> SignBasis {
    if row.family == "dividends" {
        return SignBasis::Unverified;
    }
    if row.sign_basis != SignBasis::Unverified {
        return row.sign_basis.clone();
    }
    let eligible = request.cash_sign_policy == Some(CashSignPolicy::StatementCheckedGbpV1)
        && request.scope.environment == Environment::Live
        && row.currency == "GBP"
        && match row.provider_type.as_str() {
            "INTEREST_ON_FREE_CASH" => {
                decimal(&row.amount).expect("validated") > BigDecimal::from(0)
            }
            "TRANSFER" => decimal(&row.amount).expect("validated") != BigDecimal::from(0),
            _ => false,
        };
    if eligible {
        SignBasis::VerifiedSignedAmount {
            evidence_id: "t212-statement-cash-signs-gbp-v1".to_owned(),
        }
    } else {
        SignBasis::Unverified
    }
}

pub fn reconcile(request: Request) -> Result<Report> {
    if request.schema_version != 1 {
        return Err(Error("schema_version_invalid"));
    }
    identity(&request.scope.account_id)?;
    if request.observations.len() > MAX_OBSERVATIONS
        || request.opening_cash.len() > 128
        || request.closing_cash.len() > 128
    {
        return Err(Error("observation_limit"));
    }
    let cutoff = instant(&request.cutoff)?;
    let openings = balances(&request.opening_cash, &request.scope, &cutoff, false)?;
    let closings = balances(&request.closing_cash, &request.scope, &cutoff, true)?;
    let mut currencies: BTreeSet<String> =
        openings.keys().chain(closings.keys()).cloned().collect();
    if let Some(broker) = &request.broker_cash {
        currency(&broker.currency)?;
        identity(&broker.snapshot_id)?;
        if instant(&broker.at)? != cutoff {
            return Err(Error("broker_cutoff_invalid"));
        }
        for value in [
            &broker.available_to_trade,
            &broker.in_pies,
            &broker.reserved_for_orders,
        ]
        .into_iter()
        .flatten()
        {
            decimal(value)?;
        }
        currencies.insert(broker.currency.clone());
    }
    let mut grouped: BTreeMap<(String, String), Vec<&Observation>> = BTreeMap::new();
    for row in &request.observations {
        if row.scope != request.scope
            || !matches!(row.family.as_str(), "transactions" | "dividends")
        {
            return Err(Error("scope_mismatch"));
        }
        for value in [&row.reference, &row.provider_type, &row.source_id] {
            identity(value)?;
        }
        if let Some(id) = &row.revision_id {
            identity(id)?;
        }
        if row.digest.len() != 64 || !row.digest.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(Error("digest_invalid"));
        }
        if let SignBasis::VerifiedSignedAmount { evidence_id } = &row.sign_basis {
            identity(evidence_id)?;
        }
        if let Some(label) = &row.instrument_label {
            if label.is_empty() || label.len() > 512 || label.chars().any(char::is_control) {
                return Err(Error("identity_invalid"));
            }
        }
        currency(&row.currency)?;
        decimal(&row.amount)?;
        instant(&row.occurred_at)?;
        instant(&row.observed_at)?;
        currencies.insert(row.currency.clone());
        grouped
            .entry((row.family.clone(), row.reference.clone()))
            .or_default()
            .push(row);
    }
    if currencies.len() > 128 {
        return Err(Error("currency_limit"));
    }
    let mut warnings = BTreeSet::from([
        "lifetime_coverage_unverified",
        "execution_wallets_and_dividends_not_included",
        "no_return_calculation",
    ]);
    if request.broker_cash.is_some() {
        warnings.insert("broker_cash_components_not_a_comparable_total");
    }
    let mut records = Vec::new();
    for ((family, reference), mut observations) in grouped {
        // Parsing above validates all timestamps; sort by actual instants, not offset text.
        observations.sort_by_key(|r| {
            (
                instant(&r.observed_at).expect("validated"),
                r.revision,
                r.source_id.clone(),
            )
        });
        let current = *observations.last().expect("nonempty identity");
        let rank = (instant(&current.observed_at)?, current.revision);
        let conflict = observations
            .iter()
            .filter(|r| (instant(&r.observed_at).expect("validated"), r.revision) == rank)
            .any(|r| {
                r.digest != current.digest
                    || r.currency != current.currency
                    || r.amount != current.amount
                    || r.provider_type != current.provider_type
                    || r.occurred_at != current.occurred_at
                    || r.sign_basis != current.sign_basis
            });
        let sign_basis = effective_sign_basis(current, &request);
        let state = if conflict {
            RecordState::IdentityConflictReview
        } else if instant(&current.occurred_at)? > cutoff {
            RecordState::AfterCutoff
        } else if family == "dividends" {
            RecordState::ReportedActivityOnly
        } else if !supported(&current.provider_type) {
            RecordState::UnsupportedTypeReview
        } else if matches!(sign_basis, SignBasis::Unverified) {
            RecordState::UnverifiedSignReview
        } else {
            RecordState::KnownSignedMovement
        };
        match state {
            RecordState::IdentityConflictReview => {
                warnings.insert("identity_conflict_review");
            }
            RecordState::UnsupportedTypeReview => {
                warnings.insert("unsupported_type_review");
            }
            RecordState::UnverifiedSignReview => {
                warnings.insert("cash_signs_unverified");
            }
            _ => {}
        }
        if current.provider_type == "TRANSFER" {
            warnings.insert("transfer_boundary_not_classified");
        }
        records.push(EconomicRecord {
            family,
            instrument_label: current.instrument_label.clone(),
            reference,
            provider_type: current.provider_type.clone(),
            currency: current.currency.clone(),
            reported_amount: current.amount.clone(),
            occurred_at: current.occurred_at.clone(),
            cash_delta: if state == RecordState::KnownSignedMovement {
                Some(text(&decimal(&current.amount)?))
            } else {
                None
            },
            state,
            selected_source_id: current.source_id.clone(),
            selected_revision_id: current.revision_id.clone(),
            sign_basis,
            evidence: observations.into_iter().cloned().collect(),
        });
    }
    let mut comparisons = Vec::new();
    for currency in currencies {
        let opening = openings.get(&currency).copied();
        let closing = closings.get(&currency).copied();
        if let (Some(a), Some(b)) = (opening, closing) {
            if a.basis != b.basis {
                return Err(Error("cash_control_basis_mismatch"));
            }
        }
        let available_component = opening
            .map(|o| o.basis == BalanceBasis::BrokerAvailableToTrade)
            .unwrap_or(false);
        if available_component {
            warnings.insert("available_cash_component_not_total_cash");
        }
        let mut total = BigDecimal::from(0);
        let (mut included, mut excluded) = (0, 0);
        for record in records
            .iter()
            .filter(|r| r.currency == currency && r.family == "transactions")
        {
            let at = instant(&record.occurred_at).expect("validated");
            let in_window = at <= cutoff
                && opening
                    .map(|o| at > instant(&o.at).expect("validated"))
                    .unwrap_or(true);
            if in_window {
                if let Some(delta) = &record.cash_delta {
                    total += BigDecimal::from_str(delta).expect("validated internal amount");
                    included += 1;
                } else {
                    excluded += 1;
                }
            }
        }
        let replayed = opening.map(|o| decimal(&o.amount).expect("validated") + &total);
        let difference = match (&replayed, closing) {
            (Some(value), Some(control)) => Some(decimal(&control.amount)? - value),
            _ => None,
        };
        let state = match &difference {
            None => {
                warnings.insert("cash_controls_incomplete");
                ComparisonState::InsufficientData
            }
            Some(value) if value == &BigDecimal::from(0) => ComparisonState::MatchesKnownEventsOnly,
            Some(_) => ComparisonState::Difference,
        };
        comparisons.push(CashComparison {
            currency,
            window_start: opening.map(|o| o.at.clone()),
            cutoff: request.cutoff.clone(),
            opening: opening.cloned(),
            closing: closing.cloned(),
            known_signed_movements: text(&total),
            replayed_cash: replayed.as_ref().map(text),
            unexplained_difference: difference.as_ref().map(text),
            state,
            included_movement_count: available_component.then_some(included),
            excluded_movement_count: available_component.then_some(excluded),
        });
    }
    let activity = request
        .activity_since
        .as_ref()
        .map(|since| {
            reported_activity(
                &records,
                since,
                &request.cutoff,
                request.detail_query.as_ref(),
            )
        })
        .transpose()?;
    Ok(Report {
        reported_activity: activity,
        method: "cash_reconciliation_rust_v1",
        availability: "provisional",
        scope: request.scope,
        cutoff: request.cutoff,
        lifetime_coverage: "unverified",
        records,
        cash: comparisons,
        broker_cash: request.broker_cash,
        warnings,
        cash_sign_policy: request.cash_sign_policy,
    })
}

pub(crate) fn decimal_percent(numerator: &BigDecimal, denominator: &BigDecimal) -> Option<String> {
    (denominator > &0).then(|| text(&((numerator * BigDecimal::from(100)) / denominator).round(4)))
}
