#!/usr/bin/env python3
"""Calculate transition-based lead/cycle time, QA returns and current aging."""
from metrics_common import arguments, distribution, issue_metrics, load_config, load_snapshot, plot, save, timestamp, write_csv, write_json


def main():
    args = arguments(__doc__).parse_args()
    config = load_config(args.config)
    snapshot = load_snapshot(args.run_dir, config)
    rows = [issue_metrics(i, config, timestamp(snapshot["as_of"])) for i in snapshot["issues"]]
    columns = ["key", "status", "assignee", "dev_assignee", "points", "created", "in_progress_entry", "done_entry", "cycle_days", "lead_days", "qa_entries", "qa_returns", "days_in_status", "reopened"]
    write_csv(args.run_dir / "cycle-time.csv", columns, rows)
    write_csv(args.run_dir / "qa-returns.csv", ["key", "dev_assignee", "qa_entries", "qa_returns"],
              [{k: r[k] for k in ("key", "dev_assignee", "qa_entries", "qa_returns")} for r in rows])
    aging = [r for r in rows if r["status"] in ("active", "review", "qa", "hold")]
    aging.sort(key=lambda r: -r["days_in_status"])
    write_csv(args.run_dir / "wip-aging.csv", ["key", "status", "assignee", "days_in_status", "alert"],
              [{**{k: r[k] for k in ("key", "status", "assignee", "days_in_status")},
                "alert": r["days_in_status"] > config.get("aging_days", {}).get(r["status"], float("inf"))} for r in aging])
    entries, returns = sum(r["qa_entries"] for r in rows), sum(r["qa_returns"] for r in rows)
    summary = {"as_of": snapshot["as_of"], "tickets": len(rows),
               "cycle_days": distribution([r["cycle_days"] for r in rows if r["cycle_days"] != ""]),
               "lead_days": distribution([r["lead_days"] for r in rows if r["lead_days"] != ""]),
               "qa_entries": entries, "qa_returns": returns, "qa_return_rate": returns / entries if entries else None,
               "unestimated": sum(r["points"] is None for r in rows),
               "reopened_after_first_delivery": sum(r["reopened"] for r in rows),
               "done_without_observed_delivery": [r["key"] for r in rows if r["status"] == "done" and not r["done_entry"]]}
    write_json(args.run_dir / "flow-summary.json", summary)
    fig, ax = plot(config["title"] + " — cycle time to first delivery", "Calendar days")
    completed = [r for r in rows if r["cycle_days"] != ""]
    if completed:
        ax.scatter([timestamp(r["done_entry"]) for r in completed], [r["cycle_days"] for r in completed])
    else:
        ax.text(.5, .5, "No observed cycle durations", transform=ax.transAxes, ha="center")
    save(fig, args.run_dir / "cycle-time.png")
    fig, ax = plot(config["title"] + " — oldest active/parked work", "Calendar days in mapped status")
    ax.barh([r["key"] for r in aging[:20]], [r["days_in_status"] for r in aging[:20]])
    ax.invert_yaxis()
    save(fig, args.run_dir / "wip-aging.png")
    fig, ax = plot(config["title"] + " — QA events (not pass/fail outcomes)", "Events")
    ax.bar(["QA entries", "Backward returns"], [entries, returns])
    save(fig, args.run_dir / "qa-returns.png")
    print(summary)


if __name__ == "__main__":
    main()
