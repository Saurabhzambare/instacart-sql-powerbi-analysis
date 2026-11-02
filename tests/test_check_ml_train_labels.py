import copy
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.check_ml_train_labels import (
    COLUMNS, DATASET_LABEL, bulk_sql, check_input, expected_checks,
    load_spec, main, run_validation, validate_checks,
)


class LabelFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "order_products__train.csv"
        self.path.write_bytes(
            b"order_id,product_id,add_to_cart_order,reordered\n"
            b"1,10,1,1\n1,11,2,0\n"
        )
        self.spec = {
            "dataset_label": DATASET_LABEL,
            "file": self.path.name,
            "columns": COLUMNS.copy(),
            "rows": 2,
            "size_bytes": self.path.stat().st_size,
            "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "full_train_orders": 1,
            "subset": {
                "dataset_label": "instacart_ml_5000_users_v1",
                "selection": "lowest_user_ids",
                "selected_users": 2,
                "selected_train_users": 1,
            },
        }
        self.spec_path = self.root / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec))

    def connection(self, replacement=None):
        rows = [
            ("test_database", "test_server"),
            (2, 0, 1), (0,), (0,), (0,), (0,), (0,),
            (2,), (1, 1), (2, 1, 2, 1),
        ]
        if replacement:
            for index, row in replacement.items():
                rows[index] = row
        connection = Mock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = rows
        return connection, cursor

    def run_check(self, connection, report):
        with patch("builtins.print"):
            run_validation(connection, self.path, self.spec, report)


