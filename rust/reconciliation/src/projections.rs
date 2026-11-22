//! Dated GBP forecasts with exact contributions and effective annual growth.
use crate::{decimal, identity, instant, text, Error, Result};
use bigdecimal::{BigDecimal, FromPrimitive, ToPrimitive};
use chrono::{Datelike, Months, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

const METHOD: &str = "dated_isa_projection_v1";
const MAX_PERIODS: i64 = 365 * 10;

#[derive(Deserialize)]
pub(crate) struct Snapshot {
    pub source: String,
    pub basis: String,
    pub currency: String,
    pub total_value: String,
    pub account_retrieval: Capture,
    pub positions: Vec<Position>,
}

#[derive(Deserialize)]
pub(crate) struct Capture {
    pub retrieval_completed_at: String,
}

#[derive(Deserialize)]
pub(crate) struct Position {
    pub ticker: String,
}

impl Snapshot {
    pub fn opening(&self) -> Result<BigDecimal> {
        if self.source != "trading212" || self.basis != "broker_reported" || self.currency != "GBP"
        {
            return Err(Error("snapshot_unavailable"));
        }
        let value = decimal(&self.total_value).map_err(|_| Error("snapshot_unavailable"))?;
        if value < 0 || value > 1_000_000_000 {
            return Err(Error("snapshot_unavailable"));
        }
        Ok(value)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    opening_growth_pct: String,
    plans: [Plan; 2],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    deposits: Vec<Deposit>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Deposit {
    first_date: NaiveDate,
    frequency: Frequency,
    amount: String,
    unit: Unit,
    allocations: Vec<Allocation>,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Frequency {
    Once,
    Monthly,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Unit {
    Percent,
    Gbp,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Allocation {
    kind: Destination,
    name: String,
    share: String,
    growth_pct: String,
}

#[derive(Deserialize, Serialize, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
enum Destination {
    Holding,
    Hypothetical,
    Cash,
}

#[derive(Serialize)]
struct FlowAllocation {
    kind: Destination,
    name: String,
    amount: String,
    growth_pct: String,
}

#[derive(Serialize)]
struct Flow {
    date: NaiveDate,
    deposit: usize,
}

#[derive(Serialize)]
struct Point {
    date: NaiveDate,
    value: String,
}

#[derive(Serialize)]
struct Forecast {
    target_value: String,
    deposits: String,
    growth: String,
    goal_difference: String,
    series: Vec<Point>,
    schedule: Vec<Flow>,
    instructions: Vec<Instruction>,
}

#[derive(Serialize)]
struct Report {
    method: &'static str,
    availability: &'static str,
    source: &'static str,
    currency: &'static str,
    capture_time: String,
    opening_value: String,
    opening_growth_pct: String,
    target_date: NaiveDate,
    goal: String,
    baseline: Forecast,
    plans: [Forecast; 2],
}

fn goal() -> BigDecimal {
    BigDecimal::from(100_000)
}

fn target_date() -> NaiveDate {
    NaiveDate::from_ymd_opt(2030, 4, 30).expect("fixed goal date")
}

fn growth_rate(input: &str) -> Result<f64> {
    let rate = decimal(input).map_err(|_| Error("growth_invalid"))?;
    if rate < -100 || rate > 1_000 {
        return Err(Error("growth_invalid"));
    }
    Ok(rate.to_f64().expect("bounded rate") / 100.0)
}

fn month_end(date: NaiveDate) -> NaiveDate {
    date.with_day(1)
        .and_then(|first| first.checked_add_months(Months::new(1)))
        .and_then(|next| next.pred_opt())
        .expect("bounded forecast dates")
}

fn money(value: &BigDecimal) -> String {
    text(&value.round(2))
}

#[derive(Serialize)]
struct Instruction {
    allocations: Vec<FlowAllocation>,
    total: String,
}

struct DepositProgram {
    growing: Vec<(u64, f64)>,
    flat: BigDecimal,
    total: BigDecimal,
    instruction: Instruction,
}

#[derive(Default)]
struct DepositSchedule {
    programs: Vec<DepositProgram>,
    dates: BTreeMap<NaiveDate, Vec<usize>>,
}

fn dated_flows(plan: Plan, start: NaiveDate, tickers: &BTreeSet<&str>) -> Result<DepositSchedule> {
    if plan.deposits.len() > 12 {
        return Err(Error("deposit_limit"));
    }
    let mut schedule = DepositSchedule::default();
    for deposit in plan.deposits {
        let total = decimal(&deposit.amount).map_err(|_| Error("deposit_amount_invalid"))?;
        if total <= 0 || total > 1_000_000_000 || total.round(2) != total {
            return Err(Error("deposit_amount_invalid"));
        }
        if deposit.first_date < start || deposit.first_date > target_date() {
            return Err(Error("deposit_date_invalid"));
        }
        if deposit.allocations.is_empty() || deposit.allocations.len() > 24 {
            return Err(Error("allocation_limit"));
        }
        let expected = match deposit.unit {
            Unit::Gbp => total.clone(),
            Unit::Percent => BigDecimal::from(100),
        };
        let mut sum = BigDecimal::from(0);
        let mut seen = BTreeSet::new();
        let mut allocations = Vec::new();
        for row in deposit.allocations {
            let name = row.name.trim();
            let key = if row.kind == Destination::Cash {
                ""
            } else {
                name
            };
            if (row.kind != Destination::Cash && identity(key).is_err())
                || (row.kind == Destination::Holding && !tickers.contains(key))
                || !seen.insert((row.kind, key.to_lowercase()))
            {
                return Err(Error("destination_invalid"));
            }
            let share = decimal(&row.share).map_err(|_| Error("allocation_amount_invalid"))?;
            if share <= 0 || share > expected || share.round(2) != share {
                return Err(Error("allocation_amount_invalid"));
            }
            sum += &share;
            let amount = match deposit.unit {
                Unit::Gbp => share,
                Unit::Percent => &total * share * BigDecimal::new(1.into(), 2),
            };
            allocations.push((row.kind, key.to_owned(), amount, row.growth_pct));
        }
        if sum != expected {
            return Err(Error("allocation_total_invalid"));
        }
        let mut growing = Vec::new();
        let mut flat = BigDecimal::from(0);
        let mut rows = Vec::new();
        for (kind, name, amount, growth) in allocations {
            let rate = growth_rate(&growth)?;
            rows.push(FlowAllocation {
                kind,
                name,
                amount: text(&amount),
                growth_pct: text(&decimal(&growth)?),
            });
            if rate == 0.0 {
                flat += amount;
            } else {
                growing.push((rate.to_bits(), amount.to_f64().expect("bounded allocation")));
            }
        }
        let index = schedule.programs.len();
        schedule.programs.push(DepositProgram {
            growing,
            flat,
            instruction: Instruction {
                allocations: rows,
                total: text(&total),
            },
            total,
        });
        let mut date = match deposit.frequency {
            Frequency::Once => deposit.first_date,
            Frequency::Monthly => month_end(deposit.first_date),
        };
        loop {
            schedule.dates.entry(date).or_default().push(index);
            if matches!(deposit.frequency, Frequency::Once) || date == target_date() {
                break;
            }
            date = month_end(date.succ_opt().expect("bounded forecast dates"));
        }
    }
    Ok(schedule)
}

fn forecast(opening: &BigDecimal, rate: f64, start: NaiveDate, flows: DepositSchedule) -> Forecast {
    let mut dates = BTreeSet::from([start, target_date()]);
    dates.extend(flows.dates.keys().copied());
    let mut month = month_end(start);
    while month < target_date() {
        dates.insert(month);
        month = month_end(month.succ_opt().expect("bounded forecast dates"));
    }
    let mut balances = BTreeMap::new();
    let mut flat = BigDecimal::from(0);
    if rate == 0.0 {
        flat = opening.clone();
    } else {
        balances.insert(
            rate.to_bits(),
            opening.to_f64().expect("bounded opening value"),
        );
    }
    let mut factors = BTreeMap::new();
    let mut funded = BigDecimal::from(0);
    let mut schedule = Vec::new();
    let mut series = Vec::new();
    let mut previous = start;
    let mut closing = opening.clone();
    for date in dates {
        let days = (date - previous).num_days();
        if days > 0 {
            for (rate, balance) in &mut balances {
                let factor = factors.entry((*rate, days)).or_insert_with(|| {
                    let base = 1.0 + f64::from_bits(*rate);
                    base.powf(days as f64 / 365.0)
                });
                *balance *= *factor;
            }
        }
        for &index in flows.dates.get(&date).into_iter().flatten() {
            let event = &flows.programs[index];
            funded += &event.total;
            flat += &event.flat;
            for &(rate, amount) in &event.growing {
                *balances.entry(rate).or_default() += amount;
            }
            schedule.push(Flow {
                date,
                deposit: index,
            });
        }
        let growing = balances.values().sum::<f64>();
        closing = &flat + BigDecimal::from_f64(growing).expect("forecast values are bounded");
        series.push(Point {
            date,
            value: money(&closing),
        });
        previous = date;
    }
    Forecast {
        target_value: money(&closing),
        deposits: text(&funded),
        growth: money(&(&closing - opening - &funded)),
        goal_difference: money(&(&closing - goal())),
        series,
        schedule,
        instructions: flows
            .programs
            .into_iter()
            .map(|program| program.instruction)
            .collect(),
    }
}

pub(crate) fn calculate_json(input: &str) -> Result<String> {
    #[derive(Deserialize)]
    struct Input {
        snapshot: Snapshot,
        assumptions: Request,
    }
    if input.len() > 640 * 1024 {
        return Err(Error("input_size_limit"));
    }
    let Input {
        snapshot,
        assumptions,
    } = serde_json::from_str(input).map_err(|_| Error("projection_request_invalid"))?;
    let opening = snapshot.opening()?;
    let capture_time = snapshot.account_retrieval.retrieval_completed_at.clone();
    let start = instant(&capture_time)?.with_timezone(&Utc).date_naive();
    if !(0..=MAX_PERIODS).contains(&(target_date() - start).num_days()) {
        return Err(Error("projection_horizon_unavailable"));
    }
    let rate = growth_rate(&assumptions.opening_growth_pct)?;
    let tickers = snapshot
        .positions
        .iter()
        .map(|row| row.ticker.as_str())
        .collect();
    let [first, second] = assumptions.plans;
    let run = |plan| {
        dated_flows(plan, start, &tickers).map(|flows| forecast(&opening, rate, start, flows))
    };
    let report = Report {
        method: METHOD,
        availability: "available",
        source: "trading212",
        currency: "GBP",
        capture_time,
        opening_value: text(&opening),
        opening_growth_pct: text(&decimal(&assumptions.opening_growth_pct)?),
        target_date: target_date(),
        goal: text(&goal()),
        baseline: forecast(&opening, rate, start, DepositSchedule::default()),
        plans: [run(first)?, run(second)?],
    };
    serde_json::to_string(&report).map_err(|_| Error("output_failed"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    fn allocation(kind: &str, name: &str, share: &str, rate: &str) -> Value {
        json!({"kind": kind, "name": name, "share": share, "growth_pct": rate})
    }

    fn deposit(date: &str, frequency: &str, unit: &str, allocations: Vec<Value>) -> Value {
        json!({"first_date": date, "frequency": frequency, "amount": "100",
            "unit": unit, "allocations": allocations})
    }

    fn run(opening_growth_pct: &str, a: Vec<Value>, b: Vec<Value>) -> Result<Value> {
        let request = json!({
            "snapshot": {
                "source": "trading212", "basis": "broker_reported", "currency": "GBP",
                "total_value": "1000", "positions": [{"ticker": "SYNTH"}],
                "account_retrieval": {"retrieval_completed_at": "2029-04-30T21:59:00Z"}
            },
            "assumptions": {"opening_growth_pct": opening_growth_pct,
                "plans": [{"deposits": a}, {"deposits": b}]}
        });
        Ok(serde_json::from_str(&calculate_json(&request.to_string())?).unwrap())
    }

    #[test]
    fn zero_growth_repeats_at_calendar_month_end_including_target() {
        let report = run(
            "0",
            vec![deposit(
                "2030-01-01",
                "monthly",
                "gbp",
                vec![allocation("cash", "", "100", "0")],
            )],
            vec![],
        )
        .unwrap();
        assert_eq!(report["baseline"]["target_value"], "1000");
        let plan = &report["plans"][0];
        assert_eq!(plan["target_value"], "1400");
        assert_eq!(plan["deposits"], "400");
        assert_eq!(plan["growth"], "0");
        assert_eq!(plan["goal_difference"], "-98600");
        let dates: Vec<_> = plan["schedule"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| &row["date"])
            .collect();
        assert_eq!(
            dates,
            ["2030-01-31", "2030-02-28", "2030-03-31", "2030-04-30"]
        );
    }

    #[test]
    fn target_date_deposit_has_no_growth() {
        let report = run(
            "10",
            vec![deposit(
                "2030-04-30",
                "once",
                "percent",
                vec![allocation("holding", "SYNTH", "100", "-100")],
            )],
            vec![],
        )
        .unwrap();
        assert_eq!(report["baseline"]["target_value"], "1100");
        assert_eq!(report["plans"][0]["target_value"], "1200");
        assert_eq!(report["plans"][0]["growth"], "100");
    }

    #[test]
    fn two_stock_splits_preserve_contributions_but_change_growth() {
        let plan = |growth_share: &str, flat_share: &str, unit: &str| {
            vec![deposit(
                "2029-04-30",
                "once",
                unit,
                vec![
                    allocation("hypothetical", "Synthetic growth", growth_share, "20"),
                    allocation("holding", "SYNTH", flat_share, "0"),
                ],
            )]
        };
        let report = run("0", plan("25", "75", "percent"), plan("75", "25", "gbp")).unwrap();
        assert_eq!(report["plans"][0]["deposits"], "100");
        assert_eq!(report["plans"][1]["deposits"], "100");
        assert_eq!(report["plans"][0]["target_value"], "1105");
        assert_eq!(report["plans"][1]["target_value"], "1115");
    }

    #[test]
    fn invalid_allocations_fail_in_both_units() {
        for (unit, rows, error) in [
            (
                "gbp",
                vec![allocation("cash", "", "99.99", "0")],
                "allocation_total_invalid",
            ),
            (
                "percent",
                vec![allocation("cash", "", "100.01", "0")],
                "allocation_amount_invalid",
            ),
            (
                "percent",
                vec![allocation("cash", "", "-5", "0")],
                "allocation_amount_invalid",
            ),
            (
                "percent",
                vec![allocation("holding", "UNKNOWN", "100", "0")],
                "destination_invalid",
            ),
        ] {
            let result = run("0", vec![deposit("2029-04-30", "once", unit, rows)], vec![]);
            assert_eq!(result.unwrap_err(), Error(error));
        }
    }
}
