# C:\Workspaces\port_strategy_execution\execution_repository.py

"""
Collection of DB repository functions for the execution module.
It can insert/update strategy_execution_plan/order, position_state, daily decision, and intraday check.
It also includes connector account/balance/order/fill/snapshot query paths, so do not change the SQL meaning and state transitions arbitrarily.
"""

import json
from decimal import Decimal

from execution_config import (
    ACCOUNT_NO,
    BROKER_NAME,
    ENVIRONMENT,
    STRATEGY_NAME,
    STRATEGY_VERSION,
    DEFAULT_MAX_ORDER_AMOUNT_RATIO,
)
from execution_db import fetch_one, fetch_all, execute_one


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
            as_of_ts,
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


def get_latest_strategy_run(conn):
    """
    Fetch the latest Strategy execution result.
    strategy_signal is no longer used.
    """

    sql = """
        SELECT
            run_id,
            strategy_name,
            strategy_version,
            run_mode,
            backtest_start_date,
            backtest_end_date,
            total_return,
            mdd,
            sharpe,
            trade_count,
            config_snapshot,
            started_at,
            finished_at
        FROM strategy_backtest_run
        WHERE strategy_name = %(strategy_name)s
        ORDER BY started_at DESC NULLS LAST, finished_at DESC NULLS LAST
        LIMIT 1
    """

    row = fetch_one(conn, sql, {
        "strategy_name": STRATEGY_NAME,
    })

    if not row:
        raise RuntimeError("최신 strategy_backtest_run을 찾지 못함")

    return row


def get_latest_plan_date(conn, run_id):
    """
    Use the most recent daily date for a specific run_id as the execution plan date.
    """

    sql = """
        SELECT
            MAX(date) AS plan_date
        FROM strategy_backtest_daily
        WHERE run_id = %(run_id)s
    """

    row = fetch_one(conn, sql, {"run_id": run_id})

    if not row or not row["plan_date"]:
        raise RuntimeError(f"strategy_backtest_daily 기준 최신 date를 찾지 못함: run_id={run_id}")

    return row["plan_date"]


def get_market_daily(conn, run_id, plan_date):
    """
    Fetch the market state as of plan_date.
    """

    sql = """
        SELECT
            run_id,
            date,
            market_signal,
            position_count,
            daily_return,
            cum_return
        FROM strategy_backtest_daily
        WHERE run_id = %(run_id)s
          AND date = %(plan_date)s
        LIMIT 1
    """

    row = fetch_one(conn, sql, {
        "run_id": run_id,
        "plan_date": plan_date,
    })

    if not row:
        raise RuntimeError(
            f"strategy_backtest_daily row 없음: run_id={run_id}, plan_date={plan_date}"
        )

    return row


def get_buy_candidates(conn, run_id, plan_date):
    """
    Buy candidates:
    Fetch trades from strategy_trade_log where buy_date = plan_date.
    Same nature as the '2. 매수' section of the report.
    """

    sql = """
        SELECT
            id,
            run_id,
            strategy_name,
            strategy_version,
            ticker_code,
            company_name,
            buy_date,
            sell_date,
            return_pct,
            holding_period,
            buy_open_price,
            buy_close_price,
            buy_low_price,
            sell_open_price,
            sell_close_price,
            sell_low_price,
            buy_info,
            sell_info
        FROM strategy_trade_log
        WHERE run_id = %(run_id)s
          AND buy_date = %(plan_date)s
        ORDER BY
            NULLIF(buy_info->>'score', '')::numeric DESC NULLS LAST,
            id ASC
    """

    return fetch_all(conn, sql, {
        "run_id": run_id,
        "plan_date": plan_date,
    })


def get_sell_candidates(conn, run_id, plan_date):
    """
    Sell candidates:
    Fetch trades from strategy_trade_log where sell_date = plan_date.
    Same nature as the '3. 매도' section of the report.

    However, when actually executing orders, this must always be cross-checked
    against the actual held quantity in connector_position_snapshot.
    """

    sql = """
        SELECT
            id,
            run_id,
            strategy_name,
            strategy_version,
            ticker_code,
            company_name,
            buy_date,
            sell_date,
            return_pct,
            holding_period,
            buy_open_price,
            buy_close_price,
            buy_low_price,
            sell_open_price,
            sell_close_price,
            sell_low_price,
            buy_info,
            sell_info
        FROM strategy_trade_log
        WHERE run_id = %(run_id)s
          AND sell_date = %(plan_date)s
        ORDER BY
            ticker_code ASC,
            id ASC
    """

    return fetch_all(conn, sql, {
        "run_id": run_id,
        "plan_date": plan_date,
    })


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
    """
    Query the currently held position based on the latest balance snapshot.
    """

    if not ticker_code:
        return {
            "quantity": 0,
            "eval_amount": Decimal("0"),
        }

    sql = """
        WITH latest_balance AS (
            SELECT
                account_id,
                as_of_date,
                as_of_ts
            FROM connector_balance_snapshot
            WHERE account_id = %(account_id)s
            ORDER BY as_of_date DESC, as_of_ts DESC, id DESC
            LIMIT 1
        )
        SELECT
            cps.quantity,
            cps.eval_amount
        FROM latest_balance lb
        JOIN connector_position_snapshot cps
          ON cps.account_id = lb.account_id
         AND cps.as_of_date = lb.as_of_date
        WHERE cps.account_id = %(account_id)s
          AND cps.ticker_code = %(ticker_code)s
          AND COALESCE(cps.quantity, 0) > 0
        ORDER BY cps.as_of_ts DESC, cps.id DESC
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
        ORDER BY price_date DESC
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


def create_or_get_plan(conn, account, balance, latest_run, market_daily):
    """
    Create/update strategy_execution_plan.
    Now based on the latest strategy_backtest_run + daily, not on strategy_signal.
    """

    available_cash = balance["orderable_cash"] or balance["cash_balance"] or Decimal("0")
    max_order_amount = available_cash * DEFAULT_MAX_ORDER_AMOUNT_RATIO

    plan_date = market_daily["date"]
    market_signal = market_daily["market_signal"]

    strategy_name = latest_run["strategy_name"] or STRATEGY_NAME
    strategy_version = latest_run["strategy_version"] or STRATEGY_VERSION

    memo = (
        "최신 Strategy Run 결과 기반 execution 후보 생성 "
        f"(run_id={latest_run['run_id']})"
    )

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
            %(strategy_run_id)s,
            %(market_signal)s,
            NULL,
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
            strategy_run_id = EXCLUDED.strategy_run_id,
            market_signal = EXCLUDED.market_signal,
            risk_regime = EXCLUDED.risk_regime,
            available_cash = EXCLUDED.available_cash,
            max_order_amount = EXCLUDED.max_order_amount,
            memo = EXCLUDED.memo,
            updated_at = now()
        RETURNING id
    """

    row = execute_one(conn, sql, {
        "plan_date": plan_date,
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "strategy_run_id": latest_run["run_id"],
        "market_signal": market_signal,
        "risk_regime": market_signal,
        "account_id": account["id"],
        "account_no": account["account_no"],
        "available_cash": available_cash,
        "max_order_amount": max_order_amount,
        "memo": memo,
    })

    return row["id"]


