# Alert rules and lifecycle

Status: CONFIRMED alert families and recovery re-arm policy; group threshold 10%, portfolio two-trading-day maximum drawdown threshold 2%; ADOPTED persistence model.

## Rule catalogue

| Family | Entity / basis | Trigger |
| --- | --- | --- |
| Group drawdown | Every group; compatible flow-adjusted group wealth index, EOD and eligible intraday | Drawdown from its supported running peak >=10% by default |
| Portfolio rolling drawdown | Whole ISA, EOD and eligible intraday | Largest ordered peak-to-trough fall inside the rolling two-trading-day window >=2% |
| Other drawdown | Holding/longer-horizon portfolio, if configured | Additional explicit thresholds; not replacements for the confirmed rules |
| Daily move | Held listing, intraday | Absolute or signed configured move against previous approved session close; rule states direction |
| Holding weight | Held listing, current GBP valuation | Weight exceeds configured NAV fraction |
| Group weight | Current group aggregate | Weight exceeds configured NAV fraction |
| VaR95 | Portfolio, approved daily analytics | Specified one-period loss exceeds configured NAV fraction |
| Average correlation | Eligible held universe, approved daily analytics | Average exceeds configured threshold |
| Held pair correlation | Two nonzero positions, 90-day eligible sample | Coefficient exceeds default 0.85 or configured threshold |
| Benchmark correlation | Holding/group versus verified VUAG proxy | Coefficient exceeds configured threshold |
| Effective bets | Eligible held universe | Diagnostic falls below configured threshold |
| Data quality | Price/FX/source/job | Session-aware staleness, failed refresh, missing mapping or invalid data |
| Import failure | Import/sync run | Failed accepted operation, with safe error and impacted coverage |
| Thesis review | Instrument/group thesis | Review date due and not superseded/completed |
| Group conflict | Instrument | Competing labels or unresolved assignment requires review |

Rules have stable IDs, typed thresholds/units, direction, evaluation basis, entity scope, enabled flag, settings revision and required input quality. No default threshold is invented where the owner did not supply one. In-app presentation and acknowledgement are in scope; email/Slack/push delivery requires a separate authorised feature.

## State machine

Maintain `armed → active → recovered/armed` for a rule/entity/basis. A crossing creates one alert with excursion ID, threshold, observed value, time, session, source/result revision, quality and `intraday` or `eod`. Subsequent outside-threshold evaluations update the existing excursion severity/value; they do not generate new notifications.

Acknowledgement records user/time without changing market-condition state. Recovery and acknowledgement are different events. A manually acknowledged active breach remains active until recovery. Restarting the process must not re-fire every active alert.

CONFIRMED policy: re-arm after the measured condition recovers inside its threshold; a subsequent crossing may fire in the same session. At the threshold itself the condition remains breached (>= for drawdown). A separately configurable hysteresis band may reduce chatter, but its default is zero unless explicitly set. Q08's re-arm choice is resolved. Threshold changes retire/re-evaluate state with a new rule revision.

For portfolio observations W at ordered times within the rolling window, compute max(1-W_trough/W_peak) over peak time <= trough time with both observations inside that window. Use a cash-flow-adjusted wealth index, not raw NAV or a simple two-day endpoint return. The two-day horizon uses the selected portfolio trading calendar, not 48 wall-clock hours; retain the calendar/cutoff convention with the run. Do not interpolate missed intraday peaks/troughs; disclose sampling and gaps. Intraday and daily-only estimates are labelled separately. The group 10% rule uses its supported running peak; it is not restricted to two days.

A rolling maximum retains an earlier decline until that decline ages out of the window: a price rebound alone may not bring the rolling statistic below 2%. Re-arm only when the statistic is genuinely below threshold, avoiding repeated notifications for the same historical drop.

## Evaluation quality

- Intraday move/drawdown/weight evaluations occur after committed eligible live valuation updates. Daily correlation/VaR alerts use approved analytical runs only.
- If required data becomes missing/stale, mark the financial rule's state unknown and preserve prior excursion. Do not infer recovery from a missing coefficient or zero-filled price. A separate quality alert explains the outage.
- A new instrument universe, group membership, estimator or threshold revision is recorded with a rebaseline event; distinguish a changed model from an ordinary market threshold crossing.
- Global live weights require a coherent denominator with known coverage. Do not fire a concentration alert caused solely by a failed price disappearing from NAV.
- Live drawdown uses a defined compatible wealth/price peak and flow treatment; raw NAV deposits do not count as recovery or a new investment high without qualification.

## Sessions and dates

Holding daily moves use that listing's exchange session and prior approved close. Portfolio/group sessions span multiple exchanges; Q13 must select the display session convention, initially proposed Europe/London date with explicit instrument session IDs retained. Correlation alerts identify analytical as-of date rather than a quote poll's session.

Thesis and group-review alerts are persistent review items. Re-importing the same unresolved label or polling an overdue thesis does not create another copy. A changed review date or resolved/reopened conflict has an explicit lifecycle transition.

## Acceptance

Fixed-clock tests cover first crossing, repeated outside values, acknowledgement while active, recovery, hysteresis boundary, second crossing, restart, threshold revision, insufficient samples, stale FX, missing prior close, group merge and both login sessions. Assert that intraday and EOD excursions cannot overwrite each other. Alert retention must preserve the method/source revision required to explain the event.
