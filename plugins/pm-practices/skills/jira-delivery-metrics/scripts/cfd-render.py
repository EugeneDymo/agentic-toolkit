#!/usr/bin/env python3
"""Render weekly status stocks; do not infer elapsed time from CFD geometry."""
from collections import defaultdict
from metrics_common import arguments, load_config, load_snapshot, plot, read_csv, save


def main():
    args = arguments(__doc__).parse_args()
    config = load_config(args.config)
    load_snapshot(args.run_dir, config)
    rows = read_csv(args.run_dir / "cfd.csv")
    weeks = sorted({r["week_ending"] for r in rows})
    order = ["done", "cancelled", "hold", "qa", "review", "active", "backlog"]
    for metric, label, suffix in (("issue_count", "Tickets", "issues"), ("points_sum", "Current estimated points", "points")):
        for by_assignee in (False, True):
            buckets = defaultdict(lambda: defaultdict(float))
            for row in rows:
                group = row["status"] + (" / " + row["assignee"] if by_assignee else "")
                buckets[group][row["week_ending"]] += float(row[metric])
            groups = sorted(buckets, key=lambda k: (order.index(k.split(" / ")[0]), k))
            fig, ax = plot(config["title"] + " — cumulative flow (weekly status stock)", label)
            if weeks and groups:
                values = [[buckets[g][w] for w in weeks] for g in groups]
                if len(weeks) == 1:
                    bottom = 0
                    for group, series in zip(groups, values):
                        ax.bar(weeks, series, bottom=bottom, label=group)
                        bottom += series[0]
                else:
                    ax.stackplot(weeks, *values, labels=groups)
                ax.legend(loc="upper left", fontsize=7)
            else:
                ax.text(.5, .5, "No completed UTC weeks in scope", transform=ax.transAxes, ha="center")
            ax.set_xlabel("Completed week ending Sunday (UTC)")
            name = f"cfd-{suffix}" + ("" if by_assignee else "-by-status") + ".png"
            save(fig, args.run_dir / name)


if __name__ == "__main__":
    main()
