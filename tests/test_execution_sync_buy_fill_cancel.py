from decimal import Decimal
from unittest.mock import Mock

import execution_sync_buy_fill as target


def build_order():
    return {
        "id": 80,
        "connector_order_request_id": 77,
        "result_payload": {},
    }


def build_request(status):
    return {
        "id": 77,
        "request_status": status,
        "broker_order_no": "BROKER-77",
        "broker_branch_code": "BRANCH",
        "last_event_at": "2026-08-03T09:00:00",
    }


def test_filled_buy_is_synced(monkeypatch):
    order = build_order()
    request = build_request("FILLED")

    fills = [
        {
            "id": 1001,
            "fill_qty": 39,
            "fill_amount": Decimal("780000"),
            "fill_ts": "2026-08-03T09:01:00",
        }
    ]

    monkeypatch.setattr(
        target,
        "get_connector_order_request",
        Mock(return_value=request),
    )
    monkeypatch.setattr(
        target,
        "get_connector_buy_fills",
        Mock(return_value=fills),
    )
    monkeypatch.setattr(
        target,
        "mark_execution_order_filled",
        Mock(
            return_value={
                "id": 80,
                "execution_status": "FILLED",
            }
        ),
    )

    result = target.sync_one_order(
        conn=object(),
        execution_order=order,
    )

    assert result["status"] == "SYNCED"
    assert result["fill_summary"]["total_fill_qty"] == 39
    assert result["fill_summary"]["total_fill_amount"] == Decimal("780000")

    target.mark_execution_order_filled.assert_called_once()


def test_canceled_buy_without_fill_is_terminal(monkeypatch):
    order = build_order()
    request = build_request("CANCELED")

    monkeypatch.setattr(
        target,
        "get_connector_order_request",
        Mock(return_value=request),
    )
    monkeypatch.setattr(
        target,
        "get_connector_buy_fills",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        target,
        "mark_execution_order_canceled",
        Mock(
            return_value={
                "id": 80,
                "execution_status": "CANCELED",
            }
        ),
    )

    result = target.sync_one_order(
        conn=object(),
        execution_order=order,
    )

    assert result["status"] == "CANCELED"
    assert result["execution_update"]["execution_status"] == "CANCELED"

    target.mark_execution_order_canceled.assert_called_once()


def test_cancelled_alias_without_fill_is_terminal(monkeypatch):
    order = build_order()
    request = build_request("CANCELLED")

    monkeypatch.setattr(
        target,
        "get_connector_order_request",
        Mock(return_value=request),
    )
    monkeypatch.setattr(
        target,
        "get_connector_buy_fills",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        target,
        "mark_execution_order_canceled",
        Mock(
            return_value={
                "id": 80,
                "execution_status": "CANCELED",
            }
        ),
    )

    result = target.sync_one_order(
        conn=object(),
        execution_order=order,
    )

    assert result["status"] == "CANCELED"


def test_canceled_buy_with_fill_is_error(monkeypatch):
    order = build_order()
    request = build_request("CANCELED")

    fills = [
        {
            "id": 1002,
            "fill_qty": 1,
            "fill_amount": Decimal("20000"),
            "fill_ts": "2026-08-03T09:01:00",
        }
    ]

    monkeypatch.setattr(
        target,
        "get_connector_order_request",
        Mock(return_value=request),
    )
    monkeypatch.setattr(
        target,
        "get_connector_buy_fills",
        Mock(return_value=fills),
    )
    monkeypatch.setattr(
        target,
        "mark_execution_order_canceled",
        Mock(),
    )

    result = target.sync_one_order(
        conn=object(),
        execution_order=order,
    )

    assert result["status"] == "ERROR"
    assert result["reason"] == "CANCELED_BUY_ORDER_HAS_FILL"

    target.mark_execution_order_canceled.assert_not_called()


def test_active_request_remains_failure(monkeypatch):
    order = build_order()
    request = build_request("ACCEPTED")

    monkeypatch.setattr(
        target,
        "get_connector_order_request",
        Mock(return_value=request),
    )

    result = target.sync_one_order(
        conn=object(),
        execution_order=order,
    )

    assert result["status"] == "SKIP"
    assert result["reason"] == "CONNECTOR_ORDER_NOT_FILLED:ACCEPTED"