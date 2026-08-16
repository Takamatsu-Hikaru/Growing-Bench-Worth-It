# Agent adapters

Growing Bench owns benchmark semantics: fixture isolation, exact baseline validation, completion checks, allowed-file scope, diffing, and trajectory storage. An adapter only gives an Agent the prompt and disposable workspace, then translates visible events.

| Adapter | Expected CLI | Invocation |
|---|---|---|
| `codex` | `codex` | ephemeral `codex exec` JSON stream |
| `claude-code` | `claude` | non-persistent stream JSON mode |
| `openclaw` | `openclaw` | headless agent execution with declared JSON events |
| `command` | any executable | user-supplied JSON command array |

Run `growing-bench doctor` to inspect local availability.

## Stable public artifacts

```text
run/
  task.json
  before/
  workspace/
  checks.before.json
  checks.after.json
  changes.json
  changes.diff
  trajectory.jsonl
  summary.json
  agent/
    agent.json
    prompt.md
    final.md
    stdout.log
    stderr.log
    events.jsonl
```

Evaluator packets consume normalized visible events and verified workspace results. They do not depend on Codex-specific internals and do not require private chain-of-thought.

Normalized event kinds include assistant messages, file reads/writes, search, tool calls, command start/results, test/compile results, patches, artifacts, the final response, post-checks, and the workspace diff. Events can carry receipt time, duration, status, target, visible output, and usage.

Recorded offline examples for all three built-in event formats live under `tests/fixtures/adapters/`; `tests/test_adapter_golden_events.py` proves their mapping without paid model calls.

## Custom command adapter

The command template is a JSON array. Exact elements may use `{workspace}`, `{prompt_file}`, `{final_file}`, `{model}`, and `{reasoning}`. The process runs with the disposable workspace as its current directory.

```bash
growing-bench run examples/tasks/adapter-smoke.json \
  --agent command \
  --command-template '["python","-m","growing_bench.demo_agent","{workspace}"]' \
  --output runs/custom-agent
```

A custom adapter may return `{"final":"...","events":[...]}`. Only canonical public event kinds are accepted.

## Adding another adapter

Add command construction and final parsing in `growing_bench/agents.py`; add event normalization in `growing_bench/trajectory.py`. Do not duplicate runner or scorer logic. A missing vendor CLI must be reported by `doctor` rather than breaking the offline smoke.
