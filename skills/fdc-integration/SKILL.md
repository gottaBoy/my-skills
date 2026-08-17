---
name: fdc-integration
description: Implement, review, test, or troubleshoot ZIOT FDC device integration and the transport-neutral firmware OTA workflow across firmware-component, hc-fdc-protocol, and the Firmware frontend. Use for MQTT/TCP custom protocol OTA, OTA state machines, retries, timeouts, migrations, and production-readiness checks.
---

# FDC Integration

Use this skill for FDC MQTT integration and for the shared ZIOT OTA capability used by MQTT,
TCP, or another custom protocol.

## Read First

- Read [firmware-ota-production-plan.md](references/firmware-ota-production-plan.md) before
  changing the OTA backend, frontend, schema, dispatch flow, or rollout process.
- Read [ota-service-client-state-contract.md](references/ota-service-client-state-contract.md)
  before changing device payloads, status transitions, retry, cancel, progress, or timeout logic.
- Read [华测FDC设备OTA.md](references/华测FDC设备OTA.md) before changing FDC MQTT topics,
  envelope fields, device examples, or the client integration contract.

## Repository Map

```text
zeron-cloud-web/
  src/modules/device-manager-ui/views/device/Firmware
  src/modules/device-manager-ui/api/firmware.ts

jetlinks-community/
  jetlinks-components/firmware-component
  dev/hc-fdc-protocol
  jetlinks-manager/zota-integration

.github/skills/fdc-integration/
  SKILL.md
  references/
```

## Non-Negotiable Architecture

1. `firmware-component` owns firmware metadata, tasks, device snapshots, state, retry, timeout,
   task aggregation, authorization entry points, and database constraints.
2. There is one OTA business path. Do not create an FDC-specific task/history implementation.
3. The protocol-neutral push contract is JetLinks
   `FunctionInvokeMessage(functionId="ota_upgrade")`; the pull contract is
   `RequestFirmwareMessage` and `RequestFirmwareMessageReply`. Both are delivered through
   `DeviceRegistry`.
4. A protocol codec converts those standard messages into its transport messages and converts
   device reports into `EventMessage(event="ota_status")`.
5. MQTT topics, TCP frames, vendor fields, QoS, sessions, and binary framing stay in the protocol
   module. They must not enter task or history services.
6. Product IDs such as `hc_fdc` are adapter configuration and routing values, not fields in the
   generic OTA service contract. Other products and transports must not depend on `hc_fdc`.
7. Every client OTA report must carry `upgradeId`. Do not fall back to device ID correlation.
8. The database `active_key=deviceId` unique constraint is the final guard against concurrent
   upgrades for one device.
9. New task IDs use `TASKyyyyMMddHHmmssSSS-NNN`; new per-attempt upgrade IDs use
   `UPGRADEyyyyMMddHHmmssSSS-NNN`. The three-digit sequence starts at `001` and is unique in one
   service process. Existing IDs remain valid. Add a node segment before production cluster
   deployment.

Do not describe an `OtaProtocolAdapterRegistry` as implemented. It is a possible future
abstraction; the current implementation uses JetLinks device functions and protocol codecs.

## Current OTA V1

Implemented behavior:

- A task is validated, assigned a fixed device snapshot, saved transactionally with device
  histories, and then started.
- `releaseType=all` snapshots all devices in the firmware product.
- `releaseType=part` accepts explicit device IDs and rejects missing or cross-product devices.
- V1 accepts `mode=push` and `mode=pull`.
- `push` means the cloud pushes an upgrade command; the device downloads the file from
  `fwUrl`. It does not mean pushing firmware bytes through MQTT or TCP.
- `pull` means the task remains queued until the device sends a standard
  `RequestFirmwareMessage`; the service atomically claims one matching task and replies with
  `RequestFirmwareMessageReply`.
- Default timeouts are ACK 30 seconds, status 300 seconds, and total execution 3600 seconds.
- Pull queued waiting time is not execution time. Pull response and execution timers begin when
  the device claims the assignment.
- Dispatch uses a database claim from `queued` to `dispatching`.
- Retry creates a new `upgradeId`, increments `attempt`, resets progress and timestamps, and uses
  a conditional database update.
- Queued work and timeout checks recover after service restart.
- Progress is clamped to 0-100 and never decreases.
- Terminal states cannot be overwritten by late events.
- Events are correlated by `upgradeId`, device ID, and any supplied task/history/attempt fields.
- Only queued records can be cancelled in V1.
- Task counts and task status are aggregated from device histories.
- The legacy FDC direct-upgrade endpoint returns HTTP 410.

Canonical device path:

```text
queued -> dispatching -> dispatched -> accepted
       -> preparing -> downloading -> downloaded
       -> verifying -> verified -> installing
       -> rebooting -> post_checking -> success
```

