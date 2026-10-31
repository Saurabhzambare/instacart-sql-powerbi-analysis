import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.load_table import (
    TABLES, SimulatedLoadFailure, bulk_sql, expected_checks, run_load, validate_checks,
)


class LoadingContractsTests(unittest.TestCase):
    def test_loading_columns_match_input_manifest(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "config/input_manifest.json").read_text(encoding="utf-8-sig"))
        headers = {item["name"]: item["columns"] for item in manifest["files"]}
        for specification in TABLES.values():
            with self.subTest(file=specification["file"]):
                self.assertEqual([column[0] for column in specification["columns"]], headers[specification["file"]])

    def test_wrong_counts_and_failed_rules_are_rejected(self):
        for table, specification in TABLES.items():
            checks = expected_checks(specification)
            validate_checks(checks, specification)
            for name, expected in checks.items():
                with self.subTest(table=table, check=name):
                    with self.assertRaises(ValueError):
                        validate_checks(dict(checks, **{name: expected + 1}), specification)

    def test_missing_check_is_rejected(self):
        checks = expected_checks(TABLES["orders"])
        del checks["prior_orders"]
        with self.assertRaises(ValueError):
            validate_checks(checks, TABLES["orders"])

    def test_bulk_path_quotes_are_escaped(self):
        self.assertIn("Saurabh''s data", bulk_sql(Path("D:/Saurabh's data/orders.csv")))


class TableTransactionTests(unittest.TestCase):
    def make_connection(self, rows):
        connection = Mock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = rows
        return connection, cursor

    def run_loader(self, connection, report, failure=False, inspection="PASS"):
        with patch("scripts.load_table.read_source_checks", return_value=expected_checks(TABLES["aisles"])), \
             patch("scripts.load_table.inspect_file", return_value={"status": inspection}), \
             patch("builtins.print"):
            run_load(connection, "aisles", Path("aisles.csv"), {}, {}, report, failure)

    def test_initial_load_commits(self):
        connection, cursor = self.make_connection([("test", "test"), (0,), (1,), (0,), (134,)])
        report = {}
        self.run_loader(connection, report)
        self.assertEqual(report["action"], "LOADED")
        self.assertEqual(report["target_rows_after"], 134)
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()

    def test_unchanged_rerun_avoids_target_writes(self):
        connection, cursor = self.make_connection([("test", "test"), (134,), (0,), (134,)])
        report = {}
        self.run_loader(connection, report)
        self.assertEqual(report["action"], "UNCHANGED")
        self.assertFalse(any("DELETE FROM" in call.args[0] or "INSERT INTO" in call.args[0]
                             for call in cursor.execute.call_args_list))
        connection.commit.assert_called_once()

    def test_deliberate_failure_rolls_back(self):
        connection, _ = self.make_connection([("test", "test"), (134,), (0,), (0,)])
        report = {}
        with self.assertRaises(SimulatedLoadFailure):
            self.run_loader(connection, report, failure=True)
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        self.assertEqual(report["transaction_outcome"], "ROLLED_BACK")

    def test_changed_source_after_bulk_prevents_publish(self):
        connection, cursor = self.make_connection([("test", "test")])
        with self.assertRaises(ValueError):
            self.run_loader(connection, {}, inspection="FAIL")
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        self.assertFalse(any("DELETE FROM" in call.args[0] for call in cursor.execute.call_args_list))

    def test_target_row_mismatch_rolls_back(self):
        connection, _ = self.make_connection([("test", "test"), (134,), (0,), (133,)])
        with self.assertRaises(ValueError):
            self.run_loader(connection, {})
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_commit_error_has_unknown_outcome(self):
        connection, _ = self.make_connection([("test", "test"), (134,), (0,), (134,)])
        connection.commit.side_effect = RuntimeError("lost connection during commit")
        report = {}
        with self.assertRaises(RuntimeError):
            self.run_loader(connection, report)
        self.assertEqual(report["transaction_outcome"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
