import os
# C:\Workspaces\port_strategy_execution\execution_build_candidates.py

"""
legacy 성격의 독립형 execution 후보 생성 스크립트.
daily signal과 connector 계좌/잔고 정보를 직접 조회하고 plan/order upsert를 수행할 수 있다.
DB write 경로와 로컬 설정 상수가 포함되어 있어 정리 후보로 취급하고 실행하지 않는다.
"""

import json
from decimal import Decimal, ROUND_DOWN
from datetime import date
import psycopg2
import psycopg2.extras

from db_config import get_db_config


ACCOUNT_NO = os.getenv("PORT_ACCOUNT_NO")

if not ACCOUNT_NO:
    raise RuntimeError("PORT_ACCOUNT_NO is required")
BROKER_NAME = "koreainvestment"
ENVIRONMENT = "paper"

STRATEGY_NAME = "strategy_ai"
STRATEGY_VERSION = "RESEARCH_V3_EXIT_SOFTENED"

DEFAULT_MAX_ORDER_AMOUNT_RATIO = Decimal("0.50")
MIN_ORDER_AMOUNT = Decimal("10000")


def get_conn():
    """공통 DB 설정으로 psycopg2 connection을 생성한다."""
    return psycopg2.connect(**get_db_config())


def fetch_one(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return cur.fetchone()


def fetch_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()


def execute_one(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        try:
            return cur.fetchone()
        except psycopg2.ProgrammingError:
            return None


def get_account(conn):
    sql = """
        SELECT
            id,
            account_no,
            account_product_code,
            broker_name,
            environment
        FROM connector_account
        WHERE account_no = %(account_no)s
          AND broker_name = %(broker_name)s
          AND environment = %(environment)s
          AND is_active = true
        ORDER BY id ASC
        LIMIT 1
    """
    row = fetch_one(conn, sql, {
        "account_no": ACCOUNT_NO,
        "broker_name": BROKER_NAME,
        "environment": ENVIRONMENT,
    })

    if not row:
        raise RuntimeError("활성 connector_account를 찾지 못함")

    return row


def get_latest_balance(conn, account_id):
    sql = """
        SELECT
            account_id,
            account_no,
            as_of_date,
            cash_balance,
            orderable_cash,
            total_eval_amount,
            eval_profit
        FROM connector_balance_snapshot
        WHERE account_id = %(account_id)s
        ORDER BY as_of_date DESC, as_of_ts DESC
        LIMIT 1
    """
    row = fetch_one(conn, sql, {"account_id": account_id})

    if not row:
        raise RuntimeError("최신 connector_balance_snapshot을 찾지 못함")

    return row


def get_latest_signal_date(conn):
    sql = """
        SELECT MAX(signal_date) AS signal_date
        FROM strategy_signal
    """
    row = fetch_one(conn, sql)

    if not row or not row["signal_date"]:
        raise RuntimeError("strategy_signal에 signal_date가 없음")

    return row["signal_date"]


def get_signals(conn, signal_date):
    sql = """
        SELECT
            id,
            signal_date,
            strategy_name,
            strategy_version,
            ticker_code,
            signal_type,
            score,
            position_size,
            market_signal,
            market_regime_score,
            flow_score,
            info_score,
            tape_score,
            short_pressure_score,
            reason
        FROM strategy_signal
        WHERE signal_date = %(signal_date)s
        ORDER BY
            CASE
                WHEN signal_type = 'BUY' THEN 1
                WHEN signal_type = 'SELL' THEN 2
                WHEN signal_type = 'HOLD' THEN 3
                WHEN signal_type = 'HOLD_ALL' THEN 4
                ELSE 9
            END,
            score DESC NULLS LAST,
            id ASC
    """
    return fetch_all(conn, sql, {"signal_date": signal_date})


def get_stock_name(conn, ticker_code):
    if not ticker_code:
        return None

    sql = """
        SELECT company_name
        FROM stock_universe
        WHERE ticker_code = %(ticker_code)s
        LIMIT 1
    """
    row = fetch_one(conn, sql, {"ticker_code": ticker_code})
    return row["company_name"] if row else None


def get_current_position(conn, account_id, ticker_code):
    if not ticker_code:
        return {
            "quantity": 0,
            "eval_amount": Decimal("0"),
        }

    sql = """
        SELECT
            quantity,
            eval_amount
        FROM connector_position_snapshot
        WHERE account_id = %(account_id)s
          AND ticker_code = %(ticker_code)s
        ORDER BY as_of_date DESC, as_of_ts DESC
        LIMIT 1
    """
    row = fetch_one(conn, sql, {
        "account_id": account_id,
        "ticker_code": ticker_code,
    })

    if not row:
        return {
            "quantity": 0,
            "eval_amount": Decimal("0"),
        }

    return {
        "quantity": row["quantity"] or 0,
        "eval_amount": row["eval_amount"] or Decimal("0"),
    }


def get_latest_price(conn, ticker_code):
    if not ticker_code:
        return None

    sql = """
        SELECT close_price
        FROM interest_price_raw
        WHERE ticker_code = %(ticker_code)s
        ORDER BY date DESC
        LIMIT 1
    """
    row = fetch_one(conn, sql, {"ticker_code": ticker_code})
    return row["close_price"] if row else None


def has_open_connector_order(conn, account_id, ticker_code):
    if not ticker_code:
        return False

    sql = """
        SELECT COUNT(*) AS cnt
        FROM connector_order_request
        WHERE account_id = %(account_id)s
          AND ticker_code = %(ticker_code)s
          AND request_status IN (
              'PENDING',
              'ACCEPTED',
              'MODIFIED',
              'PARTIAL_FILLED',
              'CANCEL_ACCEPTED'
          )
    """
    row = fetch_one(conn, sql, {
        "account_id": account_id,
        "ticker_code": ticker_code,
    })

    return row["cnt"] > 0


def map_action_type(signal_type):
    if signal_type == "BUY":
        return "BUY"
    if signal_type == "SELL":
        return "SELL"
    if signal_type in ("HOLD", "HOLD_ALL"):
        return "HOLD"
    return "SKIP"


def create_or_get_plan(conn, account, balance, signal_date, signals):
    first_signal = signals[0] if signals else {}

    market_signal = first_signal.get("market_signal")
    market_regime_score = first_signal.get("market_regime_score")

    available_cash = balance["orderable_cash"] or balance["cash_balance"] or Decimal("0")
    max_order_amount = available_cash * DEFAULT_MAX_ORDER_AMOUNT_RATIO

    sql = """
        INSERT INTO strategy_execution_plan (
            plan_date,
            strategy_name,
            strategy_version,
            strategy_run_id,
            market_signal,
            market_regime_score,
            risk_regime,
            account_id,
            account_no,
            plan_status,
            available_cash,
            max_order_amount,
            memo
        )
        VALUES (
            %(plan_date)s,
            %(strategy_name)s,
            %(strategy_version)s,
            NULL,
            %(market_signal)s,
            %(market_regime_score)s,
            %(risk_regime)s,
            %(account_id)s,
            %(account_no)s,
            'CREATED',
            %(available_cash)s,
            %(max_order_amount)s,
            %(memo)s
        )
        ON CONFLICT (plan_date, strategy_name, strategy_version, account_id)
        DO UPDATE SET
            market_signal = EXCLUDED.market_signal,
            market_regime_score = EXCLUDED.market_regime_score,
            available_cash = EXCLUDED.available_cash,
            max_order_amount = EXCLUDED.max_order_amount,
            memo = EXCLUDED.memo,
            updated_at = now()
        RETURNING id
    """

    row = execute_one(conn, sql, {
        "plan_date": signal_date,
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
        "market_signal": market_signal,
        "market_regime_score": market_regime_score,
        "risk_regime": market_signal,
        "account_id": account["id"],
        "account_no": account["account_no"],
        "available_cash": available_cash,
        "max_order_amount": max_order_amount,
        "memo": "strategy_signal 기반 execution 후보 생성",
    })

    return row["id"]


def build_validation(signal, account_id, available_cash):
    ticker_code = signal["ticker_code"]
    signal_type = signal["signal_type"]
    market_signal = signal["market_signal"]
    position_size = signal["position_size"] or Decimal("0")

    reasons = []

    if market_signal == "BLOCK":
        reasons.append("market_signal=BLOCK")

    if signal_type == "HOLD_ALL":
        reasons.append("signal_type=HOLD_ALL")

    if not ticker_code:
        reasons.append("ticker_code is null")

    if signal_type == "BUY" and position_size <= 0:
        reasons.append("BUY but position_size <= 0")

    if available_cash <= 0:
        reasons.append("available_cash <= 0")

    return reasons


def upsert_execution_order(conn, plan_id, account, balance, signal):
    """
    signal 1건을 strategy_execution_order row로 upsert한다.
    legacy 스크립트 내부 저장 경로이므로 SQL 의미를 임의로 바꾸지 않는다.
    """
    account_id = account["id"]
    account_no = account["account_no"]

    available_cash = balance["orderable_cash"] or balance["cash_balance"] or Decimal("0")

    ticker_code = signal["ticker_code"]
    signal_type = signal["signal_type"]
    position_size = signal["position_size"] or Decimal("0")
    score = signal["score"]

    action_type = map_action_type(signal_type)

    stock_name = get_stock_name(conn, ticker_code)
    position = get_current_position(conn, account_id, ticker_code)
    latest_price = get_latest_price(conn, ticker_code)

    validation_reasons = build_validation(signal, account_id, available_cash)

    if ticker_code and has_open_connector_order(conn, account_id, ticker_code):
        validation_reasons.append("open connector order exists")

    target_amount = Decimal("0")
    order_qty = 0
    order_price = latest_price

    if action_type == "BUY" and latest_price:
        target_amount = available_cash * position_size

        if target_amount < MIN_ORDER_AMOUNT:
            validation_reasons.append("target_amount < MIN_ORDER_AMOUNT")

        order_qty = int((target_amount / latest_price).to_integral_value(rounding=ROUND_DOWN))

        if order_qty <= 0:
            validation_reasons.append("order_qty <= 0")

    elif action_type == "SELL":
        order_qty = int(position["quantity"] or 0)
        target_amount = Decimal(order_qty) * latest_price if latest_price else Decimal("0")

        if order_qty <= 0:
            validation_reasons.append("SELL but current_qty <= 0")

    elif action_type in ("HOLD", "SKIP"):
        validation_reasons.append(f"action_type={action_type}")

    if validation_reasons:
        execution_status = "BLOCKED"
        block_reason = " / ".join(validation_reasons)
    else:
        execution_status = "READY"
        block_reason = None

    validation_result = {
        "validation_reasons": validation_reasons,
        "available_cash": str(available_cash),
        "latest_price": str(latest_price) if latest_price is not None else None,
        "current_qty": position["quantity"],
        "current_eval_amount": str(position["eval_amount"]),
    }

    sql = """
        INSERT INTO strategy_execution_order (
            execution_plan_id,
            strategy_signal_id,
            account_id,
            account_no,
            signal_date,
            ticker_code,
            stock_name,
            action_type,
            signal_type,
            signal_score,
            signal_position_size,
            market_signal,
            market_regime_score,
            flow_score,
            info_score,
            tape_score,
            final_score,
            short_pressure_score,
            target_weight,
            target_amount,
            current_qty,
            current_eval_amount,
            order_qty,
            order_price,
            order_method,
            execution_status,
            block_reason,
            approval_required,
            signal_reason,
            validation_result
        )
        VALUES (
            %(execution_plan_id)s,
            %(strategy_signal_id)s,
            %(account_id)s,
            %(account_no)s,
            %(signal_date)s,
            %(ticker_code)s,
            %(stock_name)s,
            %(action_type)s,
            %(signal_type)s,
            %(signal_score)s,
            %(signal_position_size)s,
            %(market_signal)s,
            %(market_regime_score)s,
            %(flow_score)s,
            %(info_score)s,
            %(tape_score)s,
            %(final_score)s,
            %(short_pressure_score)s,
            %(target_weight)s,
            %(target_amount)s,
            %(current_qty)s,
            %(current_eval_amount)s,
            %(order_qty)s,
            %(order_price)s,
            %(order_method)s,
            %(execution_status)s,
            %(block_reason)s,
            true,
            %(signal_reason)s,
            %(validation_result)s
        )
        ON CONFLICT (execution_plan_id, strategy_signal_id)
        DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            action_type = EXCLUDED.action_type,
            signal_type = EXCLUDED.signal_type,
            signal_score = EXCLUDED.signal_score,
            signal_position_size = EXCLUDED.signal_position_size,
            market_signal = EXCLUDED.market_signal,
            market_regime_score = EXCLUDED.market_regime_score,
            flow_score = EXCLUDED.flow_score,
            info_score = EXCLUDED.info_score,
            tape_score = EXCLUDED.tape_score,
            final_score = EXCLUDED.final_score,
            short_pressure_score = EXCLUDED.short_pressure_score,
            target_weight = EXCLUDED.target_weight,
            target_amount = EXCLUDED.target_amount,
            current_qty = EXCLUDED.current_qty,
            current_eval_amount = EXCLUDED.current_eval_amount,
            order_qty = EXCLUDED.order_qty,
            order_price = EXCLUDED.order_price,
            order_method = EXCLUDED.order_method,
            execution_status = EXCLUDED.execution_status,
            block_reason = EXCLUDED.block_reason,
            signal_reason = EXCLUDED.signal_reason,
            validation_result = EXCLUDED.validation_result,
            updated_at = now()
        RETURNING id, execution_status, block_reason
    """

    row = execute_one(conn, sql, {
        "execution_plan_id": plan_id,
        "strategy_signal_id": signal["id"],
        "account_id": account_id,
        "account_no": account_no,
        "signal_date": signal["signal_date"],
        "ticker_code": ticker_code,
        "stock_name": stock_name,
        "action_type": action_type,
        "signal_type": signal_type,
        "signal_score": score,
        "signal_position_size": position_size,
        "market_signal": signal["market_signal"],
        "market_regime_score": signal["market_regime_score"],
        "flow_score": signal["flow_score"],
        "info_score": signal["info_score"],
        "tape_score": signal["tape_score"],
        "final_score": signal["score"],
        "short_pressure_score": signal["short_pressure_score"],
        "target_weight": position_size,
        "target_amount": target_amount,
        "current_qty": position["quantity"],
        "current_eval_amount": position["eval_amount"],
        "order_qty": order_qty,
        "order_price": order_price,
        "order_method": "MARKET",
        "execution_status": execution_status,
        "block_reason": block_reason,
        "signal_reason": json.dumps(signal["reason"], ensure_ascii=False) if signal["reason"] else None,
        "validation_result": json.dumps(validation_result, ensure_ascii=False),
    })

    return row


def update_plan_summary(conn, plan_id):
    sql = """
        UPDATE strategy_execution_plan p
        SET
            total_candidate_count = s.total_count,
            ready_order_count = s.ready_count,
            blocked_order_count = s.blocked_count,
            skipped_order_count = s.skipped_count,
            total_target_amount = s.total_target_amount,
            plan_status =
                CASE
                    WHEN s.total_count = 0 THEN 'FAILED'
                    WHEN s.ready_count > 0 AND s.blocked_count > 0 THEN 'PARTIALLY_BLOCKED'
                    WHEN s.ready_count > 0 THEN 'READY'
                    WHEN s.blocked_count = s.total_count THEN 'BLOCKED'
                    ELSE 'VALIDATED'
                END,
            blocked_reason =
                CASE
                    WHEN s.blocked_count = s.total_count THEN 'all execution orders blocked'
                    ELSE NULL
                END,
            updated_at = now()
        FROM (
            SELECT
                execution_plan_id,
                COUNT(*) AS total_count,
                COUNT(*) FILTER (WHERE execution_status = 'READY') AS ready_count,
                COUNT(*) FILTER (WHERE execution_status = 'BLOCKED') AS blocked_count,
                COUNT(*) FILTER (WHERE execution_status = 'SKIPPED') AS skipped_count,
                COALESCE(SUM(target_amount), 0) AS total_target_amount
            FROM strategy_execution_order
            WHERE execution_plan_id = %(plan_id)s
            GROUP BY execution_plan_id
        ) s
        WHERE p.id = s.execution_plan_id
        RETURNING
            p.id,
            p.plan_status,
            p.total_candidate_count,
            p.ready_order_count,
            p.blocked_order_count,
            p.total_target_amount
    """
    return execute_one(conn, sql, {"plan_id": plan_id})


def main():
    conn = get_conn()
    conn.autocommit = False

    try:
        account = get_account(conn)
        balance = get_latest_balance(conn, account["id"])
        signal_date = get_latest_signal_date(conn)
        signals = get_signals(conn, signal_date)

        if not signals:
            raise RuntimeError(f"strategy_signal 없음: signal_date={signal_date}")

        plan_id = create_or_get_plan(conn, account, balance, signal_date, signals)

        print("========================================")
        print("[Execution Candidate Build]")
        print(f"account_no     : {account['account_no']}")
        print(f"signal_date    : {signal_date}")
        print(f"signals        : {len(signals)}")
        print(f"execution_plan : {plan_id}")
        print("========================================")

        for signal in signals:
            row = upsert_execution_order(conn, plan_id, account, balance, signal)
            print(
                f"- signal_id={signal['id']} "
                f"ticker={signal['ticker_code']} "
                f"signal_type={signal['signal_type']} "
                f"market={signal['market_signal']} "
                f"status={row['execution_status']} "
                f"reason={row['block_reason']}"
            )

        summary = update_plan_summary(conn, plan_id)

        conn.commit()

        print("========================================")
        print("[Plan Summary]")
        print(dict(summary))
        print("========================================")

    except Exception as e:
        conn.rollback()
        print("[ERROR]", str(e))
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
