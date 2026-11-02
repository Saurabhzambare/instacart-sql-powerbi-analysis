"""Offline contracts and transaction-flow tests; SQL Server execution is separate."""

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import load_ml_train_labels as loader


class TransactionDouble:
    """Model target state/rollback; do not pretend to implement the SQL engine."""

    def __init__(self, expected, target):
        self.expected = list(expected)
        self.target = list(target)
        self.original = list(target)
        self.calls = []
        self.current = []
        self.lock_result = 0
        self.bad_columns = False
        self.bad_keys = False
        self.bad_expected_metrics = False
        self.bad_final_comparison = False
        self.comparison_count = 0
        self.commit_error = False
        self.rollback_error = False
        self.commit = Mock(side_effect=self.do_commit)
        self.rollback = Mock(side_effect=self.do_rollback)

    def cursor(self):
        return self

    def close(self):
        pass

    def execute(self, sql, *parameters):
        self.calls.append((sql, parameters))
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT DB_NAME()"):
            self.current = [("fixture_database", "fixture_server")]
        elif "FROM sys.columns" in sql:
            self.current = [(name, "int", False, False, False) for name in loader.COLUMNS]
            if self.bad_columns:
                self.current.pop()
        elif "FROM sys.indexes" in sql:
            self.current = [(True, True, "order_id,product_id"), (False, True, "order_id,add_to_cart_order")]
            if self.bad_keys:
                self.current.pop()
        elif "SELECT @lock_result" in sql:
            self.current = [(self.lock_result,)]
        elif normalized.startswith("SELECT COUNT_BIG(*)") and "WITH (TABLOCKX, HOLDLOCK)" in sql:
            self.current = [(len(self.target),)]
        elif normalized.startswith("SELECT COUNT_BIG(*)"):
            expected_source = "FROM #ml_expected_labels" in sql
            rows = self.expected if expected_source else self.target
            metrics = (len(rows), len({r[0] for r in rows}), len({r[1] for r in rows}),
                       len({r[2] for r in rows}), sum(r[4] for r in rows))
            if expected_source and self.bad_expected_metrics:
                metrics = (metrics[0] + 1, *metrics[1:])
            self.current = [metrics]
        elif normalized.startswith("SELECT CASE WHEN EXISTS"):
            self.comparison_count += 1
            differs = set(self.target) != set(self.expected)
            if self.bad_final_comparison and self.comparison_count > 1:
                differs = True
            self.current = [(int(differs),)]
        elif normalized.startswith(f"DELETE FROM {loader.TARGET}"):
            self.target = []
        elif normalized.startswith(f"INSERT INTO {loader.TARGET}"):
            self.target = list(self.expected)
        return self

    def fetchone(self):
        return self.current[0]

    def fetchall(self):
        return self.current

    def do_commit(self):
        if self.commit_error:
            raise RuntimeError("lost during commit")
        self.original = list(self.target)

    def do_rollback(self):
        if self.rollback_error:
            raise RuntimeError("lost during rollback")
        self.target = list(self.original)


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "order_products__train.csv"
        self.path.write_bytes(b"order_id,product_id,add_to_cart_order,reordered\n1,10,1,1\n1,11,2,0\n")
        self.input_spec = dict(dataset_label="instacart_ml_train_labels_v1", file=self.path.name,
                               columns=["order_id", "product_id", "add_to_cart_order", "reordered"],
                               rows=2, size_bytes=self.path.stat().st_size,
                               sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(), full_train_orders=1,
                               subset=dict(dataset_label="instacart_ml_5000_users_v1", selection="lowest_user_ids",
                                           selected_users=2, selected_train_users=1))
        self.spec = dict(dataset_label="instacart_ml_5000_users_v1", source_dataset_label=self.input_spec["dataset_label"],
                         source_sha256=self.input_spec["sha256"], target=loader.TARGET, selected_users=2,
                         selected_train_users=1, label_entries=2, target_orders=1,
                         distinct_products=2, historically_reordered_entries=1)
        self.rows = [(42, 1, 10, 1, 1), (42, 1, 11, 2, 0)]
        self.spec_path = self.root / "load_spec.json"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        self.input_spec_path = self.root / "input_spec.json"
        self.input_spec_path.write_text(json.dumps(self.input_spec), encoding="utf-8")

    def checks(self, cursor, input_spec, report):
        report["checks"] = {"rows": 2, "selected_train_users": 1}
        report["selected_label_observations"] = {key: self.spec[key] for key in loader.OBSERVATIONS}

    def run_load(self, connection, report, simulate_failure=False):
        with patch.object(loader, "read_checks", side_effect=self.checks), patch("builtins.print"):
            loader.run_load(connection, self.path, self.input_spec, self.spec, report, simulate_failure)

    def target_writes(self, connection):
        return [sql for sql, _ in connection.calls
                if sql.strip().startswith((f"DELETE FROM {loader.TARGET}", f"INSERT INTO {loader.TARGET}"))]


