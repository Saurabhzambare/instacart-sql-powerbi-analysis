import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.export_cloud_subset import (
    EXPORTS, METRIC_NAMES, export_csv, fingerprint, load_spec, materialize_subset,
    validate_metrics, write_export,
)


ROOT = Path(__file__).resolve().parents[1]


def real_spec():
    return load_spec(ROOT / "config/cloud_subset_spec.json")


class SubsetContractTests(unittest.TestCase):
    def test_recorded_preview_counts_are_consistent(self):
        spec = real_spec()
        self.assertEqual(spec["expected_metrics"]["selected_users"], 5000)
        self.assertEqual(spec["expected_metrics"]["prior_product_entries"], 761_750)
        validate_metrics(dict(spec["expected_metrics"]), spec["expected_metrics"])

    def test_inconsistent_or_unsafe_spec_is_rejected(self):
        spec = real_spec()
        cases = [
            {**spec, "dataset_label": "other"},
            {**spec, "selection": {**spec["selection"], "user_limit": 100}},
            {**spec, "expected_metrics": {**spec["expected_metrics"], "total_orders": 1}},
            {**spec, "expected_metrics": {**spec["expected_metrics"], "missing_products": 1}},
            {**spec, "expected_metrics": {**spec["expected_metrics"], "aisles": True}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.json"
            for document in cases:
                with self.subTest(document=document):
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_spec(path)

    def test_any_changed_metric_prevents_acceptance(self):
        expected = real_spec()["expected_metrics"]
        for name, value in expected.items():
            with self.subTest(metric=name), self.assertRaises(ValueError):
                validate_metrics({**expected, name: value + 1}, expected)

    def test_export_headers_match_original_file_contract(self):
        manifest = json.loads((ROOT / "config/input_manifest.json").read_text(encoding="utf-8-sig"))
        expected = {item["name"]: item["columns"] for item in manifest["files"]}
        self.assertEqual({entry[0] for entry in EXPORTS}, set(expected))
        for filename, _, header, _, _ in EXPORTS:
            self.assertEqual(list(header), expected[filename])


class CSVExportTests(unittest.TestCase):
    def make_cursor(self, header, batches):
        cursor = Mock()
        cursor.description = [(name,) for name in header]
        cursor.fetchmany.side_effect = batches
        return cursor

    def test_csv_round_trip_preserves_unicode_quotes_newlines_and_null_gap(self):
        header = ("name", "gap")
        cursor = self.make_cursor(header, [[('Café, "tea"\nblend', None), ("O'Brien", Decimal("0.0"))], []])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            result = export_csv(cursor, path, header, 2)
            with path.open(encoding="utf-8", newline="") as source:
                rows = list(csv.reader(source))
            self.assertEqual(rows, [list(header), ['Café, "tea"\nblend', ""], ["O'Brien", "0.0"]])
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["sha256"], fingerprint(path)["sha256"])

    def test_batches_are_streamed_without_fetchall(self):
        cursor = self.make_cursor(("id",), [[(1,)], [(2,)], []])
        with tempfile.TemporaryDirectory() as directory:
            export_csv(cursor, Path(directory) / "sample.csv", ("id",), 2, batch_size=1)
        cursor.fetchall.assert_not_called()
        self.assertEqual(cursor.fetchmany.call_count, 3)
        self.assertTrue(all(call.args == (1,) for call in cursor.fetchmany.call_args_list))

    def test_header_mismatch_stops_before_file_creation(self):
        cursor = self.make_cursor(("wrong",), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            with self.assertRaises(ValueError):
                export_csv(cursor, path, ("id",), 1)
            self.assertFalse(path.exists())

    def test_wrong_row_count_is_rejected(self):
        cursor = self.make_cursor(("id",), [[(1,)], []])
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            export_csv(cursor, Path(directory) / "sample.csv", ("id",), 2)

    def test_existing_file_is_not_overwritten(self):
        cursor = self.make_cursor(("id",), [[(1,)], []])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            path.write_text("keep me", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_csv(cursor, path, ("id",), 1)
            self.assertEqual(path.read_text(), "keep me")


class SQLCaptureTests(unittest.TestCase):
    def connection(self, values):
        connection = Mock()
        connection.cursor.return_value.fetchone.side_effect = [("InstacartAnalytics", "test"), values]
        return connection

    def test_valid_capture_commits_before_csv_export(self):
        spec = real_spec()
        connection = self.connection(tuple(spec["expected_metrics"][name] for name in METRIC_NAMES))
        report = {}
        materialize_subset(connection, spec, report)
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()
        self.assertTrue(connection.autocommit)
        self.assertEqual(report["capture_status"], "VALIDATED")
        self.assertEqual(report["metrics"], spec["expected_metrics"])

    def test_temp_users_survive_parameterized_batch_scope(self):
        """Model the scope boundary missed by an unrestricted SQL mock.

        This is an offline regression contract, not a SQL Server integration
        test. Temp tables created in parameterized batches do not survive in
        this model; later queries must use a directly created session table.
        """
        spec = real_spec()
        connection = self.connection(tuple(spec["expected_metrics"][name] for name in METRIC_NAMES))
        cursor = connection.cursor.return_value
        session_tables = set()
        bound_limits = []

        def execute_with_scope(sql, *parameters):
            normalized = " ".join(sql.upper().split())
            creates_users = (
                "CREATE TABLE #CLOUD_USERS" in normalized
                or "INTO #CLOUD_USERS" in normalized and normalized.startswith("SELECT")
            )
            if creates_users:
                if not parameters:
                    session_tables.add("#CLOUD_USERS")
            elif "#CLOUD_USERS" in normalized and "#CLOUD_USERS" not in session_tables:
                raise RuntimeError("Invalid object name '#cloud_users'.")
            if parameters:
                self.assertIn("INSERT INTO #CLOUD_USERS", normalized)
                self.assertIn("TOP (?)", normalized)
                bound_limits.append(parameters)
            return cursor

        cursor.execute.side_effect = execute_with_scope
        materialize_subset(connection, spec, {})
        self.assertEqual(bound_limits, [(5000,)])
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()

    def test_failed_capture_rolls_back(self):
        spec = real_spec()
        metrics = {**spec["expected_metrics"], "missing_products": 1}
        connection = self.connection(tuple(metrics[name] for name in METRIC_NAMES))
        with self.assertRaises(ValueError):
            materialize_subset(connection, spec, {})
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_commit_error_does_not_mark_capture_validated(self):
        spec = real_spec()
        connection = self.connection(tuple(spec["expected_metrics"][name] for name in METRIC_NAMES))
        connection.commit.side_effect = RuntimeError("connection lost")
        report = {}
        with self.assertRaises(RuntimeError):
            materialize_subset(connection, spec, report)
        self.assertNotIn("capture_status", report)
        connection.rollback.assert_called_once()


class PublicationTests(unittest.TestCase):
    def report(self):
        return {"run_id": "test-run", "database": "test", "server": "test",
                "metrics": real_spec()["expected_metrics"], "spec_sha256": "a"*64,
                "script_sha256": "b"*64}

    def fake_csv(self, cursor, path, header, expected_rows):
        path.write_text(",".join(header) + "\n", encoding="utf-8")
        return {"file": path.name, "rows": expected_rows, "header": list(header), **fingerprint(path)}

    def test_complete_files_and_manifest_are_published(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "subset"
            report = self.report()
            with patch("scripts.export_cloud_subset.export_csv", side_effect=self.fake_csv), patch("builtins.print"):
                write_export(Mock(), real_spec(), destination, report)
            manifest = json.loads((destination / "_manifest.json").read_text())
            self.assertEqual(manifest["status"], "PASS")
            self.assertEqual(len(manifest["files"]), 5)
            self.assertEqual(set(p.name for p in destination.iterdir()),
                             {entry[0] for entry in EXPORTS} | {"_manifest.json"})

    def test_existing_destination_stops_before_export(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "subset"
            destination.mkdir()
            marker = destination / "existing.txt"
            marker.write_text("keep")
            connection = Mock()
            with self.assertRaises(FileExistsError):
                write_export(connection, real_spec(), destination, self.report())
            self.assertEqual(marker.read_text(), "keep")
            connection.cursor.assert_not_called()

    def test_mid_export_failure_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "subset"
            with patch("scripts.export_cloud_subset.export_csv", side_effect=OSError("disk full")), patch("builtins.print"):
                with self.assertRaises(OSError):
                    write_export(Mock(), real_spec(), destination, self.report())
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_destination_created_during_export_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "subset"
            def competing_export(cursor, path, header, rows):
                destination.mkdir(exist_ok=True)
                (destination / "existing.txt").write_text("keep")
                return self.fake_csv(cursor, path, header, rows)
            with patch("scripts.export_cloud_subset.export_csv", side_effect=competing_export), patch("builtins.print"):
                with self.assertRaises(FileExistsError):
                    write_export(Mock(), real_spec(), destination, self.report())
            self.assertEqual((destination / "existing.txt").read_text(), "keep")

    def test_failed_publication_cleans_only_its_own_new_files(self):
        original_replace = Path.replace
        moves = []
        def fail_second_move(path, target):
            moves.append(path.name)
            if len(moves) == 2:
                raise OSError("publish failed")
            return original_replace(path, target)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "subset"
            with patch("scripts.export_cloud_subset.export_csv", side_effect=self.fake_csv), \
                 patch.object(Path, "replace", fail_second_move), patch("builtins.print"):
                with self.assertRaises(OSError):
                    write_export(Mock(), real_spec(), destination, self.report())
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
