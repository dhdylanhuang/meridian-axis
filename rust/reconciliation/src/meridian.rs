//! Diversification review of the approved GBP snapshot on a reviewed session grid.
use crate::{decimal, decimal_percent, instant, risk_sessions::Reviewed, text, Error, Result};
use bigdecimal::{BigDecimal, ToPrimitive};
use chrono::NaiveDate;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

const MINIMUM: usize = 60;
const CLUSTER_DISTANCE: f64 = 0.83;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    snapshot: Value,
    reviewed: Option<Value>,
    now: String,
    window: usize,
    pair: Option<[usize; 2]>,
    #[serde(default)]
    pair_only: bool,
}

struct Holding<'a> {
    ticker: &'a str,
    value: BigDecimal,
    returns: Vec<Option<f64>>,
    carried: Option<Vec<bool>>,
}

fn returns(levels: &[Option<f64>]) -> Vec<Option<f64>> {
    levels
        .windows(2)
        .map(|p| Some(p[1]?.ln() - p[0]?.ln()))
        .collect()
}

fn common(columns: &[&Holding], left: usize, right: usize) -> Vec<usize> {
    (left..right)
        .filter(|&i| columns.iter().all(|h| h.returns[i].is_some()))
        .collect()
}

fn variable(values: impl Iterator<Item = f64>) -> bool {
    let mut values = values;
    values
        .next()
        .is_some_and(|first| values.any(|x| x != first))
}

