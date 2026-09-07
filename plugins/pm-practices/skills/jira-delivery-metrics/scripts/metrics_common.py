"""Shared config, snapshot validation and transition replay for the five stages."""
import argparse
import csv
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

GROUPS = ("backlog", "active", "review", "qa", "hold", "done", "cancelled")


def timestamp(value):
    # Jira's compact UTC offset needs normalization on Python 3.9/3.10.
    value = re.sub(r"([+-][0-9]{2})([0-9]{2})$", r"\1:\2", value)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return dt.astimezone(timezone.utc)


def load_config(path):
    config = json.loads(Path(path).read_text())
    url = urlsplit(config["base_url"])
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("base_url must be an HTTPS site origin without credentials")
    for field in ("project_key", "jql", "title"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    points = config["story_points_field"]
    if points is not None and (not isinstance(points, str) or not re.fullmatch(r"customfield_[0-9]+", points)):
        raise ValueError("story_points_field must be a customfield_ ID or null")
    mapping = config["status_mapping"]
    if not mapping or any(not isinstance(k, str) or not k or v not in GROUPS for k, v in mapping.items()):
        raise ValueError(f"Map each status to one of {GROUPS}")
    if not {"active", "done"} <= set(mapping.values()):
        raise ValueError("Map at least one active and one delivered/done status")
    for group, days in config.get("aging_days", {}).items():
        if group not in GROUPS or isinstance(days, bool) or not isinstance(days, (int, float)) or not math.isfinite(days) or days < 0:
            raise ValueError("aging_days must map groups to finite nonnegative days")
    return config


def fingerprint(config):
    # Cosmetic and refinement-only settings do not invalidate fetched evidence.
    fields = ("base_url", "project_key", "jql", "story_points_field")
    return hashlib.sha256(json.dumps({k: config.get(k) for k in fields}, sort_keys=True).encode()).hexdigest()


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path,
                        help="Private run directory outside version control")
    return parser


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def load_snapshot(run_dir, config):
    snapshot = json.loads((run_dir / "snapshot.json").read_text())
    if snapshot.get("complete") is not True or snapshot.get("config_fingerprint") != fingerprint(config):
        raise ValueError("Snapshot incomplete or belongs to another config; fetch a new run")
    if snapshot.get("schema_version") != 1:
        raise ValueError("Unsupported snapshot format")
    as_of = timestamp(snapshot["as_of"])
    seen = set()
    for issue in snapshot["issues"]:
        if issue["key"] in seen:
            raise ValueError("Duplicate issue in snapshot")
        seen.add(issue["key"])
        if timestamp(issue["created"]) > as_of:
            raise ValueError("Issue created after snapshot")
        previous = timestamp(issue["created"])
        for event in issue["events"]:
            when = timestamp(event["at"])
            if not previous <= when <= as_of:
                raise ValueError("Out-of-order or out-of-snapshot history")
            previous = when
        states = [issue["status"]] + [e[side] for e in issue["events"] if e["field"] == "status" for side in ("from", "to")]
        unknown = set(states) - config["status_mapping"].keys()
        if unknown:
            raise ValueError(f"Unmapped statuses: {sorted(unknown, key=str)}")
        for field in ("status", "assignee"):
            events = [e for e in issue["events"] if e["field"] == field]
            for first, second in zip(events, events[1:]):
                if first["to"] != second["from"]:
                    raise ValueError(f"Discontinuous {field} history for {issue['key']}")
            if events and events[-1]["to"] != issue[field]:
                raise ValueError(f"History/metadata mismatch for {issue['key']}")
        points = issue["points"]
        if points is not None and (isinstance(points, bool) or not isinstance(points, (float, int)) or not math.isfinite(points) or points < 0):
            raise ValueError("Invalid points in snapshot")
    return snapshot


def state_at(issue, cutoff):
    state = {field: next((e["from"] for e in issue["events"] if e["field"] == field), issue[field])
             for field in ("status", "assignee")}
    for event in issue["events"]:
        if timestamp(event["at"]) > cutoff:
            break
        state[event["field"]] = event["to"]
    return state


def week_ends(snapshot):
    """Only completed UTC weeks; never label a partial week as complete."""
    if not snapshot["issues"]:
        return []
    earliest = min(timestamp(i["created"]) for i in snapshot["issues"])
    monday = earliest.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=earliest.weekday())
    end = monday + timedelta(days=7) - timedelta(microseconds=1)
    result = []
    while end < timestamp(snapshot["as_of"]):
        result.append(end)
        end += timedelta(days=7)
    return result


def week_key(when):
    year, week, _ = when.isocalendar()
    return f"{year}-W{week:02d}"


def issue_metrics(issue, config, as_of):
    mapping = config["status_mapping"]
    events = [e for e in issue["events"] if e["field"] == "status"]
    initial = events[0]["from"] if events else issue["status"]
    created = timestamp(issue["created"])
    start = created if mapping[initial] == "active" else None
    done = None
    qa_entries = int(mapping[initial] == "qa")
    qa_returns = 0
    entered = created
    attribution_time = None
    for event in events:
        when = timestamp(event["at"])
        before, after = mapping[event["from"]], mapping[event["to"]]
        if before != after:
            entered = when
        if after == "active" and start is None:
            start = when
        if before == "active" and after != "active" and attribution_time is None:
            attribution_time = when
        if after == "done" and before != "done" and done is None:
            done = when
        if after == "qa" and before != "qa":
            qa_entries += 1
        if before == "qa" and after in ("backlog", "active", "review"):
            qa_returns += 1
    # Attribution is a proxy: use the assignee BEFORE a simultaneous review handoff.
    who = None
    if attribution_time:
        who = state_at(issue, attribution_time - timedelta(microseconds=1))["assignee"]
    group = mapping[issue["status"]]
    return {
        "key": issue["key"], "status": group, "assignee": issue["assignee"] or "(unassigned)",
        "dev_assignee": who or "(unknown)", "points": issue["points"],
        "created": issue["created"], "in_progress_entry": start.isoformat() if start else "",
        "done_entry": done.isoformat() if done else "",
        "cycle_days": (done - start).total_seconds() / 86400 if done and start and start <= done else "",
        "lead_days": (done - created).total_seconds() / 86400 if done else "",
        "qa_entries": qa_entries, "qa_returns": qa_returns,
        "days_in_status": (as_of - entered).total_seconds() / 86400,
        "reopened": bool(done and group != "done"),
    }


def distribution(values):
    values = sorted(values)
    return {"n": len(values), "median": median(values) if values else None,
            "p85": values[max(0, math.ceil(len(values) * .85) - 1)] if values else None}


def plot(title, ylabel):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    return fig, ax


def save(fig, path):
    import matplotlib.pyplot as plt
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