def upsert_execution_order(conn, order_data):
    """
    Create/update strategy_execution_order.

    Key changes:
    - strategy_signal_id is no longer used, so store NULL
    - Use source_run_id, source_trade_log_id, source_type
    - ON CONFLICT uses the newly created trade_log-based unique index
    """

    sql = """
        INSERT INTO strategy_execution_order (
            execution_plan_id,
            strategy_signal_id,
            source_run_id,
            source_trade_log_id,
            source_type,
            execution_mode,
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
            NULL,
            %(source_run_id)s,
            %(source_trade_log_id)s,
            %(source_type)s,
            %(execution_mode)s,
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
        ON CONFLICT (
            execution_plan_id,
            source_trade_log_id,
            action_type
        )
        WHERE source_trade_log_id IS NOT NULL
        DO UPDATE SET
            source_run_id = EXCLUDED.source_run_id,
            source_type = EXCLUDED.source_type,
            execution_mode = EXCLUDED.execution_mode,
            account_id = EXCLUDED.account_id,
            account_no = EXCLUDED.account_no,
            signal_date = EXCLUDED.signal_date,
            ticker_code = EXCLUDED.ticker_code,
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
        RETURNING
            id,
            action_type,
            ticker_code,
            execution_status,
            block_reason
    """

    return execute_one(conn, sql, order_data)


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
            p.skipped_order_count,
            p.total_target_amount
    """

    return execute_one(conn, sql, {"plan_id": plan_id})

def mark_plan_no_candidate(conn, plan_id):
    sql = """
        UPDATE strategy_execution_plan
        SET
            total_candidate_count = 0,
            ready_order_count = 0,
            blocked_order_count = 0,
            skipped_order_count = 0,
            total_target_amount = 0,
            plan_status = 'NO_CANDIDATE',
            blocked_reason = NULL,
            memo = COALESCE(memo, '') || ' / 후보 없음',
            updated_at = now()
        WHERE id = %(plan_id)s
        RETURNING
            id,
            plan_status,
            total_candidate_count,
            ready_order_count,
            blocked_order_count,
            skipped_order_count,
            total_target_amount
    """

    return execute_one(conn, sql, {"plan_id": plan_id})

def get_execution_order_for_execute(conn, execution_order_id):
    sql = """
        SELECT
            eo.id,
            eo.execution_plan_id,
            eo.source_run_id,
            eo.source_trade_log_id,
            eo.source_position_state_id,
            eo.source_type,
            eo.execution_mode,
            eo.account_id,
            eo.account_no,
            eo.signal_date,
            eo.ticker_code,
            eo.stock_name,
            eo.action_type,
            eo.signal_type,
            eo.signal_score,
            eo.signal_position_size,
            eo.market_signal,
            eo.target_amount,
            eo.current_qty,
            eo.order_qty,
            eo.order_price,
            eo.order_method,
            eo.execution_status,
            eo.block_reason,
            eo.connector_order_request_id,
            ca.broker_name,
            ca.environment,
            ca.account_product_code
        FROM strategy_execution_order eo
        JOIN connector_account ca
          ON ca.id = eo.account_id
        WHERE eo.id = %(execution_order_id)s
        LIMIT 1
    """

    row = fetch_one(conn, sql, {
        "execution_order_id": execution_order_id,
    })

    if not row:
        raise RuntimeError(f"strategy_execution_order 없음: id={execution_order_id}")

    return row

def mark_execution_order_execution_mode(conn, execution_order_id, execution_mode):
    """
    Explicitly change the execution mode of strategy_execution_order.

    Usage examples:
    - DRY_RUN
    - MANUAL_TEST
    - PAPER_STRATEGY
    - LIVE_STRATEGY
    """

    sql = """
        UPDATE strategy_execution_order
        SET
            execution_mode = %(execution_mode)s,
            updated_at = now()
        WHERE id = %(execution_order_id)s
        RETURNING
            id,
            execution_mode,
            execution_status,
            connector_order_request_id
    """

    return execute_one(conn, sql, {
        "execution_order_id": execution_order_id,
        "execution_mode": execution_mode,
    })


def mark_execution_order_manual_test(conn, execution_order_id):
    """
    Backward-compatibility wrapper.
    New executors are recommended to use mark_execution_order_execution_mode().
    """

    return mark_execution_order_execution_mode(
        conn=conn,
        execution_order_id=execution_order_id,
        execution_mode="MANUAL_TEST",
    )

def mark_execution_order_requested(conn, execution_order_id, result_payload):
    """
    Mark a READY strategy_execution_order as a MarketConnector execution request target.
    connector_order_request_id is linked when the MarketConnector executor creates the order request.
    """
    sql = """
        UPDATE strategy_execution_order
        SET
            execution_status = 'REQUESTED',
            result_payload = %(result_payload)s,
            updated_at = now()
        WHERE id = %(execution_order_id)s
          AND execution_status = 'READY'
          AND connector_order_request_id IS NULL
        RETURNING
            id,
            execution_status,
            execution_mode,
            connector_order_request_id,
            action_type,
            source_type
    """

    return execute_one(conn, sql, {
        "execution_order_id": execution_order_id,
        "result_payload": dumps_json(result_payload),
    })


def mark_execution_order_submitted(conn, execution_order_id, connector_order_request_id, result_payload):
    """
    Reflect the connector order-acceptance result into strategy_execution_order as SUBMITTED status.
    The connector_order_request_id link becomes the basis for subsequent fill sync.
    """
    sql = """
        UPDATE strategy_execution_order
        SET
            execution_status = 'SUBMITTED',
            connector_order_request_id = %(connector_order_request_id)s,
            result_payload = %(result_payload)s,
            updated_at = now()
        WHERE id = %(execution_order_id)s
        RETURNING
            id,
            execution_status,
            execution_mode,
            connector_order_request_id
    """

    return execute_one(conn, sql, {
        "execution_order_id": execution_order_id,
        "connector_order_request_id": connector_order_request_id,
        "result_payload": dumps_json(result_payload),
    })


def mark_execution_order_execute_failed(
    conn,
    execution_order_id,
    result_payload,
    connector_order_request_id=None,
):
    sql = """
        UPDATE strategy_execution_order
        SET
            execution_status = 'FAILED',
            connector_order_request_id = COALESCE(
                %(connector_order_request_id)s,
                connector_order_request_id
            ),
            result_payload = %(result_payload)s,
            block_reason = COALESCE(
                %(error_message)s,
                block_reason
            ),
            updated_at = now()
        WHERE id = %(execution_order_id)s
        RETURNING
            id,
            execution_status,
            execution_mode,
            connector_order_request_id,
            block_reason
    """

    error_message = None

    if isinstance(result_payload, dict):
        error_message = result_payload.get("error")

    return execute_one(conn, sql, {
        "execution_order_id": execution_order_id,
        "connector_order_request_id": connector_order_request_id,
        "result_payload": dumps_json(result_payload),
        "error_message": error_message,
    })

def dumps_json(value):
    """
    Safely convert DB json/jsonb, dict, list, and None values into a JSON string.
    """

    if value is None:
        return None

    if isinstance(value, str):
        return value

    return json.dumps(value, ensure_ascii=False, default=str)

# =========================================================
# POSITION_SELL repository functions dedicated to operational SELL
# =========================================================

def get_latest_stock_feature_for_sell(conn, ticker_code, plan_date):
    """
    Query the stock feature for operational SELL evaluation.

    Criteria:
    - Use the latest pre_total_stock_daily_feature at or before plan_date
    - Right after market open the same-day feature may be absent, so use the <= plan_date basis
    """

    sql = """
        SELECT
            *
        FROM pre_total_stock_daily_feature
        WHERE ticker_code = %(ticker_code)s
          AND date <= %(plan_date)s
        ORDER BY date DESC
        LIMIT 1
    """

    return fetch_one(conn, sql, {
        "ticker_code": ticker_code,
        "plan_date": plan_date,
    })


def get_latest_market_feature_for_sell(conn, plan_date):
    """
    Query the market feature for operational SELL evaluation.

    Criteria:
    - Use the latest pre_total_market_daily_feature at or before plan_date
    - The market_signal column may be absent, so the evaluator treats it as UNKNOWN
    """

    sql = """
        SELECT
            *
        FROM pre_total_market_daily_feature
        WHERE date <= %(plan_date)s
        ORDER BY date DESC
        LIMIT 1
    """

    return fetch_one(conn, sql, {
        "plan_date": plan_date,
    })


def update_position_sell_evaluation(conn, position_state_id, plan_date, evaluation_result):
    """
    Store the latest SELL evaluation result in strategy_position_state.

    Store SELL/HOLD/SKIP alike.
    - Last evaluation date
    - Latest sell reason
    - Latest sell_info
    - validation result
    """

    sell_info = evaluation_result.get("sell_info") or {}

    validation_result = {
        "action": evaluation_result.get("action"),
        "reason": evaluation_result.get("reason"),
        "order_qty": evaluation_result.get("order_qty"),
        "expected_sell_price": str(evaluation_result.get("expected_sell_price")),
        "expected_pnl_amount": str(evaluation_result.get("expected_pnl_amount")),
        "expected_pnl_rate": str(evaluation_result.get("expected_pnl_rate")),
    }

    sql = """
        UPDATE strategy_position_state
        SET
            last_evaluated_date = %(plan_date)s,
            latest_sell_reason = %(latest_sell_reason)s,
            latest_sell_info = %(latest_sell_info)s::jsonb,
            latest_validation_result = %(latest_validation_result)s::jsonb,
            updated_at = now()
        WHERE id = %(position_state_id)s
        RETURNING
            id,
            ticker_code,
            position_status,
            last_evaluated_date,
            latest_sell_reason
    """

    return execute_one(conn, sql, {
        "position_state_id": position_state_id,
        "plan_date": plan_date,
        "latest_sell_reason": evaluation_result.get("reason"),
        "latest_sell_info": dumps_json(sell_info),
        "latest_validation_result": dumps_json(validation_result),
    })


def mark_position_sell_ready(conn, position_state_id, evaluation_result):
    """
    Change the position status to SELL_READY when a SELL candidate is created as READY.
    """

    sql = """
        UPDATE strategy_position_state
        SET
            position_status = 'SELL_READY',
            latest_sell_reason = %(latest_sell_reason)s,
            latest_sell_info = %(latest_sell_info)s::jsonb,
            updated_at = now()
        WHERE id = %(position_state_id)s
          AND position_status = 'OPEN'
        RETURNING
            id,
            ticker_code,
            position_status,
            latest_sell_reason
    """

    return execute_one(conn, sql, {
        "position_state_id": position_state_id,
        "latest_sell_reason": evaluation_result.get("reason"),
        "latest_sell_info": dumps_json(evaluation_result.get("sell_info") or {}),
    })


def mark_position_sell_ordered(conn, position_state_id):
    """
    Function to be used later after an actual connector SELL order submission.
    Not yet used at the current builder stage.
    """

    sql = """
        UPDATE strategy_position_state
        SET
            position_status = 'SELL_ORDERED',
            updated_at = now()
        WHERE id = %(position_state_id)s
          AND position_status IN ('OPEN', 'SELL_READY')
        RETURNING
            id,
            ticker_code,
            position_status
    """

    return execute_one(conn, sql, {
        "position_state_id": position_state_id,
    })


def mark_position_closed_after_sell(conn, position_state_id, closed_qty):
    """
    Function to be used later after confirming SELL fills.
    Reduce remaining_qty and mark CLOSED if it reaches 0.
    Not yet used at the current builder stage.
    """

    sql = """
        UPDATE strategy_position_state
        SET
            remaining_qty = GREATEST(remaining_qty - %(closed_qty)s, 0),
            position_status =
                CASE
                    WHEN GREATEST(remaining_qty - %(closed_qty)s, 0) <= 0
                        THEN 'CLOSED'
                    ELSE 'OPEN'
                END,
            updated_at = now()
        WHERE id = %(position_state_id)s
        RETURNING
            id,
            ticker_code,
            remaining_qty,
            position_status
    """

    return execute_one(conn, sql, {
        "position_state_id": position_state_id,
        "closed_qty": closed_qty,
    })


def upsert_position_sell_execution_order(conn, order_data):
    """
    Create/update a POSITION_SELL operational sell candidate in strategy_execution_order.

    Reason for separating from the existing upsert_execution_order():
    - The existing function is based on source_trade_log_id
    - Operational SELL is based on source_position_state_id
    """

    sql = """
        INSERT INTO strategy_execution_order (
            execution_plan_id,
            strategy_signal_id,

            source_run_id,
            source_trade_log_id,
            source_position_state_id,
            source_type,
            execution_mode,

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
            validation_result,

            sell_reason,
            sell_info,
            expected_sell_price,
            expected_pnl_amount,
            expected_pnl_rate
        )
        VALUES (
            %(execution_plan_id)s,
            NULL,

            %(source_run_id)s,
            NULL,
            %(source_position_state_id)s,
            %(source_type)s,
            %(execution_mode)s,

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
            %(validation_result)s,

            %(sell_reason)s,
            %(sell_info)s,
            %(expected_sell_price)s,
            %(expected_pnl_amount)s,
            %(expected_pnl_rate)s
        )
        ON CONFLICT (
            execution_plan_id,
            source_position_state_id,
            action_type
        )
        WHERE source_position_state_id IS NOT NULL
          AND source_type = 'POSITION_SELL'
          AND action_type = 'SELL'
        DO UPDATE SET
            source_run_id = EXCLUDED.source_run_id,
            source_type = EXCLUDED.source_type,
            execution_mode = EXCLUDED.execution_mode,

            account_id = EXCLUDED.account_id,
            account_no = EXCLUDED.account_no,
            signal_date = EXCLUDED.signal_date,
            ticker_code = EXCLUDED.ticker_code,
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

            sell_reason = EXCLUDED.sell_reason,
            sell_info = EXCLUDED.sell_info,
            expected_sell_price = EXCLUDED.expected_sell_price,
            expected_pnl_amount = EXCLUDED.expected_pnl_amount,
            expected_pnl_rate = EXCLUDED.expected_pnl_rate,

            updated_at = now()
        RETURNING
            id,
            execution_plan_id,
            source_position_state_id,
            source_type,
            action_type,
            ticker_code,
            stock_name,
            order_qty,
            order_price,
            execution_status,
            block_reason,
            sell_reason
    """

    return execute_one(conn, sql, order_data)

# =========================================================
# DAILY_SIGNAL_BUY repository functions
# =========================================================

def get_latest_daily_run(conn):
    """
    Query the latest COMPLETED Daily Signal run.
    """

    sql = """
        SELECT
            id,
            strategy_name,
            strategy_version,
            run_date,
            data_date,
            run_type,
            run_status,
            market_signal,
            base_exposure,
            max_positions,
            candidate_count,
            signal_count,
            config_snapshot,
            started_at,
            finished_at
        FROM strategy_daily_run
        WHERE strategy_name = %(strategy_name)s
          AND strategy_version = %(strategy_version)s
          AND run_type = 'DAILY_SIGNAL'
          AND run_status = 'COMPLETED'
        ORDER BY run_date DESC, data_date DESC, id DESC
        LIMIT 1
    """

    row = fetch_one(conn, sql, {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
    })

    if not row:
        raise RuntimeError("최신 strategy_daily_run을 찾지 못함")

    return row


def get_daily_buy_signals(conn, daily_run_id):
    """
    Query Daily Signal BUY candidates.
    """

    sql = """
        SELECT
            id,
            daily_run_id,
            strategy_name,
            strategy_version,
            run_date,
            data_date,
            signal_date,
            ticker_code,
            company_name,
            signal_type,
            signal_status,
            rank_no,
            market_signal,
            base_exposure,
            final_score,
            flow_score,
            tape_score,
            info_score,
            short_score,
            volatility_20d,
            intraday_range,
            position_size,
            target_amount,
            target_qty,
            entry_reason,
            block_reason,
            buy_info,
            raw_features,
            source_table,
            processor_version,
            created_at,
            updated_at
        FROM strategy_daily_signal
        WHERE daily_run_id = %(daily_run_id)s
          AND signal_type = 'BUY'
          AND signal_status = 'READY'
        ORDER BY rank_no ASC NULLS LAST, id ASC
    """

    return fetch_all(conn, sql, {
        "daily_run_id": daily_run_id,
    })


def create_or_get_daily_signal_plan(conn, account, balance, daily_run):
    """
    Create/update strategy_execution_plan based on the Daily Signal.
    """

    available_cash = balance["orderable_cash"] or balance["cash_balance"] or Decimal("0")
    max_order_amount = available_cash * DEFAULT_MAX_ORDER_AMOUNT_RATIO

    plan_date = daily_run["run_date"]
    market_signal = daily_run["market_signal"]

    memo = (
        "Daily Signal 기반 execution 후보 생성 "
        f"(daily_run_id={daily_run['id']}, data_date={daily_run['data_date']})"
    )

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
            NULL,
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
            risk_regime = EXCLUDED.risk_regime,
            available_cash = EXCLUDED.available_cash,
            max_order_amount = EXCLUDED.max_order_amount,
            memo = EXCLUDED.memo,
            updated_at = now()
        RETURNING id
    """

    row = execute_one(conn, sql, {
        "plan_date": plan_date,
        "strategy_name": daily_run["strategy_name"] or STRATEGY_NAME,
        "strategy_version": daily_run["strategy_version"] or STRATEGY_VERSION,
        "market_signal": market_signal,
        "risk_regime": market_signal,
        "account_id": account["id"],
        "account_no": account["account_no"],
        "available_cash": available_cash,
        "max_order_amount": max_order_amount,
        "memo": memo,
    })

    return row["id"]


