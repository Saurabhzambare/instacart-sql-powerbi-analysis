import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.run_pipeline import build_stages, execute_stage, run_pipeline


class PipelineRunnerTests(unittest.TestCase):
    def test_commands_preserve_dependency_order_and_baseline(self):
        stages = build_stages(Path("input data"), Path("config/baseline.json"))
        self.assertEqual([stage["name"] for stage in stages], [
            "Input baseline", "Load departments", "Load aisles", "Load products",
            "Load orders", "Load order_products_prior", "Validate automation tables",
        ])
        for stage in stages[:-1]:
            self.assertIn(str(Path("config/baseline.json")), stage["command"])
            self.assertIn("input data", stage["command"])
        self.assertEqual(stages[-1]["command"][-1], "scripts.validate_pipeline")

    def run_with(self, outcomes):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run123.json"
            stages = build_stages(Path("inputs"), Path("baseline.json"))
            with patch("scripts.run_pipeline.execute_stage", side_effect=outcomes) as runner, \
                 patch("builtins.print"):
                report = run_pipeline(stages, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved, report)
            return report, runner.call_count

    def test_complete_success_runs_all_stages_and_saves_report(self):
        report, calls = self.run_with([0] * 7)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(calls, 7)
        self.assertTrue(all(stage["status"] == "PASS" for stage in report["stages"]))

    def test_failed_input_prevents_every_loader(self):
        report, calls = self.run_with([1])
        self.assertEqual(calls, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["stopped_at_stage"], "Input baseline")
        self.assertTrue(all(stage["status"] == "NOT_RUN" for stage in report["stages"][1:]))

    def test_failed_loader_retains_prior_success_and_skips_dependents(self):
        report, calls = self.run_with([0, 0, 1])
        self.assertEqual(calls, 3)
        self.assertEqual([stage["status"] for stage in report["stages"]],
                         ["PASS", "PASS", "FAIL", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN"])

    def test_launch_error_is_recorded_and_stops_pipeline(self):
        report, calls = self.run_with([OSError("cannot start child")])
        self.assertEqual(calls, 1)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["stages"][0]["error_type"], "OSError")

    def test_interruption_is_recorded_and_stops_pipeline(self):
        report, calls = self.run_with([0, KeyboardInterrupt()])
        self.assertEqual(calls, 2)
        self.assertEqual(report["status"], "INTERRUPTED")
        self.assertEqual(report["stages"][2]["status"], "NOT_RUN")

    def test_final_validation_failure_makes_pipeline_fail(self):
        report, calls = self.run_with([0] * 6 + [1])
        self.assertEqual(calls, 7)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["stopped_at_stage"], "Validate automation tables")

    def test_report_write_failure_prevents_starting_children(self):
        with patch("scripts.run_pipeline.write_report", side_effect=OSError("disk full")), \
             patch("scripts.run_pipeline.execute_stage") as runner:
            with self.assertRaises(OSError):
                run_pipeline(build_stages(Path("inputs"), Path("baseline")), Path("test.json"))
            runner.assert_not_called()

    def test_later_report_write_failure_stops_before_next_stage(self):
        with patch("scripts.run_pipeline.write_report", side_effect=[None, None, OSError("disk full")]), \
             patch("scripts.run_pipeline.execute_stage", return_value=0) as runner, \
             patch("builtins.print"):
            with self.assertRaises(OSError):
                run_pipeline(build_stages(Path("inputs"), Path("baseline")), Path("test.json"))
            self.assertEqual(runner.call_count, 1)


class StreamingStageTests(unittest.TestCase):
    def test_real_children_stream_output_and_stop_after_nonzero_exit(self):
        stages = [
            {"name": "First", "command": [sys.executable, "-c", "print('first complete')"],
             "status": "NOT_RUN", "exit_code": None},
            {"name": "Second", "command": [sys.executable, "-c", "print('failure detail'); raise SystemExit(1)"],
             "status": "NOT_RUN", "exit_code": None},
            {"name": "Third", "command": [sys.executable, "-c", "raise RuntimeError('must not run')"],
             "status": "NOT_RUN", "exit_code": None},
        ]
        with tempfile.TemporaryDirectory() as directory, patch("builtins.print"):
            report = run_pipeline(stages, Path(directory) / "real-children.json")
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual([stage["status"] for stage in stages], ["PASS", "FAIL", "NOT_RUN"])
        self.assertEqual(stages[1]["exit_code"], 1)
        self.assertIn("first complete", stages[0]["output"])
        self.assertIn("failure detail", stages[1]["output"])

    def test_child_output_and_report_path_are_retained(self):
        process = Mock()
        process.stdout = io.StringIO("Action: UNCHANGED\nReport saved: D:/logs/run.json\n")
        process.wait.return_value = 0
        process.poll.return_value = 0
        stage = {"command": ["python", "-m", "example"]}
        with patch("scripts.run_pipeline.subprocess.Popen", return_value=process) as launcher, \
             patch("builtins.print"):
            self.assertEqual(execute_stage(stage), 0)
        self.assertIn("Action: UNCHANGED", stage["output"])
        self.assertEqual(stage["child_report_paths"], ["D:/logs/run.json"])
        self.assertEqual(launcher.call_args.kwargs["stderr"], subprocess.STDOUT)
        process.terminate.assert_not_called()

    def test_interrupted_child_is_stopped_before_next_stage(self):
        process = Mock()
        process.stdout = Mock()
        process.stdout.__iter__ = Mock(side_effect=KeyboardInterrupt())
        process.poll.return_value = None
        stage = {"command": ["python"]}
        with patch("scripts.run_pipeline.subprocess.Popen", return_value=process):
            with self.assertRaises(KeyboardInterrupt):
                execute_stage(stage)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)


if __name__ == "__main__":
    unittest.main()