class LabelInputTests(LabelFixture):
    def test_valid_separate_contract_loads(self):
        self.assertEqual(load_spec(self.spec_path), self.spec)

    def test_invalid_contract_fields_are_rejected(self):
        mutations = [
            ("dataset_label", "original_five_file_baseline"),
            ("file", "../other.csv"),
            ("columns", ["order_id", "product_id", "reordered"]),
            ("rows", True), ("size_bytes", 0), ("full_train_orders", -1),
            ("sha256", "not-a-sha256"),
        ]
        for name, value in mutations:
            with self.subTest(field=name):
                spec = copy.deepcopy(self.spec)
                spec[name] = value
                self.spec_path.write_text(json.dumps(spec))
                with self.assertRaises(ValueError):
                    load_spec(self.spec_path)

    def test_invalid_subset_contract_is_rejected(self):
        for name, value in (("selection", "first_csv_rows"), ("selected_users", True),
                            ("selected_train_users", 3), ("dataset_label", "unknown")):
            with self.subTest(field=name):
                spec = copy.deepcopy(self.spec)
                spec["subset"][name] = value
                self.spec_path.write_text(json.dumps(spec))
                with self.assertRaises(ValueError):
                    load_spec(self.spec_path)

    def test_file_header_size_and_hash_match(self):
        self.assertEqual(check_input(self.path, self.spec)["status"], "PASS")

    def test_same_size_content_change_is_rejected(self):
        self.path.write_bytes(self.path.read_bytes().replace(b"1,10,1,1", b"1,10,1,0"))
        with self.assertRaisesRegex(ValueError, "baseline"):
            check_input(self.path, self.spec)

    def test_three_column_header_is_rejected(self):
        self.path.write_text("order_id,product_id,reordered\n1,10,1\n")
        with self.assertRaisesRegex(ValueError, "Header mismatch"):
            check_input(self.path, self.spec)

    def test_utf8_bom_is_accepted_when_its_bytes_match_contract(self):
        self.path.write_bytes(b"\xef\xbb\xbf" + self.path.read_bytes())
        self.spec.update(size_bytes=self.path.stat().st_size,
                         sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(check_input(self.path, self.spec)["status"], "PASS")

    def test_missing_file_is_rejected(self):
        self.path.unlink()
        with self.assertRaises(ValueError):
            check_input(self.path, self.spec)

    def test_bulk_path_quote_is_escaped(self):
        sql = bulk_sql(Path("D:/Saurabh's data/order_products__train.csv"))
        self.assertIn("Saurabh''s data", sql)
        self.assertIn("BULK INSERT #ml_train_input", sql)

    def test_missing_and_changed_checks_are_rejected(self):
        expected = expected_checks(self.spec)
        validate_checks(expected, self.spec)
        for key in expected:
            with self.subTest(check=key):
                wrong = dict(expected, **{key: expected[key] + 1})
                with self.assertRaises(ValueError):
                    validate_checks(wrong, self.spec)
                missing = dict(expected)
                del missing[key]
                with self.assertRaises(ValueError):
                    validate_checks(missing, self.spec)

    def test_bad_fingerprint_stops_before_database_connection(self):
        self.path.write_bytes(self.path.read_bytes().replace(b"1,10,1,1", b"1,10,1,0"))
        get_connection = Mock()
        module = types.ModuleType("scripts.db_connection")
        module.get_connection = get_connection
        argv = ["check_ml_train_labels", "--data-dir", str(self.root), "--spec", str(self.spec_path)]
        with patch.object(sys, "argv", argv), \
             patch("scripts.check_ml_train_labels.PROJECT_ROOT", self.root), \
             patch.dict(sys.modules, {"scripts.db_connection": module}), \
             patch("builtins.print"):
            self.assertEqual(main(), 1)
        get_connection.assert_not_called()
        report = json.loads(next((self.root / "logs/ml_inputs").glob("*.json")).read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["transaction_outcome"], "NOT_STARTED")
        self.assertFalse(report["permanent_table_writes"])


class LabelSQLValidationTests(LabelFixture):
    def test_valid_capture_commits_and_reports_selected_observations(self):
        connection, _ = self.connection()
        report = {}
        self.run_check(connection, report)
        self.assertEqual(report["checks"], expected_checks(self.spec))
        self.assertEqual(report["selected_label_observations"], {
            "label_entries": 2, "target_orders": 1, "distinct_products": 2,
            "historically_reordered_entries": 1,
        })
        self.assertEqual(report["transaction_outcome"], "COMMITTED")
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()

    def test_invalid_rows_stop_before_key_or_reference_queries(self):
        connection, cursor = self.connection({1: (2, 1, 1)})
        report = {}
        with self.assertRaisesRegex(ValueError, "row count or values"):
            self.run_check(connection, report)
        self.assertFalse(any("duplicate_groups" in c.args[0] for c in cursor.execute.call_args_list))
        self.assertEqual(report["transaction_outcome"], "ROLLED_BACK")
        connection.commit.assert_not_called()

    def test_wrong_row_count_stops_validation(self):
        connection, _ = self.connection({1: (1, 0, 1)})
        with self.assertRaises(ValueError):
            self.run_check(connection, {})
        connection.rollback.assert_called_once()

    def test_duplicate_keys_and_missing_references_prevent_acceptance(self):
        # Pair duplicates, cart-position duplicates, invalid order references,
        # invalid product references, and uncovered train orders are distinct.
        for index in (2, 3, 4, 5, 6):
            with self.subTest(result_index=index):
                connection, cursor = self.connection({index: (1,)})
                with self.assertRaisesRegex(ValueError, "keys, coverage, or references"):
                    self.run_check(connection, {})
                connection.commit.assert_not_called()
                self.assertFalse(any("CREATE TABLE #ml_selected_users" in c.args[0]
                                     for c in cursor.execute.call_args_list))

    def test_wrong_global_train_order_count_is_rejected(self):
        connection, _ = self.connection({1: (2, 0, 2)})
        with self.assertRaises(ValueError):
            self.run_check(connection, {})

    def test_wrong_selected_user_count_is_rejected(self):
        connection, _ = self.connection({7: (1,)})
        with self.assertRaises(ValueError):
            self.run_check(connection, {})

    def test_wrong_selected_train_eligibility_is_rejected(self):
        connection, _ = self.connection({8: (2, 1)})
        with self.assertRaises(ValueError):
            self.run_check(connection, {})

    def test_inconsistent_selected_observations_are_rejected(self):
        for observation in ((0, 1, 1, 0), (2, 0, 2, 1), (2, 1, 3, 1), (2, 1, 2, 3)):
            with self.subTest(observation=observation):
                connection, _ = self.connection({9: observation})
                with self.assertRaisesRegex(ValueError, "observations are inconsistent"):
                    self.run_check(connection, {})

    def test_changed_file_after_bulk_stops_before_sql_checks(self):
        connection, cursor = self.connection()
        with patch("scripts.check_ml_train_labels.check_input", side_effect=ValueError("changed")):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.run_check(connection, {})
        self.assertFalse(any("COUNT_BIG(*)" in c.args[0] for c in cursor.execute.call_args_list))
        connection.rollback.assert_called_once()

    def test_commit_error_is_unknown(self):
        connection, _ = self.connection()
        connection.commit.side_effect = RuntimeError("connection lost")
        report = {}
        with self.assertRaises(RuntimeError):
            self.run_check(connection, report)
        self.assertEqual(report["transaction_outcome"], "UNKNOWN")

    def test_rollback_error_is_preserved(self):
        connection, _ = self.connection({1: (2, 1, 1)})
        connection.rollback.side_effect = RuntimeError("rollback lost")
        report = {}
        with self.assertRaises(ValueError):
            self.run_check(connection, report)
        self.assertEqual(report["transaction_outcome"], "UNKNOWN")
        self.assertEqual(report["rollback_error"], "rollback lost")

    def test_temp_tables_use_plain_session_scope_and_permanent_sources_are_read_only(self):
        connection, cursor = self.connection()
        self.run_check(connection, {})
        sql = "\n".join(c.args[0] for c in cursor.execute.call_args_list)
        self.assertNotIn("CREATE SCHEMA", sql)
        self.assertNotIn("DELETE FROM", sql)
        self.assertNotIn("UPDATE ", sql)
        self.assertNotIn("INSERT INTO pipeline_", sql)
        creates = [c for c in cursor.execute.call_args_list if "CREATE TABLE" in c.args[0]]
        self.assertEqual(len(creates), 2)
        self.assertTrue(all(len(c.args) == 1 for c in creates))
        self.assertIn("ORDER BY user_id", sql)
        self.assertIn("o.eval_set = 'train'", sql)


if __name__ == "__main__":
    unittest.main()
