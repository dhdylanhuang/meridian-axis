//! Point-in-time allocation of broker-reported values. No prices, FX or history.
use crate::{currency, decimal, identity, instant, text, Error, Result};
use bigdecimal::BigDecimal;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const METHOD: &str = "broker_exposures_v1";

#[derive(Deserialize)]
pub struct Request {
    snapshot_id: String,
    account_as_of: String,
    positions_as_of: String,
    currency: String,
    portfolio_value: Option<String>,
    invested_value: Option<String>,
    cash_components: BTreeMap<String, Option<String>>,
    positions: Vec<Position>,
}

#[derive(Deserialize)]
struct Position {
    ticker: String,
    current_value: Option<String>,
    account_currency: Option<String>,
    quote_currency: Option<String>,
}

#[derive(Serialize)]
struct Weights {
    portfolio_pct: Option<String>,
    invested_pct: Option<String>,
}

#[derive(Serialize)]
struct Exposure {
    value: Option<String>,
    #[serde(flatten)]
    weights: Weights,
}

#[derive(Serialize)]
struct Holding {
    ticker: String,
    quote_currency: Option<String>,
    #[serde(flatten)]
    exposure: Exposure,
}

#[derive(Serialize)]
struct Bucket {
    quote_currency: Option<String>,
    missing_values: usize,
    #[serde(flatten)]
    exposure: Exposure,
}

#[derive(Serialize)]
pub struct Report {
    method: &'static str,
    snapshot_id: String,
    account_as_of: String,
    positions_as_of: String,
    currency: String,
    portfolio_denominator: Option<String>,
    invested_denominator: Option<String>,
    observed_holdings: Exposure,
    missing_values: usize,
    holdings: Vec<Holding>,
    quote_currencies: Vec<Bucket>,
    concentration: Vec<Concentration>,
    cash_component_pct: BTreeMap<String, Option<String>>,
}

#[derive(Serialize)]
struct Concentration {
    top: usize,
    position_count: usize,
    #[serde(flatten)]
    exposure: Exposure,
}

fn nonnegative(value: Option<&str>) -> Option<BigDecimal> {
    value
        .and_then(|value| decimal(value).ok())
        .filter(|value| value >= &0)
}

// Round just the output percentage (half up to two decimal places). Align
// scales first so integer division and the rounding remainder are exact.
fn percent(value: &BigDecimal, denominator: &BigDecimal) -> String {
    let scaled = value * 10_000_i32;
    let scale = scaled
        .fractional_digit_count()
        .max(denominator.fractional_digit_count());
    let (numerator, _) = scaled.with_scale(scale).into_bigint_and_scale();
    let (divisor, _) = denominator.with_scale(scale).into_bigint_and_scale();
    let mut quotient = &numerator / &divisor;
    if (numerator % &divisor) * 2_i32 >= divisor {
        quotient += 1;
    }
    text(&BigDecimal::new(quotient, 2))
}

pub fn calculate(request: Request) -> Result<Report> {
    identity(&request.snapshot_id)?;
    currency(&request.currency)?;
    if instant(&request.account_as_of)? > instant(&request.positions_as_of)? {
        return Err(Error("exposure_observation_order"));
    }
    if request.positions.len() > 1_024 {
        return Err(Error("exposure_position_limit"));
    }
    let invested = nonnegative(request.invested_value.as_deref());
    let portfolio = nonnegative(request.portfolio_value.as_deref())
        .filter(|total| total > &0 && invested.as_ref().is_some_and(|invested| invested <= total));
    let invested = invested.filter(|value| value > &0);

    let weight = |value: Option<&BigDecimal>, denom: Option<&BigDecimal>| {
        value.zip(denom).map(|(value, denom)| percent(value, denom))
    };
    let exposure = |value: Option<&BigDecimal>| Exposure {
        value: value.map(text),
        weights: Weights {
            portfolio_pct: weight(value, portfolio.as_ref()),
            invested_pct: weight(value, invested.as_ref()),
        },
    };

    let mut seen = BTreeSet::new();
    let mut positions = Vec::with_capacity(request.positions.len());
    for row in request.positions {
        identity(&row.ticker)?;
        if !seen.insert(row.ticker.clone()) {
            return Err(Error("exposure_duplicate_position"));
        }
        let value = if row.account_currency.as_deref() == Some(request.currency.as_str()) {
            nonnegative(row.current_value.as_deref())
        } else {
            None
        };
        let quote = row
            .quote_currency
            .filter(|code| code.len() == 3 && code.bytes().all(|b| b.is_ascii_alphabetic()));
        positions.push((row.ticker, quote, value));
    }
    positions.sort_by(|a, b| b.2.cmp(&a.2).then_with(|| a.0.cmp(&b.0)));
    let valued_count = positions.iter().take_while(|row| row.2.is_some()).count();
    let missing_values = positions.len() - valued_count;
    let observed: BigDecimal = positions.iter().filter_map(|row| row.2.as_ref()).sum();
    let observed_holdings =
        exposure((valued_count > 0 || positions.is_empty()).then_some(&observed));

    let mut currencies: BTreeMap<_, (Option<BigDecimal>, usize)> = BTreeMap::new();
    let mut holdings = Vec::with_capacity(positions.len());
    for (ticker, quote, value) in &positions {
        let (subtotal, missing) = currencies.entry(quote.clone()).or_default();
        match value {
            Some(value) => *subtotal = Some(subtotal.take().unwrap_or_default() + value),
            None => *missing += 1,
        }
        holdings.push(Holding {
            ticker: ticker.clone(),
            quote_currency: quote.clone(),
            exposure: exposure(value.as_ref()),
        });
    }
    let mut currencies: Vec<_> = currencies.into_iter().collect();
    currencies.sort_by(|a, b| b.1 .0.cmp(&a.1 .0).then_with(|| a.0.cmp(&b.0)));
    let quote_currencies = currencies
        .into_iter()
        .map(|(quote_currency, (subtotal, missing_values))| Bucket {
            quote_currency,
            missing_values,
            exposure: exposure(subtotal.as_ref()),
        })
        .collect();

    let concentration = [1, 5, 10]
        .into_iter()
        .map(|top| {
            let position_count = top.min(positions.len());
            let amount = (missing_values == 0 && position_count > 0).then(|| {
                positions
                    .iter()
                    .take(position_count)
                    .filter_map(|row| row.2.as_ref())
                    .sum()
            });
            Concentration {
                top,
                position_count,
                exposure: exposure(amount.as_ref()),
            }
        })
        .collect();

    let cash_component_pct = ["availableToTrade", "inPies", "reservedForOrders"]
        .into_iter()
        .map(|key| {
            let amount = nonnegative(request.cash_components.get(key).and_then(Option::as_deref));
            (key.to_owned(), weight(amount.as_ref(), portfolio.as_ref()))
        })
        .collect();

    Ok(Report {
        method: METHOD,
        snapshot_id: request.snapshot_id,
        account_as_of: request.account_as_of,
        positions_as_of: request.positions_as_of,
        currency: request.currency,
        portfolio_denominator: portfolio.as_ref().map(text),
        invested_denominator: invested.as_ref().map(text),
        observed_holdings,
        missing_values,
        holdings,
        quote_currencies,
        concentration,
        cash_component_pct,
    })
}