def upsert_daily_signal_execution_order(conn, order_data):
    """
    Create/update a DAILY_SIGNAL_BUY operational buy candidate in strategy_execution_order.

    Reason for separating from the existing upsert_execution_order():
    - The existing function is based on source_trade_log_id
    - Daily Signal is based on source_daily_signal_id
    """

    sql = """
        INSERT INTO strategy_execution_order (
            execution_plan_id,
            strategy_signal_id,

            source_run_id,
            source_trade_log_id,
            source_position_state_id,
            source_daily_run_id,
            source_daily_signal_id,
            source_daily_position_decision_id,
            source_type,
            execution_mode,

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
            NULL,

            NULL,
            NULL,
            NULL,
            %(source_daily_run_id)s,
            %(source_daily_signal_id)s,
            NULL,
            %(source_type)s,
            %(execution_mode)s,

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
        ON CONFLICT (
            execution_plan_id,
            source_daily_signal_id,
            action_type
        )
        WHERE source_daily_signal_id IS NOT NULL
          AND source_type = 'DAILY_SIGNAL_BUY'
          AND action_type = 'BUY'
        DO UPDATE SET
            source_daily_run_id = EXCLUDED.source_daily_run_id,
            source_daily_signal_id = EXCLUDED.source_daily_signal_id,
            source_type = EXCLUDED.source_type,
            execution_mode = EXCLUDED.execution_mode,

            account_id = EXCLUDED.account_id,
            account_no = EXCLUDED.account_no,
            signal_date = EXCLUDED.signal_date,
            ticker_code = EXCLUDED.ticker_code,
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
        RETURNING
            id,
            execution_plan_id,
            source_daily_run_id,
            source_daily_signal_id,
            source_type,
            action_type,
            ticker_code,
            stock_name,
            signal_position_size,
            target_amount,
            current_qty,
            current_eval_amount,
            order_qty,
            order_price,
            execution_status,
            block_reason,
            validation_result
    """

    return execute_one(conn, sql, order_data)

