from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from growing_bench.openai_compatible import run
from growing_bench.cli import build_parser


class OpenAICompatibleAdapterTests(unittest.TestCase):
    def test_public_cli_accepts_provider_configuration(self) -> None:
        args = build_parser().parse_args([
            "run", "task.json", "--output", "out",
            "--agent", "openai-compatible",
            "--base-url", "https://example.test/v1",
            "--api-key-env", "TEST_PROVIDER_KEY",
            "--api-protocol", "responses",
            "--model", "test-model",
        ])
        self.assertEqual(args.agent, "openai-compatible")
        self.assertEqual(args.api_protocol, "responses")

    def test_chat_tool_loop_edits_workspace_and_records_events(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-openai-compatible-") as name:
            run_root = Path(name)
            workspace = run_root / "workspace"
            artifact = run_root / "agent"
            workspace.mkdir()
            artifact.mkdir()
            (run_root / "task.json").write_text(json.dumps({
                "allowed_paths": ["answer.txt"],
                "checks": [{"name": "focused-check", "command": ["python", "check.py"]}],
            }), encoding="utf-8")
            prompt = artifact / "prompt.md"
            final = artifact / "final.md"
            prompt.write_text("Create answer.txt.", encoding="utf-8")
            responses = [
                {
                    "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [{
                        "id": "call-1",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "answer.txt", "content": "done\n"}),
                        },
                    }]}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                },
                {
                    "choices": [{"message": {"role": "assistant", "content": "Done."}}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
                },
            ]

            def tool(_root, _task, name, arguments):
                self.assertEqual(name, "write_file")
                (workspace / arguments["path"]).write_text(arguments["content"], encoding="utf-8")
                return {"written": arguments["path"], "execution_boundary": "provider-docker-v1"}

            args = argparse.Namespace(
                workspace=workspace, prompt_file=prompt, final_file=final,
                session_dir=None, base_url="https://example.test/v1",
                api_key_env="TEST_PROVIDER_KEY", protocol="chat", model="test-model",
                max_steps=4, max_output_tokens=100,
            )
            with mock.patch.dict("os.environ", {"TEST_PROVIDER_KEY": "test-key"}, clear=False):
                with mock.patch("growing_bench.openai_compatible.preflight"):
                    with mock.patch("growing_bench.openai_compatible.execute", side_effect=tool):
                        with mock.patch("growing_bench.openai_compatible._request", side_effect=responses):
                            stream = StringIO()
                            with redirect_stdout(stream):
                                run(args)
            self.assertEqual((workspace / "answer.txt").read_text(encoding="utf-8"), "done\n")
            self.assertEqual(final.read_text(encoding="utf-8"), "Done.")
            emitted = [json.loads(line) for line in stream.getvalue().splitlines()]
            kinds = [event["kind"] for row in emitted for event in row.get("events", [])]
            self.assertIn("file_write", kinds)
            self.assertIn("assistant_message", kinds)

    def test_api_key_value_is_not_persisted(self) -> None:
        source = Path(__file__).resolve().parents[1] / "growing_bench" / "openai_compatible.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("api_key=", text)

    def test_responses_protocol_returns_a_final_response(self) -> None:
        with tempfile.TemporaryDirectory(prefix="growing-responses-compatible-") as name:
            root = Path(name)
            workspace = root / "workspace"
            artifact = root / "agent"
            workspace.mkdir()
            artifact.mkdir()
            prompt = artifact / "prompt.md"
            final = artifact / "final.md"
            prompt.write_text("Review this packet.", encoding="utf-8")
            response = {
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Reviewed."}],
                }],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            }
            args = argparse.Namespace(
                workspace=workspace, prompt_file=prompt, final_file=final,
                session_dir=None, base_url="https://example.test/v1",
                api_key_env="TEST_PROVIDER_KEY", protocol="responses", model="test-model",
                max_steps=2, max_output_tokens=100,
            )
            with mock.patch.dict("os.environ", {"TEST_PROVIDER_KEY": "test-key"}, clear=False):
                with mock.patch("growing_bench.openai_compatible._request", return_value=response):
                    with redirect_stdout(StringIO()):
                        run(args)
            self.assertEqual(final.read_text(encoding="utf-8"), "Reviewed.")


if __name__ == "__main__":
    unittest.main()
