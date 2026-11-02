"""Offline ID-scoped fill sync and unchanged default Daily entrypoint tests."""
import argparse
import ast
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "execution_sync_sell_fill.py"


class IntradayFillTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "urllib.request.urlopen", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("External access forbidden"))
            blocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(blocked.assert_not_called)
        names = {"sync_intraday_orders", "main"}
        functions = [n for n in ast.parse(SOURCE.read_text(encoding="utf-8-sig")).body
                     if isinstance(n, ast.FunctionDef) and n.name in names]
        self.conn = MagicMock()
        self.order = dict(id=10, account_id=2, execution_status="SUBMITTED", ticker_code="TEST_STOCK",
                          order_qty=2, connector_order_request_id=7, source_position_state_id=3)
        self.request = dict(id=7, account_id=2, ticker_code="TEST_STOCK", request_type="SELL",
                            strategy_run_id="intraday:10", order_qty=2, request_status="FILLED")
        self.position = dict(id=3, remaining_qty=2)
        self.fills = [dict(id=8, account_id=2, ticker_code="TEST_STOCK", side="SELL", fill_qty=2)]
        self.ns = dict(argparse=argparse, INTRADAY_SYNC_API="intraday-id-scope-v1",
                       fetch_one=Mock(side_effect=[self.order, self.request, self.position]),
                       get_connector_sell_fills=Mock(return_value=self.fills),
                       summarize_fills=lambda rows: {"total_fill_qty": sum(r["fill_qty"] for r in rows)},
                       sync_one_order=Mock(return_value={"execution_order_id": 10, "status": "SYNCED"}),
                       daily_main=Mock(), get_conn=Mock(return_value=self.conn), print=Mock())
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), self.ns)

    def sync(self, ids=None):
        return self.ns["sync_intraday_orders"](self.conn, [10] if ids is None else ids, 2)

    def test_filled_reuses_existing_sync_for_exact_locked_id(self):
        self.assertEqual(self.sync()[0]["status"], "SYNCED")
        self.ns["sync_one_order"].assert_called_once_with(self.conn, self.order)
        sql, params = self.ns["fetch_one"].call_args_list[0].args[1:]
        for clause in ("id = %(id)s", "account_id = %(account_id)s", "PAPER_INTRADAY", "FOR UPDATE"):
            self.assertIn(clause, sql)
        self.assertEqual(params, {"id": 10, "account_id": 2})
        self.assertEqual(len(self.ns["fetch_one"].call_args_list), 3)

    def test_already_filled_never_deducts_position_again(self):
        self.order["execution_status"] = "FILLED"
        self.assertEqual(self.sync()[0]["status"], "ALREADY_FILLED")
        self.ns["sync_one_order"].assert_not_called()
        self.assertEqual(self.ns["fetch_one"].call_count, 1)

    def test_pending_partial_fills_are_not_closed(self):
        for status in ("ACCEPTED", "SUBMITTED", "PARTIAL_FILLED"):
            with self.subTest(status=status):
                self.request["request_status"] = status
                self.ns["fetch_one"].side_effect = [self.order, self.request]
                self.assertEqual(self.sync()[0]["status"], "PENDING")
        self.ns["sync_one_order"].assert_not_called()

    def test_missing_wrong_account_or_rejected_request_blocks_sync(self):
        for mutation in (None, {"account_id": 9}, {"strategy_run_id": "DAILY"},
                         {"request_status": "CANCELED"}, {"request_status": "REJECTED"}):
            with self.subTest(mutation=mutation):
                request = {**self.request, **(mutation or {})} if mutation is not None else None
                self.ns["fetch_one"].side_effect = [self.order, request]
                with self.assertRaises(RuntimeError):
                    self.sync()
        self.ns["sync_one_order"].assert_not_called()

    def test_incomplete_overfilled_wrong_side_or_duplicate_fill_blocks(self):
        for fills in ([], [{**self.fills[0], "fill_qty": 1}], [{**self.fills[0], "fill_qty": 3}],
                      [{**self.fills[0], "side": "BUY"}], [self.fills[0], self.fills[0]]):
            with self.subTest(fills=fills):
                self.ns["fetch_one"].side_effect = [self.order, self.request, self.position]
                self.ns["get_connector_sell_fills"].return_value = fills
                with self.assertRaises(RuntimeError):
                    self.sync()
        self.ns["sync_one_order"].assert_not_called()

    def test_invalid_ids_never_query_db(self):
        for ids in ([], [True], [0], [-1], ["10"], list(range(1, 22))):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.sync(ids)
        self.ns["fetch_one"].assert_not_called()

    def test_default_cli_calls_only_existing_daily_main(self):
        with patch.object(sys, "argv", ["execution_sync_sell_fill.py"]):
            self.ns["main"]()
        self.ns["daily_main"].assert_called_once_with()
        self.ns["get_conn"].assert_not_called()

    def test_preflight_has_no_db_or_daily_execution(self):
        with patch.object(sys, "argv", ["execution_sync_sell_fill.py", "--intraday-preflight"]):
            self.ns["main"]()
        self.ns["get_conn"].assert_not_called()
        self.ns["daily_main"].assert_not_called()
        self.ns["sync_one_order"].assert_not_called()

    def test_intraday_cli_commits_or_rolls_back_atomically(self):
        args = ["execution_sync_sell_fill.py", "--intraday-order-id", "10", "--intraday-account-id", "2"]
        with patch.object(sys, "argv", args):
            self.ns["main"]()
        self.conn.commit.assert_called_once_with()
        self.conn.close.assert_called_once_with()
        self.conn.reset_mock()
        self.ns["sync_intraday_orders"] = Mock(side_effect=RuntimeError("synthetic failure"))
        with patch.object(sys, "argv", args), self.assertRaises(RuntimeError):
            self.ns["main"]()
        self.conn.rollback.assert_called_once_with()
        self.conn.commit.assert_not_called()
        self.conn.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
