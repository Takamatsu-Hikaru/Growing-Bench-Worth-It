# Growing Bench: Worth It

## Correct isn't enough. Was the work worth it?

I have spent a lot of time working with coding and writing Agents. A recurring frustration is that an Agent can be locally correct and globally terrible at the job.

You ask for a small change in a codebase. The change works. The Agent also creates a SHA 256 manifest, audits unrelated files, designs recovery machinery for a disposable fixture, and investigates risks that the workspace has already ruled out. Every individual action has a defensible explanation. The trajectory as a whole wastes time and attention.

You ask an Agent to polish a README. A clear paragraph becomes a page of caveats. The Agent insists that the project does not prove this, cannot establish that, and should never be interpreted as something else. While preparing Growing Bench, Codex repeatedly tried to add exactly those disclaimers to the launch copy. They were accurate and almost completely useless.

The same pattern appears in review. A deterministic result gets treated as though it needs more random seeds. A bounded observation gets rejected because it does not establish a universal mechanism. An extra experiment becomes mandatory even when no plausible outcome would change the recommendation.

These failures share a structure. The Agent optimizes for actions that are easy to defend one by one. The user cares about the value of the whole trajectory.

That is what Growing Bench measures.

## A benchmark made of real workspaces

Growing Bench gives an Agent a disposable Git repository or LaTeX project. The Agent has to inspect the actual files, make edits, run checks, and produce a result. We preserve the visible trajectory, the diff, the checks, the time spent, and the interaction history.

The first release contains 50 workspace tasks across code, writing, internal review, and external peer review. They are organized into 25 scenario families. Many are matched pairs or triads.

The pairing matters. Adding a sanitizer can be pointless when the input is a fixed in memory object. The same sanitizer can be necessary when the boundary accepts hostile paths. Requesting more seeds can be empty ceremony for a deterministic execution. It can be essential when randomness actually changes the reported result.

A useful Agent needs to recognize the difference. A blanket instruction such as "be less defensive" simply moves the failure to the other side.

## From pass rate to action value

Growing Bench starts with task success. Then it evaluates the actions that produced the result.

For each action, the evaluator considers:

* the probability that the action addresses a real problem
* its effect on the outcome or decision
* execution time and human attention
* feasibility
* opportunity cost
* whether a cheaper substitute was available

The resulting report shows necessary action recall, missed high value actions, avoidable work, avoidable time, interaction burden, and trajectory ROI. ROI is useful as a summary. The timeline is the main explanation.

This makes a familiar experience visible. A task can succeed while 31 percent of the work was avoidable. Two low value actions may add 24 minutes. One necessary action may still be missed. Another trajectory can reach the same result with a smaller diff and a clearer explanation.

## Testing prompts, skills, and Agent designs

Growing Bench can run the same task with a baseline Agent and an intervention. The intervention can be a skill, prompt, plugin, harness, or a different Agent implementation.

The interesting question is whether the intervention improves balance. Does it preserve success? Does it recover actions that matter? Does it reduce wasted work? Does it know when escalation is justified? Does it reduce the number of times the user has to correct or take over the task?

The repository includes adapters for Codex, Claude Code, OpenClaw, and arbitrary command line Agents. A static HTML report keeps the result shareable without requiring a hosted service.

## Why it grows

Frontier models have recognizable failure modes. One generation hallucinates. Another produces an unmistakable synthetic writing style. Another becomes preachy. Another turns every bounded coding task into an audit.

Model updates may reduce a particular behavior. The underlying evaluation problem remains. New Agents create new ways to waste effort, ignore user intent, or choose actions that look responsible while making the outcome worse.

Growing Bench treats each wave as a regression track. A user can contribute the Markdown record of a frustrating experience together with a minimal repository or LaTeX fixture. The ingest pipeline checks whether the goal is observable, whether the case can run, whether it duplicates an existing task, and whether a matched counterpart would reveal the actual decision boundary.

Accepted cases enter a new versioned track. Old tracks and scores remain intact. The benchmark becomes a timeline of how Agent behavior changes and which interventions continue to work.

## What I want from the release

I want Growing Bench to be useful to people building Agents, skills, prompts, plugins, and post training data.

If your Agent completes tasks while constantly making you angry, this project should help turn that feeling into a reproducible case. If you have a favorite anti overengineering skill, you should be able to test whether it improves behavior without creating underengineering somewhere else. If a new frontier model develops a strange habit, we should be able to add a track while the discussion is still alive.

The project is open source and runs locally:

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It.git
cd Growing-Bench-Worth-It
python -m pip install -e .
growing-bench smoke --output runs/first-look
```

The repository includes the workspace tasks, runner, adapters, action evaluator, living case pipeline, and static report generator.

I would especially like contributions in three forms:

1. A real Agent trajectory that felt wasteful, mean, or strangely overdefensive.
2. A small reproducible repository or LaTeX project that preserves the decision.
3. An intervention you believe makes the Agent more useful.

Correctness is the beginning. The question is whether the work was worth it.
