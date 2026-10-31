import unittest
from unittest.mock import Mock, patch

from scripts.load_departments import EXPECTED_STATS
from scripts.load_table import TABLES, expected_checks, read_source_checks
from scripts.validate_pipeline import validate_tables


class ValidationSourceTests(unittest.TestCase):
    def test_committed_table_is_used_for_values_keys_and_references(self):
        specification = TABLES["products"]
        cursor = Mock()
        cursor.fetchone.side_effect = [(49_688, 0), (0,), (0,), (0,)]
        checks = read_source_checks(cursor, specification, "pipeline_staging.[products]")
        self.assertEqual(checks, expected_checks(specification))
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(len(statements), 4)
        self.assertTrue(all("pipeline_staging.[products]" in sql for sql in statements))
        self.assertTrue(all("#pipeline_input" not in sql for sql in statements))

    def test_default_source_remains_temporary_input(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(134, 0), (0,)]
        self.assertEqual(read_source_checks(cursor, TABLES["aisles"]), expected_checks(TABLES["aisles"]))
        self.assertTrue(all("#pipeline_input" in call.args[0] for call in cursor.execute.call_args_list))

    def test_unapproved_source_is_rejected_before_sql(self):
        for source in ("staging.products", "pipeline_staging.[orders]", "products; DELETE FROM products"):
            cursor = Mock()
            with self.subTest(source=source), self.assertRaises(ValueError):
                read_source_checks(cursor, TABLES["products"], source)
            cursor.execute.assert_not_called()

    def test_bad_values_prevent_later_validation_queries(self):
        cursor = Mock()
        cursor.fetchone.return_value = (134, 1)
        with self.assertRaises(ValueError):
            read_source_checks(cursor, TABLES["aisles"], "pipeline_staging.[aisles]")
        self.assertEqual(cursor.execute.call_count, 1)


class PipelineTableValidationTests(unittest.TestCase):
    def validate_with(self, outcomes=None, department_stats=None):
        connection = Mock()
        connection.cursor.return_value.fetchone.return_value = ("test_database", "test_server")
        report = {}
        results = outcomes or [expected_checks(spec) for spec in TABLES.values()]
        with patch("scripts.validate_pipeline.read_stats", return_value=department_stats or EXPECTED_STATS), \
             patch("scripts.validate_pipeline.read_source_checks", side_effect=results) as reader, \
             patch("builtins.print"):
            status = validate_tables(connection, report)
        return status, report, connection, reader

    def test_all_five_committed_tables_pass_without_writes(self):
        status, report, connection, reader = self.validate_with()
        self.assertEqual(status, "PASS")
        self.assertEqual(len(report["tables"]), 5)
        self.assertEqual(report["database"], "test_database")
        self.assertEqual([call.kwargs["source"] for call in reader.call_args_list],
                         [f"pipeline_staging.[{table}]" for table in TABLES])
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
        self.assertTrue(connection.autocommit)

    def test_failed_department_check_does_not_hide_other_tables(self):
        stats = dict(EXPECTED_STATS, rows=20)
        status, report, _, reader = self.validate_with(department_stats=stats)
        self.assertEqual(status, "FAIL")
        self.assertEqual(report["tables"][0]["status"], "FAIL")
        self.assertEqual(reader.call_count, 4)

    def test_sql_error_is_distinct_from_rule_failure(self):
        outcomes = [RuntimeError("table missing"), ValueError("bad key"),
                    expected_checks(TABLES["orders"]), expected_checks(TABLES["order_products_prior"])]
        status, report, _, _ = self.validate_with(outcomes=outcomes)
        self.assertEqual(status, "ERROR")
        self.assertEqual([item["status"] for item in report["tables"]],
                         ["PASS", "ERROR", "FAIL", "PASS", "PASS"])


if __name__ == "__main__":
    unittest.main()
