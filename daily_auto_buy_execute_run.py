import argparse
import sys
from pathlib import Path
from datetime import date

from execution_db import get_conn
from execution_config import STRATEGY_NAME, STRATEGY_VERSION
from execution_repository import (
    get_ready_daily_buy_execution_orders,
    mark_execution_order_execution_mode,
    mark_execution_order_submitted,
    mark_execution_order_execute_failed,
)

# -------------------------------------------------
# Market Connector import path
# -------------------------------------------------
CONNECTOR_PATH = Path(r"C:\Workspaces\port-marketconnector").resolve()

if not CONNECTOR_PATH.exists():
    raise RuntimeError(f"Market Connector 경로가 없음: {CONNECTOR_PATH}")

sys.path.insert(0, str(CONNECTOR_PATH))

try:
    from connector_buy import buy_stock  # noqa: E402
except ModuleNotFoundError as e:
    print("[IMPORT ERROR]")
    print(f"CONNECTOR_PATH = {CONNECTOR_PATH}")
    print(f"sys.path[0]    = {sys.path[0]}")
    print("connector_buy.py 파일이 C:\\Workspaces\\port-marketconnector 아래에 있는지 확인 필요")
    raise e


EXECUTION_MODE_PAPER_STRATEGY = "PAPER_STRATEGY"
SIZING_POLICY = "PAPER_STRATEGY_FULL_STRATEGY_QTY"

ACCEPTED_REQUEST_STATUSES = {"SUBMITTED", "ACCEPTED", "ORDERED"}
REJECTED_REQUEST_STATUSES = {"REJECTED", "FAILED", "ERROR"}

# -------------------------------------------------
# Korean business day guard
# -------------------------------------------------
def _load_kr_holiday_checker():
    """
    port-interest-crawler / port_interest_crawler 쪽의 interest_get_holidays.py를
    사용할 수 있으면 한국 휴장일/공휴일 판정을 함께 사용한다.
    없으면 주말 판정만 수행한다.
    """
    candidate_paths = [
        Path(r"C:\Workspaces\port-interest-crawler"),
        Path(r"C:\Workspaces\port_interest_crawler"),
    ]

    for path in candidate_paths:
        try:
            if path.exists() and str(path) not in sys.path:
                sys.path.insert(0, str(path))

            from interest_get_holidays import is_holiday  # noqa: WPS433
            return is_holiday
        except Exception:
            continue

    return None


def is_kr_business_day(target_date=None):
    target_date = target_date or date.today()

    if target_date.weekday() >= 5:
        return False, "WEEKEND"

    holiday_checker = _load_kr_holiday_checker()

    if holiday_checker is not None:
        try:
            if holiday_checker(target_date, "KR"):
                return False, "KR_HOLIDAY"
        except Exception:
            # 휴일 유틸 오류 때문에 배치를 죽이지는 않고, 주말 판정만 신뢰한다.
            pass

    return True, "BUSINESS_DAY"


def print_non_business_day_no_target(step_name):
    today = date.today()
    is_business_day, reason = is_kr_business_day(today)

    if is_business_day:
        return False

    print_header(f"[{step_name} Blocked]")
    print(f"today  : {today}")
    print(f"reason : {reason}")
    print("[NO_TARGET] 한국 영업일이 아니므로 주문 관련 처리를 실행하지 않습니다.")
    print("connector_order_request를 생성하지 않고 종료합니다.")

    return True



def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto execute READY Daily BUY Signal orders in PAPER_STRATEGY mode"
    )

    parser.add_argument(
        "--plan-id",
        required=False,
        type=int,
        help="특정 execution_plan_id만 자동매수 실행",
    )

    parser.add_argument(
        "--limit",
        required=False,
        type=int,
        default=20,
        help="자동매수 대상 최대 건수",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 Connector BUY 주문 실행. 없으면 조회/검증만 수행",
    )

    return parser.parse_args()


def to_int(value, default=0):
    if value is None:
        return default

    try:
        return int(value)
    except Exception:
        return default


def to_float_or_none(value):
    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def normalize_status(value):
    if value is None:
        return None

    return str(value).strip().upper()


