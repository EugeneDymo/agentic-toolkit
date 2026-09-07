# Validation record — pm-ilb

Date: 2026-09-07. Local environment: Python 3.10.0, matplotlib 3.9.2,
numpy 1.26.4 (installed transitively; no direct numpy dependency in this skill).

## Automated checks

`PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_metrics.py`: 11 tests passed.
Includes all four local stages for normal, empty and one-week snapshots, each
producing 6 CSVs and 13 charts. The test uses temporary synthetic data, not Jira.

Assertions cover weekly exact totals, fractional estimates, a zero-delivery week,
partial-week exclusion, first-delivery/reopen semantics, simultaneous assignee
handoff, QA aliases and returns, cancelled/held scope, parent overlap, missing
estimates, zero velocity, unknown completion dates, snapshot validation,
two-page search, 101 changelog entries, missing/looping pages, refreshed closed
ticket metadata, edit detection, HTTPS-origin validation and redirect refusal.
Jira compact timezone offsets (+0000/-0700) and absent timezone rejection are
regression-tested on Python 3.10, not merely checked against ISO-Z fixtures.

Skill quick_validate passed. JSON syntax, local Markdown links, Python 3.9 AST
syntax and whitespace checks passed. Python 3.9 runtime itself was not available
for execution. No customer origin, keys, names or field IDs are bundled; examples
are invented. Shared plugin metadata remains owned by pm-h8l.

## Forward test

One fresh-context agent (`metrics_forward`) executed both cases sequentially.
It received runtime instructions, config and raw synthetic snapshots, but no
expected answers, test file or prior outputs. The cases are therefore independent
of the implementation discussion, not independent of each other.

Temporary artifacts: `/private/tmp/pm-ilb-eval-kgxmbyif/normal/` and `missing/`.
These paths are ephemeral and the files are not committed. Each report was read
by the main agent and graded against all 9 expectations in evals.json: passed.

- Normal: 1/0/1 weekly deliveries; 2 points/week; cycle median/P85 9/16 days;
  lead 10/17; 1 QA return in 3 entries; held age 21 days. Conditional clearance
  is three weeks from August 24, September 14, not from runtime's current date.
- Missing estimate: same count throughput; one unestimated remaining ticket;
  no clearance date. The report explicitly distinguishes zero known points from
  an empty backlog. Neither report interprets QA entries minus returns as passes
  or assignee attribution as individual productivity.

The main agent visually inspected a status CFD, throughput and unavailable-
forecast chart. A single rolling-velocity observation had no visible marker;
added a contrasting marker, reran the normal points stage and verified the image.
No arithmetic changed. The final timezone-normalization fix was covered by the
automated rerun, not a second independent forward run. A matplotlib version
probe by the agent initially created an automatic temporary cache outside the
designated eval root; subsequent pipeline commands used the designated cache.
No customer data, live calls, installs, Git operations or input edits occurred.

## Scope and untested paths

Live authentication, real Jira permissions, rate limiting, production-scale
performance and concurrent server edits are untested against a live site.
Pagination/edit/error behavior is tested through deterministic function-level
responses, not a fake CLI or live endpoint. HTTPS uses the standard-library
client; credentials never enter subprocess arguments. Read-only fetch is
sequential and always fresh; the old terminal cache optimization is not ported.

The five stage names and core metrics are retained; shared replay/config logic
is in one helper. Deliberate corrections to the drafts include complete
changelog paging, metadata freshness, zero weeks, missing-vs-zero estimates,
fractional points, conservative forecasts and safe credential handling.
Mislabelled flow-efficiency, invalid graphical CFD duration arrows and an
arbitrary employee-concentration alarm are not retained. Definitions and reasons
are documented in references/metrics.md. No additional dependency or configuration
system was introduced; curl/xargs and direct numpy usage are unnecessary.
