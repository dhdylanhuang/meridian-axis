from datetime import UTC, datetime
from decimal import Decimal

from meridian.application import export_evidence


def test_allowance_replaces_older_funds_before_counting_subscriptions():
    amounts = [5000, -9000, 3000, 1500]
    result = export_evidence.allowance([(None, Decimal(amount)) for amount in amounts])
    assert result == {
        "net_subscriptions_gbp": "500",
        "remaining_from_this_isa_only_gbp": "19500",
        "prior_funds_replaceable_gbp": "0",
    }


def test_export_projects_flows_fills_dividends_and_turnover(monkeypatch):
    end = "2026-11-28T16:00:00+00:00"
    value = {
        "start": "2026-10-28T16:00:00+00:00",
        "end": end,
        "weekly": {"2026-11-25": "2026-11-25T16:00:00+00:00"},
        "turnover_open": {
            "account_captured_at": "2025-11-28T16:00:00+00:00",
            "invested_value": "800",
        },
        "securities_gbp": "1200",
    }
    date = datetime.fromisoformat
    coverage = (date("2025-11-01T00:00:00+00:00"), date("2026-11-29T00:00:00+00:00"))
    at = date("2026-11-19T16:00:00+00:00")

    def funding(*_):
        return {
            "coverage": {"start_at": coverage[0].isoformat(), "end_at": coverage[1].isoformat()},
            "events": [
                {
                    "at": "2026-04-05T23:00:00+00:00",
                    "amount": "500",
                    "kind": "DEPOSIT",
                    "currency": "GBP",
                },
                {"at": at.isoformat(), "amount": "-50", "kind": "WITHDRAW", "currency": "GBP"},
            ],
        }

    def history(_db, family, *_):
        if family == "orders":
            return [
                (
                    at,
                    {
                        "order": {"ticker": "SYNl_EQ", "side": "SELL", "currency": "GBP"},
                        "fill": {
                            "quantity": "0.5",
                            "price": "10",
                            "type": "TRADE",
                            "walletImpact": {
                                "currency": "GBP",
                                "netValue": "5",
                                "realisedProfitLoss": "2",
                            },
                        },
                    },
                )
            ], coverage
        return [(at, {"ticker": "SYNl_EQ", "amount": "3", "currency": "GBP"})], coverage

    monkeypatch.setattr(export_evidence, "performance_input", funding)
    monkeypatch.setattr(export_evidence, "_history", history)
    export = export_evidence.export_history(None, value, datetime(2026, 11, 30, tzinfo=UTC))
    assert export["isa"]["tax_year_start"] == "2026-04-06"
    assert export["isa"]["net_subscriptions_gbp"] == "450"
    assert export["monthly_net_deposits_gbp"] == "-50"
    assert export["weekly_net_deposits_gbp"] == {"2026-11-25": "450"}
    assert export["monthly_dividends_gbp"] == {"SYNl_EQ": "3"}
    assert export["monthly_trade_activity"] == ["SYNl_EQ"]
    assert export["trades"][0]["realised_pnl_gbp"] == "2"
    assert export["turnover_pct"] == "0.5"
