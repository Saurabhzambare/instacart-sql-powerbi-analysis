import tempfile
import unittest
from pathlib import Path

from scripts.check_inputs import inspect_file


class InputChecksTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.data_directory = Path(temporary_directory.name)
        self.specification = {
            "name": "departments.csv",
            "columns": ["department_id", "department"],
        }
        self.path = self.data_directory / "departments.csv"

    def inspect(self):
        return inspect_file(self.data_directory, self.specification)

    def test_valid_input_passes(self):
        self.path.write_text(
            "department_id,department\n1,frozen\n", encoding="utf-8"
        )
        result = self.inspect()
        self.assertEqual(result["status"], "PASS")
        self.assertGreater(result["size_bytes"], 0)
        self.assertEqual(len(result["sha256"]), 64)

    def test_missing_file_fails(self):
        result = self.inspect()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("error", result)

    def test_empty_file_fails(self):
        self.path.write_bytes(b"")
        result = self.inspect()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("empty", result["error"].lower())

    def test_wrong_column_name_fails(self):
        self.path.write_text("department_id,wrong_name\n", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Header mismatch", result["error"])

    def test_wrong_column_order_fails(self):
        self.path.write_text("department,department_id\n", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("Header mismatch", result["error"])

    def test_utf8_bom_is_accepted(self):
        self.path.write_text(
            "department_id,department\n1,frozen\n", encoding="utf-8-sig"
        )
        self.assertEqual(self.inspect()["status"], "PASS")

    def test_same_size_content_change_changes_fingerprint(self):
        self.path.write_text(
            "department_id,department\n1,frozen\n", encoding="utf-8"
        )
        original = self.inspect()
        self.path.write_text(
            "department_id,department\n1,bakery\n", encoding="utf-8"
        )
        changed = self.inspect()

        self.assertEqual(original["status"], "PASS")
        self.assertEqual(changed["status"], "PASS")
        self.assertEqual(original["size_bytes"], changed["size_bytes"])
        self.assertNotEqual(original["sha256"], changed["sha256"])


if __name__ == "__main__":
    unittest.main()
