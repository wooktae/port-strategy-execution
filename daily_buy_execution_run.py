# C:\Workspaces\port_strategy_execution\daily_buy_execution_run.py

"""
Batch entrypoint that generates execution order candidates based on the Daily BUY signal.
It can read the account/balance, latest daily run, and BUY signals from the DB and store strategy_execution_order.
Because DB writes occur on execution, do not run it without explicit approval.
"""

import sys
from pathlib import Path
from datetime import date

from execution_db import get_conn
from execution_repository import (
    get_account,
    get_latest_balance,
    get_latest_daily_run,
    get_daily_buy_signals,
    create_or_get_daily_signal_plan,
    upsert_daily_signal_execution_order,
    update_plan_summary,
    mark_plan_no_candidate,
)
from execution_daily_signal_builder import build_daily_signal_execution_orders


def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")

# -------------------------------------------------
# Korean business day guard
# -------------------------------------------------
def _load_kr_holiday_checker():
    """
    If interest_get_holidays.py from port-interest-crawler / port_interest_crawler
    is available, use the Korean market-closure/public-holiday check as well.
    Otherwise, perform only the weekend check.
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
            # Do not kill the batch due to a holiday-utility error; trust only the weekend check.
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



def main():
    if print_non_business_day_no_target("Daily BUY Execution Build"):
        return

    conn = get_conn()
    conn.autocommit = False

    try:
        # -------------------------------------------------
        # 1. Query the Connector account / balance
        # -------------------------------------------------
        account = get_account(conn)
        balance = get_latest_balance(conn, account["id"])

        # -------------------------------------------------
        # 2. Query the latest Daily Signal Run
        # -------------------------------------------------
        daily_run = get_latest_daily_run(conn)

        # -------------------------------------------------
        # 3. Query the Daily BUY Signal
        # -------------------------------------------------
        daily_signals = get_daily_buy_signals(conn, daily_run["id"])

        # -------------------------------------------------
        # 4. Create/update the Execution Plan
        # -------------------------------------------------
        plan_id = create_or_get_daily_signal_plan(
            conn=conn,
            account=account,
            balance=balance,
            daily_run=daily_run,
        )

        # -------------------------------------------------
        # 5. Build Execution Order candidates
        # -------------------------------------------------
        order_data_list = build_daily_signal_execution_orders(
            conn=conn,
            plan_id=plan_id,
            account=account,
            balance=balance,
            daily_run=daily_run,
            signals=daily_signals,
        )

        print_header("[Daily Signal Execution Candidate Build]")
        print(f"account_no       : {account['account_no']}")
        print(f"balance_date     : {balance['as_of_date']}")
        print(f"strategy_name    : {daily_run['strategy_name']}")
        print(f"strategy_version : {daily_run['strategy_version']}")
        print(f"daily_run_id     : {daily_run['id']}")
        print(f"run_date         : {daily_run['run_date']}")
        print(f"data_date        : {daily_run['data_date']}")
        print(f"market_signal    : {daily_run['market_signal']}")
        print(f"daily_signals    : {len(daily_signals)}")
        print(f"execution_plan   : {plan_id}")
        print(f"orders_to_upsert : {len(order_data_list)}")

        if not order_data_list:
            print()
            print("[WARN] 생성할 Daily Signal execution order 후보가 없음")

        # -------------------------------------------------
        # 6. Store Execution Orders in the DB
        # -------------------------------------------------
        saved_rows = []

        for order_data in order_data_list:
            row = upsert_daily_signal_execution_order(conn, order_data)
            saved_rows.append(row)

            validation_result = row.get("validation_result") or {}
            sizing_detail = validation_result.get("sizing_detail") or {}

            print(
                f"- {row['action_type']} "
                f"source={row['source_type']} "
                f"daily_signal_id={row['source_daily_signal_id']} "
                f"ticker={row['ticker_code']} "
                f"name={row['stock_name']} "
                f"position_size={row['signal_position_size']} "
                f"target_amount={row['target_amount']} "
                f"qty={row['order_qty']} "
                f"price={row['order_price']} "
                f"status={row['execution_status']} "
                f"reason={row['block_reason']}"
            )

            if sizing_detail:
                print(
                    f"  sizing_method={sizing_detail.get('sizing_method')} "
                    f"total_eval={sizing_detail.get('total_eval_amount')} "
                    f"available_cash={sizing_detail.get('available_cash')} "
                    f"target_position={sizing_detail.get('target_position_amount')} "
                    f"current_eval={sizing_detail.get('current_position_eval_amount')} "
                    f"additional_buy={sizing_detail.get('additional_buy_amount')} "
                    f"capped_buy={sizing_detail.get('capped_buy_amount')} "
                    f"estimated_order={sizing_detail.get('estimated_order_amount')}"
                )

        # -------------------------------------------------
        # 7. Update the Plan Summary
        # -------------------------------------------------
        if order_data_list:
            summary = update_plan_summary(conn, plan_id)
        else:
            summary = mark_plan_no_candidate(conn, plan_id)

        conn.commit()

        print_header("[Plan Summary]")
        if summary:
            print(f"plan_id          : {summary['id']}")
            print(f"plan_status      : {summary['plan_status']}")
            print(f"total_candidates : {summary['total_candidate_count']}")
            print(f"ready_orders     : {summary['ready_order_count']}")
            print(f"blocked_orders   : {summary['blocked_order_count']}")
            print(f"skipped_orders   : {summary['skipped_order_count']}")
            print(f"target_amount    : {summary['total_target_amount']}")
        else:
            print("[WARN] plan summary 없음")

        print_header("[DONE]")
        print("Daily Signal execution candidate build 완료")

    except Exception as e:
        conn.rollback()
        print_header("[ERROR]")
        print(str(e))
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
