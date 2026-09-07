#!/usr/bin/env python3
"""Weekly throughput, rolling velocity and conditional fixed-scope forecast."""
from collections import defaultdict
from datetime import timedelta
from statistics import mean
from metrics_common import arguments, issue_metrics, load_config, load_snapshot, plot, save, timestamp, week_ends, week_key, write_csv, write_json


def throughput(snapshot, config):
    as_of = timestamp(snapshot["as_of"])
    metrics = [issue_metrics(i, config, as_of) for i in snapshot["issues"]]
    # Includes zero-delivery weeks, excludes the current partial UTC week.
    weekly = {week_key(end): {"iso_week": week_key(end), "week_ending": end.date().isoformat(),
              "tickets_done": 0, "points_done": 0, "unestimated_done": 0, "tickets_created": 0,
              "points_created": 0} for end in week_ends(snapshot)}
    by_assignee = defaultdict(lambda: {"tickets_done": 0, "points_done": 0})
    for row in metrics:
        created_week = week_key(timestamp(row["created"]))
        if created_week in weekly:
            weekly[created_week]["tickets_created"] += 1
            weekly[created_week]["points_created"] += row["points"] or 0
        if not row["done_entry"]:
            continue
        week = week_key(timestamp(row["done_entry"]))
        if week not in weekly:
            continue
        weekly[week]["tickets_done"] += 1
        weekly[week]["points_done"] += row["points"] or 0
        weekly[week]["unestimated_done"] += row["points"] is None
        by_assignee[(week, row["dev_assignee"])]["tickets_done"] += 1
        by_assignee[(week, row["dev_assignee"])]["points_done"] += row["points"] or 0
    rows = list(weekly.values())
    for i, row in enumerate(rows):
        row["velocity_3w"] = mean(r["points_done"] for r in rows[i-2:i+1]) if i >= 2 else ""
    remaining = [r for r in metrics if r["status"] not in ("done", "cancelled")]
    points = sum(r["points"] or 0 for r in remaining)
    velocity = rows[-1]["velocity_3w"] if rows else ""
    missing = sum(r["points"] is None for r in remaining)
    unknown_done = any(r["status"] == "done" and not r["done_entry"] for r in metrics)
    overlap = {i["key"] for i in snapshot["issues"]} & {i.get("parent") for i in snapshot["issues"]}
    reasons = []
    if missing or any(r["unestimated_done"] for r in rows[-3:]):
        reasons.append("unestimated remaining/recently delivered work")
    if unknown_done:
        reasons.append("done tickets without observed delivery dates")
    if overlap:
        reasons.append("parents and children both in scope")
    if any(r["reopened"] for r in metrics):
        reasons.append("reopened work makes first-delivery velocity unsuitable for clearance")
    if velocity == "" or velocity <= 0:
        reasons.append("fewer than three complete weeks or zero recent velocity")
    forecast = {"as_of": snapshot["as_of"], "remaining_tickets": len(remaining),
                "remaining_points": points, "unestimated_remaining": missing,
                "velocity_points_per_week": velocity if velocity != "" else None,
                "weeks_to_clear": None, "clear_date": None, "unavailable_reasons": reasons}
    if not reasons:
        forecast["weeks_to_clear"] = points / velocity
        forecast["clear_date"] = (as_of + timedelta(weeks=points / velocity)).date().isoformat()
    attribution = [{"iso_week": week, "assignee": who, **values} for (week, who), values in sorted(by_assignee.items())]
    return rows, attribution, forecast, metrics


def main():
    args = arguments(__doc__).parse_args()
    config = load_config(args.config)
    snapshot = load_snapshot(args.run_dir, config)
    rows, attribution, forecast, metrics = throughput(snapshot, config)
    write_csv(args.run_dir / "throughput.csv", ["iso_week", "week_ending", "tickets_done", "points_done", "unestimated_done", "tickets_created", "points_created", "velocity_3w"], rows)
    write_csv(args.run_dir / "throughput-by-assignee.csv", ["iso_week", "assignee", "tickets_done", "points_done"], attribution)
    write_json(args.run_dir / "forecast.json", forecast)
    weeks = [r["iso_week"] for r in rows]
    fig, ax = plot(config["title"] + " — weekly delivery", "Current estimated points")
    ax.bar(weeks, [r["points_done"] for r in rows], label="Points delivered")
    if len(rows) >= 3:
        ax.plot(weeks[2:], [r["velocity_3w"] for r in rows[2:]], color="black", marker="o", label="3 complete week mean")
    right = ax.twinx()
    right.plot(weeks, [r["tickets_done"] for r in rows], color="tab:orange", label="Tickets")
    right.set_ylabel("Tickets delivered")
    ax.legend(loc="upper left")
    right.legend(loc="upper right")
    save(fig, args.run_dir / "throughput.png")
    for field, suffix in (("points_done", ""), ("tickets_done", "-tickets")):
        fig, ax = plot(config["title"] + " — assignee before first active exit (proxy)", field)
        bottom = [0] * len(weeks)
        for who in sorted({r["assignee"] for r in attribution}):
            series = [sum(r[field] for r in attribution if r["assignee"] == who and r["iso_week"] == week) for week in weeks]
            ax.bar(weeks, series, bottom=bottom, label=who)
            bottom = [a + b for a, b in zip(bottom, series)]
        if attribution:
            ax.legend(fontsize=7)
        save(fig, args.run_dir / f"throughput-by-assignee{suffix}.png")
    fig, ax = plot(config["title"] + " — created vs first delivered (current scope)", "Tickets per complete week")
    ax.plot(weeks, [r["tickets_created"] for r in rows], label="Created")
    ax.plot(weeks, [r["tickets_done"] for r in rows], label="First delivery")
    ax.legend()
    save(fig, args.run_dir / "arrival-vs-delivery.png")
    fig, ax = plot(config["title"] + " — cycle time by current estimate", "Calendar days")
    buckets = defaultdict(list)
    for row in metrics:
        if row["cycle_days"] != "":
            label = "unestimated" if row["points"] is None else str(row["points"])
            buckets[label].append(row["cycle_days"])
    if buckets:
        ax.boxplot(list(buckets.values()), tick_labels=list(buckets), showmeans=True)
    else:
        ax.text(.5, .5, "No observed cycle durations", transform=ax.transAxes, ha="center")
    save(fig, args.run_dir / "cycle-by-points.png")
    fig, ax = plot(config["title"] + " — fixed-scope clearance scenario", "Remaining estimated points")
    if forecast["weeks_to_clear"] is not None:
        ax.plot([0, forecast["weeks_to_clear"]], [forecast["remaining_points"], 0])
        ax.set_xlabel("Weeks from snapshot; assumes stable velocity and no new scope")
    else:
        ax.text(.5, .5, "Forecast unavailable:\n" + "\n".join(forecast["unavailable_reasons"]), transform=ax.transAxes, ha="center", va="center", fontsize=9)
    save(fig, args.run_dir / "forecast.png")
    print(forecast)


if __name__ == "__main__":
    main()
