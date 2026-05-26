# C:\Workspaces\port_strategy_execution\daily_sell_execution_run.py

import sys
from pathlib import Path
from datetime import date

from psycopg2.extras import RealDictCursor

from execution_db import get_conn
from execution_repository import (
    get_account,
    get_latest_balance,
    get_latest_daily_run_for_position_decision,
    get_ready_daily_position_sell_decisions,
    create_or_get_daily_signal_plan,
    upsert_daily_position_sell_execution_order,
    update_daily_position_decision_execution_order_link,
    update_plan_summary,
)
from execution_daily_position_sell_builder import build_daily_position_sell_execution_orders


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



def get_execution_plan_summary(conn, plan_id):
    """
    update_plan_summary()가 order 0건인 plan에서 None을 반환할 수 있으므로,
    로그 출력용 fallback summary를 직접 조회한다.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                id,
                plan_date,
                plan_status,
                total_candidate_count,
                ready_order_count,
                blocked_order_count,
                skipped_order_count,
                total_target_amount,
                memo,
                updated_at
            FROM strategy_execution_plan
            WHERE id = %s
            """,
            (plan_id,),
        )
        return cur.fetchone()


def resolve_plan_summary(conn, plan_id):
    """
    1차: update_plan_summary()로 실제 order 기준 summary 재계산
    2차: summary가 None이면 strategy_execution_plan row를 직접 조회
    """
    summary = update_plan_summary(conn, plan_id)

    if summary:
        return summary

    return get_execution_plan_summary(conn, plan_id)


def main():
    if print_non_business_day_no_target("Daily SELL Execution Build"):
        return

    conn = get_conn()
    conn.autocommit = False

    try:
        # -------------------------------------------------
        # 1. Connector 계좌 / 최신 잔고 조회
        # -------------------------------------------------
        account = get_account(conn)
        balance = get_latest_balance(conn, account["id"])

        # -------------------------------------------------
        # 2. 최신 Daily Run 조회
        #    - Daily Position 판단 기준이 되는 최신 run
        # -------------------------------------------------
        daily_run = get_latest_daily_run_for_position_decision(conn)

        # -------------------------------------------------
        # 3. SELL 실행 후보가 되는 Daily Position Decision 조회
        #    - 보통 SELL / READY 상태 decision만 대상
        # -------------------------------------------------
        sell_decisions = get_ready_daily_position_sell_decisions(
            conn=conn,
            daily_run_id=daily_run["id"],
        )

        # -------------------------------------------------
        # 4. Daily Signal Plan 생성 또는 재사용
        #    - BUY/SELL Daily 실행을 같은 날짜 plan으로 묶기 위함
        # -------------------------------------------------
        plan_id = create_or_get_daily_signal_plan(
            conn=conn,
            account=account,
            balance=balance,
            daily_run=daily_run,
        )

        # -------------------------------------------------
        # 5. SELL Execution Order 후보 생성
        # -------------------------------------------------
        order_data_list = build_daily_position_sell_execution_orders(
            plan_id=plan_id,
            account=account,
            daily_run=daily_run,
            decisions=sell_decisions,
        )

        print_header("[Daily Position SELL Execution Build]")
        print(f"account_no       : {account['account_no']}")
        print(f"balance_date     : {balance['as_of_date']}")
        print(f"daily_run_id     : {daily_run['id']}")
        print(f"run_date         : {daily_run['run_date']}")
        print(f"data_date        : {daily_run['data_date']}")
        print(f"market_signal    : {daily_run['market_signal']}")
        print(f"sell_decisions   : {len(sell_decisions)}")
        print(f"execution_plan   : {plan_id}")
        print(f"orders_to_upsert : {len(order_data_list)}")

        if not order_data_list:
            print()
            print("[INFO] 생성할 Daily Position SELL execution order 후보가 없음")
            print("       SELL decision이 없거나, 전략 포지션 OPEN 대상이 없는 상태일 수 있음")

        # -------------------------------------------------
        # 6. Execution Order 저장 + Daily Position Decision 링크 갱신
        # -------------------------------------------------
        saved_rows = []

        for order_data in order_data_list:
            row = upsert_daily_position_sell_execution_order(conn, order_data)
            saved_rows.append(row)

            update_daily_position_decision_execution_order_link(
                conn=conn,
                decision_id=row["source_daily_position_decision_id"],
                execution_order_id=row["id"],
            )

            print(
                f"- {row['action_type']} "
                f"source={row['source_type']} "
                f"decision_id={row['source_daily_position_decision_id']} "
                f"position_state_id={row['source_position_state_id']} "
                f"ticker={row['ticker_code']} "
                f"name={row['stock_name']} "
                f"qty={row['order_qty']} "
                f"price={row['order_price']} "
                f"status={row['execution_status']} "
                f"reason={row['block_reason']} "
                f"sell_reason={row['sell_reason']}"
            )

        # -------------------------------------------------
        # 7. Plan Summary 갱신 / 조회
        #    - order 0건이어도 plan summary를 출력해야 하므로 fallback 조회
        # -------------------------------------------------
        summary = resolve_plan_summary(conn, plan_id)

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
        print("Daily Position SELL execution build 완료")

    except Exception as e:
        conn.rollback()
        print_header("[ERROR]")
        print(str(e))
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()