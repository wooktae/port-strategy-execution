from unittest.mock import Mock

import execution_validate_order_chain as target


PLAN_TABLE = '"execution"."strategy_execution_plan"'
REQUEST_TABLE = '"execution"."connector_order_request"'
FILL_TABLE = '"execution"."connector_fill"'
POSITION_TABLE = '"execution"."strategy_position_state"'


def build_order(status="FILLED"):
    return {
        "id": 80,
        "execution_plan_id": 20,
        "execution_mode": "PAPER_STRATEGY",
        "action_type": "BUY",
        "execution_status": status,
        "ticker_code": "183300",
        "order_qty": 39,
        "connector_order_request_id": 77,
        "source_position_state_id": None,
    }


def build_request(status="FILLED"):
    return {
        "id": 77,
        "request_type": "BUY",
        "request_status": status,
        "ticker_code": "183300",
        "order_qty": 39,
    }


def build_fill(qty=39):
    return {
        "id": 1001,
        "order_request_id": 77,
        "ticker_code": "183300",
        "side": "BUY",
        "fill_qty": qty,
    }


def build_position():
    return {
        "id": 501,
        "ticker_code": "183300",
        "entry_qty": 39,
        "remaining_qty": 39,
    }


def install_common_mocks(
    monkeypatch,
    *,
    request,
    fills,
    position,
):
    def fetch_one_by_id(conn, table_ref, row_id):
        if table_ref == PLAN_TABLE and row_id == 20:
            return {"id": 20}

        if table_ref == REQUEST_TABLE and row_id == 77:
            return request

        return None

    monkeypatch.setattr(
        target,
        "_fetch_one_by_id",
        Mock(side_effect=fetch_one_by_id),
    )

    monkeypatch.setattr(
        target,
        "_load_fills",
        Mock(return_value=fills),
    )

    monkeypatch.setattr(
        target,
        "_load_position_by_buy_order",
        Mock(return_value=position),
    )


def validate(order):
    return target._validate_order(
        conn=object(),
        order=order,
        plan_table=PLAN_TABLE,
        request_table=REQUEST_TABLE,
        fill_table=FILL_TABLE,
        position_table=POSITION_TABLE,
    )


def error_codes(errors):
    return {
        error["code"]
        for error in errors
    }


def test_filled_buy_chain_is_valid(monkeypatch):
    install_common_mocks(
        monkeypatch,
        request=build_request("FILLED"),
        fills=[build_fill(39)],
        position=build_position(),
    )

    errors = validate(build_order("FILLED"))

    assert errors == []


def test_canceled_buy_chain_without_fill_or_position_is_valid(
    monkeypatch,
):
    install_common_mocks(
        monkeypatch,
        request=build_request("CANCELED"),
        fills=[],
        position=None,
    )

    errors = validate(build_order("CANCELED"))

    assert errors == []


def test_cancelled_alias_chain_is_valid(monkeypatch):
    install_common_mocks(
        monkeypatch,
        request=build_request("CANCELLED"),
        fills=[],
        position=None,
    )

    errors = validate(build_order("CANCELLED"))

    assert errors == []


def test_canceled_buy_with_fill_is_invalid(monkeypatch):
    install_common_mocks(
        monkeypatch,
        request=build_request("CANCELED"),
        fills=[build_fill(1)],
        position=None,
    )

    errors = validate(build_order("CANCELED"))

    assert "CANCELED_ORDER_HAS_FILL" in error_codes(errors)


def test_canceled_execution_with_active_request_is_invalid(
    monkeypatch,
):
    install_common_mocks(
        monkeypatch,
        request=build_request("ACCEPTED"),
        fills=[],
        position=None,
    )

    errors = validate(build_order("CANCELED"))

    assert (
        "CANCELED_ORDER_REQUEST_STATUS_MISMATCH"
        in error_codes(errors)
    )


def test_canceled_buy_with_position_trace_is_invalid(
    monkeypatch,
):
    install_common_mocks(
        monkeypatch,
        request=build_request("CANCELED"),
        fills=[],
        position=build_position(),
    )

    errors = validate(build_order("CANCELED"))

    assert "CANCELED_BUY_HAS_POSITION_TRACE" in error_codes(errors)


def test_filled_buy_without_position_is_invalid(monkeypatch):
    install_common_mocks(
        monkeypatch,
        request=build_request("FILLED"),
        fills=[build_fill(39)],
        position=None,
    )

    errors = validate(build_order("FILLED"))

    assert "BUY_POSITION_NOT_FOUND" in error_codes(errors)


def test_filled_buy_with_partial_fill_is_invalid(monkeypatch):
    install_common_mocks(
        monkeypatch,
        request=build_request("FILLED"),
        fills=[build_fill(20)],
        position=build_position(),
    )

    errors = validate(build_order("FILLED"))

    assert "ORDER_FILL_QTY_MISMATCH" in error_codes(errors)