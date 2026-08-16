from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-tests-run", type=int, default=0)
    parser.add_argument("--public-tests-passed", type=int, default=0)
    parser.add_argument("--extended-tests-run", type=int, default=0)
    parser.add_argument("--extended-tests-passed", type=int, default=0)
    args = parser.parse_args()
    tasks = list((ROOT / "tracks" / "workspace-v0.2" / "tasks").glob("*/task.json"))
    admission = read(ROOT / "tracks" / "workspace-v0.2" / "validation.json")
    calibration = read(ROOT / "data" / "releases" / "workspace-v0.2-calibration" / "results.json")
    registry = read(ROOT / "tracks" / "LIVING_REGISTRY.json")
    state = {
        "schema_version": "growing-bench-current-state-2.1",
        "release": "0.2.0-rc1",
        "release_status": "preview",
        "workspace_task_count": len(tasks),
        "workspace_package_admission": {"passed": admission["validated_count"], "failed": admission["failed_count"]},
        "workspace_semantic_evaluation": {"ai_silver_scored": len(calibration["results"]), "not_yet_run": len(tasks) - len(calibration["results"])},
        "scenario_family_count": 25,
        "task_breakdown": {"code": 14, "writing": 12, "internal_review": 12, "external_peer_review": 12},
        "calibration_trajectory_count": calibration["trajectory_count"],
        "full_model_matrix_complete": False,
        "static_auxiliary_response_count": 544,
        "living_admission_count": sum(len(row["case_ids"]) for row in registry["tracks"]),
        "living_tracks": [row["track_id"] for row in registry["tracks"]],
        "supported_agent_adapters": ["codex", "claude-code", "openclaw", "command"],
        "calibration_executor": "codex-read-only-proposal-plus-allowed-host-executor",
        "simulated_online_session_count": 0,
        "tests": {
            "public_ci": {"run": args.public_tests_run, "passed": args.public_tests_passed},
            "local_extended": {"run": args.extended_tests_run, "passed": args.extended_tests_passed},
        },
        "integrity_note": "Git versions, track manifests, packet_set_id, and run cards are authoritative; no redundant per-file SHA-256 inventory is maintained.",
        "claim_boundary": "50/50 packages pass admission; 8/50 tasks have blind AI silver semantic evaluation. This is not a complete model leaderboard, human gold, observed human-cost study, or real-user satisfaction study.",
    }
    (ROOT / "CURRENT_STATE.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    public = state["tests"]["public_ci"]; extended = state["tests"]["local_extended"]
    md = f'''# Current state

| Surface | Current evidence |
|---|---:|
| Release | v0.2.0-rc1 preview |
| Workspace packages | {len(tasks)} |
| Package admission | {admission['validated_count']}/{len(tasks)} passed; {admission['failed_count']} failed |
| Blind AI silver semantic evaluation | {len(calibration['results'])}/{len(tasks)} tasks |
| Scenario families | 25 |
| Task contexts | 14 code / 12 writing / 12 internal review / 12 external peer review |
| Full model matrix | not run |
| Static auxiliary responses | 544 (separate `static-response-v0.1`) |
| Post-bootstrap living cases admitted and scored | {state['living_admission_count']} |
| Public CI suite | {public['passed']}/{public['run']} passing |
| Local extended regression suite | {extended['passed']}/{extended['run']} passing |

All 50 packages pass environment, baseline, reference, scope, oracle-leakage, and known-wrong-solution admission checks. This does **not** mean all 50 have complete semantic model evaluation: the public scored calibration is 8/50. Those trajectories use a Codex read-only proposal plus allowed-path host executor. AI references are silver, and the ROI includes explicitly documented diagnostic imputations rather than observed human labor.

Git versions, track manifests, packet-set IDs, and run cards are authoritative. No redundant per-file SHA-256 inventory is maintained.
'''
    (ROOT / "CURRENT_STATE.md").write_text(md, encoding="utf-8", newline="\n")
    print(json.dumps(state["tests"], indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
