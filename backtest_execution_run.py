# C:\Workspaces\port_strategy_execution\backtest_execution_run.py

"""
Execution script that converts a backtest trade log into execution order candidates.
It can read the latest strategy run, market daily, and buy/sell candidates from the DB and store the plan/order.
Because operational DB writes may occur, do not run it during documentation/review work.
"""

import argparse
from datetime import datetime

from execution_db import get_conn
from execution_repository import (
    get_account,
    get_latest_balance,
    get_latest_strategy_run,
    get_latest_plan_date,
    get_market_daily,
    get_buy_candidates,
    get_sell_candidates,
    create_or_get_plan,
    upsert_execution_order,
    update_plan_summary,
    mark_plan_no_candidate,
)
from execution_builder import build_execution_orders


def print_header(title):
    print()
    print("========================================")
    print(title)
    print("========================================")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backtest trade-log based execution candidate builder"
    )

    parser.add_argument(
        "--plan-date",
        dest="plan_date",
        required=False,
        help="강제로 사용할 execution plan date. 예: 2026-04-22",
    )

    return parser.parse_args()


def parse_plan_date(plan_date_text):
    if not plan_date_text:
        return None

    try:
        return datetime.strptime(plan_date_text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"--plan-date 형식이 잘못됨: {plan_date_text}. 예: 2026-04-22"
        )


def main():
    args = parse_args()
    forced_plan_date = parse_plan_date(args.plan_date)

    conn = get_conn()
    conn.autocommit = False

    try:
        # -------------------------------------------------
        # 1. Query the Connector account / latest balance
        # -------------------------------------------------
        account = get_account(conn)
        balance = get_latest_balance(conn, account["id"])

        # -------------------------------------------------
        # 2. Query the latest Backtest Strategy Run
        # -------------------------------------------------
        latest_run = get_latest_strategy_run(conn)
        run_id = latest_run["run_id"]

        # -------------------------------------------------
        # 3. Determine plan_date
        #    - If the option is provided, use the forced date
        #    - Otherwise, use the latest backtest daily date
        # -------------------------------------------------
        if forced_plan_date:
            plan_date = forced_plan_date
            plan_date_mode = "FORCED"
        else:
            plan_date = get_latest_plan_date(conn, run_id)
            plan_date_mode = "LATEST"

        # -------------------------------------------------
        # 4. Query the Backtest daily market row
        # -------------------------------------------------
        market_daily = get_market_daily(conn, run_id, plan_date)

        # -------------------------------------------------
        # 5. Query BUY / SELL candidates based on the Backtest trade_log
        # -------------------------------------------------
        buy_candidates = get_buy_candidates(conn, run_id, plan_date)
        sell_candidates = get_sell_candidates(conn, run_id, plan_date)

        # -------------------------------------------------
        # 6. Create or reuse the Execution Plan
        # -------------------------------------------------
        plan_id = create_or_get_plan(
            conn=conn,
            account=account,
            balance=balance,
            latest_run=latest_run,
            market_daily=market_daily,
        )

        # -------------------------------------------------
        # 7. Build Execution Order candidates
        # -------------------------------------------------
        order_data_list = build_execution_orders(
            conn=conn,
            plan_id=plan_id,
            account=account,
            balance=balance,
            market_daily=market_daily,
            buy_candidates=buy_candidates,
            sell_candidates=sell_candidates,
        )

        print_header("[Backtest Execution Candidate Build]")
        print(f"account_no       : {account['account_no']}")
        print(f"balance_date     : {balance['as_of_date']}")
        print(f"strategy_name    : {latest_run['strategy_name']}")
        print(f"strategy_version : {latest_run['strategy_version']}")
        print(f"run_id           : {run_id}")
        print(f"plan_date        : {plan_date}")
        print(f"plan_date_mode   : {plan_date_mode}")
        print(f"market_signal    : {market_daily['market_signal']}")
        print(f"buy_candidates   : {len(buy_candidates)}")
        print(f"sell_candidates  : {len(sell_candidates)}")
        print(f"execution_plan   : {plan_id}")
        print(f"orders_to_upsert : {len(order_data_list)}")

        if not order_data_list:
            print()
            print("[WARN] 생성할 backtest execution order 후보가 없음")
            print("       plan_date 기준 buy_date/sell_date 후보가 없는 상태일 수 있음")

        # -------------------------------------------------
        # 8. Store Execution Orders in the DB
        # -------------------------------------------------
        saved_rows = []

        for order_data in order_data_list:
            row = upsert_execution_order(conn, order_data)
            saved_rows.append(row)

            print(
                f"- {row['action_type']} "
                f"ticker={row['ticker_code']} "
                f"status={row['execution_status']} "
                f"reason={row['block_reason']}"
            )

        # -------------------------------------------------
        # 9. Update the Plan Summary
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
        print("Backtest execution candidate build 완료")

    except Exception as e:
        conn.rollback()
        print_header("[ERROR]")
        print(str(e))
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
