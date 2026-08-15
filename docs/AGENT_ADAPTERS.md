# Agent adapters

Growing Bench owns the benchmark semantics: fixture isolation, baseline validation, completion checks, allowed-file scope, diffing, and trajectory storage. An adapter only has to give an agent the prompt and workspace.

Built-in adapters:

| Adapter | Expected CLI | Invocation style |
|---|---|---|
| `codex` | `codex` | `codex exec` with JSON events and an ephemeral session |
| `claude-code` | `claude` | print mode with stream JSON and no session persistence |
| `openclaw` | `openclaw` | headless `agent exec` with a message file and JSON output |
| `command` | any executable | user-supplied JSON command array |

Run `python -m growing_bench doctor` to see what is installed.

## Stable run artifacts

Every adapter produces the same public shape:

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
```

This is the portability boundary. Evaluators consume the normalized trajectory and verified workspace results, not Codex-specific event formats.

## Custom command adapter

The command template is a JSON array. Exact array elements may use `{workspace}`, `{prompt_file}`, `{final_file}`, `{model}`, and `{reasoning}` placeholders. The command runs with the workspace as its current directory. It should return zero on successful execution and may print `{"final": "..."}`.

Bash example:

```bash
python -m growing_bench run examples/tasks/adapter-smoke.json \
  --agent command \
  --command-template '["python","-m","growing_bench.demo_agent","{workspace}"]' \
  --output runs/custom-agent
```

For a production integration, keep credentials and private chain-of-thought out of stdout. The benchmark needs visible messages, tool activity, file changes, checks, timing, and usage—not hidden reasoning.

## Adding another adapter

Add command construction and final-message parsing in `growing_bench/agents.py`; do not duplicate workspace or scoring logic. Add a no-network contract test using `examples/tasks/adapter-smoke.json`. A missing third-party CLI must be reported by `doctor` rather than breaking offline smoke.