# =========================================================
# DAILY_POSITION_SELL repository functions
# =========================================================

def get_latest_daily_run_for_position_decision(conn):
    """
    Query the latest COMPLETED Daily Signal run.
    Daily Position Decision uses strategy_daily_run as its parent.
    """

    sql = """
        SELECT
            id,
            strategy_name,
            strategy_version,
            run_date,
            data_date,
            run_type,
            run_status,
            market_signal,
            base_exposure,
            max_positions,
            candidate_count,
            signal_count,
            config_snapshot,
            started_at,
            finished_at
        FROM strategy_daily_run
        WHERE strategy_name = %(strategy_name)s
          AND strategy_version = %(strategy_version)s
          AND run_type = 'DAILY_SIGNAL'
          AND run_status = 'COMPLETED'
        ORDER BY run_date DESC, data_date DESC, id DESC
        LIMIT 1
    """

    row = fetch_one(conn, sql, {
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
    })

    if not row:
        raise RuntimeError("최신 strategy_daily_run을 찾지 못함")

    return row


def get_ready_daily_position_sell_decisions(conn, daily_run_id):
    """
    Query SELL READY candidates among Daily Position Decisions.
    """

    sql = """
        SELECT
            id,
            daily_run_id,
            strategy_name,
            strategy_version,
            run_date,
            data_date,
            decision_date,
            position_state_id,
            account_id,
            account_no,
            ticker_code,
            stock_name,
            decision_type,
            decision_status,
            sell_reason,
            hold_reason,
            skip_reason,
            holding_days,
            entry_date,
            entry_price,
            entry_qty,
            remaining_qty,
            current_price,
            current_qty,
            sellable_qty,
            expected_pnl_amount,
            expected_pnl_rate,
            market_signal,
            market_regime_score,
            flow_score,
            info_score,
            tape_score,
            final_score,
            short_pressure_score,
            order_qty,
            order_price,
            target_amount,
            position_context,
            sell_info,
            validation_result,
            raw_stock_feature,
            raw_market_feature,
            source_table,
            processor_version,
            execution_order_id,
            error_message,
            created_at,
            updated_at
        FROM strategy_daily_position_decision
        WHERE daily_run_id = %(daily_run_id)s
          AND decision_type = 'SELL'
          AND decision_status = 'READY'
        ORDER BY
            expected_pnl_rate ASC NULLS LAST,
            id ASC
    """

    return fetch_all(conn, sql, {
        "daily_run_id": daily_run_id,
    })


