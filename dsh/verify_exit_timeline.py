#!/usr/bin/env python3
"""Extract a read-only remote-session exit/MRC timeline from vehicle logs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TIMESTAMP_RE = re.compile(r"\[(\d{10}\.\d+)\]")
DRIVE_MODE_RE = re.compile(r"drive_mode=(\d+)")
MRC_RESULT_RE = re.compile(r"(?:result|effective_mrc)=(\d+)")
GAP_RE = re.compile(r"gap=(\d+)ms")
CORRELATION_RE = re.compile(r"(?:correlation_id|message_id)=([^\s,]+)")
MRC_FIELD_RES = {
    "pd": re.compile(r"\bpd=(\d+)"),
    "health": re.compile(r"\bhealth=(\d+)"),
    "pd_timeout": re.compile(r"\bpd_timeout=(yes|no)", re.IGNORECASE),
    "hold": re.compile(r"\bhold=(\d+)"),
    "stop": re.compile(r"\bstop=([^\s,)]+)"),
    "stable": re.compile(r"\bstable=(\d+)"),
}


def mrc_label(result: int | None) -> str | None:
    return {
        0: "NORMAL",
        1: "MRC0",
        2: "MRC1",
        3: "MRC2",
    }.get(result)


def classify_line(line: str) -> tuple[str, dict[str, Any]] | None:
    details: dict[str, Any] = {}
    if "[remote-session] release" in line:
        event_type = "release_cleanup"
    elif "onRelease" in line and "received" in line.lower():
        event_type = "on_release"
    elif "onRelease" in line and (
        "drive_mode=0(M)" in line or "drive_mode=0" in line and "cache" in line.lower()
    ):
        event_type = "legacy_release_cleanup"
    elif "onRelease" in line and "onRelease" in line:
        event_type = "on_release"
    elif "onTakeover" in line:
        event_type = "on_takeover"
    elif "driver exit" in line:
        event_type = "bt_others_exit"
    elif "MRC1 triggered" in line:
        event_type = "watchdog_mrc1"
    elif "detecting loss" in line:
        event_type = "watchdog_detecting"
    elif "MRC1 is triggering" in line:
        event_type = "e2e_mrc1"
    elif "[E2eControlV2] MRC active" in line or "effective_mrc=" in line:
        event_type = "e2e_mrc"
    elif "driveMode" in line and "drive_mode=" in line:
        event_type = "drive_mode"
    elif "[MRC] status:" in line or "[MRC] source:" in line:
        event_type = "cloud_mrc_status"
    else:
        return None

    drive_mode = DRIVE_MODE_RE.search(line)
    if drive_mode:
        details["drive_mode"] = int(drive_mode.group(1))
    mrc_result = MRC_RESULT_RE.search(line)
    if mrc_result:
        result = int(mrc_result.group(1))
        details["mrc_result"] = result
        details["mrc_level"] = mrc_label(result)
    for field_name, pattern in MRC_FIELD_RES.items():
        field_match = pattern.search(line)
        if field_match:
            value = field_match.group(1)
            details[field_name] = (
                value.lower() == "yes"
                if field_name == "pd_timeout"
                else int(value)
                if value.isdigit()
                else value
            )
    gap = GAP_RE.search(line)
    if gap:
        details["gap_ms"] = int(gap.group(1))
    correlation = CORRELATION_RE.search(line)
    if correlation:
        details["correlation_id"] = correlation.group(1)
    if "source=onRelease" in line:
        details["release_source"] = "onRelease"
    elif "source=bt_others=1" in line:
        details["release_source"] = "bt_others=1"
    elif "joystick source" in line.lower() and "bt_others" in line:
        details["release_source"] = "bt_others=1"
    return event_type, details


def parse_log(
    path: Path,
    source: str,
    since: float | None,
    until: float | None,
) -> tuple[list[dict[str, Any]], bool]:
    events: list[dict[str, Any]] = []
    session_id_observed = False
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            timestamp_match = TIMESTAMP_RE.search(line)
            if not timestamp_match:
                continue
            timestamp = float(timestamp_match.group(1))
            if since is not None and timestamp < since:
                continue
            if until is not None and timestamp > until:
                continue
            if '"session_id"' in line or '"sessionId"' in line:
                session_id_observed = True
            classified = classify_line(line)
            if not classified:
                continue
            event_type, details = classified
            events.append(
                {
                    "timestamp": timestamp,
                    "source": source,
                    "line": line_number,
                    "event_type": event_type,
                    "details": details,
                }
            )
    return events, session_id_observed


def summarize(events: list[dict[str, Any]], session_id_observed: bool) -> dict[str, Any]:
    exit_events = [
        event
        for event in events
        if event["event_type"] in {"bt_others_exit", "on_release", "release_cleanup"}
    ]
    exit_at = min((event["timestamp"] for event in exit_events), default=None)
    cleanup_events = [
        event
        for event in events
        if event["event_type"] in {"release_cleanup", "legacy_release_cleanup"}
    ]
    mrc1_events = [
        event
        for event in events
        if event["event_type"] in {"watchdog_mrc1", "e2e_mrc1"}
        or (
            event["event_type"] == "e2e_mrc"
            and event["details"].get("mrc_result", 0) >= 2
        )
    ]
    mrc_level_counts: dict[str, int] = {}
    pd_timeout_yes_count = 0
    for event in events:
        if event["event_type"] not in {"e2e_mrc", "e2e_mrc1"}:
            continue
        level = event["details"].get("mrc_level")
        if level:
            mrc_level_counts[level] = mrc_level_counts.get(level, 0) + 1
        if event["details"].get("pd_timeout") is True:
            pd_timeout_yes_count += 1
    post_exit_mrc1 = [
        event for event in mrc1_events if exit_at is not None and event["timestamp"] > exit_at
    ]
    remote_reentry = [
        event
        for event in events
        if exit_at is not None
        and event["timestamp"] > exit_at
        and event["event_type"] == "drive_mode"
        and event["details"].get("drive_mode") == 2
    ]

    if exit_at is None:
        conclusion = "exit_signal_missing"
    elif post_exit_mrc1 and remote_reentry:
        conclusion = "remote_mode_reentered_before_post_exit_mrc1"
    elif post_exit_mrc1 and not cleanup_events:
        conclusion = "exit_seen_without_release_cleanup_before_mrc1"
    elif post_exit_mrc1:
        conclusion = "post_exit_mrc1_requires_cross_log_review"
    elif any(event["event_type"] == "release_cleanup" for event in cleanup_events):
        conclusion = "new_release_path_observed_without_post_exit_mrc1"
    else:
        conclusion = "legacy_release_path_observed_without_post_exit_mrc1"

    gaps = []
    if not session_id_observed:
        gaps.append("no_session_id_observed")
    if not cleanup_events:
        gaps.append("no_release_cleanup_observed")
    return {
        "conclusion": conclusion,
        "exit_at": exit_at,
        "release_cleanup_count": len(cleanup_events),
        "mrc1_count": len(mrc1_events),
        "mrc_level_counts": mrc_level_counts,
        "pd_timeout_yes_count": pd_timeout_yes_count,
        "post_exit_mrc1_count": len(post_exit_mrc1),
        "remote_reentry_count": len(remote_reentry),
        "session_id_observed": session_id_observed,
        "evidence_gaps": gaps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud-driving", type=Path, required=True)
    parser.add_argument("--e2e", type=Path)
    parser.add_argument("--since", type=float)
    parser.add_argument("--until", type=float)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    events, cloud_session_id = parse_log(
        args.cloud_driving, "cloud_driving", args.since, args.until
    )
    e2e_session_id = False
    if args.e2e:
        e2e_events, e2e_session_id = parse_log(args.e2e, "e2e", args.since, args.until)
        events.extend(e2e_events)
    events.sort(key=lambda event: (event["timestamp"], event["source"], event["line"]))
    summary = summarize(events, cloud_session_id or e2e_session_id)
    report = {
        "policy": {
            "read_only": True,
            "e2e_state_machine": "unchanged",
            "watchdog_judgement": "unchanged",
        },
        "window": {"since": args.since, "until": args.until},
        "summary": summary,
        "timeline": events[: max(0, args.limit)],
        "timeline_truncated": len(events) > max(0, args.limit),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(
            f"conclusion={summary['conclusion']} "
            f"exit_at={summary['exit_at']} "
            f"cleanup={summary['release_cleanup_count']} "
            f"mrc1={summary['mrc1_count']} "
            f"post_exit_mrc1={summary['post_exit_mrc1_count']} "
            f"remote_reentry={summary['remote_reentry_count']}"
        )
        for event in report["timeline"]:
            details = " ".join(
                f"{key}={value}" for key, value in event["details"].items()
            )
            print(
                f"{event['timestamp']:.9f} {event['source']}:{event['line']} "
                f"{event['event_type']} {details}".rstrip()
            )
        for gap in summary["evidence_gaps"]:
            print(f"evidence_gap={gap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
