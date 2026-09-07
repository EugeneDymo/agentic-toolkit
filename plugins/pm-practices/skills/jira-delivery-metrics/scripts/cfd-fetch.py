#!/usr/bin/env python3
"""Fetch a new, read-only Jira Cloud snapshot; never reuse stale terminal tickets."""
import base64
import json
import math
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from metrics_common import arguments, fingerprint, load_config, load_snapshot, write_json


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Jira redirect refused; verify configured HTTPS origin")


def client(config):
    email, token = os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        raise ValueError("Set JIRA_EMAIL and JIRA_API_TOKEN in the environment")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    opener = build_opener(NoRedirect())

    def get(path, params=None):
        url = config["base_url"].rstrip("/") + "/rest/api/3/" + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
        try:
            with opener.open(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise ValueError(f"Jira HTTP {exc.code}; snapshot aborted, resolve access/rate limit before retry") from None
        except (URLError, json.JSONDecodeError):
            raise ValueError("Jira transport/JSON failure; snapshot aborted") from None
    return get


def scope_keys(get, jql):
    keys, seen_tokens = set(), set()
    params = {"jql": jql, "fields": "key", "maxResults": 100}
    while True:
        page = get("search/jql", params)
        if not isinstance(page.get("issues"), list) or page.get("warningMessages"):
            raise ValueError("Invalid or warning-bearing scope search")
        for issue in page["issues"]:
            key = issue["key"]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-[0-9]+", key):
                raise ValueError("Unexpected issue key")
            keys.add(key)
        token = page.get("nextPageToken")
        if not token:
            if page.get("isLast") is False:
                raise ValueError("Missing search continuation token")
            break
        if token in seen_tokens or page.get("isLast") is True:
            raise ValueError("Inconsistent search pagination")
        seen_tokens.add(token)
        params["nextPageToken"] = token
    return sorted(keys)


def histories(get, key):
    result, seen = [], set()
    offset, expected_total = 0, None
    while True:
        page = get(f"issue/{quote(key)}/changelog", {"startAt": offset, "maxResults": 100})
        values = page.get("values")
        total = page.get("total")
        if (not isinstance(values, list) or not isinstance(total, int) or total < 0
                or page.get("startAt") != offset):
            raise ValueError("Invalid changelog page")
        if expected_total is not None and total != expected_total:
            raise ValueError("Changelog changed while paging; retry a new snapshot")
        expected_total = total
        for value in values:
            if value["id"] in seen:
                raise ValueError("Duplicate changelog history")
            seen.add(value["id"])
            result.append(value)
        offset += len(values)
        if offset == total:
            if page.get("isLast") is False:
                raise ValueError("Inconsistent changelog completion")
            return result
        if not values or offset > total or page.get("isLast") is True:
            raise ValueError("Incomplete changelog")


def fetch_issue(get, key, config):
    field = config.get("story_points_field")
    fields = "status,assignee,created,updated,issuetype,parent" + ("," + field if field else "")
    data = get(f"issue/{quote(key)}", {"fields": fields})["fields"]
    history = histories(get, key)
    # Detect edits during per-issue retrieval instead of mixing old metadata/new history.
    after = get(f"issue/{quote(key)}", {"fields": "updated"})["fields"]["updated"]
    if after != data["updated"]:
        raise ValueError(f"{key} changed during fetch; retry a new run")
    if field and field not in data:
        raise ValueError("Configured points field unavailable; use correct ID or explicitly disable points")
    points = data.get(field) if field else None
    if points is not None and (isinstance(points, bool) or not isinstance(points, (int, float)) or not math.isfinite(points) or points < 0):
        raise ValueError(f"Invalid estimate for {key}; correct data or disable points")
    events = []
    for hist in history:
        for item in hist["items"]:
            if item["field"] in ("status", "assignee"):
                events.append({"at": hist["created"], "field": item["field"],
                               "from": item.get("fromString"), "to": item.get("toString")})
    from metrics_common import timestamp
    events.sort(key=lambda e: timestamp(e["at"]))
    return {"key": key, "created": data["created"], "updated": data["updated"],
            "status": data["status"]["name"],
            "assignee": (data["assignee"] or {}).get("displayName"),
            "points": points, "issue_type": data["issuetype"]["name"],
            "parent": (data.get("parent") or {}).get("key"), "events": events}


def main():
    args = arguments(__doc__).parse_args()
    config = load_config(args.config)
    get = client(config)
    # A failed fetch never replaces a usable snapshot or looks complete downstream.
    args.run_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(args.run_dir, 0o700)
    started = datetime.now(timezone.utc).isoformat()
    keys = scope_keys(get, config["jql"])
    # ponytail: sequential requests; add bounded concurrency only for measured large-scope latency.
    issues = [fetch_issue(get, key, config) for key in keys]
    if scope_keys(get, config["jql"]) != keys:
        raise ValueError("Scope changed during retrieval; retry a new run")
    snapshot = {"schema_version": 1, "complete": True, "config_fingerprint": fingerprint(config),
                "started_at": started, "as_of": datetime.now(timezone.utc).isoformat(),
                "jql": config["jql"], "issues": issues}
    write_json(args.run_dir / "snapshot.json", snapshot)
    try:
        load_snapshot(args.run_dir, config)
    except (ValueError, KeyError, TypeError):
        snapshot["complete"] = False
        write_json(args.run_dir / "snapshot.json", snapshot)
        raise
    print(f"Fetched {len(issues)} visible tickets; snapshot is not a transactional Jira backup")


if __name__ == "__main__":
    main()