def upsert_daily_position_sell_execution_order(conn, order_data):
    """
    Create/update a DAILY_POSITION_SELL operational sell candidate in strategy_execution_order.

    Criteria:
    - Based on source_daily_position_decision_id
    - source_type = DAILY_POSITION_SELL
    - action_type = SELL
    """

    sql = """
        INSERT INTO strategy_execution_order (
            execution_plan_id,
            strategy_signal_id,

            source_run_id,
            source_trade_log_id,
            source_position_state_id,
            source_daily_run_id,
            source_daily_signal_id,
            source_daily_position_decision_id,
            source_type,
            execution_mode,

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
            validation_result,

            sell_reason,
            sell_info,
            expected_sell_price,
            expected_pnl_amount,
            expected_pnl_rate
        )
        VALUES (
            %(execution_plan_id)s,
            NULL,

            NULL,
            NULL,
            %(source_position_state_id)s,
            %(source_daily_run_id)s,
            NULL,
            %(source_daily_position_decision_id)s,
            %(source_type)s,
            %(execution_mode)s,

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
            %(validation_result)s,

            %(sell_reason)s,
            %(sell_info)s,
            %(expected_sell_price)s,
            %(expected_pnl_amount)s,
            %(expected_pnl_rate)s
        )
        ON CONFLICT (
            execution_plan_id,
            source_daily_position_decision_id,
            action_type
        )
        WHERE source_daily_position_decision_id IS NOT NULL
          AND source_type = 'DAILY_POSITION_SELL'
          AND action_type = 'SELL'
        DO UPDATE SET
            source_position_state_id = EXCLUDED.source_position_state_id,
            source_daily_run_id = EXCLUDED.source_daily_run_id,
            source_daily_position_decision_id = EXCLUDED.source_daily_position_decision_id,
            source_type = EXCLUDED.source_type,
            execution_mode = EXCLUDED.execution_mode,

            account_id = EXCLUDED.account_id,
            account_no = EXCLUDED.account_no,
            signal_date = EXCLUDED.signal_date,
            ticker_code = EXCLUDED.ticker_code,
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

            sell_reason = EXCLUDED.sell_reason,
            sell_info = EXCLUDED.sell_info,
            expected_sell_price = EXCLUDED.expected_sell_price,
            expected_pnl_amount = EXCLUDED.expected_pnl_amount,
            expected_pnl_rate = EXCLUDED.expected_pnl_rate,

            updated_at = now()
        RETURNING
            id,
            execution_plan_id,
            source_position_state_id,
            source_daily_run_id,
            source_daily_position_decision_id,
            source_type,
            action_type,
            ticker_code,
            stock_name,
            order_qty,
            order_price,
            execution_status,
            block_reason,
            sell_reason
    """

    return execute_one(conn, sql, order_data)


