//! Common-sample Pearson correlation of approved GBP total-return marks.
use super::{average, formatted, MAX_DAILY, MIN_DAILY};
use crate::risk_sessions::Reviewed;
use crate::{decimal, text};
use bigdecimal::BigDecimal;
use chrono::NaiveDate;
use serde_json::{json, Value};

pub(super) fn calculate(data: &Reviewed, start: NaiveDate, end: NaiveDate) -> Value {
    let Some(holdings) = &data.holdings else {
        return json!({"state":"awaiting_approved_holding_series"});
    };
    let left = data.sessions.partition_point(|row| row.date < start);
    let right = data.sessions.partition_point(|row| row.date <= end);
    let first = left.max(right.saturating_sub(MAX_DAILY + 1));
    let mut eligible = Vec::new();
    let mut excluded = Vec::new();
    let mut universe_weight = BigDecimal::default();
    for row in &holdings.instruments {
        universe_weight += decimal(&row.weight_pct).expect("validated weight");
        let returns: Vec<_> = row.levels[first..right]
            .windows(2)
            .map(|pair| {
                let change = pair[1]?.ln() - pair[0]?.ln();
                change.is_finite().then_some(change)
            })
            .collect();
        let usable: Vec<_> = returns.iter().flatten().copied().collect();
        if usable.len() < MIN_DAILY {
            excluded.push(json!({"ticker":row.ticker,"weight_pct":row.weight_pct,"reason":"insufficient_returns","n":usable.len()}));
        } else if usable.iter().all(|value| *value == usable[0]) {
            excluded.push(json!({"ticker":row.ticker,"weight_pct":row.weight_pct,"reason":"constant_returns","n":usable.len()}));
        } else {
            eligible.push((row, returns));
        }
    }
    let common: Vec<_> = if eligible.len() >= 2 {
        (0..right.saturating_sub(first + 1))
            .filter(|&index| eligible.iter().all(|(_, dates)| dates[index].is_some()))
            .collect()
    } else {
        Vec::new()
    };
    let mut weights = BigDecimal::default();
    let mut vectors = Vec::new();
    for (row, returns) in eligible {
        let mut vector: Vec<_> = common
            .iter()
            .map(|&index| returns[index].expect("common sample"))
            .collect();
        if common.len() >= MIN_DAILY {
            if vector.iter().all(|value| *value == vector[0]) {
                excluded.push(json!({"ticker":row.ticker,"weight_pct":row.weight_pct,"reason":"constant_on_common_sample","n":common.len()}));
                continue;
            }
            let mean = average(&vector);
            let norm = vector
                .iter()
                .map(|value| (value - mean).powi(2))
                .sum::<f64>()
                .sqrt();
            for value in &mut vector {
                *value = (*value - mean) / norm;
            }
        }
        weights += decimal(&row.weight_pct).expect("validated weight");
        vectors.push((row.ticker.as_str(), vector));
    }
    let state = if vectors.len() < 2 {
        "needs_two_holdings"
    } else if common.len() < MIN_DAILY {
        "insufficient_common_sample"
    } else {
        "available"
    };
    let mut pairs = Vec::new();
    if state == "available" {
        vectors.sort_by_key(|(ticker, _)| *ticker);
        for (i, (a, xs)) in vectors.iter().enumerate() {
            for (b, ys) in &vectors[i + 1..] {
                let rho = xs
                    .iter()
                    .zip(ys)
                    .map(|(x, y)| x * y)
                    .sum::<f64>()
                    .clamp(-1.0, 1.0);
                pairs.push((rho, a, b));
            }
        }
        pairs.sort_by(|a, b| {
            b.0.total_cmp(&a.0)
                .then_with(|| a.1.cmp(b.1))
                .then_with(|| a.2.cmp(b.2))
        });
    }
    let pair_count = pairs.len();
    json!({
        "state": state, "method":"common_sample_pearson_gbp_log_returns_v1", "holdings_as_of": holdings.as_of,
        "included_holdings": vectors.len(), "universe_holdings": holdings.instruments.len(),
        "universe_weight_pct": text(&universe_weight), "included_weight_pct": text(&weights),
        "n":common.len(), "minimum_daily":MIN_DAILY,
        "start_date":common.first().map(|index| data.sessions[first + index].date),
        "end_date":common.last().map(|index| data.sessions[first + index + 1].date),
        "excluded": excluded, "pair_count": pair_count,
        "pairs":pairs.into_iter().take(20).map(|(rho,a,b)| json!({"first":a,"second":b,"correlation":formatted(rho,6)})).collect::<Vec<_>>(),
    })
}
