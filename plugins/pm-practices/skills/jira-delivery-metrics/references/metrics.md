# Definitions and interpretation

These are Jira-transition metrics, not merge/deploy metrics, working hours or
individual productivity measures. Workflow boundaries must be agreed with the
team. Calendar durations include nights, weekends, queues and blocked time.

- **CFD:** historical weekly stock of the currently selected issues in each
  mapped group, optionally split by historical assignee. Reopening reduces the
  done stock. Cancelled/held work stays visibly separate. Points use today's
  estimate retroactively, not estimate-history replay. Only complete UTC weeks
  are plotted; current backlog/aging still comes from the snapshot time.
- **Lead time:** creation to first observed entry into done. A ticket initially
  created in done has an unknown delivery time, not a fabricated zero-day lead.
- **Cycle time:** first active entry (or creation if initially active) to first
  observed done entry. Subsequent reopen/redelivery cycles do not produce another
  delivery. Reopened tickets remain in historical samples, are flagged, and are
  included in current remaining work. Zero durations are valid; unavailable
  durations are excluded and sample counts shown. Median uses the ordinary
  statistical median; P85 is nearest-rank (ceiling of 0.85 × sample size).
- **QA return rate:** backward transitions from qa to backlog/active/review
  divided by entries into qa, including an initial qa state. Transitions within
  qa do not count twice. No entries means unavailable. Entries minus returns
  does NOT mean passed QA: some are still there or moved elsewhere.
- **Aging:** snapshot time minus entry into the current mapped group for active,
  review, qa and hold. A same-group rename does not reset age. Thresholds are
  team-configured signals, not universal readiness gates. Example thresholds
  (7/3/3/30 days) are inherited illustrative values, not industry benchmarks.
- **Throughput:** first observed deliveries per complete UTC week, including
  every zero-delivery week since scope creation. Current partial week excluded.
- **Velocity:** mean of estimated points delivered in the last three complete
  consecutive UTC weeks. Fewer than three weeks means unavailable. Null estimates
  add no points but count as tickets and unestimated; explicit zero differs from
  unestimated. Fractional points are not truncated. Values cannot be compared
  meaningfully between teams with different estimation scales.
- **Arrival vs delivery:** creation events versus first-delivery events among
  today's scope. This is not the history of sprint/milestone membership changes.
- **Attribution:** assignee immediately before the first exit from active; a
  simultaneous reviewer reassignment therefore does not credit the reviewer.
  Unknown stays unknown: the transition author is not proof of who did the work.
  Display-name collisions/renames and collaborative work limit this proxy. Do not
  infer a person's capability, effort or performance from these charts.
- **Forecast:** current remaining points (including held work) divided by recent
  velocity, projected from snapshot time. A frozen-scope, constant-rate scenario,
  not a probability or commitment. Suppressed with unestimated remaining/recent
  deliveries, unknown completion dates, parent/child overlap, reopened work,
  insufficient weeks or zero recent velocity. Count throughput remains available.

## Limitations to carry into reports

1. Permission-visible, current JQL population only. Deleted/inaccessible issues
   and earlier removed scope cannot be reconstructed. Retrieval is not atomic:
   per-issue checks and a second scope check reduce but cannot eliminate drift.
2. Current point values rewrite historical totals. Missing points and concurrent
   parent/child selection distort point comparisons; no rollup or point imputation.
3. First-delivery counts differ from current done stock after reopening. Delivery
   may lag or lead release; do not substitute merge dates silently.
4. All local calculations use the snapshot timestamp; stale snapshots produce
   stale aging/forecast. UTC weeks may differ from the team's reporting timezone.
5. Small samples, holiday weeks, scope changes and workflow changes limit trends.
   Interpret alert thresholds with project context, not generic healthy ranges.

The draft's `cycle / lead` plot was labelled flow efficiency, but elapsed cycle
time includes queues and is not active effort. It is intentionally not carried
forward. CFD graphical lead/cycle arrows are also omitted: cancelled/held work
and non-monotonic reopened stocks invalidate that geometry. Use observed
per-ticket durations instead. No employee concentration alarm is inferred from
an arbitrary percentage of estimated points.
