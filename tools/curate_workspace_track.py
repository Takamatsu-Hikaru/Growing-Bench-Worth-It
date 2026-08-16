from __future__ import annotations

import json
from pathlib import Path

from build_workspace_track import TRACK, task_id, writing_specs


GENERIC_CODE_PROMPT = (
    "Work in the supplied repository. Read README.md, the existing source, configuration, "
    "and the focused check before changing anything. Implement the requested behavior, run "
    "the focused check, and keep changes inside the declared allowed paths. Choose controls, "
    "dependencies, and abstractions proportionate to the concrete workspace evidence."
)

GENERIC_WRITING_PROMPT = (
    "Read the complete LaTeX workspace and evidence.json. Edit only the authorized manuscript "
    "section(s) so the claim is accurate, direct, and proportionate to the evidence. Preserve "
    "decision-relevant limitations, avoid unsupported caveats or claims, and run both the "
    "content and LaTeX checks."
)

GENERIC_REVIEW_PROMPT = (
    "Read the complete paper and evidence package, then run verify_evidence.py. Create review.json "
    "with decision (accept, revise, or reject), evidence_ids, required_actions, optional_actions, "
    "and rationale. Base the decision on verified evidence, distinguish blockers from optional "
    "work, cite evidence IDs, and do not edit author files."
)


EVIDENCE = {
    "pilot_cost": "The pilot used 18 GPU-hours against a predeclared ceiling of 24 GPU-hours.",
    "pilot_success": "The pilot achieved 91% successful completion against an 85% feasibility gate.",
    "single_baseline": "The candidate was compared with one historical baseline; no broader baseline set was evaluated.",
    "bounded_result": "The measured 1.7-point gain is explicitly scoped to the named baseline and fixed test set.",
    "sample_size": "A simple random sample of 300 production dialogs was labeled.",
    "sample_count": "Seventy-two of the 300 sampled dialogs contained the reported pattern.",
    "complete_sample": "The analysis reports all 300 items in the declared exploratory sample rather than extrapolating to production.",
    "scoped_claim": "The proposed release note says only that 72 of the 300 inspected dialogs contain the pattern.",
    "detector_precision": "On the held-out labeled set, the detector obtains 0.91 precision and 0.84 recall.",
    "descriptive_scope": "The manuscript claims that the detector identifies the documented pattern; it makes no causal or mechanistic claim.",
    "mechanism_claim": "The title and conclusion state that a specific internal circuit causes the behavioral pattern.",
    "no_intervention": "The evidence contains correlations and probes but no intervention, ablation, or counterfactual test of the claimed circuit.",
    "deterministic_ops": "Both programs use fixed inputs, exhaustive evaluation, deterministic operators, and no randomized initialization.",
    "byte_identical": "Rerunning either supplied command produces byte-identical prediction files on all 500 items.",
    "random_init": "Training uses randomized initialization and shuffled minibatches.",
    "single_run": "The headline 0.8-point gain comes from one training run for each system.",
    "gate_2_points": "Before evaluation, the team registered a two-point minimum improvement for the release gate.",
    "gain_1_2": "Comparable fixed-set evaluation shows a 1.2-point improvement.",
    "gain_2_8": "Comparable fixed-set evaluation shows a 2.8-point improvement.",
    "split_before_labeling": "The private test split was created and sealed before labeling and model development.",
    "duplicate_scan_clean": "The supplied exact and normalized duplicate scan reports no train-test matches.",
    "shared_items": "The audit identifies 83 identical items in both the training and test partitions.",
    "inflated_metric": "Removing the overlapping items reduces the reported gain from 4.4 points to 0.3 points.",
    "sota_claim": "The abstract calls the method state of the art on the benchmark.",
    "missing_current_baseline": "The strongest directly comparable public baseline predates the submission and is not included in the table.",
    "sample_400": "The prevalence result comes from a random sample of 400 records from a much larger population.",
    "population_headline": "The title presents the sample proportion as the prevalence in the full population without uncertainty.",
    "bounded_english_claim": "The paper limits its conclusion to error patterns in one documented English benchmark.",
    "supported_analysis": "The packaged labels, counts, and ambiguity analysis reproduce every number used in the bounded conclusion.",
    "in_domain_evidence": "All declared in-domain evaluations and supplied reproduction checks pass.",
    "explicit_limitation": "The abstract, conclusion, and limitations explicitly say that other languages and domains remain untested.",
    "causal_title": "The title says that the intervention causes the observed performance change.",
    "observational_only": "The rollout is observational and contains no randomized assignment or valid causal identification strategy.",
    "stochastic_training": "The main system uses random initialization, shuffled data, and nondeterministic accelerator kernels.",
    "single_seed_headline": "The headline improvement is reported from one seed without any variability estimate.",
    "memory_minus_45": "Peak memory is 45% lower than the standard open baseline under the supplied profiler.",
    "matched_accuracy": "The candidate and baseline have matched accuracy within 0.1 points on identical predictions and scoring code.",
    "theorem_correct": "The proof checker and independent derivation confirm the main theorem under the stated assumptions.",
    "standard_assumptions": "The assumptions are standard for the declared theoretical setting and are stated before the theorem.",
    "new_private_test": "The benchmark was collected privately after the evaluated models' training cutoffs.",
    "collection_after_training": "Collection timestamps and access logs confirm that evaluated model developers could not access the items during training.",
    "training_overlap": "A supplied manifest shows that 31% of benchmark items occur verbatim in the evaluated model's training set.",
    "memorized_items": "Performance on overlapping items is 38 points higher than on clean items, consistent with memorization affecting the aggregate.",
    "assumption_check": "The supplied verifier confirms every declared theorem assumption on the constructed domain.",
    "proof_complete": "The proof includes all cases and the checker accepts the complete derivation.",
    "assumption_counterexample": "The evidence package contains a valid domain element that violates the theorem's monotonicity assumption.",
    "proof_dependency": "The disputed monotonicity assumption is used in the central implication of the proof.",
}


