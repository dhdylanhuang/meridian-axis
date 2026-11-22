//! Cash-flow-adjusted returns at reviewed daily portfolio endpoints.
use super::super::{growth, pct, round, CheckedEvent, Mark, RiskRange};
use super::{Sample, MAX_DAILY};
use crate::risk_sessions::{level, Reviewed, Session};
use crate::{decimal, instant, text};
use bigdecimal::{BigDecimal, ToPrimitive};
use chrono::{DateTime, FixedOffset, NaiveDate};
use serde_json::{json, Value};

pub(super) type Coverage = Option<(DateTime<FixedOffset>, DateTime<FixedOffset>)>;

fn mark(row: &Session) -> Option<Mark> {
    Some(Mark {
        time: instant(&row.cutoff_at).ok()?,
        value: decimal(row.portfolio_value_gbp.as_deref()?).ok()?,
    })
}

pub(super) struct Stretch {
    start: NaiveDate,
    end: NaiveDate,
    count: usize,
    factor: BigDecimal,
    benchmark_factor: Option<BigDecimal>,
}

impl Stretch {
    pub(super) fn report(self) -> Value {
        json!({
            "start_date":self.start, "end_date":self.end, "sessions":self.count,
            "portfolio_pct":pct(&self.factor),
            "vuag_pct":self.benchmark_factor.as_ref().map(pct),
            "spread_pp":self.benchmark_factor.as_ref().map(|proxy| text(&round(&((&self.factor - proxy) * 100), 6))),
        })
    }
}

pub(super) fn extend(
    track: &mut Option<Stretch>,
    last: &mut Option<Stretch>,
    start: NaiveDate,
    end: NaiveDate,
    factor: Option<&BigDecimal>,
    benchmark: Option<&BigDecimal>,
) {
    let Some(factor) = factor else {
        if let Some(closed) = track.take() {
            *last = Some(closed);
        }
        return;
    };
    let stretch = track.get_or_insert_with(|| Stretch {
        start,
        end,
        count: 0,
        factor: 1.into(),
        benchmark_factor: benchmark.map(|_| 1.into()),
    });
    stretch.end = end;
    stretch.count += 1;
    stretch.factor = round(&(&stretch.factor * factor), 24);
    if let Some((chain, proxy)) = stretch.benchmark_factor.as_mut().zip(benchmark) {
        *chain = round(&(&*chain * proxy), 24);
    }
}

pub(super) fn calculate(
    data: &Reviewed,
    range: &RiskRange,
    covered: Coverage,
    events: &[CheckedEvent],
) -> (Vec<Sample>, Value) {
    let left = data.sessions.partition_point(|row| row.date < range.start);
    let right = data.sessions.partition_point(|row| row.date <= range.end);
    let rows = &data.sessions[left.max(right.saturating_sub(MAX_DAILY + 1))..right];
    let marks: Vec<_> = rows.iter().map(mark).collect();
    let mut portfolio = None;
    let mut matched = None;
    let mut latest = None;
    let mut latest_matched = None;
    let mut returns = Vec::new();
    let mut samples = Vec::new();
    for (i, pair) in rows.windows(2).enumerate() {
        let (a, b) = (&pair[0], &pair[1]);
        let result = marks[i]
            .as_ref()
            .zip(marks[i + 1].as_ref())
            .ok_or("missing_session_valuation")
            .and_then(|(start, end)| growth(start, end, covered, events));
        let factor = result.as_ref().ok().map(|(growth, _, _)| growth);
        let price = |row: &Session| {
            row.vuag_index
                .as_deref()
                .and_then(|value| decimal(value).ok())
        };
        let benchmark = price(a)
            .zip(price(b))
            .map(|(start, end)| round(&(end / start), 24))
            .filter(|ratio| ratio > &0);
        extend(&mut portfolio, &mut latest, a.date, b.date, factor, None);
        extend(
            &mut matched,
            &mut latest_matched,
            a.date,
            b.date,
            factor.filter(|_| benchmark.is_some()),
            benchmark.as_ref(),
        );
        if let Some(portfolio_ratio) = factor
            .and_then(ToPrimitive::to_f64)
            .filter(|x| x.is_finite() && *x > 0.0)
        {
            samples.push(Sample {
                start: a.date,
                end: b.date,
                portfolio_ratio,
                vuag_ratio: benchmark.as_ref().and_then(ToPrimitive::to_f64),
                rate_pct: None,
                nav: b.portfolio_value_gbp.as_deref().and_then(level),
            });
        }
        returns.push(json!({
            "start":a.date, "end":b.date, "start_at":a.cutoff_at,"end_at":b.cutoff_at,
            "portfolio_pct":factor.map(pct), "reason":result.as_ref().err(),
            "external_flow_count":result.as_ref().ok().map(|row| row.2),
            "net_external_flow_gbp":result.as_ref().ok().map(|row| text(&row.1)),
            "vuag_pct":benchmark.as_ref().map(pct),
            "vuag_start_at":a.vuag_close_at.as_ref().filter(|_| a.vuag_index.is_some()),
            "vuag_end_at":b.vuag_close_at.as_ref().filter(|_| b.vuag_index.is_some()),
        }));
    }
    (
        samples,
        json!({
            "method":"reviewed_session_modified_dietz_gbp_v1","reviewed_at":data.reviewed_at,
            "latest_portfolio":portfolio.or(latest).map(Stretch::report),
            "latest_matched":matched.or(latest_matched).map(Stretch::report), "rows":returns,
        }),
    )
}
