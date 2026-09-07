# One project config

Use a private JSON file, conventionally `jira-project.json` in the user's project
config location. Pass its path explicitly with `--config`; scripts do not search
the filesystem. Ticket refinement may later read the same file when present and
otherwise take arguments. No second metrics config, credential file or plugin
config is required.

Start from [config.example.json](../assets/config.example.json). Its people,
origin, keys and field IDs are invented examples, never working defaults. Ask
for real values or obtain them through already-authorized read-only project
metadata; never guess field IDs from another site.

Required keys:

| Key | Meaning |
| --- | --- |
| `base_url` | Confirmed HTTPS Jira Cloud site origin, no path or credentials |
| `project_key` | Project identity shared with refinement |
| `jql` | Exact historical population; this controls retrieval, not project_key |
| `title` | Chart label for this scope |
| `story_points_field` | Site's custom field ID, or null to disable point metrics |
| `status_mapping` | Every current and historical status name mapped to a group |
| `aging_days` | Optional group-to-calendar-day alert thresholds |

Groups: `backlog` (not started), `active` (development), `review`, `qa`, `hold`,
`done` (the team's delivered boundary), `cancelled` (will not deliver). Multiple
statuses may map to the same group. Map historical renamed statuses as well.
At least active and done must be defined. A move within a group is not an entry,
QA return, delivery or aging reset. Remaining work includes hold; cancelled work
is neither delivered nor remaining. A production-ready state is only done if
the user defines delivery there; do not infer it from its name.

`project_key` does not constrain an arbitrary JQL automatically. Confirm that the
JQL corresponds to the intended project(s), issue types and inclusion of closed
work. Additional refinement-specific keys are ignored by metrics; do not put
credentials in them. Source config, field discovery and custom-field writes are
outside the fetcher's responsibilities.

# Snapshot contract

`snapshot.json` version 1 contains `complete`, `config_fingerprint`, `started_at`,
`as_of`, `jql`, and `issues`. Each issue has key, created/updated timestamps,
status, assignee display name or null, points number or null, issue_type, parent
key or null, and chronologically ordered `events`. An event has `at`, `field`
(status or assignee), `from` and `to` strings/null. This is the fetcher's normalized
format, not a generic Jira search export. Search exports alone lack history.

Fingerprint covers origin, project, JQL and points field. Mapping and thresholds
may change for offline reanalysis; regenerate every downstream stage. Do not
mark partial exports complete manually. No status/assignee events means the
current value has applied since creation only when the full changelog was read.
Unknown statuses, discontinuous histories, invalid estimates and metadata/history
mismatches fail validation. Negative/invalid estimates need a source-data
decision; fractional estimates are preserved and absent estimates remain null.

The fetcher uses standard-library HTTPS Basic authentication with email/API-token
environment variables. Redirects are refused to avoid forwarding credentials to
another origin; errors omit response bodies and credentials. It fetches fresh
data sequentially, with bounded request timeouts, and does not reuse stale closed
issue caches. For very large scopes, performance is a known limitation; measure
before adding bounded concurrency.

API references: [enhanced search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-jql-get)
uses continuation tokens; [issue changelogs](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-changelog-get)
use offset pagination. Live retrieval is separate from offline test confidence.