def validate_auto_buy_order(order):
    reasons = []

    if order["environment"] != "paper":
        reasons.append(f"paper 환경이 아님: environment={order['environment']}")

    if order["source_type"] != "DAILY_SIGNAL_BUY":
        reasons.append(f"DAILY_SIGNAL_BUY가 아님: source_type={order['source_type']}")

    if order["action_type"] != "BUY":
        reasons.append(f"BUY가 아님: action_type={order['action_type']}")

    if order["execution_status"] != "READY":
        reasons.append(f"READY 상태가 아님: execution_status={order['execution_status']}")

    if order["connector_order_request_id"] is not None:
        reasons.append(
            f"이미 connector_order_request_id가 있음: {order['connector_order_request_id']}"
        )

    if order["execution_mode"] not in ("DRY_RUN", "PAPER_STRATEGY"):
        reasons.append(f"자동매수 허용 execution_mode가 아님: {order['execution_mode']}")

    if to_int(order["order_qty"], 0) <= 0:
        reasons.append(f"order_qty가 0 이하: order_qty={order['order_qty']}")

    if order["order_price"] is None:
        reasons.append("order_price 없음")

    if not order["ticker_code"]:
        reasons.append("ticker_code 없음")

    if not order["account_no"]:
        reasons.append("account_no 없음")

    return reasons


def build_connector_kwargs(order):
    return {
        "stock_code": order["ticker_code"],
        "qty": to_int(order["order_qty"], 0),
        "order_method": "MARKET",
        "order_price": None,
        "stock_name": order["stock_name"],
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "strategy_run_id": None,
        "strategy_signal_id": order.get("source_daily_signal_id"),
        "signal_date": str(order["signal_date"]),
        "signal_type": "BUY",
        "signal_score": to_float_or_none(order["signal_score"]),
        "signal_position_size": to_float_or_none(order["signal_position_size"]),
    }


def is_connector_order_accepted(result):
    """
    Connector BUY 결과가 실제로 broker/KIS에 접수된 주문인지 판단.

    주의:
    - connector_order_request row가 생성되었다고 해서 주문 접수 성공은 아님.
    - KIS가 거절해도 order_request_id는 생성될 수 있음.
    - 따라서 request_status / response_code / broker_order_no를 함께 확인해야 함.
    """

    if not result:
        return False

    if not result.get("order_request_id"):
        return False

    request_status = normalize_status(result.get("request_status"))
    response_code = result.get("response_code")
    broker_order_no = result.get("broker_order_no")

    if request_status in REJECTED_REQUEST_STATUSES:
        return False

    if response_code not in (None, "0", 0):
        return False

    if not broker_order_no:
        return False

    if request_status and request_status not in ACCEPTED_REQUEST_STATUSES:
        return False

    return True


def build_rejected_error_message(result):
    if not result:
        return "connector BUY result is empty"

    request_status = result.get("request_status")
    response_code = result.get("response_code")
    response_message = result.get("response_message")
    broker_order_no = result.get("broker_order_no")

    return (
        "connector BUY rejected or not accepted"
        f" / request_status={request_status}"
        f" / response_code={response_code}"
        f" / response_message={response_message}"
        f" / broker_order_no={broker_order_no}"
    )


def build_result_payload(order, connector_result=None, error=None):
    strategy_order_qty = to_int(order["order_qty"], 0)
    executed_order_qty = strategy_order_qty

    payload = {
        "request_type": "BUY",
        "execution_mode": EXECUTION_MODE_PAPER_STRATEGY,

        "strategy_order_qty": strategy_order_qty,
        "executed_order_qty": executed_order_qty,
        "sizing_policy": SIZING_POLICY,

        "source_type": order.get("source_type"),
        "source_daily_run_id": order.get("source_daily_run_id"),
        "source_daily_signal_id": order.get("source_daily_signal_id"),

        "ticker_code": order.get("ticker_code"),
        "stock_name": order.get("stock_name"),
        "order_price": str(order["order_price"]) if order.get("order_price") is not None else None,
        "target_amount": str(order["target_amount"]) if order.get("target_amount") is not None else None,
        "signal_position_size": (
            str(order["signal_position_size"])
            if order.get("signal_position_size") is not None
            else None
        ),

        "environment": order.get("environment"),
        "order_method": order.get("order_method"),

        "auto_execute": True,
        "auto_execute_type": "DAILY_SIGNAL_BUY_PAPER_STRATEGY",

        "connector_acceptance_check": {
            "accepted": is_connector_order_accepted(connector_result),
            "request_status": connector_result.get("request_status") if connector_result else None,
            "response_code": connector_result.get("response_code") if connector_result else None,
            "response_message": connector_result.get("response_message") if connector_result else None,
            "broker_order_no": connector_result.get("broker_order_no") if connector_result else None,
            "order_request_id": connector_result.get("order_request_id") if connector_result else None,
        },
    }

    if connector_result is not None:
        payload["connector_result"] = connector_result

    if error is not None:
        payload["error"] = error

    return payload