class PublicationContractTests(Fixture):
    def test_valid_publication_spec(self):
        self.assertEqual(loader.load_publication_spec(self.spec_path, self.input_spec), self.spec)

    def test_changed_identity_is_rejected(self):
        for key in ("dataset_label", "source_dataset_label", "source_sha256", "target", "selected_users", "selected_train_users"):
            with self.subTest(field=key):
                wrong = dict(self.spec, **{key: "other"})
                self.spec_path.write_text(json.dumps(wrong))
                with self.assertRaises(ValueError):
                    loader.load_publication_spec(self.spec_path, self.input_spec)

    def test_missing_boolean_negative_and_inconsistent_counts_are_rejected(self):
        cases = [dict(self.spec, label_entries=True), dict(self.spec, label_entries=0),
                 dict(self.spec, historically_reordered_entries=-1), dict(self.spec, distinct_products=3),
                 dict(self.spec, historically_reordered_entries=3), dict(self.spec, target_orders=2),
                 {key: value for key, value in self.spec.items() if key != "target_orders"}]
        for wrong in cases:
            with self.subTest(spec=wrong):
                self.spec_path.write_text(json.dumps(wrong))
                with self.assertRaises(ValueError):
                    loader.load_publication_spec(self.spec_path, self.input_spec)

    def test_all_observed_metrics_are_required(self):
        expected = {key: self.spec[key] for key in loader.OBSERVATIONS}
        loader.require_observations(expected, self.spec)
        for key in expected:
            wrong = dict(expected, **{key: expected[key] + 1})
            with self.assertRaises(ValueError):
                loader.require_observations(wrong, self.spec)
            missing = dict(expected)
            del missing[key]
            with self.assertRaises(ValueError):
                loader.require_observations(missing, self.spec)

    def test_arbitrary_metric_source_is_rejected_before_execute(self):
        cursor = Mock()
        with self.assertRaises(ValueError):
            loader.read_metrics(cursor, "pipeline_staging.orders")
        cursor.execute.assert_not_called()