def update_daily_position_decision_execution_order_link(conn, decision_id, execution_order_id):
    """
    Link the created execution_order_id to strategy_daily_position_decision.
    """

    sql = """
        UPDATE strategy_daily_position_decision
        SET
            execution_order_id = %(execution_order_id)s,
            decision_status = 'EXECUTION_CREATED',
            updated_at = now()
        WHERE id = %(decision_id)s
        RETURNING
            id,
            decision_status,
            execution_order_id
    """

    return execute_one(conn, sql, {
        "decision_id": decision_id,
        "execution_order_id": execution_order_id,
    })

def get_ready_daily_buy_execution_orders(conn, plan_id=None, limit=20):
    """
    Query DAILY_SIGNAL_BUY READY orders targeted for automatic buy execution.

    Conditions:
    - Order based on the Daily BUY Signal
    - BUY
    - READY
    - No Connector order request yet
    - Only DRY_RUN or PAPER_STRATEGY status allowed
    """

    params = {
        "limit": limit,
    }

    plan_filter = ""

    if plan_id is not None:
        plan_filter = "AND eo.execution_plan_id = %(plan_id)s"
        params["plan_id"] = plan_id

    sql = f"""
        SELECT
            eo.id,
            eo.execution_plan_id,

            eo.source_daily_run_id,
            eo.source_daily_signal_id,
            eo.source_type,
            eo.execution_mode,

            eo.account_id,
            eo.account_no,

            eo.signal_date,
            eo.ticker_code,
            eo.stock_name,

            eo.action_type,
            eo.signal_type,
            eo.signal_score,
            eo.signal_position_size,

            eo.market_signal,
            eo.flow_score,
            eo.info_score,
            eo.tape_score,
            eo.final_score,
            eo.short_pressure_score,

            eo.target_weight,
            eo.target_amount,
            eo.current_qty,
            eo.current_eval_amount,

            eo.order_qty,
            eo.order_price,
            eo.order_method,

            eo.execution_status,
            eo.block_reason,
            eo.connector_order_request_id,

            eo.signal_reason,
            eo.validation_result,
            eo.result_payload,

            ca.broker_name,
            ca.environment,
            ca.account_product_code

        FROM strategy_execution_order eo
        JOIN connector_account ca
          ON ca.id = eo.account_id

        WHERE eo.source_type = 'DAILY_SIGNAL_BUY'
          AND eo.action_type = 'BUY'
          AND eo.execution_status = 'READY'
          AND eo.connector_order_request_id IS NULL
          AND eo.order_qty > 0
          AND COALESCE(eo.execution_mode, 'DRY_RUN') IN ('DRY_RUN', 'PAPER_STRATEGY')
          {plan_filter}

        ORDER BY
            eo.signal_score DESC NULLS LAST,
            eo.id ASC

        LIMIT %(limit)s
    """

    return fetch_all(conn, sql, params)

def get_ready_daily_position_sell_execution_orders(conn, plan_id=None, limit=20):
    """
    Query targets for Daily/Intraday SELL automatic execution.

    Targets:
    - source_type IN (DAILY_POSITION_SELL, INTRADAY_STOP_SELL)
    - action_type = SELL
    - execution_status = READY
    - execution_mode = DRY_RUN or PAPER_STRATEGY
    - No connector_order_request_id
    """

    params = {
        "limit": limit,
    }

    plan_filter_sql = ""
    if plan_id is not None:
        plan_filter_sql = "AND seo.execution_plan_id = %(plan_id)s"
        params["plan_id"] = plan_id

    sql = f"""
        SELECT
            seo.id,
            seo.execution_plan_id,
            seo.account_id,
            seo.account_no,
            ca.environment,
            seo.source_type,
            seo.execution_mode,
            seo.action_type,
            seo.execution_status,
            seo.signal_date,
            seo.ticker_code,
            seo.stock_name,
            seo.current_qty,
            seo.order_qty,
            seo.order_price,
            seo.order_method,
            seo.expected_sell_price,
            seo.expected_pnl_amount,
            seo.expected_pnl_rate,
            seo.sell_reason,
            seo.sell_info,
            seo.connector_order_request_id,
            seo.source_position_state_id,
            seo.source_daily_run_id,
            seo.source_daily_position_decision_id,
            seo.validation_result,
            seo.request_payload,
            seo.result_payload,
            seo.created_at,
            seo.updated_at
        FROM strategy_execution_order seo
        JOIN connector_account ca
          ON ca.id = seo.account_id
        WHERE seo.source_type IN ('DAILY_POSITION_SELL', 'INTRADAY_STOP_SELL')
          AND seo.action_type = 'SELL'
          AND seo.execution_status = 'READY'
          AND seo.execution_mode IN ('DRY_RUN', 'PAPER_STRATEGY')
          AND seo.connector_order_request_id IS NULL
          {plan_filter_sql}
        ORDER BY seo.id ASC
        LIMIT %(limit)s
    """

    return fetch_all(conn, sql, params)

