#!/usr/bin/env python3
"""Offline behavioral checks. Run directly; uses only temporary synthetic data."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from metrics_common import fingerprint, issue_metrics, load_config, load_snapshot, state_at, timestamp, write_json

SCRIPTS = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


fetch = module("cfd-fetch")
compute = module("cfd-compute")
points = module("cfd-points-metrics")


def fixture():
    config = load_config(SCRIPTS.parent / "assets/config.example.json")

    def event(day, field, before, after):
        return {"at": f"2026-08-{day:02d}T12:00:00Z", "field": field, "from": before, "to": after}

    issues = [{"key": "DEMO-1", "created": "2026-08-03T12:00:00Z", "updated": "2026-08-06T12:00:00Z",
               "status": "Shipped", "assignee": "Reviewer Reed", "points": 2.5, "issue_type": "Task", "parent": None,
               "events": [event(4, "status", "Queued", "Building"), event(5, "status", "Building", "Verification"),
                          event(5, "assignee", "Maker Moss", "Reviewer Reed"), event(6, "status", "Verification", "Shipped")]},
              {"key": "DEMO-2", "created": "2026-08-03T12:00:00Z", "updated": "2026-08-20T12:00:00Z",
               "status": "Shipped", "assignee": "Maker Moss", "points": 3.5, "issue_type": "Task", "parent": None,
               "events": [event(4, "status", "Queued", "Building"), event(10, "status", "Building", "Verification"),
                          event(11, "status", "Verification", "Building"), event(17, "status", "Building", "Verification"),
                          event(20, "status", "Verification", "Shipped")]},
              {"key": "DEMO-3", "created": "2026-08-03T12:00:00Z", "updated": "2026-08-03T12:00:00Z",
               "status": "Paused", "assignee": None, "points": 6, "issue_type": "Task", "parent": None, "events": []}]
    return config, {"schema_version": 1, "complete": True, "config_fingerprint": fingerprint(config),
                    "started_at": "2026-08-24T12:00:00Z", "as_of": "2026-08-24T12:00:00Z",
                    "jql": config["jql"], "issues": issues}


class MetricsTests(unittest.TestCase):
    def test_jira_timestamp_offsets(self):
        self.assertEqual(timestamp("2026-08-03T12:00:00.000+0000"), timestamp("2026-08-03T12:00:00Z"))
        self.assertEqual(timestamp("2026-08-03T05:00:00.000-0700"), timestamp("2026-08-03T12:00:00+00:00"))
        with self.assertRaises(ValueError):
            timestamp("2026-08-03T12:00:00")

    def test_replay_and_same_time_handoff(self):
        config, snapshot = fixture()
        issue = snapshot["issues"][0]
        self.assertEqual(state_at(issue, timestamp("2026-08-04T23:00:00Z")), {"status": "Building", "assignee": "Maker Moss"})
        metric = issue_metrics(issue, config, timestamp(snapshot["as_of"]))
        self.assertEqual(metric["dev_assignee"], "Maker Moss")
        self.assertEqual((metric["cycle_days"], metric["lead_days"]), (2, 3))
        cfd = compute.compute(snapshot, config)
        for week in {r["iso_week"] for r in cfd}:
            self.assertEqual(sum(r["issue_count"] for r in cfd if r["iso_week"] == week), 3)
            self.assertEqual(sum(r["points_sum"] for r in cfd if r["iso_week"] == week), 12)

    def test_zero_weeks_fractional_points_and_forecast(self):
        config, snapshot = fixture()
        rows, _, forecast, metrics = points.throughput(snapshot, config)
        self.assertEqual([r["tickets_done"] for r in rows], [1, 0, 1])
        self.assertEqual(rows[-1]["velocity_3w"], 2)
        self.assertEqual(forecast["weeks_to_clear"], 3)
        self.assertEqual(forecast["clear_date"], "2026-09-14")
        self.assertEqual((metrics[1]["qa_entries"], metrics[1]["qa_returns"]), (2, 1))
        snapshot["as_of"] = "2026-08-23T12:00:00Z"
        rows, _, forecast, _ = points.throughput(snapshot, config)
        self.assertEqual(len(rows), 2)
        self.assertIsNone(forecast["weeks_to_clear"])

    def test_reopened_unknown_and_missing_estimates(self):
        config, snapshot = fixture()
        issue = snapshot["issues"][0]
        issue["status"] = "Building"
        issue["events"].append({"at": "2026-08-21T12:00:00Z", "field": "status", "from": "Shipped", "to": "Building"})
        rows, _, forecast, metrics = points.throughput(snapshot, config)
        self.assertTrue(metrics[0]["reopened"])
        self.assertEqual(sum(r["tickets_done"] for r in rows), 2)
        self.assertEqual(forecast["remaining_points"], 8.5)
        self.assertIsNone(forecast["weeks_to_clear"])
        config, snapshot = fixture()
        snapshot["issues"][2]["points"] = None
        self.assertIsNone(points.throughput(snapshot, config)[2]["clear_date"])
        snapshot["issues"][2]["status"] = "Shipped"
        metric = issue_metrics(snapshot["issues"][2], config, timestamp(snapshot["as_of"]))
        self.assertEqual(metric["done_entry"], "")
        self.assertEqual(metric["lead_days"], "")

    def test_snapshot_validation(self):
        config, snapshot = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_json(path / "snapshot.json", snapshot)
            load_snapshot(path, config)
            for mutation in ("complete", "unmapped", "discontinuous", "fingerprint", "negative"):
                broken = copy.deepcopy(snapshot)
                if mutation == "complete":
                    broken["complete"] = False
                elif mutation == "unmapped":
                    broken["issues"][2]["status"] = "Mystery"
                elif mutation == "discontinuous":
                    broken["issues"][0]["events"][1]["from"] = "Paused"
                elif mutation == "negative":
                    broken["issues"][0]["points"] = -1
                else:
                    broken["config_fingerprint"] = "different"
                write_json(path / "snapshot.json", broken)
                with self.assertRaises(ValueError, msg=mutation):
                    load_snapshot(path, config)

    def test_search_pagination_and_missing_token(self):
        calls = []
        def get(path, params):
            calls.append(dict(params))
            if "nextPageToken" not in params:
                return {"issues": [{"key": "DEMO-1"}], "isLast": False, "nextPageToken": "page2"}
            return {"issues": [{"key": "DEMO-2"}], "isLast": True}
        self.assertEqual(fetch.scope_keys(get, "project = DEMO"), ["DEMO-1", "DEMO-2"])
        self.assertEqual(calls[1]["nextPageToken"], "page2")
        with self.assertRaises(ValueError):
            fetch.scope_keys(lambda *a: {"issues": [], "isLast": False}, "x")
        with self.assertRaises(ValueError):
            fetch.scope_keys(lambda *a: {"issues": [], "nextPageToken": "loop"}, "x")

    def test_changelog_over_100_and_incomplete(self):
        def get(path, params):
            offset = params["startAt"]
            return {"startAt": offset, "total": 101, "isLast": offset == 100,
                    "values": [{"id": str(i)} for i in range(offset, min(101, offset + 100))]}
        self.assertEqual(len(fetch.histories(get, "DEMO-1")), 101)
        with self.assertRaises(ValueError):
            fetch.histories(lambda *a: {"startAt": 0, "total": 2, "isLast": True, "values": [{"id": "1"}]}, "DEMO-1")

    def test_metadata_fetch_and_change_detection(self):
        config, _ = fixture()
        calls = []
        def get(path, params):
            calls.append(path)
            if path.endswith("changelog"):
                return {"startAt": 0, "total": 0, "values": [], "isLast": True}
            return {"fields": {"created": "2026-08-01T12:00:00Z", "updated": "v1",
                    "status": {"name": "Shipped"}, "assignee": None, "issuetype": {"name": "Task"}, "customfield_99999": 2.5}}
        self.assertEqual(fetch.fetch_issue(get, "DEMO-1", config)["points"], 2.5)
        fetch.fetch_issue(get, "DEMO-1", config)
        self.assertEqual(len(calls), 6)  # Closed tickets are fetched again too.
        def changing(path, params):
            result = get(path, params)
            if params.get("fields") == "updated":
                result["fields"]["updated"] = "v2"
            return result
        with self.assertRaises(ValueError):
            fetch.fetch_issue(changing, "DEMO-1", config)

    def test_config_origin_and_redirect(self):
        config, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for origin in ("http://jira.example.invalid", "https://user:token@jira.example.invalid", "https://jira.example.invalid/path"):
                config["base_url"] = origin
                write_json(path, config)
                with self.assertRaises(ValueError):
                    load_config(path)
        with self.assertRaises(ValueError):
            fetch.NoRedirect().redirect_request(None, None, 302, None, None, "https://elsewhere.example.invalid")

    def test_cancelled_aliases_zero_velocity_and_overlap(self):
        config, snapshot = fixture()
        snapshot["issues"][2]["status"] = "Abandoned"
        self.assertEqual(points.throughput(snapshot, config)[2]["remaining_points"], 0)
        config["status_mapping"]["Checking"] = "qa"
        issue = snapshot["issues"][1]
        issue["events"].insert(-1, {"at": "2026-08-18T12:00:00Z", "field": "status", "from": "Verification", "to": "Checking"})
        issue["events"][-1]["from"] = "Checking"
        metric = issue_metrics(issue, config, timestamp(snapshot["as_of"]))
        self.assertEqual((metric["qa_entries"], metric["qa_returns"]), (2, 1))
        snapshot["issues"][1]["parent"] = "DEMO-1"
        self.assertIn("parents and children both in scope", points.throughput(snapshot, config)[2]["unavailable_reasons"])
        snapshot["as_of"] = "2026-09-21T12:00:00Z"
        forecast = points.throughput(snapshot, config)[2]
        self.assertEqual(forecast["velocity_points_per_week"], 0)
        self.assertIsNone(forecast["clear_date"])

    def test_pipeline_normal_empty_and_one_week(self):
        with tempfile.TemporaryDirectory(prefix="delivery-metrics-test-") as directory:
            root = Path(directory)
            env = dict(os.environ, MPLCONFIGDIR=str(root / "mpl"), PYTHONDONTWRITEBYTECODE="1")
            for case in ("normal", "empty", "one-week"):
                config, snapshot = fixture()
                if case == "empty":
                    snapshot["issues"] = []
                elif case == "one-week":
                    snapshot["issues"] = [snapshot["issues"][0]]
                    snapshot["as_of"] = "2026-08-10T12:00:00Z"
                run = root / case
                write_json(root / "config.json", config)
                write_json(run / "snapshot.json", snapshot)
                for script in ("cfd-compute", "cfd-flow-metrics", "cfd-render", "cfd-points-metrics"):
                    result = subprocess.run([sys.executable, str(SCRIPTS / (script + ".py")), "--config", str(root / "config.json"), "--run-dir", str(run)], env=env, text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(list(run.glob("*.png"))), 13)
                self.assertEqual(len(list(run.glob("*.csv"))), 6)


if __name__ == "__main__":
    unittest.main()
