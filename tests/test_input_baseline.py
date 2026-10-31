import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_inputs import inspect_file, load_baseline


class InputBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.specification = {
            "name": "departments.csv",
            "columns": ["department_id", "department"],
        }
        self.source = self.directory / "departments.csv"
        self.source.write_text(
            "department_id,department\n1,frozen\n", encoding="utf-8"
        )
        inspected = inspect_file(self.directory, self.specification)
        self.entry = {
            key: inspected[key]
            for key in ("file", "size_bytes", "header", "sha256")
        }
        self.baseline_path = self.directory / "input_baseline.json"
        self.document = {"dataset_label": "test_dataset", "files": [self.entry]}

    def write_baseline(self):
        self.baseline_path.write_text(
            json.dumps(self.document), encoding="utf-8-sig"
        )

    def load(self):
        return load_baseline(
            self.baseline_path, [self.specification], "test_dataset"
        )

    def test_matching_fingerprint_passes(self):
        result = inspect_file(self.directory, self.specification, self.entry)
        self.assertEqual(result["status"], "PASS")

    def test_same_size_changed_content_fails(self):
        self.source.write_text(
            "department_id,department\n1,bakery\n", encoding="utf-8"
        )
        result = inspect_file(self.directory, self.specification, self.entry)
        self.assertEqual(result["size_bytes"], self.entry["size_bytes"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("differs", result["error"])

    def test_incorrect_baseline_size_fails(self):
        altered_entry = dict(self.entry, size_bytes=self.entry["size_bytes"] + 1)
        result = inspect_file(self.directory, self.specification, altered_entry)
        self.assertEqual(result["status"], "FAIL")

    def test_valid_baseline_with_bom_loads(self):
        self.write_baseline()
        self.assertEqual(self.load()["departments.csv"], self.entry)

    def test_missing_baseline_entry_is_rejected(self):
        self.document["files"] = []
        self.write_baseline()
        with self.assertRaisesRegex(ValueError, "filenames"):
            self.load()

    def test_wrong_dataset_is_rejected(self):
        self.document["dataset_label"] = "other_dataset"
        self.write_baseline()
        with self.assertRaisesRegex(ValueError, "dataset label"):
            self.load()

    def test_missing_baseline_file_is_rejected(self):
        with self.assertRaises(OSError):
            self.load()

    def test_invalid_baseline_hash_is_rejected(self):
        self.entry["sha256"] = "invalid"
        self.write_baseline()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.load()


if __name__ == "__main__":
    unittest.main()