Canonical terminal failures:

```text
dispatch_failed rejected ack_timeout status_timeout execution_timeout
download_failed verify_failed install_failed reboot_failed
post_check_failed failed cancelled
```

See the state contract for allowed skips and state ownership.

## FDC Contract

The generic OTA core does not know `hc_fdc` or MQTT topics. `hc_fdc` is the current FDC product
ID and MQTT topic prefix. The same OTA task and state machine can be used by another MQTT product,
TCP protocol, or vendor protocol through its own codec.

Topics:

```text
up:   hc_fdc/{deviceId}/status/up
      hc_fdc/{deviceId}/data/up
      hc_fdc/{deviceId}/ota/up

down: hc_fdc/{deviceId}/command/down
      hc_fdc/{deviceId}/ota/down
```

Rules:

- MQTT OTA and ordinary commands use QoS 1.
- Treat the topic prefix as `{productId}` in reusable MQTT designs. The FDC adapter expands it to
  `hc_fdc`; a different product must use its own configured product ID.
- `ota_upgrade` goes to `ota/down`; other commands go to `command/down`.
- `ota_check` is decoded as `RequestFirmwareMessage`; `ota_check_reply` encodes
  `RequestFirmwareMessageReply` and also goes to `ota/down`.
- The message envelope contains exactly `deviceId`, `type`, `messageId`, `ts`, and `data`.
- Common envelope, device-status, and OTA fields use camelCase. FDC-specific telemetry fields
  keep their contract names: `bw_up`, `bw_down`, `rtt_ms`, `packet_loss`, and `kl15`.
- The codec does not implicitly convert camelCase and snake_case. Device payloads, protocol
  decoding, and product metadata must use the same exact property ID.
- Downstream OTA data includes `upgradeId`, `taskId`, `historyId`, `firmwareId`, `attempt`,
  target version, URL, size, digest, force flag, and deadline.
- Upstream OTA data is normalized to `ota_status`.
- New messages keep OTA correlation fields in `data`. Legacy root correlation fields are accepted
  only when they do not conflict with `data`.
- The authenticated MQTT device ID is authoritative. Reject a different payload `deviceId`.
- FDC client states are `accepted`, `rejected`, execution stages, `success`, and stage-specific
  failures. Dispatch and timeout states are generated by the service.

## API Surface

```text
POST   /firmware/upgrade/task
POST   /firmware/upgrade/task/{taskId}/_start
POST   /firmware/upgrade/task/{taskId}/_stop
POST   /firmware/upgrade/task/{taskId}/devices/_retry
POST   /firmware/upgrade/task/{taskId}/devices/_cancel
POST   /firmware/upgrade/history/{historyId}/_retry
POST   /firmware/upgrade/history/{historyId}/_cancel
DELETE /firmware/upgrade/history/{historyId}
DELETE /firmware/upgrade/task/{taskId}
```

Batch endpoints receive device IDs. Single-history endpoints receive a history ID.

Do not use these endpoints for the formal OTA workflow:

```text
POST /api/firmware/upload
GET  /api/firmware/list
GET  /api/firmware/download/{productId}/{filename}
POST /api/firmware/ota/upgrade
```

The first three remain legacy file APIs with unresolved production concerns. The final endpoint
is retired and returns 410.

## Change Workflow

1. Read the entity, task service, event handler, timeout scheduler, controller, migrations,
   protocol codec/factory/metadata, frontend API, task form, and task detail.
2. Preserve the single generic task/history model.
3. Define state ownership before adding a state. Client-reported and service-generated states
   must remain separate.
4. Use conditional database updates for claims, retries, events, cancellation, and timeouts.
5. Add tests for aliases, terminal protection, invalid transitions, client-reportable states,
   correlation fields, topic selection, and QoS.
6. Update both reference documents when behavior or rollout requirements change.
7. Run the verification commands below. Do not claim production readiness from compilation alone.

## Verification

```bash
cd /Users/minyi/workspace/autodrive/jetlinks-community
./mvnw -pl jetlinks-components/firmware-component -am test
./mvnw -f dev/hc-fdc-protocol/pom.xml test
./mvnw -pl jetlinks-manager/zota-integration -am -DskipTests compile

cd /Users/minyi/workspace/autodrive/zeron-cloud-web
pnpm build

cd /Users/minyi/workspace/autodrive
python3 /Users/minyi/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .github/skills/fdc-integration
```

Also run `git diff --check` in each Git repository.

## Production Decision

The code is a production-oriented OTA V1 baseline, not an automatic production approval.
Release only after the database migration, HTTPS and short-lived firmware URL controls, firmware
signature policy, gray rollout and dispatch throttling, metrics and alerts, RBAC/data isolation,
capacity testing, and real FDC end-to-end tests pass. The production plan contains the exact gate.