def get_open_strategy_positions_for_intraday_monitor(conn, account_id=None):
    """
    Query OPEN strategy positions targeted by the Intraday Position Monitor.

    Criteria:
    - strategy_position_state.position_status = OPEN
    - remaining_qty > 0
    - account_id filter when needed
    """

    params = {}

    account_filter_sql = ""
    if account_id is not None:
        account_filter_sql = "AND sps.account_id = %(account_id)s"
        params["account_id"] = account_id

    sql = f"""
        SELECT
            sps.id AS position_state_id,
            sps.account_id,
            sps.account_no,
            ca.environment,
            sps.ticker_code,
            sps.stock_name,
            sps.source_buy_execution_order_id,
            sps.source_connector_order_request_id,
            sps.source_connector_fill_id,
            sps.entry_date,
            sps.entry_price,
            sps.entry_qty,
            sps.remaining_qty,
            sps.position_status,
            sps.last_evaluated_date,
            sps.latest_sell_reason,
            sps.latest_sell_info,
            sps.latest_validation_result,
            sps.buy_info,
            sps.memo,
            sps.created_at,
            sps.updated_at
        FROM strategy_position_state sps
        JOIN connector_account ca
          ON ca.id = sps.account_id
        WHERE sps.position_status = 'OPEN'
          AND COALESCE(sps.remaining_qty, 0) > 0
          {account_filter_sql}
        ORDER BY sps.id ASC
    """

    return fetch_all(conn, sql, params)


def get_latest_connector_position_snapshot(conn, account_id, ticker_code):
    """
    Query connector_position_snapshot based on the latest balance snapshot.
    """

    sql = """
        WITH latest_balance AS (
            SELECT
                account_id,
                account_no,
                as_of_date,
                as_of_ts
            FROM connector_balance_snapshot
            WHERE account_id = %(account_id)s
            ORDER BY as_of_date DESC, as_of_ts DESC, id DESC
            LIMIT 1
        )
        SELECT
            cps.id,
            cps.account_id,
            cps.account_no,
            cps.ticker_code,
            cps.stock_name,
            cps.market,
            cps.as_of_date,
            cps.as_of_ts,
            cps.quantity,
            cps.sellable_quantity,
            cps.avg_buy_price,
            cps.buy_amount,
            cps.current_price,
            cps.eval_amount,
            cps.eval_profit,
            cps.eval_profit_rate,
            cps.raw_json,
            cps.source_api,
            cps.source_version,
            cps.created_at
        FROM latest_balance lb
        JOIN connector_position_snapshot cps
          ON cps.account_id = lb.account_id
         AND cps.as_of_date = lb.as_of_date
        WHERE cps.account_id = %(account_id)s
          AND cps.ticker_code = %(ticker_code)s
          AND COALESCE(cps.quantity, 0) > 0
        ORDER BY cps.as_of_ts DESC, cps.id DESC
        LIMIT 1
    """

    return fetch_one(conn, sql, {
        "account_id": account_id,
        "ticker_code": ticker_code,
    })

def get_latest_daily_execution_plan(conn, account_id):
    """
    Query the latest Daily execution plan to attach an Intraday Stop SELL order to.

    Primary policy:
    - Reuse today's or the most recent Daily execution plan
    - Needed because strategy_execution_order.execution_plan_id must be NOT NULL
    """

    sql = """
        SELECT
            id,
            plan_date,
            strategy_name,
            strategy_version,
            strategy_run_id,
            market_signal,
            risk_regime,
            account_id,
            account_no,
            plan_status,
            available_cash,
            max_order_amount,
            memo,
            created_at,
            updated_at
        FROM strategy_execution_plan
        WHERE account_id = %(account_id)s
          AND strategy_name = %(strategy_name)s
          AND strategy_version = %(strategy_version)s
        ORDER BY plan_date DESC, id DESC
        LIMIT 1
    """

    row = fetch_one(conn, sql, {
        "account_id": account_id,
        "strategy_name": STRATEGY_NAME,
        "strategy_version": STRATEGY_VERSION,
    })

    if not row:
        raise RuntimeError("Intraday Stop SELL을 붙일 최신 strategy_execution_plan을 찾지 못함")

    return row