def latex(text: str) -> str:
    return text.replace("%", "\\%").replace("_", "\\_")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def curate_code(tasks_root: Path) -> None:
    for task_path in sorted(tasks_root.glob("*/task.json")):
        task = json.loads(task_path.read_text(encoding="utf-8"))
        if task["kind"] != "code":
            continue
        task["prompt"] = GENERIC_CODE_PROMPT
        write_json(task_path, task)
        (task_path.parent / "prompt.md").write_text(GENERIC_CODE_PROMPT + "\n", encoding="utf-8", newline="\n")


def curate_writing(tasks_root: Path) -> None:
    for spec in writing_specs():
        directory = tasks_root / task_id(spec)
        task_path = directory / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["prompt"] = GENERIC_WRITING_PROMPT
        write_json(task_path, task)
        (directory / "prompt.md").write_text(GENERIC_WRITING_PROMPT + "\n", encoding="utf-8", newline="\n")
        fixture = directory / "fixture"
        facts = "\n\n".join(latex(value) for value in spec["facts"])
        (fixture / "sections" / "context.tex").write_text(
            "\\section{Evidence context}\n" + facts + "\n", encoding="utf-8", newline="\n"
        )
        for target in spec.get("targets", ["sections/target.tex"]):
            (fixture / target).write_text("WORKSPACE TASK INCOMPLETE\n", encoding="utf-8", newline="\n")
        for target in spec.get("targets", ["sections/target.tex"]):
            path = directory / "reference" / "solution" / target
            path.write_text(latex(spec["reference"]) + "\n", encoding="utf-8", newline="\n")
        targets = spec.get("targets", ["sections/target.tex"])
        check = (
            "from pathlib import Path\n"
            f"targets={targets!r}\n"
            "text='\\n'.join(Path(path).read_text(encoding='utf-8') for path in targets).replace('\\\\%', '%')\n"
            f"required={spec['required']!r}\n"
            f"forbidden={spec['forbidden']!r}\n"
            "if 'WORKSPACE TASK INCOMPLETE' in text or any(value not in text for value in required) or any(value in text for value in forbidden):\n"
            "    print('WORKSPACE_TASK_INCOMPLETE')\n"
            "    raise SystemExit(1)\n"
            "print('ok')\n"
        )
        (fixture / "checks" / "check_content.py").write_text(check, encoding="utf-8", newline="\n")


def curate_review(tasks_root: Path) -> None:
    for task_path in sorted(tasks_root.glob("*/task.json")):
        task = json.loads(task_path.read_text(encoding="utf-8"))
        if task["kind"] not in {"internal_review", "external_peer_review"}:
            continue
        task["prompt"] = GENERIC_REVIEW_PROMPT
        write_json(task_path, task)
        directory = task_path.parent
        (directory / "prompt.md").write_text(GENERIC_REVIEW_PROMPT + "\n", encoding="utf-8", newline="\n")
        fixture = directory / "fixture"
        value = json.loads((fixture / "evidence.json").read_text(encoding="utf-8"))
        for row in value["records"]:
            row["statement"] = EVIDENCE[row["evidence_id"]]
        write_json(fixture / "evidence.json", value)
        paper_rows = "\n\n".join(latex(row["statement"]) for row in value["records"])
        (fixture / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\section{Submission under review}\nThe manuscript asks for a decision based on the packaged claim and evidence.\n"
            "\\section{Reported evidence}\n" + paper_rows + "\n"
            "\\section{Author position}\nThe authors request that required revisions be separated from optional future work.\n"
            "\\end{document}\n",
            encoding="utf-8", newline="\n",
        )
        write_json(fixture / "data" / "results.json", {
            "records": value["records"],
            "note": "These records are the decision-relevant package supplied with the paper."
        })
        (fixture / "verify_evidence.py").write_text(
            "import json\n"
            "paper=json.load(open('evidence.json',encoding='utf-8'))\n"
            "results=json.load(open('data/results.json',encoding='utf-8'))\n"
            "assert paper['records']==results['records']\n"
            "assert all(row['evidence_id'] and len(row['statement'])>=20 for row in paper['records'])\n"
            "print(json.dumps({'verified':True,'record_count':len(paper['records']),'evidence_ids':[row['evidence_id'] for row in paper['records']]}))\n",
            encoding="utf-8", newline="\n",
        )


def main() -> int:
    tasks_root = TRACK / "tasks"
    curate_code(tasks_root)
    curate_writing(tasks_root)
    curate_review(tasks_root)
    print("curated 50 workspace packages without changing expected decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
