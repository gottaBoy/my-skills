#!/usr/bin/env python3
"""Validate the DSH integration pack and its canonical fixtures.

This intentionally uses only the Python standard library. It implements the
Draft 2020-12 keywords used by the repository schemas; it is not a general
purpose JSON Schema implementation.
"""

import datetime as dt
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCHEMA_DIR = ROOT / "schemas"
FIXTURE_DIR = ROOT / "fixtures" / "valid"
INVALID_FIXTURE_DIR = ROOT / "fixtures" / "invalid"
REPLAY_FIXTURE = ROOT / "fixtures" / "replay" / "remote-session-scenarios.json"


class ValidationError(ValueError):
    pass


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _type_matches(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise ValidationError(f"unsupported schema type {expected!r}")


def _resolve_ref(ref, root, registry):
    document, _, fragment = ref.partition("#")
    ref_root = root
    if document:
        ref_root = registry.get(Path(document).name)
        if ref_root is None:
            raise ValidationError(f"unresolved schema reference {ref}")
    target = ref_root
    if fragment:
        for part in fragment.lstrip("/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
    return target, ref_root


def validate(value, schema, *, root, registry, path="$"):
    if "$ref" in schema:
        target, target_root = _resolve_ref(schema["$ref"], root, registry)
        return validate(value, target, root=target_root, registry=registry, path=path)

    if "const" in schema and value != schema["const"]:
        raise ValidationError(f"{path}: expected {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(f"{path}: value {value!r} is not in enum")

    if "allOf" in schema:
        for index, child in enumerate(schema["allOf"]):
            validate(value, child, root=root, registry=registry, path=f"{path}.allOf[{index}]")
    if "anyOf" in schema:
        errors = []
        for child in schema["anyOf"]:
            try:
                validate(value, child, root=root, registry=registry, path=path)
                break
            except ValidationError as error:
                errors.append(str(error))
        else:
            raise ValidationError(f"{path}: anyOf failed: {'; '.join(errors)}")
    if "oneOf" in schema:
        matches = 0
        errors = []
        for child in schema["oneOf"]:
            try:
                validate(value, child, root=root, registry=registry, path=path)
                matches += 1
            except ValidationError as error:
                errors.append(str(error))
        if matches != 1:
            raise ValidationError(f"{path}: oneOf matched {matches} branches: {'; '.join(errors)}")

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, item) for item in types):
            raise ValidationError(f"{path}: expected type {types}, got {type(value).__name__}")

    if isinstance(value, dict):
        for required in schema.get("required", []):
            if required not in value:
                raise ValidationError(f"{path}: missing required property {required!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, child_value in value.items():
            child_path = f"{path}.{key}"
            if key in properties:
                validate(child_value, properties[key], root=root, registry=registry, path=child_path)
            elif additional is False:
                raise ValidationError(f"{child_path}: additional property is not allowed")
            elif isinstance(additional, dict):
                validate(child_value, additional, root=root, registry=registry, path=child_path)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValidationError(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValidationError(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, child_value in enumerate(value):
                validate(child_value, schema["items"], root=root, registry=registry, path=f"{path}[{index}]")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValidationError(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValidationError(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ValidationError(f"{path}: value does not match pattern")
        if schema.get("format") == "date-time":
            try:
                dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValidationError(f"{path}: invalid date-time") from error

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{path}: above maximum {schema['maximum']}")


def validate_no_sensitive_event_body(event):
    forbidden = {"prompt", "model_output", "raw_parameters", "raw_tool_result", "token", "secret", "password"}

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in forbidden:
                    raise ValidationError(f"{path}.{key}: sensitive session body is forbidden")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(event.get("attributes", {}), "$.attributes")


def main() -> int:
    profile = load_json(ROOT / "vehicle-cloud-observability.profile.json")
    schema_names = {
        "query-request.schema.json",
        "query-response.schema.json",
        "incident-envelope.schema.json",
        "evidence-envelope.schema.json",
        "action-task.schema.json",
        "session-event.schema.json",
    }
    schemas = {name: load_json(SCHEMA_DIR / name) for name in schema_names}

    required_capabilities = {
        "model",
        "tools",
        "skills",
        "agents",
        "sessions",
        "scheduler",
        "review_and_approval",
        "controlled_execution",
        "telemetry",
        "sandbox",
        "evidence",
    }
    missing = required_capabilities - profile.keys()
    if missing:
        raise SystemExit(f"missing profile capabilities: {sorted(missing)}")

    for name, document in schemas.items():
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"{name}: unexpected schema dialect")
        if not document.get("$id"):
            raise SystemExit(f"{name}: missing $id")

    registry = profile["tools"].get("registry", [])
    registry_names = [entry.get("name") for entry in registry]
    if len(registry_names) != len(set(registry_names)):
        raise SystemExit("tool registry contains duplicate names")
    if set(registry_names) != set(profile["tools"]["read_only"]):
        raise SystemExit("tool registry and read_only tool list differ")
    if any(entry.get("read_only") is not True for entry in registry):
        raise SystemExit("all registered tools must be read-only")
    known_schema_refs = set(schemas) | {f"schemas/{name}" for name in schemas}
    if any(entry.get("request_schema") not in known_schema_refs for entry in registry):
        raise SystemExit("tool registry references an unknown request schema")
    if any(entry.get("response_schema") not in known_schema_refs for entry in registry):
        raise SystemExit("tool registry references an unknown response schema")

    if profile["tools"]["write"] != []:
        raise SystemExit("profile must start with no direct write tools")
    if profile["controlled_execution"]["dsh_direct_execution"]:
        raise SystemExit("DSH direct execution must remain disabled")
    if profile["scheduler"]["must_not_block_business_path"] is not True:
        raise SystemExit("scheduler business-path isolation is required")
    if profile["scheduler"]["triggers"] != ["alert", "post_deploy", "periodic", "manual"]:
        raise SystemExit("scheduler trigger enum is not canonical")
    if profile["telemetry"]["export_body"]:
        raise SystemExit("session telemetry body export must remain disabled")
    if profile["sandbox"]["linux_capabilities"] != []:
        raise SystemExit("DSH sandbox must start without Linux capabilities")

    fixture_schemas = {
        "query-command.json": "query-request.schema.json",
        "query-media.json": "query-request.schema.json",
        "query-response.json": "query-response.schema.json",
        "incident.json": "incident-envelope.schema.json",
        "evidence.json": "evidence-envelope.schema.json",
        "action-task.json": "action-task.schema.json",
        "session-event.json": "session-event.schema.json",
    }
    for filename, schema_name in fixture_schemas.items():
        fixture = load_json(FIXTURE_DIR / filename)
        try:
            validate(fixture, schemas[schema_name], root=schemas[schema_name], registry=schemas, path="$")
            if schema_name == "session-event.schema.json":
                validate_no_sensitive_event_body(fixture)
        except ValidationError as error:
            raise SystemExit(f"{filename}: {error}") from error

    invalid_fixture_schemas = {
        "query-raw-shell.json": "query-request.schema.json",
        "session-sensitive-body.json": "session-event.schema.json",
    }
    for filename, schema_name in invalid_fixture_schemas.items():
        fixture = load_json(INVALID_FIXTURE_DIR / filename)
        try:
            validate(fixture, schemas[schema_name], root=schemas[schema_name], registry=schemas, path="$")
            if schema_name == "session-event.schema.json":
                validate_no_sensitive_event_body(fixture)
        except ValidationError:
            continue
        raise SystemExit(f"{filename}: invalid fixture unexpectedly passed validation")

    replay = load_json(REPLAY_FIXTURE)
    if replay.get("fixture_version") != "1":
        raise SystemExit("remote-session replay fixture has an unsupported version")
    if replay.get("policy", {}).get("production_writes") is not False:
        raise SystemExit("remote-session replay must disable production writes")
    replay_scenarios = replay.get("scenarios")
    if not isinstance(replay_scenarios, list) or not replay_scenarios:
        raise SystemExit("remote-session replay fixture has no scenarios")
    replay_names = [scenario.get("name") for scenario in replay_scenarios]
    if any(not isinstance(name, str) or not name for name in replay_names):
        raise SystemExit("remote-session replay scenario names must be non-empty strings")
    if len(replay_names) != len(set(replay_names)):
        raise SystemExit("remote-session replay contains duplicate scenario names")
    supported_replay_events = {"takeover", "drive_mode", "release", "joystick", "tick"}
    for scenario in replay_scenarios:
        if scenario.get("classification") not in {"safe", "known-risk"}:
            raise SystemExit(f"{scenario.get('name')}: invalid replay classification")
        events = scenario.get("events")
        if not isinstance(events, list) or not events:
            raise SystemExit(f"{scenario.get('name')}: replay scenario has no events")
        previous_at_ms = -1
        for event in events:
            if event.get("type") not in supported_replay_events:
                raise SystemExit(f"{scenario.get('name')}: unsupported replay event")
            at_ms = event.get("at_ms")
            if not isinstance(at_ms, int) or at_ms < previous_at_ms:
                raise SystemExit(f"{scenario.get('name')}: replay timestamps are not monotonic")
            previous_at_ms = at_ms

    print(
        f"validated DSH contract: {len(schema_names)} schemas, "
        f"{len(required_capabilities)} capability groups, {len(registry_names)} read-only tools, "
        f"{len(fixture_schemas)} valid fixtures, {len(invalid_fixture_schemas)} rejected fixtures, "
        f"{len(replay_scenarios)} replay scenarios"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
