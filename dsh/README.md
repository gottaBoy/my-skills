# DSH Vehicle Cloud Observability Integration Pack

This directory is the repository-level contract for connecting DSH to the
vehicle-cloud observability plane.

The pack is intentionally runtime-neutral. DSH, Cordis, plugins, model
endpoints and deployment versions must be pinned before installation. The
files here define the data contracts, capability boundaries and acceptance
checks; they do not claim that a production DSH service is deployed.

## Capability Coverage

`vehicle-cloud-observability.profile.json` maps every requested DSH capability:

- Model endpoint with version and redaction policy.
- A versioned read-only tool registry for command, media, broker, ZLMediaKit,
  eBPF, vehicle health, topology, deployment, gateway and runbook evidence.
- Supporting topology, deployment, gateway state and runbook tools.
- Skills for command reliability, video QoE, network correlation, vehicle
  diagnostics, change analysis and evidence review.
- Coordinator plus bounded specialist agents.
- Append-only sessions with replay and fork support.
- Alert, post-deploy and periodic scheduler triggers.
- War-room review and human approval.
- A separate signed task handoff to a controlled executor.
- OTel Session Telemetry containing metadata and evidence references only.
- Sandbox, RBAC, audit, time-window and result-size limits.

## Contract Files

| File | Purpose |
|---|---|
| `vehicle-cloud-observability.profile.json` | Capability manifest and runtime wiring |
| `schemas/query-request.schema.json` | Bounded structured query input |
| `schemas/query-response.schema.json` | Query status, freshness, gaps and evidence references |
| `schemas/incident-envelope.schema.json` | DSH incident input |
| `schemas/evidence-envelope.schema.json` | Immutable evidence reference |
| `schemas/action-task.schema.json` | Approved task handoff to executor |
| `schemas/session-event.schema.json` | Append-only session and telemetry event |
| `fixtures/valid/` | Canonical requests, evidence, task and session examples |
| `fixtures/replay/remote-session-scenarios.json` | Read-only remote-session replay timelines |
| `replay_remote_session.py` | Deterministic cloud-session exit/MRC evidence harness |
| `verify_exit_timeline.py` | Read-only cloud/e2e log timeline extractor |
| `validate_contract.py` | Dependency-free schema and cross-file validation |

## Runtime Boundary

DSH may query approved adapters and produce evidence-backed proposals. It must
not call vehicle TCP, MQTT, CAN, ROS 2 control, ZLMediaKit global mutation or
host SSH directly. Any write operation must be converted into an
`action-task` after human approval and submitted to an independent executor.

The business path remains independent:

```text
vehicle/cockpit -> cloud -> broker -> vehicle/media -> browser
                           |
                           +-> observability stores -> DSH read-only analysis
```

If DSH, a model, a plugin, a collector or a data source is unavailable, the
original control, media, alerting and manual operations paths must continue.

## Suggested Rollout

1. Validate the contracts and install no production write capability.
2. Run one read-only incident against recorded command and media evidence.
3. Enable specialist agents with bounded concurrency and reviewer gating.
4. Add Session replay/fork and OTel metadata telemetry.
5. Add approval UI and a staging executor with signed, idempotent tasks.
6. Perform failure, security, replay and rollback tests before any production
   read or controlled-execution rollout.

The runtime status is `unverified` until each step has an evidence reference
from the target DSH/Cordis deployment and its connected data sources.

## Remote Session Replay

The replay harness validates the cloud-side release boundary without ROS,
vehicle TCP, MQTT, CAN, or production writes:

```bash
python3 .github/dsh/replay_remote_session.py --all
python3 .github/dsh/replay_remote_session.py --scenario normal-onrelease --json
python3 .github/dsh/verify_exit_timeline.py \
  --cloud-driving /path/to/ztd_cloud_driving.log \
  --e2e /path/to/e2e_control.log \
  --since 1788954800 --until 1788954860
```

The safe scenarios verify that `onRelease` and `bt_others=1` clear the cloud
session cache, publish at most one R-mode brake frame, and do not create a
post-release joystick MRC1. The `real-joystick-loss` scenario intentionally
keeps the existing watchdog behavior and must still reach MRC1.

The harness also exposes, rather than masks, the two current cross-session
risks: a delayed old-session joystick can re-arm timeout detection, and a
late old-session release can clear a newer session. Use
`--strict-risks` when those known risks should fail a gate. No replay result
changes the e2e state machine or watchdog judgement policy.

## Capability Rules

- The tool registry is canonical. A tool name must not have a second alias in
  the profile or documentation.
- Every query has an authenticated caller, tenant scope, incident, bounded
  time window, structured parameters and a result cursor. Raw shell, SQL,
  PromQL, LogQL and sensitive bodies are not query parameters.
- Evidence is immutable by reference: every item names its claim, correlation
  keys, clock domains, freshness and `sha256` content hash.
- An action task is a handoff, not execution. It carries L2/L3 risk, scope
  binding, preconditions, success/exit criteria, rollback, approval token
  binding, nonce and task hash. The independent executor revalidates all of
  them.
- Session events are append-only and hash chained. Replay and fork operate on
  frozen evidence references and cannot call production write interfaces.
- Scheduler jobs are bounded, persisted and fail closed to `human_queue`.
  Session telemetry exports metadata and evidence references only, with mTLS,
  WAL and explicit drop counters.
