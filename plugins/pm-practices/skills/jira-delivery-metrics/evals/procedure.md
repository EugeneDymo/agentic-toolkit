# Offline validation

Run `PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_metrics.py` from the skill
directory. Standard-library unittest checks replay, complete UTC weeks, zero
weeks, estimates, QA, reopenings, parent overlap, pagination beyond 100 entries,
missing/looping pages, fresh metadata, edit detection, config and redirect
refusal. It also runs all four local stages in normal, empty and one-week cases
and checks that their CSV and PNG outputs exist. Matplotlib 3.9+ is required.

For forward testing, make a private temporary directory. Use `fixture()` from
`scripts/test_metrics.py` to generate synthetic config and normalized snapshot
via `metrics_common.write_json`. Put a copy in `normal/snapshot.json`. For the
second case set the third issue's points to null and write `missing/snapshot.json`.
Everything is invented, including display names and example field IDs.

Give a fresh-context agent only the realistic prompt, runtime skill/resources,
config and corresponding snapshot. Allow offline pipeline execution and report
creation in those private directories; prohibit live calls, installs, source
edits and nested delegation. Do not give it this procedure, expectations,
test_metrics.py or previous outputs. Multiple independent agents are optional;
if one agent runs both cases, disclose the lack of independence between cases.

Read actual CSV/JSON and reports against evals.json. Do not grade by exact prose
or headings. Check the missing estimate changes the conclusion, not just the
file contents. Inspect representative rendered charts for readability. Record
versions, scope, failures and untested paths in results.md; keep generated
reports/PNGs outside Git. Offline mocks do not validate live authentication,
permission completeness, server rate limiting or production-scale performance.
