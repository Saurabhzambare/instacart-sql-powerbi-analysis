import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import Mock, patch

from scripts.load_departments import (
    EXPECTED_STATS, SimulatedLoadFailure, bulk_sql, run_load, validate_stats,
)


class DepartmentRulesTests(unittest.TestCase):
    def test_valid_statistics_pass(self):
        validate_stats(dict(EXPECTED_STATS))

    def test_invalid_statistics_fail(self):
        for key, value in (("rows", 20), ("unique_ids", 20), ("missing_ids", 1),
                           ("blank_names", 1), ("invalid_ids", 1)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_stats(dict(EXPECTED_STATS, **{key: value}))

    def test_quote_in_bulk_path_is_escaped(self):
        cases = (
            (
                PureWindowsPath(r"D:\Saurabh's data\departments.csv"),
                r"D:\Saurabh''s data\departments.csv",
            ),
            (
                PurePosixPath("D:/Saurabh's data/departments.csv"),
                "D:/Saurabh''s data/departments.csv",
            ),
        )

        for path, escaped_path in cases:
            with self.subTest(path=str(path)):
                self.assertIn(f"FROM '{escaped_path}'", bulk_sql(path))


class DepartmentTransactionTests(unittest.TestCase):
    def make_connection(self, rows):
        connection = Mock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = rows
        return connection, cursor

    def run_loader(self, connection, report, simulate_failure=False):
        with patch("scripts.load_departments.inspect_file", return_value={"status": "PASS"}):
            run_load(connection, Path("departments.csv"), {}, {}, report, simulate_failure)

    def test_first_load_commits(self):
        connection, cursor = self.make_connection([
            ("InstacartAnalytics", "test"), (21, 21, 0, 0, 0), (0,),
            (1,), (21, 21, 0, 0, 0), (0,),
        ])
        report = {}
        self.run_loader(connection, report)
        self.assertEqual(report["action"], "LOADED")
        self.assertEqual(report["rows_written"], 21)
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        self.assertTrue(any("INSERT INTO pipeline_staging.departments" in call.args[0]
                            for call in cursor.execute.call_args_list))

    def test_unchanged_rerun_does_not_replace_rows(self):
        connection, cursor = self.make_connection([
            ("InstacartAnalytics", "test"), (21, 21, 0, 0, 0), (21,),
            (0,), (21, 21, 0, 0, 0), (0,),
        ])
        report = {}
        self.run_loader(connection, report)
        self.assertEqual(report["action"], "UNCHANGED")
        self.assertEqual(report["rows_written"], 0)
        self.assertFalse(any("DELETE FROM" in call.args[0] or "INSERT INTO" in call.args[0]
                             for call in cursor.execute.call_args_list))
        connection.commit.assert_called_once()

    def test_failure_after_clear_rolls_back(self):
        connection, cursor = self.make_connection([
            ("InstacartAnalytics", "test"), (21, 21, 0, 0, 0), (21,),
            (21, 21, 0, 0, 0), (0,),
        ])
        report = {}
        with self.assertRaises(SimulatedLoadFailure):
            self.run_loader(connection, report, simulate_failure=True)
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        self.assertEqual(report["target_rows_during_failure"], 0)
        self.assertEqual(report["transaction_outcome"], "ROLLED_BACK")

    def test_invalid_input_rows_stop_before_target_delete(self):
        connection, cursor = self.make_connection([
            ("InstacartAnalytics", "test"), (20, 20, 0, 0, 0),
        ])
        with self.assertRaises(ValueError):
            self.run_loader(connection, {})
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        self.assertFalse(any("DELETE FROM" in call.args[0] for call in cursor.execute.call_args_list))

    def test_input_change_after_bulk_stops_before_target_delete(self):
        connection, cursor = self.make_connection([
            ("InstacartAnalytics", "test"), (21, 21, 0, 0, 0),
        ])
        with patch("scripts.load_departments.inspect_file", return_value={"status": "FAIL"}):
            with self.assertRaises(ValueError):
                run_load(connection, Path("departments.csv"), {}, {}, {})
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        self.assertFalse(any("DELETE FROM" in call.args[0] for call in cursor.execute.call_args_list))

    def test_commit_error_is_reported_as_unknown(self):
        connection, _ = self.make_connection([
            ("InstacartAnalytics", "test"), (21, 21, 0, 0, 0), (21,),
            (0,), (21, 21, 0, 0, 0), (0,),
        ])
        connection.commit.side_effect = RuntimeError("connection lost during commit")
        report = {}
        with self.assertRaises(RuntimeError):
            self.run_loader(connection, report)
        self.assertEqual(report["transaction_outcome"], "UNKNOWN")
        connection.rollback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