def print_candidate(order, index):
    print(
        f"{index}. id={order['id']} "
        f"plan={order['execution_plan_id']} "
        f"daily_run={order['source_daily_run_id']} "
        f"daily_signal={order['source_daily_signal_id']} "
        f"ticker={order['ticker_code']} "
        f"name={order['stock_name']} "
        f"qty={order['order_qty']} "
        f"price={order['order_price']} "
        f"mode={order['execution_mode']} "
        f"status={order['execution_status']}"
    )


def execute_one_auto_buy(conn, order):
    execution_order_id = order["id"]

    # -------------------------------------------------
    # 1. execution_mode를 PAPER_STRATEGY로 전환
    # -------------------------------------------------
    updated = mark_execution_order_execution_mode(
        conn=conn,
        execution_order_id=execution_order_id,
        execution_mode=EXECUTION_MODE_PAPER_STRATEGY,
    )
    conn.commit()

    print()
    print(
        f"[MODE] execution_order_id={updated['id']} "
        f"execution_mode={updated['execution_mode']} "
        f"status={updated['execution_status']}"
    )

    # -------------------------------------------------
    # 2. Connector BUY 호출
    # -------------------------------------------------
    kwargs = build_connector_kwargs(order)

    print(
        f"[CONNECTOR BUY] "
        f"ticker={order['ticker_code']} "
        f"name={order['stock_name']} "
        f"qty={kwargs['qty']} "
        f"policy={SIZING_POLICY}"
    )

    result = buy_stock(**kwargs)

    # -------------------------------------------------
    # 3. Connector 결과 판정
    # -------------------------------------------------
    if not is_connector_order_accepted(result):
        error_message = build_rejected_error_message(result)

        failed_payload = build_result_payload(
            order=order,
            connector_result=result,
            error=error_message,
        )

        failed = mark_execution_order_execute_failed(
            conn,
            execution_order_id,
            failed_payload,
            connector_order_request_id=(
                result.get("order_request_id")
                if result
                else None
            ),
        )
        conn.commit()

        print(
            f"[FAILED] execution_order_id={failed['id']} "
            f"status={failed['execution_status']} "
            f"connector_order_request_id={result.get('order_request_id') if result else None}"
        )
        print(f"reason={error_message}")
        print(result)
        return failed

    # -------------------------------------------------
    # 4. 접수 성공 시 SUBMITTED 저장
    # -------------------------------------------------
    submitted_payload = build_result_payload(
        order=order,
        connector_result=result,
    )

    submitted = mark_execution_order_submitted(
        conn,
        execution_order_id,
        result["order_request_id"],
        submitted_payload,
    )
    conn.commit()

    print(
        f"[SUBMITTED] execution_order_id={submitted['id']} "
        f"status={submitted['execution_status']} "
        f"mode={submitted['execution_mode']} "
        f"connector_order_request_id={submitted['connector_order_request_id']} "
        f"broker_order_no={result.get('broker_order_no')}"
    )

    return submitted


def main():
    args = parse_args()

    if print_non_business_day_no_target("Daily Auto BUY"):
        return

    conn = get_conn()
    conn.autocommit = False

    try:
        orders = get_ready_daily_buy_execution_orders(
            conn,
            plan_id=args.plan_id,
            limit=args.limit,
        )

        print_header("[Daily Auto BUY Candidates]")
        print(f"plan_id : {args.plan_id}")
        print(f"limit   : {args.limit}")
        print(f"execute : {args.execute}")
        print(f"count   : {len(orders)}")

        if not orders:
            print()
            print("[WARN] 자동매수 대상 READY Daily BUY 주문이 없음")
            conn.rollback()
            return

        executable_orders = []

        for idx, order in enumerate(orders, start=1):
            print_candidate(order, idx)

            reasons = validate_auto_buy_order(order)

            if reasons:
                print("  BLOCKED")
                for reason in reasons:
                    print(f"  - {reason}")
                continue

            executable_orders.append(order)

        print_header("[Validation Summary]")
        print(f"candidate_count  : {len(orders)}")
        print(f"executable_count : {len(executable_orders)}")

        if not executable_orders:
            print("[WARN] 실행 가능한 자동매수 주문이 없음")
            conn.rollback()
            return

        if not args.execute:
            print()
            print("조회/검증만 완료. 실제 자동매수 실행은 --execute 필요.")
            conn.rollback()
            return

        print_header("[Auto BUY Execute]")
        print("자동매수는 PAPER_STRATEGY 모드만 허용됨.")
        print("전략 order_qty 그대로 Connector BUY 호출.")

        for order in executable_orders:
            execute_one_auto_buy(conn, order)

        print_header("[DONE]")
        print("Daily Signal 자동매수 실행 완료")

    except Exception as e:
        conn.rollback()
        print_header("[ERROR]")
        print(str(e))
        raise

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()