fn centred(holding: &Holding, rows: &[usize]) -> Vec<f64> {
    let mut values: Vec<_> = rows.iter().map(|&i| holding.returns[i].unwrap()).collect();
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    values.iter_mut().for_each(|value| *value -= mean);
    values
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

fn coefficient(cov: f64, a: f64, b: f64) -> Option<f64> {
    (a > 0.0 && b > 0.0).then(|| (cov / (a * b).sqrt()).clamp(-1.0, 1.0))
}

struct Branch {
    members: Vec<usize>,
    children: Option<Box<[Branch; 2]>>,
    height: f64,
}

fn tree(correlation: &[Vec<f64>], order: &[usize]) -> Branch {
    let mut branches: Vec<_> = order
        .iter()
        .map(|&i| Branch {
            members: vec![i],
            children: None,
            height: 0.0,
        })
        .collect();
    let mut distances: Vec<Vec<_>> = correlation
        .iter()
        .map(|row| row.iter().map(|rho| (2.0 * (1.0 - rho)).sqrt()).collect())
        .collect();
    while branches.len() > 1 {
        let mut best = (f64::INFINITY, 0, 1);
        for (i, a) in branches.iter().enumerate() {
            for (j, b) in branches.iter().enumerate().skip(i + 1) {
                let d = distances[a.members[0]][b.members[0]];
                if d < best.0 {
                    best = (d, i, j);
                }
            }
        }
        let (height, i, j) = best;
        let right = branches.remove(j);
        let left = branches.remove(i);
        let a = left.members[0];
        let b = right.members[0];
        let (na, nb) = (left.members.len() as f64, right.members.len() as f64);
        for group in &branches {
            let k = group.members[0];
            let combined = (na * distances[a][k] + nb * distances[b][k]) / (na + nb);
            distances[a][k] = combined;
            distances[k][a] = combined;
        }
        let members = left.members.iter().chain(&right.members).copied().collect();
        branches.insert(
            i,
            Branch {
                members,
                children: Some(Box::new([left, right])),
                height,
            },
        );
    }
    branches.pop().unwrap()
}

fn clusters(branch: &Branch, output: &mut Vec<Vec<usize>>) {
    if branch.height <= CLUSTER_DISTANCE {
        if branch.members.len() > 1 {
            output.push(branch.members.clone());
        }
    } else if let Some(children) = &branch.children {
        for child in children.iter() {
            clusters(child, output);
        }
    }
}

fn point(
    columns: &[&Holding],
    pair: [&Holding; 2],
    sessions: &[NaiveDate],
    left: usize,
    right: usize,
    threshold: usize,
) -> Value {
    let rows = common(columns, left, right);
    let n = rows.len();
    let rho = if n < threshold {
        None
    } else {
        let [a, b] = pair.map(|holding| centred(holding, &rows));
        coefficient(dot(&a, &b), dot(&a, &a), dot(&b, &b))
    };
    let imputed = columns.iter().all(|h| h.carried.is_some()).then(|| {
        rows.iter()
            .filter(|&&i| columns.iter().any(|h| h.carried.as_ref().unwrap()[i]))
            .count()
    });
    let affected: Vec<_> = columns
        .iter()
        .filter(|h| (left..right).any(|i| h.returns[i].is_none()))
        .map(|h| h.ticker)
        .collect();
    json!({
        "start": sessions[left], "end": sessions[right], "n": n, "rho": rho,
        "excluded": right - left - n, "affected": affected, "imputed": imputed,
        "reason": if n < threshold { Some("insufficient_matched_returns") }
                  else if rho.is_none() { Some("constant_pair") }
                  else { None },
    })
}

pub fn calculate_json(input: &str) -> Result<String> {
    if input.len() > 1024 * 1024 {
        return Err(Error("meridian_input_limit"));
    }
    let request: Request =
        serde_json::from_str(input).map_err(|_| Error("meridian_request_invalid"))?;
    let window = request.window;
    if !matches!(window, 30 | 90 | 252) {
        return Err(Error("meridian_request_invalid"));
    }
    let snapshot = &request.snapshot;
    let capture_time = snapshot["account_retrieval"]["retrieval_completed_at"]
        .as_str()
        .unwrap_or_default();
    let holdings_time = snapshot["positions_retrieval"]["retrieval_completed_at"]
        .as_str()
        .unwrap_or_default();
    if snapshot["source"] != "trading212"
        || snapshot["basis"] != "broker_reported"
        || snapshot["currency"] != "GBP"
        || instant(capture_time).is_err()
        || instant(holdings_time).is_err()
    {
        return Err(Error("meridian_snapshot_invalid"));
    }
    let isa = amount(&snapshot["total_value"])
        .filter(|v| v > &0)
        .ok_or(Error("meridian_snapshot_invalid"))?;
    let cash = amount(&snapshot["cash_components"]["availableToTrade"]);
    let positions = snapshot["positions"]
        .as_array()
        .ok_or(Error("meridian_snapshot_invalid"))?;
    let mut tickers = BTreeSet::new();
    let mut marked = BigDecimal::default();
    let mut included = Vec::new();
    let mut excluded = Vec::new();
    let (reviewed, gate) = match request.reviewed {
        None => (None, "awaiting_approved_holding_series"),
        Some(input) => match Reviewed::parse(&input, &request.now) {
            Ok(data) if data.holdings.is_some() => (Some(data), "available"),
            Ok(_) => (None, "awaiting_approved_holding_series"),
            Err(_) => (None, "reviewed_evidence_invalid"),
        },
    };
    let cut_at = instant(holdings_time)?;
    let dates = reviewed
        .as_ref()
        .map(|r| {
            r.sessions
                .iter()
                .take_while(|row| instant(&row.cutoff_at).is_ok_and(|at| at <= cut_at))
                .map(|s| s.date)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let right = dates.len().saturating_sub(1);
    let left = right.saturating_sub(window);
    let threshold = if window == 30 { 3 } else { MINIMUM };
    let prices: BTreeMap<_, _> = reviewed
        .as_ref()
        .and_then(|r| r.holdings.as_ref())
        .map(|h| {
            h.instruments
                .iter()
                .map(|item| (item.ticker.as_str(), item))
                .collect()
        })
        .unwrap_or_default();
    let mut labels = BTreeMap::new();
    let mut sectors = BTreeMap::new();
    if let Some(buckets) = snapshot["exposures"]["sectors"]["buckets"].as_array() {
        for b in buckets {
            if let (Some(label), Some(members)) = (b["label"].as_str(), b["members"].as_object()) {
                for ticker in members.keys() {
                    sectors.insert(ticker.as_str(), label);
                }
            }
        }
    }
    for position in positions {
        let ticker = position["ticker"]
            .as_str()
            .ok_or(Error("meridian_snapshot_invalid"))?;
        crate::identity(ticker)?;
        if !tickers.insert(ticker) {
            return Err(Error("meridian_snapshot_invalid"));
        }
        let name = position["name"].as_str().unwrap_or(ticker);
        labels.insert(ticker, name);
        let value =
            amount(&position["current_value"]).filter(|_| position["account_currency"] == "GBP");
        if let Some(v) = &value {
            marked += v;
        }
        let matched = prices.get(ticker);
        let mut count = 0;
        let reason = match (&value, matched) {
            (None, _) => "missing_gbp_value",
            (Some(v), _) if v <= &0 => "no_positive_value",
            (Some(_), _)
                if !matches!(position["instrument_type"].as_str(), Some("STOCK" | "ETF"))
                    || !amount(&position["quantity"]).is_some_and(|q| q > 0) =>
            {
                "position_ineligible"
            }
            (Some(_), None) => "missing_approved_series",
            (Some(value), Some(series)) => {
                let returns = returns(&series.levels);
                let usable = || returns[left..right].iter().flatten().copied();
                count = usable().count();
                if count < threshold {
                    "insufficient_holding_returns"
                } else if !variable(usable()) {
                    "constant_holding"
                } else {
                    let carried = series
                        .imputed
                        .as_ref()
                        .map(|marks| marks.windows(2).map(|p| p[0] || p[1]).collect());
                    included.push(Holding {
                        ticker,
                        value: value.clone(),
                        returns,
                        carried,
                    });
                    continue;
                }
            }
        };
        excluded.push(exclusion(ticker, name, value.as_ref(), &isa, reason, count));
    }
    included.sort_by_key(|h| h.ticker);
    let initial = common(&included.iter().collect::<Vec<_>>(), left, right);
    if included.len() > 1 && initial.len() >= threshold {
        included.retain(|h| {
            if variable(initial.iter().filter_map(|&i| h.returns[i])) {
                return true;
            }
            excluded.push(exclusion(
                h.ticker,
                labels[h.ticker],
                Some(&h.value),
                &isa,
                "constant_on_common_sample",
                initial.len(),
            ));
            false
        });
    }
    let columns: Vec<_> = included.iter().collect();
    let rows = if columns.is_empty() {
        Vec::new()
    } else {
        common(&columns, left, right)
    };
    let n = rows.len();
    let covered: BigDecimal = included.iter().map(|h| &h.value).sum();
    let excluded_value = &marked - &covered;
    let residual = cash.as_ref().map(|cash| &isa - &marked - cash);
    let state = if gate != "available" {
        gate
    } else if included.len() < 2 {
        "needs_two_holdings"
    } else if n < threshold {
        "insufficient_common_sample"
    } else if right < window {
        "insufficient_session_grid"
    } else {
        "available"
    };
    let mut report = json!({
        "method":"meridian_common_sample_v1", "state":state, "window":window, "minimum":MINIMUM,
        "descriptive": window == 30, "capture_time":capture_time, "holdings_time":holdings_time,
        "isa":text(&isa), "n":n, "scheduled":right.min(window), "excluded":excluded,
        "covered_value":text(&covered), "covered_pct":decimal_percent(&covered, &isa),
        "excluded_value":text(&excluded_value), "excluded_pct":decimal_percent(&excluded_value, &isa),
        "cash":cash.as_ref().map(text), "cash_pct":cash.as_ref().and_then(|v| decimal_percent(v, &isa)),
        "residual":residual.as_ref().map(text), "residual_pct":residual.as_ref().and_then(|v| decimal_percent(v, &isa)),
    });
    if state != "available" {
        return Ok(report.to_string());
    }

    let data: Vec<_> = included.iter().map(|h| centred(h, &rows)).collect();
    let mut covariance = vec![vec![0.0; data.len()]; data.len()];
    for (i, a) in data.iter().enumerate() {
        for (j, b) in data.iter().enumerate().skip(i) {
            let value = dot(a, b) / (n - 1) as f64;
            covariance[i][j] = value;
            covariance[j][i] = value;
        }
    }
    let corr: Vec<Vec<_>> = covariance
        .iter()
        .enumerate()
        .map(|(i, row)| {
            row.iter()
                .enumerate()
                .map(|(j, &cov)| coefficient(cov, covariance[i][i], covariance[j][j]).unwrap())
                .collect()
        })
        .collect();
    let order: Vec<_> = (0..included.len()).collect();
    let root = tree(&corr, &order);
    let mut branches = Vec::new();
    clusters(&root, &mut branches);
    let weights: Vec<_> = included
        .iter()
        .map(|h| (&h.value / &covered).to_f64().unwrap())
        .collect();
    let mut by_sector = BTreeMap::<_, Vec<_>>::new();
    for (&i, h) in order.iter().zip(&included) {
        by_sector
            .entry(sectors.get(h.ticker).copied().unwrap_or("Unclassified"))
            .or_default()
            .push(i);
    }
    let sector_order: Vec<_> = by_sector
        .values()
        .flat_map(|leaves| tree(&corr, leaves).members)
        .collect();
    let contributions: Vec<_> = covariance
        .iter()
        .zip(&weights)
        .map(|(row, w)| w * dot(row, &weights))
        .collect();
    let variance: f64 = contributions.iter().sum();
    let risk = (window >= MINIMUM && variance.is_finite() && variance > 0.0).then(|| {
        contributions
            .iter()
            .map(|v| v / variance * 100.0)
            .collect::<Vec<_>>()
    });
    let largest = branches.iter().max_by(|a, b| {
        let total = |group: &[usize]| group.iter().map(|&k| weights[k]).sum::<f64>();
        total(a).total_cmp(&total(b))
    });
    let pair = request.pair.unwrap_or_else(|| {
        let group = largest.unwrap_or(&root.members);
        [group[0], group[1]]
    });
    if pair[0] == pair[1] || pair.iter().any(|&i| i >= columns.len()) {
        return Err(Error("meridian_pair_invalid"));
    }
    let pair_columns = pair.map(|i| columns[i]);
    let basis = if request.pair_only {
        pair_columns.as_slice()
    } else {
        columns.as_slice()
    };
    let mut history: Vec<_> = (window..=right)
        .map(|end| point(basis, pair_columns, &dates, end - window, end, threshold))
        .collect();
    if !request.pair_only {
        history.last_mut().unwrap()["rho"] = json!(corr[pair[0]][pair[1]]);
    }
    report["group_totals"] = json!(branches
        .iter()
        .map(|group| {
            let value: BigDecimal = group.iter().map(|&i| &included[i].value).sum();
            let group_risk = risk
                .as_ref()
                .map(|risk| group.iter().map(|&i| risk[i]).sum::<f64>());
            let other_risk = risk.as_ref().map(|risk| {
                order
                    .iter()
                    .filter(|i| !group.contains(i))
                    .map(|&i| risk[i])
                    .sum::<f64>()
            });
            json!({
                "capital": decimal_percent(&value, &isa),
                "other_capital": decimal_percent(&(&covered - &value), &isa),
                "risk": group_risk, "other_risk": other_risk,
            })
        })
        .collect::<Vec<_>>());
    report["matrix"] = json!(corr);
    report["order"] = json!(root.members);
    report["sector_order"] = json!(sector_order);
    report["clusters"] = json!(branches);
    report["selected_cluster"] = json!(largest);
    report["risk"] = json!(risk);
    report["pair"] = json!(pair);
    report["pair_only"] = json!(request.pair_only);
    report["history"] = json!(history);
    report["holdings"] = json!(included
        .iter()
        .map(|h| json!({
            "ticker":h.ticker, "name":labels[h.ticker], "value":text(&h.value),
            "sector":sectors.get(h.ticker).copied().unwrap_or("Unclassified"),
            "capital":decimal_percent(&h.value, &isa),
        }))
        .collect::<Vec<_>>());
    Ok(report.to_string())
}

fn amount(value: &Value) -> Option<BigDecimal> {
    decimal(value.as_str()?).ok()
}

fn exclusion(
    ticker: &str,
    name: &str,
    value: Option<&BigDecimal>,
    isa: &BigDecimal,
    reason: &str,
    n: usize,
) -> Value {
    json!({"ticker":ticker, "name":name, "value":value.map(text),
           "capital":value.and_then(|v| decimal_percent(v, isa)), "reason":reason, "n":n})
}
