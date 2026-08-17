# Adapter event contract

Growing Bench compares visible Agent trajectories. Adapter coverage is reported so missing telemetry is not mistaken for an action the Agent never took.

## Common fields

The common evidence surface is:

| Capability | Meaning |
|---|---|
| `command_start` | A shell or execution command began |
| `command_result` | The command produced a result |
| `file_read` | A file read was visible to the adapter |
| `file_write` | A file write or patch was visible |
| `tool_call` | A non-shell tool was invoked |
| `tool_result` | A tool returned a visible result |
| `assistant_message` | Visible Agent reasoning or communication |
| `duration` | The event has an observed or derived duration |
| `exit_status` | Success or failure is visible |

Every run stores an adapter capability declaration and a trajectory completeness score. `not_exposed` and `partial` remain visible in the result. They are never converted into evidence that the Agent skipped the action.

## Current adapters

| Adapter | Native strengths | Known gaps |
|---|---|---|
| Codex | Commands, command results, file changes, messages, duration, exit status | Individual file reads are not always exposed as structured events |
| Claude Code | File reads, tool calls, messages, usage | Command results, file writes, durations, and exit status depend on stream detail |
| OpenClaw | Uses declared normalized events | Completeness depends on the OpenClaw event producer |
| Custom command | Uses declared normalized events | Plain stdout without declared events has low completeness |

Custom and OpenClaw output may include an `events` array. Missing event types remain missing and lower completeness.

## Conformance expectations

Golden fixtures verify that:

* command starts and results remain paired when the source exposes both
* file reads and writes keep their targets
* failure status remains visible
* durations use milliseconds
* missing event types are reported as missing

Trajectory completeness measures evidence coverage. It does not adjust the Agent's score or fabricate unavailable events.
