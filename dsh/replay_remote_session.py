#!/usr/bin/env python3
"""Replay remote-session and joystick-source exit behavior offline.

This is a DSH-side evidence harness. It models the cloud-session cache
boundary and the existing joystick-loss policy. It intentionally does not
implement or mutate the e2e state machine or watchdog policy.

The two exit signals are intentionally different:

* onRelease ends the page-level remote session and clears its cache.
* bt_others=1 suppresses the joystick source and publishes a brake-hold frame,
  while keeping the page-level remote session active.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "replay" / "remote-session-scenarios.json"
TIMEOUT_MS = 300
CONSECUTIVE_MRC1_TICKS = 6


@dataclass
class ReplayModel:
    active_session_id: str | None = None
    cached_drive_mode: int = 0
    cloud_mrc: int = 0
    joystick_rx_seen: bool = False
    last_joystick_ms: int | None = None
    joy_state: str = "NORMAL"
    lost_count: int = 0
    brake_frames: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    release_count: int = 0
    joystick_exit_count: int = 0
    joystick_hold_frames: int = 0
    stale_messages_accepted: int = 0
    mrc1_events: list[dict[str, Any]] = field(default_factory=list)
    release_event_indexes: list[int] = field(default_factory=list)
    release_times_ms: list[int] = field(default_factory=list)

    def record(self, at_ms: int, event_type: str, **attributes: Any) -> None:
        self.events.append({"at_ms": at_ms, "event_type": event_type, **attributes})

    def reset_monitor(self) -> None:
        self.joystick_rx_seen = False
        self.last_joystick_ms = None
        self.joy_state = "NORMAL"
        self.lost_count = 0

    def release_remote_session(self, at_ms: int, source: str, requested_session: str | None) -> None:
        previous_mode = self.cached_drive_mode
        previous_session = self.active_session_id
        self.cached_drive_mode = 0
        self.cloud_mrc = 0
        self.reset_monitor()
        if previous_mode == 2:
            self.brake_frames += 1
        self.release_count += 1
        self.release_event_indexes.append(len(self.events))
        self.release_times_ms.append(at_ms)
        self.record(
            at_ms,
            "remote_session_released",
            source=source,
            requested_session=requested_session,
            active_session=previous_session,
            previous_drive_mode=previous_mode,
            e2e_brake_frame="published" if previous_mode == 2 else "not_needed",
        )
        if requested_session and previous_session and requested_session != previous_session:
            self.findings.append(
                {
                    "id": "late-release-clears-new-session",
                    "severity": "medium",
                    "evidence": "release request session differs from active session",
                    "action": "add optional session validation before clearing cloud session state",
                }
            )

    def joystick_source_exit(
        self,
        at_ms: int,
        requested_session: str | None,
        bt_others_source: str,
    ) -> None:
        """Handle bt_others=1 without ending the page-level session."""
        self.cloud_mrc = 0
        self.joy_state = "SUPPRESSED"
        self.lost_count = 0
        self.joystick_exit_count += 1
        self.joystick_hold_frames += 1
        self.record(
            at_ms,
            "joystick_source_exit",
            session_id=requested_session,
            bt_others=1,
            bt_others_source=bt_others_source,
            remote_session="active",
            drive_mode=self.cached_drive_mode,
            e2e_brake_frame="published" if self.cached_drive_mode == 2 else "not_needed",
        )

    def on_tick(self, at_ms: int) -> None:
        if self.cached_drive_mode != 2 or not self.joystick_rx_seen or self.last_joystick_ms is None:
            self.record(at_ms, "watchdog_tick_skipped", reason="session_not_armed_or_no_first_packet")
            return

        if self.joy_state == "SUPPRESSED":
            self.record(at_ms, "watchdog_tick_skipped", reason="joystick_source_exit_suppressed")
            return

        gap_ms = max(0, at_ms - self.last_joystick_ms)
        if gap_ms < TIMEOUT_MS:
            self.joy_state = "NORMAL"
            self.lost_count = 0
            return
        if self.joy_state == "NORMAL":
            self.joy_state = "DETECTING"
            self.lost_count = 1
            self.record(at_ms, "watchdog_detecting", gap_ms=gap_ms)
            return
        if self.joy_state == "DETECTING":
            self.lost_count += 1
            if self.lost_count >= CONSECUTIVE_MRC1_TICKS:
                self.joy_state = "MRC1"
                self.cloud_mrc = 2
                mrc = {
                    "at_ms": at_ms,
                    "event_type": "watchdog_mrc1",
                    "gap_ms": gap_ms,
                    "session_id": self.active_session_id,
                }
                self.mrc1_events.append(mrc)
                self.record(**mrc)

    def apply(self, event: dict[str, Any]) -> None:
        at_ms = int(event["at_ms"])
        event_type = event["type"]
        if event_type == "takeover":
            self.active_session_id = event.get("session_id")
            self.cached_drive_mode = 0
            self.cloud_mrc = 0
            self.reset_monitor()
            self.record(at_ms, "takeover", session_id=self.active_session_id)
            return
        if event_type == "drive_mode":
            mode = int(event["mode"])
            if mode != 2:
                self.cached_drive_mode = mode
                self.cloud_mrc = 0
                self.reset_monitor()
            else:
                if self.cached_drive_mode != 2:
                    self.reset_monitor()
                self.cached_drive_mode = 2
            self.record(at_ms, "drive_mode", mode=mode)
            return
        if event_type == "release":
            self.release_remote_session(at_ms, "onRelease", event.get("session_id"))
            return
        if event_type == "joystick":
            requested_session = event.get("session_id")
            if (
                requested_session
                and self.active_session_id
                and requested_session != self.active_session_id
            ):
                self.stale_messages_accepted += 1
                self.findings.append(
                    {
                        "id": "old-session-message-accepted",
                        "severity": "medium",
                        "evidence": "joystick message session differs from active session",
                        "action": "add session generation or message ownership validation",
                    }
                )
            self.last_joystick_ms = at_ms
            if self.cached_drive_mode != 2:
                self.record(at_ms, "joystick_dropped", reason="not_in_remote_mode")
                return
            self.joystick_rx_seen = True
            joystickdata = event.get("joystickdata")
            if isinstance(joystickdata, dict) and "bt_others" in joystickdata:
                bt_others = int(joystickdata["bt_others"])
                bt_others_source = "joystickdata_nested"
            elif "bt_others" in event:
                bt_others = int(event["bt_others"])
                bt_others_source = "top_level"
            else:
                bt_others = 0
                bt_others_source = "default"
            self.record(
                at_ms,
                "joystick_received",
                session_id=requested_session,
                bt_others=bt_others,
                bt_others_source=bt_others_source,
            )
            if bt_others == 1:
                self.joystick_source_exit(at_ms, requested_session, bt_others_source)
            elif bt_others == 2:
                self.joy_state = "MRC1"
                self.cloud_mrc = 2
                mrc = {
                    "at_ms": at_ms,
                    "event_type": "joystick_mrc1",
                    "gap_ms": 0,
                    "session_id": self.active_session_id,
                }
                self.mrc1_events.append(mrc)
                self.record(**mrc)
            else:
                self.joy_state = "NORMAL"
                self.lost_count = 0
            return
        if event_type == "tick":
            self.on_tick(at_ms)
            return
        raise ValueError(f"unsupported event type: {event_type}")


def load_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        fixture = json.load(stream)
    if fixture.get("policy", {}).get("production_writes") is not False:
        raise ValueError("replay fixture must disable production writes")
    return fixture


def evaluate(scenario: dict[str, Any]) -> dict[str, Any]:
    model = ReplayModel()
    for event in scenario["events"]:
        model.apply(event)

    name = scenario["name"]
    classification = scenario["classification"]
    assertions: list[dict[str, Any]] = []

    def assertion(name_: str, passed: bool, detail: str) -> None:
        assertions.append({"name": name_, "passed": passed, "detail": detail})

    if name in {
        "normal-onrelease",
        "release-vs-timeout",
        "repeated-release",
    }:
        last_release_ms = max(model.release_times_ms, default=-1)
        assertion(
            "release_clears_remote_state",
            model.cached_drive_mode == 0 and model.cloud_mrc == 0 and not model.joystick_rx_seen,
            "drive mode, cloud MRC and joystick monitor are cleared",
        )
        assertion(
            "no_mrc1_after_release",
            not any(
                mrc["at_ms"] > last_release_ms
                for mrc in model.mrc1_events
            ),
            "no post-release watchdog MRC1 event",
        )
    if name == "repeated-release":
        assertion(
            "release_is_idempotent",
            model.release_count == 3 and model.brake_frames == 1,
            "only the first release from R publishes the brake frame",
        )
    if name == "release-vs-timeout":
        assertion(
            "release_clears_prior_mrc",
            model.cloud_mrc == 0 and model.joy_state == "NORMAL",
            "release clears MRC state even when timeout won the race",
        )
    if name == "bt-others-exit":
        assertion(
            "joystick_exit_does_not_release_session",
            model.cached_drive_mode == 2
            and model.release_count == 0
            and model.active_session_id == "s1",
            "bt_others=1 keeps the page-level remote session active",
        )
        assertion(
            "joystick_exit_suppresses_watchdog",
            model.joy_state == "NORMAL"
            and model.joystick_exit_count == 1
            and model.joystick_hold_frames == 1
            and not model.mrc1_events,
            "the source is suppressed until a later bt_others=0 frame resumes it",
        )
        assertion(
            "joystick_exit_allows_resume",
            any(
                event["event_type"] == "joystick_received"
                and event.get("bt_others") == 0
                and event["at_ms"] > 1000
                for event in model.events
            ),
            "a later normal joystick frame remains valid in the same session",
        )
    if name == "real-joystick-loss":
        assertion(
            "watchdog_policy_preserved",
            bool(model.mrc1_events),
            "real active-session joystick loss still reaches MRC1",
        )
    if name == "delayed-old-session-message":
        assertion(
            "known_cross_session_risk_is_exposed",
            model.stale_messages_accepted > 0 and bool(model.mrc1_events),
            "old-session joystick is accepted and can re-arm timeout detection",
        )
    if name == "late-release-clears-new-session":
        assertion(
            "known_late_release_risk_is_exposed",
            model.cached_drive_mode == 0 and any(
                finding["id"] == "late-release-clears-new-session"
                for finding in model.findings
            ),
            "old release request clears the active new session",
        )

    failed = [item for item in assertions if not item["passed"]]
    risk = classification == "known-risk"
    status = "risk" if risk and not failed else ("failed" if failed else "passed")
    return {
        "scenario": name,
        "classification": classification,
        "status": status,
        "policy": {
            "e2e_state_machine": "unchanged",
            "watchdog_judgement": "unchanged",
            "production_writes": False,
        },
        "summary": {
            "final_drive_mode": model.cached_drive_mode,
            "final_cloud_mrc": model.cloud_mrc,
            "final_joy_state": model.joy_state,
            "brake_frames": model.brake_frames,
            "release_count": model.release_count,
            "joystick_exit_count": model.joystick_exit_count,
            "joystick_hold_frames": model.joystick_hold_frames,
            "mrc1_events": len(model.mrc1_events),
            "stale_messages_accepted": model.stale_messages_accepted,
        },
        "assertions": assertions,
        "findings": model.findings,
        "timeline": model.events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--all", action="store_true", help="replay every fixture scenario")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--strict-risks",
        action="store_true",
        help="return non-zero when a known risk is observed",
    )
    args = parser.parse_args()

    fixture = load_fixture(args.fixture)
    selected = set(args.scenarios or [])
    if args.all or not selected:
        scenarios = fixture["scenarios"]
    else:
        scenarios = [scenario for scenario in fixture["scenarios"] if scenario["name"] in selected]
    known_names = {scenario["name"] for scenario in fixture["scenarios"]}
    unknown = selected - known_names
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(sorted(unknown))}")

    reports = [evaluate(scenario) for scenario in scenarios]
    if args.json:
        print(json.dumps(reports, ensure_ascii=True, indent=2))
    else:
        for report in reports:
            print(
                f"{report['status'].upper():6} {report['scenario']}: "
                f"mrc1={report['summary']['mrc1_events']} "
                f"brake_frames={report['summary']['brake_frames']} "
                f"stale_messages={report['summary']['stale_messages_accepted']}"
            )
            for finding in report["findings"]:
                print(f"  risk[{finding['severity']}]: {finding['id']} - {finding['action']}")

    failed = any(report["status"] == "failed" for report in reports)
    risk = any(report["status"] == "risk" for report in reports)
    return 1 if failed or (args.strict_risks and risk) else 0


if __name__ == "__main__":
    raise SystemExit(main())