class PublicationTransactionTests(Fixture):
    def test_first_load_commits_exact_selected_rows(self):
        connection, report = TransactionDouble(self.rows, []), {}
        self.run_load(connection, report)
        self.assertEqual(connection.target, self.rows)
        self.assertEqual(report["rows_written"], 2)
        self.assertEqual(report["action"], "REPLACED")
        self.assertEqual(report["transaction_outcome"], "COMMITTED")
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()

    def test_unchanged_rerun_does_not_write_target(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        self.run_load(connection, report)
        self.assertEqual(report["action"], "UNCHANGED")
        self.assertEqual(report["rows_written"], 0)
        self.assertFalse(report["target_write_attempted"])
        self.assertEqual(self.target_writes(connection), [])

    def test_equal_counts_but_changed_user_cart_or_flag_are_replaced(self):
        for changed in ((43, 1, 10, 1, 1), (42, 1, 10, 3, 1), (42, 1, 10, 1, 0)):
            with self.subTest(row=changed):
                connection, report = TransactionDouble(self.rows, [changed, self.rows[1]]), {}
                self.run_load(connection, report)
                self.assertEqual(connection.target, self.rows)
                self.assertEqual(report["action"], "REPLACED")

    def test_extra_target_rows_are_removed_transactionally(self):
        connection, report = TransactionDouble(self.rows, self.rows + [(99, 9, 99, 1, 0)]), {}
        self.run_load(connection, report)
        self.assertEqual(report["target_rows_before"], 3)
        self.assertEqual(connection.target, self.rows)

    def test_source_validation_failure_prevents_target_setup(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        with patch.object(loader, "read_checks", side_effect=ValueError("bad source")), patch("builtins.print"):
            with self.assertRaisesRegex(ValueError, "bad source"):
                loader.run_load(connection, self.path, self.input_spec, self.spec, report)
        self.assertFalse(any("CREATE SCHEMA" in sql for sql, _ in connection.calls))
        self.assertEqual(connection.target, self.rows)
        self.assertEqual(report["transaction_outcome"], "ROLLED_BACK")

    def test_file_change_after_bulk_prevents_publication(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        with patch.object(loader, "check_input", side_effect=ValueError("changed")):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.run_load(connection, report)
        self.assertEqual(self.target_writes(connection), [])
        connection.commit.assert_not_called()

    def test_observation_drift_prevents_target_setup(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        with patch.object(loader, "read_checks") as checks, patch("builtins.print"):
            checks.side_effect = lambda cursor, spec, report: report.update(selected_label_observations={})
            with self.assertRaises(ValueError):
                loader.run_load(connection, self.path, self.input_spec, self.spec, report)
        self.assertFalse(any("CREATE SCHEMA" in sql for sql, _ in connection.calls))

    def test_wrong_expected_table_metrics_prevent_target_setup(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        connection.bad_expected_metrics = True
        with self.assertRaises(ValueError):
            self.run_load(connection, report)
        self.assertFalse(any("CREATE SCHEMA" in sql for sql, _ in connection.calls))

    def test_publication_lock_failure_prevents_target_setup(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        connection.lock_result = -1
        with self.assertRaisesRegex(RuntimeError, "publication lock"):
            self.run_load(connection, report)
        self.assertFalse(any("CREATE SCHEMA" in sql for sql, _ in connection.calls))

    def test_unexpected_existing_schema_or_keys_prevent_target_writes(self):
        for flag in ("bad_columns", "bad_keys"):
            connection, report = TransactionDouble(self.rows, self.rows), {}
            setattr(connection, flag, True)
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.run_load(connection, report)
            self.assertEqual(self.target_writes(connection), [])
            self.assertEqual(connection.target, self.rows)

    def test_final_comparison_failure_restores_preexisting_rows(self):
        original = [(42, 1, 10, 1, 0), self.rows[1]]
        connection, report = TransactionDouble(self.rows, original), {}
        connection.bad_final_comparison = True
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.run_load(connection, report)
        self.assertEqual(connection.target, original)
        self.assertEqual(report["rows_written"], 0)
        self.assertEqual(report["transaction_outcome"], "ROLLED_BACK")

    def test_clear_and_failure_restores_verified_target(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        with self.assertRaises(loader.SimulatedMLLoadFailure):
            self.run_load(connection, report, simulate_failure=True)
        self.assertEqual(connection.target, self.rows)
        self.assertEqual(len(self.target_writes(connection)), 1)
        self.assertEqual(report["transaction_outcome"], "ROLLED_BACK")
        connection.commit.assert_not_called()

    def test_rollback_exercise_refuses_missing_or_different_target(self):
        for original in ([], [(42, 1, 10, 1, 0), self.rows[1]]):
            connection, report = TransactionDouble(self.rows, original), {}
            with self.subTest(rows=original), self.assertRaisesRegex(ValueError, "requires an existing target"):
                self.run_load(connection, report, simulate_failure=True)
            self.assertEqual(self.target_writes(connection), [])
            self.assertEqual(connection.target, original)

    def test_commit_failure_reports_unknown_not_zero_writes(self):
        connection, report = TransactionDouble(self.rows, []), {}
        connection.commit_error = True
        with self.assertRaises(RuntimeError):
            self.run_load(connection, report)
        self.assertEqual(report["transaction_outcome"], "UNKNOWN")
        self.assertIsNone(report["rows_written"])

    def test_rollback_failure_preserves_error_and_unknown_outcome(self):
        connection, report = TransactionDouble(self.rows, self.rows), {}
        connection.rollback_error = True
        with self.assertRaises(loader.SimulatedMLLoadFailure):
            self.run_load(connection, report, simulate_failure=True)
        self.assertEqual(report["transaction_outcome"], "UNKNOWN")
        self.assertEqual(report["rollback_error"], "lost during rollback")
        self.assertIsNone(report["rows_written"])

    def test_plain_temp_scope_all_columns_compared_and_source_tables_read_only(self):
        connection = TransactionDouble(self.rows, [])
        self.run_load(connection, {})
        for sql, parameters in connection.calls:
            if "CREATE TABLE #" in sql:
                self.assertEqual(parameters, ())
            if "EXCEPT" in sql:
                for name in loader.COLUMNS:
                    self.assertIn(f"[{name}]", sql)
            for verb in ("DELETE FROM", "INSERT INTO", "UPDATE", "TRUNCATE TABLE", "DROP TABLE"):
                self.assertNotIn(f"{verb} pipeline_staging", sql)


class PublicationCLITests(Fixture):
    def invoke(self, connection):
        module = types.ModuleType("scripts.db_connection")
        module.get_connection = Mock(return_value=connection)
        argv = ["load_ml_train_labels", "--data-dir", str(self.root), "--input-spec", str(self.input_spec_path),
                "--load-spec", str(self.spec_path)]
        with patch.object(sys, "argv", argv), patch.object(loader, "PROJECT_ROOT", self.root), \
             patch.dict(sys.modules, {"scripts.db_connection": module}), \
             patch.object(loader, "read_checks", side_effect=self.checks), patch("builtins.print"):
            result = loader.main()
        return result, module.get_connection

    def test_bad_file_stops_before_connection_and_saves_failure(self):
        self.path.write_bytes(self.path.read_bytes().replace(b"1,10,1,1", b"1,10,1,0"))
        result, connect = self.invoke(TransactionDouble(self.rows, []))
        self.assertEqual(result, 1)
        connect.assert_not_called()
        report = json.loads(next((self.root / "logs/ml_loading").glob("*.json")).read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["transaction_outcome"], "NOT_STARTED")

    def test_successful_cli_saves_counts_and_source_provenance(self):
        result, _ = self.invoke(TransactionDouble(self.rows, []))
        self.assertEqual(result, 0)
        report = json.loads(next((self.root / "logs/ml_loading").glob("*.json")).read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["source_sha256"], self.input_spec["sha256"])
        self.assertEqual(report["rows_written"], 2)

    def test_report_write_error_returns_nonzero_after_committed_load(self):
        connection = TransactionDouble(self.rows, [])
        # Make the report's parent impossible to create, without changing input fixtures.
        (self.root / "logs").write_text("occupied")
        result, _ = self.invoke(connection)
        self.assertEqual(result, 1)
        connection.commit.assert_called_once()
        self.assertEqual(connection.target, self.rows)


if __name__ == "__main__":
    unittest.main()
