from decimal import Decimal
from unittest.mock import Mock

import execution_daily_signal_builder as target
from execution_buy_sizing import (
    MARKET_BUY_CASH_RESERVE_RATIO,
    calculate_buy_order_sizing,
)


def build_balance(orderable_cash="100000"):
    return {
        "orderable_cash": Decimal(orderable_cash),
        "cash_balance": Decimal(orderable_cash),
        "total_eval_amount": Decimal("1000000"),
    }


def test_ready_orders_use_decreasing_remaining_cash(monkeypatch):
    calls = []

    def fake_build_order(
        conn,
        plan_id,
        account,
        balance,
        daily_run,
        signal,
        available_cash_override=None,
        allocation_sequence=None,
        initial_available_cash=None,
    ):
        calls.append(
            {
                "signal_id": signal["id"],
                "available_cash_override": available_cash_override,
                "allocation_sequence": allocation_sequence,
                "initial_available_cash": initial_available_cash,
            }
        )

        reserved_amount = {
            1: Decimal("40000"),
            2: Decimal("35000"),
            3: Decimal("25000"),
        }[signal["id"]]

        return {
            "execution_status": "READY",
            "estimated_order_amount": reserved_amount,
            "required_cash_amount": reserved_amount,
            "validation_result": "{}",
        }

    monkeypatch.setattr(
        target,
        "build_daily_signal_buy_execution_order",
        Mock(side_effect=fake_build_order),
    )

    result = target.build_daily_signal_execution_orders(
        conn=object(),
        plan_id=10,
        account={"id": 1, "account_no": "TEST"},
        balance=build_balance("100000"),
        daily_run={"id": 20},
        signals=[
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ],
    )

    assert len(result) == 3

    assert [
        call["available_cash_override"]
        for call in calls
    ] == [
        Decimal("100000"),
        Decimal("60000"),
        Decimal("25000"),
    ]

    assert [
        call["allocation_sequence"]
        for call in calls
    ] == [1, 2, 3]

    assert all(
        call["initial_available_cash"] == Decimal("100000")
        for call in calls
    )


def test_blocked_order_does_not_reserve_cash(monkeypatch):
    calls = []

    def fake_build_order(
        conn,
        plan_id,
        account,
        balance,
        daily_run,
        signal,
        available_cash_override=None,
        allocation_sequence=None,
        initial_available_cash=None,
    ):
        calls.append(available_cash_override)

        if signal["id"] == 1:
            return {
                "execution_status": "BLOCKED",
                "estimated_order_amount": Decimal("90000"),
                "required_cash_amount": Decimal("99000"),
                "validation_result": "{}",
            }

        return {
            "execution_status": "READY",
            "estimated_order_amount": Decimal("30000"),
            "required_cash_amount": Decimal("33000"),
            "validation_result": "{}",
        }

    monkeypatch.setattr(
        target,
        "build_daily_signal_buy_execution_order",
        Mock(side_effect=fake_build_order),
    )

    result = target.build_daily_signal_execution_orders(
        conn=object(),
        plan_id=10,
        account={"id": 1, "account_no": "TEST"},
        balance=build_balance("100000"),
        daily_run={"id": 20},
        signals=[
            {"id": 1},
            {"id": 2},
        ],
    )

    assert len(result) == 2
    assert calls == [
        Decimal("100000"),
        Decimal("100000"),
    ]


def test_reserved_amount_never_makes_cash_negative(monkeypatch):
    calls = []

    def fake_build_order(
        conn,
        plan_id,
        account,
        balance,
        daily_run,
        signal,
        available_cash_override=None,
        allocation_sequence=None,
        initial_available_cash=None,
    ):
        calls.append(available_cash_override)

        return {
            "execution_status": "READY",
            "estimated_order_amount": Decimal("150000"),
            "required_cash_amount": Decimal("165000"),
            "validation_result": "{}",
        }

    monkeypatch.setattr(
        target,
        "build_daily_signal_buy_execution_order",
        Mock(side_effect=fake_build_order),
    )

    target.build_daily_signal_execution_orders(
        conn=object(),
        plan_id=10,
        account={"id": 1, "account_no": "TEST"},
        balance=build_balance("100000"),
        daily_run={"id": 20},
        signals=[
            {"id": 1},
            {"id": 2},
        ],
    )

    assert calls == [
        Decimal("100000"),
        Decimal("0"),
    ]

def test_buy_sizing_requires_110_percent_cash():
    result = calculate_buy_order_sizing(
        available_cash=Decimal("1053963"),
        total_eval_amount=Decimal("8542073"),
        position_size=Decimal("0.11954165"),
        latest_price=Decimal("127200"),
        current_position_qty=0,
        current_position_eval_amount=Decimal("0"),
        min_order_amount=Decimal("10000"),
        max_order_amount=Decimal("4271036.50"),
    )

    assert MARKET_BUY_CASH_RESERVE_RATIO == Decimal("1.10")
    assert result["order_qty"] == 7
    assert result["estimated_order_amount"] == Decimal("890400")
    assert result["required_cash_amount"] == Decimal("979440.00")


def test_second_buy_uses_cash_remaining_after_110_percent_reserve():
    first = calculate_buy_order_sizing(
        available_cash=Decimal("1053963"),
        total_eval_amount=Decimal("8542073"),
        position_size=Decimal("0.11954165"),
        latest_price=Decimal("127200"),
        current_position_qty=0,
        current_position_eval_amount=Decimal("0"),
        min_order_amount=Decimal("10000"),
        max_order_amount=Decimal("4271036.50"),
    )
    remaining_cash = (
        Decimal("1053963") - first["required_cash_amount"]
    )

    second = calculate_buy_order_sizing(
        available_cash=remaining_cash,
        total_eval_amount=Decimal("8542073"),
        position_size=Decimal("0.08045835"),
        latest_price=Decimal("40100"),
        current_position_qty=0,
        current_position_eval_amount=Decimal("0"),
        min_order_amount=Decimal("10000"),
        max_order_amount=Decimal("4271036.50"),
    )

    assert remaining_cash == Decimal("74523.00")
    assert second["order_qty"] == 1
    assert second["estimated_order_amount"] == Decimal("40100")
    assert second["required_cash_amount"] == Decimal("44110.00")
    assert remaining_cash - second["required_cash_amount"] == Decimal(
        "30413.00"
    )
