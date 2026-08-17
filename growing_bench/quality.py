from __future__ import annotations

from typing import Any


COMMON_EVENT_CONTRACT = (
    "command_start",
    "command_result",
    "file_read",
    "file_write",
    "tool_call",
    "tool_result",
    "assistant_message",
    "duration",
    "exit_status",
)


ADAPTER_CAPABILITIES: dict[str, dict[str, str]] = {
    "codex": {
        "command_start": "native",
        "command_result": "native",
        "file_read": "not_exposed",
        "file_write": "native",
        "tool_call": "native",
        "tool_result": "partial",
        "assistant_message": "native",
        "duration": "derived_from_native_timestamps",
        "exit_status": "native",
    },
    "claude-code": {
        "command_start": "native",
        "command_result": "native_when_tool_result_is_exposed",
        "file_read": "native",
        "file_write": "native_when_tool_result_is_exposed",
        "tool_call": "native",
        "tool_result": "native_when_tool_result_is_exposed",
        "assistant_message": "native",
        "duration": "derived_when_tool_result_is_exposed",
        "exit_status": "native_when_tool_result_is_exposed",
    },
    "openclaw": {name: "declared_by_adapter" for name in COMMON_EVENT_CONTRACT},
    "command": {name: "declared_by_adapter" for name in COMMON_EVENT_CONTRACT},
}


MOJIBAKE_MARKERS = ("\ufffd", "��")


def find_mojibake(text: str) -> list[str]:
    return [marker for marker in MOJIBAKE_MARKERS if marker in text]


def adapter_capabilities(adapter: str) -> dict[str, str]:
    return dict(ADAPTER_CAPABILITIES.get(adapter, {name: "unknown" for name in COMMON_EVENT_CONTRACT}))


ISOLATION_MODES = {"copy", "agent-native"}


def validate_isolation(adapter: str, requested: str) -> None:
    if requested not in ISOLATION_MODES:
        raise ValueError(f"unknown isolation mode {requested!r}; choose from {sorted(ISOLATION_MODES)}")
    if requested == "agent-native" and adapter != "codex":
        raise ValueError(f"agent-native isolation is currently supported only by the Codex adapter, not {adapter}")


def isolation_profile(adapter: str, requested: str = "copy") -> dict[str, Any]:
    """Describe controls the runner actually applies, without implying a container sandbox."""

    validate_isolation(adapter, requested)
    return {
        "requested_mode": requested,
        "workspace_copy": "fresh fixture copy created by Growing Bench",
        "process_cwd": "agent process starts in the disposable workspace",
        "agent_native_sandbox": "workspace-write" if adapter == "codex" else "adapter_managed_or_none",
        "agent_native_required": requested == "agent-native",
        "enforced_container_or_vm": False,
        "network_isolation": "not_enforced_by_growing_bench",
    }


def trajectory_completeness(adapter: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = {str(row.get("kind")) for row in events}
    capabilities = adapter_capabilities(adapter)
    observed: dict[str, bool] = {
        "command_start": "command_start" in kinds,
        "command_result": bool(kinds & {"command_result", "test_result", "compile_result"}),
        "file_read": "file_read" in kinds,
        "file_write": bool(kinds & {"file_write", "patch"}),
        "tool_call": bool(kinds & {"tool_call", "command_start"}),
        "tool_result": bool(kinds & {"tool_result", "command_result", "test_result", "compile_result"}),
        "assistant_message": "assistant_message" in kinds,
        "duration": any(row.get("duration_ms") is not None for row in events),
        "exit_status": any(
            row.get("exit_status") is not None or row.get("status") in {"success", "failure"}
            for row in events
        ),
    }
    supported = [name for name, value in capabilities.items() if value not in {"not_exposed", "unknown"}]
    observed_supported = [name for name in supported if observed[name]]
    score = 1.0 if not supported else len(observed_supported) / len(supported)
    missing = [name for name in supported if not observed[name]]
    unavailable = [name for name, value in capabilities.items() if value == "not_exposed"]
    return {
        "schema_version": "growing-bench-trajectory-completeness-1.0",
        "adapter": adapter,
        "score": score,
        "observed": observed,
        "capabilities": capabilities,
        "missing_supported_events": missing,
        "adapter_does_not_expose": unavailable,
    }
