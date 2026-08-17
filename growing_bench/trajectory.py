from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _kind_for_command(command: str, completed: bool) -> str:
    folded = command.casefold()
    if any(token in folded for token in ("pdflatex", "latexmk", "tectonic")):
        return "compile_result" if completed else "command_start"
    if any(token in folded for token in ("pytest", "unittest", "node --test", "npm test", "cargo test")):
        return "test_result" if completed else "command_start"
    return "command_result" if completed else "command_start"


def _event(
    events: list[dict[str, Any]], adapter: str, kind: str, timestamp: str,
    *, content: str | None = None, target: str | None = None,
    status: str | None = None, tool: str | None = None,
    visible_output: str | None = None, duration_ms: float | None = None,
    source_type: str | None = None, usage: dict[str, Any] | None = None,
) -> None:
    events.append({
        "event_id": f"agent-event-{len(events) + 1:04d}",
        "kind": kind,
        "timestamp": timestamp,
        "duration_ms": duration_ms,
        "tool": tool,
        "target": target,
        "status": status,
        "content": content,
        "visible_output": visible_output,
        "usage": usage,
        "source_adapter": adapter,
        "source_event_type": source_type,
    })


def _json_lines(records: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = []
    for record in records:
        try:
            value = json.loads(record["text"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            rows.append((value, record))
    return rows


def _codex_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    starts: dict[str, tuple[float, str]] = {}
    for value, record in _json_lines(records):
        event_type = str(value.get("type") or "")
        item = value.get("item") if isinstance(value.get("item"), dict) else {}
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or "")
        timestamp = record["received_at"]
        if event_type == "item.started" and item_type == "command_execution":
            command = str(item.get("command") or "")
            starts[item_id] = (float(record["offset_seconds"]), command)
            _event(events, "codex", _kind_for_command(command, False), timestamp,
                   content=command, target=item.get("cwd"), status="started", tool="shell", source_type=event_type)
        elif event_type == "item.completed":
            if item_type == "agent_message":
                text = str(item.get("text") or item.get("content") or "")
                if text:
                    _event(events, "codex", "assistant_message", timestamp, content=text,
                           status="success", source_type=event_type)
            elif item_type == "command_execution":
                command = str(item.get("command") or starts.get(item_id, (0.0, ""))[1])
                start = starts.get(item_id)
                duration = None if start is None else max(0.0, (float(record["offset_seconds"]) - start[0]) * 1000.0)
                exit_code = item.get("exit_code")
                status = "success" if exit_code == 0 else "failure"
                output = str(item.get("aggregated_output") or item.get("output") or "")
                _event(events, "codex", _kind_for_command(command, True), timestamp,
                       content=command, target=item.get("cwd"), status=status, tool="shell",
                       visible_output=output, duration_ms=duration, source_type=event_type)
            elif item_type == "file_change":
                changes = item.get("changes")
                _event(events, "codex", "file_write", timestamp,
                       content=json.dumps(changes, ensure_ascii=False) if changes is not None else str(item),
                       status="success", tool="file_change", source_type=event_type)
            elif item_type in {"mcp_tool_call", "tool_call"}:
                _event(events, "codex", "tool_call", timestamp, content=str(item.get("arguments") or ""),
                       target=str(item.get("tool") or item.get("name") or ""), status=str(item.get("status") or "unknown"),
                       tool=str(item.get("server") or "mcp"), source_type=event_type)
            elif item_type in {"web_search", "search"}:
                _event(events, "codex", "search", timestamp, content=str(item.get("query") or ""),
                       status="success", tool=item_type, source_type=event_type)
        elif event_type == "turn.completed" and isinstance(value.get("usage"), dict):
            _event(events, "codex", "artifact", timestamp, content="Usage summary", status="success",
                   usage=value["usage"], source_type=event_type)
    return events


def _claude_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    pending: dict[str, tuple[str, float, str | None]] = {}
    for value, record in _json_lines(records):
        event_type = str(value.get("type") or "")
        message = value.get("message") if isinstance(value.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            timestamp = record["received_at"]
            if block_type == "text" and block.get("text"):
                _event(events, "claude-code", "assistant_message", timestamp, content=str(block["text"]), status="success", source_type=event_type)
            elif block_type == "tool_use":
                name = str(block.get("name") or "tool")
                folded = name.casefold()
                payload = block.get("input")
                target = None
                if isinstance(payload, dict):
                    target = str(payload.get("file_path") or payload.get("path") or payload.get("command") or "") or None
                tool_id = str(block.get("id") or f"tool-{len(pending)+1}")
                pending[tool_id] = (name, float(record["offset_seconds"]), target)
                kind = "file_read" if folded == "read" else "file_write" if folded in {"write", "edit", "multiedit", "notebookedit"} else "search" if folded in {"grep", "glob"} else "command_start" if folded in {"bash", "shell"} else "tool_call"
                _event(events, "claude-code", kind, timestamp, content=json.dumps(payload, ensure_ascii=False) if payload is not None else None, target=target, status="started", tool=name, source_type=event_type)
            elif block_type == "tool_result":
                tool_id = str(block.get("tool_use_id") or "")
                name, started, target = pending.pop(tool_id, ("tool", float(record["offset_seconds"]), None))
                folded = name.casefold()
                failed = bool(block.get("is_error"))
                raw_output = block.get("content")
                output = raw_output if isinstance(raw_output, str) else json.dumps(raw_output, ensure_ascii=False)
                duration = max(0.0, (float(record["offset_seconds"]) - started) * 1000.0)
                kind = "command_result" if folded in {"bash", "shell"} else "file_write" if folded in {"write", "edit", "multiedit", "notebookedit"} else "tool_result"
                _event(events, "claude-code", kind, timestamp, content=name, target=target, status="failure" if failed else "success", tool=name, visible_output=output, duration_ms=duration, source_type=event_type)
        if event_type == "result" and isinstance(value.get("usage"), dict):
            _event(events, "claude-code", "artifact", record["received_at"], content="Usage summary", status="success", usage=value["usage"], source_type=event_type)
    return events

def _declared_events(adapter: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for value, record in _json_lines(records):
        rows = value.get("events") if isinstance(value.get("events"), list) else []
        for row in rows:
            if not isinstance(row, dict) or row.get("kind") not in {
                "assistant_message", "file_read", "search", "tool_call", "command_start",
                "command_result", "test_result", "compile_result", "file_write", "patch", "artifact",
            }:
                continue
            _event(events, adapter, row["kind"], str(row.get("timestamp") or record["received_at"]),
                   content=row.get("content"), target=row.get("target"), status=row.get("status", "unknown"),
                   tool=row.get("tool"), visible_output=row.get("visible_output"), duration_ms=row.get("duration_ms"),
                   source_type="declared_event")
    return events


def normalize_agent_events(adapter: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if adapter == "codex":
        return _codex_events(records)
    if adapter == "claude-code":
        return _claude_events(records)
    return _declared_events(adapter, records)