def upsert_intraday_stop_sell_execution_order(conn, order_data):
    """
    Create/update an INTRADAY_STOP_SELL operational sell candidate in strategy_execution_order.

    Note:
    - The DB does not yet have a unique index dedicated to INTRADAY_STOP_SELL
    - Therefore, before INSERT, check whether a READY/SUBMITTED row with the same plan/position/source_type/action_type exists
    - If one already exists, UPDATE the existing row and return it
    """

    find_sql = """
        SELECT
            id
        FROM strategy_execution_order
        WHERE execution_plan_id = %(execution_plan_id)s
          AND source_position_state_id = %(source_position_state_id)s
          AND source_type = 'INTRADAY_STOP_SELL'
          AND action_type = 'SELL'
          AND execution_status IN ('READY', 'SUBMITTED')
        ORDER BY id DESC
        LIMIT 1
    """

    existing = fetch_one(conn, find_sql, order_data)

    if existing:
        update_sql = """
            UPDATE strategy_execution_order
            SET
                account_id = %(account_id)s,
                account_no = %(account_no)s,
                signal_date = %(signal_date)s,
                ticker_code = %(ticker_code)s,
                stock_name = %(stock_name)s,

                signal_type = %(signal_type)s,
                market_signal = %(market_signal)s,

                current_qty = %(current_qty)s,
                current_eval_amount = %(current_eval_amount)s,
                order_qty = %(order_qty)s,
                order_price = %(order_price)s,
                order_method = %(order_method)s,

                execution_mode = %(execution_mode)s,
                execution_status = %(execution_status)s,
                block_reason = %(block_reason)s,
                approval_required = %(approval_required)s,

                signal_reason = %(signal_reason)s::jsonb,
                validation_result = %(validation_result)s::jsonb,
                request_payload = %(request_payload)s::jsonb,

                sell_reason = %(sell_reason)s,
                sell_info = %(sell_info)s::jsonb,
                expected_sell_price = %(expected_sell_price)s,
                expected_pnl_amount = %(expected_pnl_amount)s,
                expected_pnl_rate = %(expected_pnl_rate)s,

                updated_at = now()
            WHERE id = %(existing_id)s
            RETURNING
                id,
                execution_plan_id,
                source_type,
                action_type,
                execution_status,
                ticker_code,
                stock_name,
                order_qty,
                sell_reason
        """

        params = dict(order_data)
        params["existing_id"] = existing["id"]

        return execute_one(conn, update_sql, params)

    insert_sql = """
        INSERT INTO strategy_execution_order (
            execution_plan_id,
            strategy_signal_id,

            source_run_id,
            source_trade_log_id,
            source_position_state_id,
            source_daily_run_id,
            source_daily_signal_id,
            source_daily_position_decision_id,
            source_type,
            execution_mode,

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
            validation_result,
            request_payload,

            sell_reason,
            sell_info,
            expected_sell_price,
            expected_pnl_amount,
            expected_pnl_rate
        )
        VALUES (
            %(execution_plan_id)s,
            NULL,

            NULL,
            NULL,
            %(source_position_state_id)s,
            %(source_daily_run_id)s,
            NULL,
            NULL,
            %(source_type)s,
            %(execution_mode)s,

            %(account_id)s,
            %(account_no)s,
            %(signal_date)s,
            %(ticker_code)s,
            %(stock_name)s,

            %(action_type)s,
            %(signal_type)s,
            NULL,
            NULL,

            %(market_signal)s,

            NULL,
            %(target_amount)s,
            %(current_qty)s,
            %(current_eval_amount)s,

            %(order_qty)s,
            %(order_price)s,
            %(order_method)s,

            %(execution_status)s,
            %(block_reason)s,
            %(approval_required)s,

            %(signal_reason)s::jsonb,
            %(validation_result)s::jsonb,
            %(request_payload)s::jsonb,

            %(sell_reason)s,
            %(sell_info)s::jsonb,
            %(expected_sell_price)s,
            %(expected_pnl_amount)s,
            %(expected_pnl_rate)s
        )
        RETURNING
            id,
            execution_plan_id,
            source_type,
            action_type,
            execution_status,
            ticker_code,
            stock_name,
            order_qty,
            sell_reason
    """

    return execute_one(conn, insert_sql, order_data)

def insert_intraday_position_check(conn, monitor_result, created_execution_order_id=None):
    """
    Store the Intraday Position Monitor result in strategy_intraday_position_check.

    Call policy:
    - Warning present
    - current_price <= 0
    - A should_stop candidate detected without --create-order
    - Record created_execution_order_id after creating an INTRADAY_STOP_SELL order

    This function itself does not decide whether to save;
    the caller determines the save policy.
    """

    warnings = monitor_result.get("warnings") or []

    sql = """
        INSERT INTO strategy_intraday_position_check (
            account_id,
            account_no,
            environment,

            position_state_id,
            ticker_code,
            stock_name,

            entry_date,
            entry_price,
            remaining_qty,
            snapshot_qty,
            sellable_qty,

            current_price,
            snapshot_current_price,
            previous_close,

            pnl_rate,
            intraday_drop_rate,
            hard_stop_rate,

            should_stop,
            stop_reason,

            created_execution_order_id,

            warning_count,
            warnings,
            raw_payload
        )
        VALUES (
            %(account_id)s,
            %(account_no)s,
            %(environment)s,

            %(position_state_id)s,
            %(ticker_code)s,
            %(stock_name)s,

            %(entry_date)s,
            %(entry_price)s,
            %(remaining_qty)s,
            %(snapshot_qty)s,
            %(sellable_qty)s,

            %(current_price)s,
            %(snapshot_current_price)s,
            %(previous_close)s,

            %(pnl_rate)s,
            %(intraday_drop_rate)s,
            %(hard_stop_rate)s,

            %(should_stop)s,
            %(stop_reason)s,

            %(created_execution_order_id)s,

            %(warning_count)s,
            %(warnings)s::jsonb,
            %(raw_payload)s::jsonb
        )
        RETURNING
            id,
            check_ts,
            position_state_id,
            ticker_code,
            should_stop,
            stop_reason,
            created_execution_order_id,
            warning_count
    """

    return execute_one(conn, sql, {
        "account_id": monitor_result.get("account_id"),
        "account_no": monitor_result.get("account_no"),
        "environment": monitor_result.get("environment"),

        "position_state_id": monitor_result.get("position_state_id"),
        "ticker_code": monitor_result.get("ticker_code"),
        "stock_name": monitor_result.get("stock_name"),

        "entry_date": monitor_result.get("entry_date"),
        "entry_price": monitor_result.get("entry_price"),
        "remaining_qty": monitor_result.get("remaining_qty"),
        "snapshot_qty": monitor_result.get("snapshot_qty"),
        "sellable_qty": monitor_result.get("sellable_qty"),

        "current_price": monitor_result.get("current_price"),
        "snapshot_current_price": monitor_result.get("snapshot_current_price"),
        "previous_close": monitor_result.get("previous_close"),

        "pnl_rate": monitor_result.get("pnl_rate"),
        "intraday_drop_rate": monitor_result.get("intraday_drop_rate"),
        "hard_stop_rate": monitor_result.get("hard_stop_rate"),

        "should_stop": monitor_result.get("should_stop"),
        "stop_reason": monitor_result.get("stop_reason"),

        "created_execution_order_id": created_execution_order_id,

        "warning_count": len(warnings),
        "warnings": dumps_json(warnings),
        "raw_payload": dumps_json(monitor_result),
    })
