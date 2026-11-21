//! Effective-date Bank Rate facts, reviewed against the Bank of England Database.
//! Source: Bank of England Database. Reused under Open Government Licence v3.0.
use chrono::NaiveDate;

pub(super) const SOURCE: &str = "Bank of England Database · Official Bank Rate";
pub(super) const URL: &str = "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp";
pub(super) const VERIFIED_THROUGH: NaiveDate = date(2026, 11, 21);
const CHANGES: [(NaiveDate, f64); 3] = [
    (date(2025, 8, 7), 4.00),
    (date(2025, 12, 18), 3.75),
    (date(2026, 11, 5), 4.00),
];

const fn date(year: i32, month: u32, day: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(year, month, day).unwrap()
}

pub(super) fn first_covered() -> NaiveDate {
    CHANGES[0].0.succ_opt().expect("valid coverage start")
}

pub(super) fn opening_rate(day: NaiveDate) -> Option<f64> {
    if day > VERIFIED_THROUGH {
        return None;
    }
    // The official history has dates. Use the previous published rate when
    // opening falls on a change date and its effective instant is unknown.
    CHANGES
        .iter()
        .rfind(|(effective, _)| *effective < day)
        .map(|(_, rate)| *rate)
}
