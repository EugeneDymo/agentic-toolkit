#!/usr/bin/env python3
"""Replay status and assignee histories at completed UTC week ends."""
from collections import defaultdict
from metrics_common import arguments, load_config, load_snapshot, state_at, timestamp, week_ends, week_key, write_csv


def compute(snapshot, config):
    rows = []
    for end in week_ends(snapshot):
        buckets = defaultdict(lambda: {"issue_count": 0, "points_sum": 0, "unestimated_count": 0})
        for issue in snapshot["issues"]:
            if timestamp(issue["created"]) > end:
                continue
            state = state_at(issue, end)
            bucket = buckets[(config["status_mapping"][state["status"]], state["assignee"] or "(unassigned)")]
            bucket["issue_count"] += 1
            bucket["points_sum"] += issue["points"] or 0
            bucket["unestimated_count"] += issue["points"] is None
        for (status, assignee), values in sorted(buckets.items()):
            rows.append({"week_ending": end.date().isoformat(), "iso_week": week_key(end),
                         "status": status, "assignee": assignee, **values})
    return rows


def main():
    args = arguments(__doc__).parse_args()
    config = load_config(args.config)
    snapshot = load_snapshot(args.run_dir, config)
    rows = compute(snapshot, config)
    write_csv(args.run_dir / "cfd.csv", ["week_ending", "iso_week", "status", "assignee", "issue_count", "points_sum", "unestimated_count"], rows)
    print(f"CFD: {len(snapshot['issues'])} tickets, {len(week_ends(snapshot))} completed UTC weeks")


if __name__ == "__main__":
    main()
