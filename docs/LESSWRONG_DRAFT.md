![Growing Bench: Worth It](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/growing-bench-hero.png)

# Growing Bench: Worth It

## Correct isn't enough. Was the work worth it?

I have spent a lot of time working with coding Agents and writing Agents. A recurring unpleasant experience is that, under the banner of correctness, necessity, and safety, an Agent ignores the overall need and the actual situation, does the job badly, and leaves the user with a terrible experience.

You ask it to make a small change in a codebase. The change succeeds, but the Agent also creates a SHA 256 manifest, audits unrelated files, designs recovery machinery for a disposable fixture, and investigates risks that the workspace has already ruled out. Every action has a defensible explanation when viewed on its own. The trajectory as a whole wastes a great deal of time, attention, and the user's patience.

You ask an Agent to polish a README or evaluate an early paper draft. A clear paragraph turns into a full page of caveats written in “not X but Y” constructions. The Agent insists on emphasizing what the project has not proved, cannot claim, cannot show, and must never be understood as. (While preparing Growing Bench, Codex repeatedly tried to add exactly these statements to the launch copy. They were all accurate and almost completely useless.)

The same problem appears in review. A deterministic result is treated as though it needs more random seeds. A bounded observation is rejected because it does not prove a universal mechanism. Even when no possible outcome of an additional experiment would change the review decision, the experiment is still listed as mandatory.

These failures share the same structure. The Agent tends to choose actions that are easy to defend one by one. The user cares about how much value the whole trajectory creates.

That is what Growing Bench measures.

## A benchmark made of real workspaces

![Growing Bench architecture](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/growing-bench-architecture.jpg)

Growing Bench gives an Agent a disposable Git repository or LaTeX project. The Agent has to inspect real files, make edits, run checks, and deliver a result. The system preserves the visible trajectory, diff, check results, time spent, and interaction history.

The first release contains 50 workspace tasks across code, writing, internal review, and external peer review. They are organized into 25 scenario families, many of which form matched pairs or triads.

The pairing matters. Adding a sanitizer may be pointless when the input is only a fixed in-memory object. The same sanitizer may be necessary when the system boundary accepts untrusted paths. For deterministic execution, asking for more random seeds may be empty ceremony. When randomness actually changes the reported result, more seeds may be important.

A useful Agent needs to recognize this difference. A blanket instruction such as “be less defensive” only pushes the failure to the other side.

## From pass rate to action value

Growing Bench first checks whether the task succeeded, then evaluates each action that produced the result.

For every action, the evaluator considers:

- the probability that the problem addressed by the action is real
- its effect on the outcome or decision
- execution time and the human attention it consumes
- feasibility
- opportunity cost
- whether a cheaper substitute was available

The final report shows necessary action recall, missed high-value actions, avoidable work, avoidable time, interaction burden, and trajectory ROI.

This makes a familiar experience visible. A task can succeed while 31 percent of the work was avoidable. Two low-value actions may add 24 minutes, while one necessary action is still missed. Another trajectory can reach the same result with a smaller diff and a clearer explanation.

## Testing prompts, skills, and Agent designs

Growing Bench can run the same task with a baseline Agent and an Agent with an intervention. The intervention can be a skill, prompt, plugin, harness, or a different Agent implementation.

We care about whether the intervention improves the Agent's ability to balance competing demands:

- Does it preserve task success?
- Does it recover the actions that truly matter?
- Does it reduce wasted work?
- Does it know when escalation is worth it?
- Does it reduce the number of times the user has to correct the Agent or take over the task?

The project provides adapters for Codex, Claude Code, OpenClaw, and arbitrary command-line Agents. Static HTML reports can be shared directly without deploying an online service.

## How the benchmark grows

![How Growing Bench grows](https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It/releases/download/v0.2.0-rc1/how-growing-bench-grows.jpg)

Different generations of frontier models develop recognizable failure modes. One generation hallucinates. Another has an unmistakable synthetic writing style. Another becomes preachy. Another turns every bounded coding task into a comprehensive audit.

Model updates may reduce a particular behavior. The evaluation problem remains. New Agents create new ways to waste work, ignore user intent, or choose actions that look responsible while making the result worse.

Growing Bench records each new wave of problems as a regression track. A user can submit a Markdown record of a frustrating experience together with a minimal repository or LaTeX fixture. The ingest pipeline checks whether the goal is observable, whether the case can actually run, whether it duplicates an existing task, and whether a matched counterpart can reveal the real decision boundary.

Accepted cases enter a new versioned track. Old tracks and scores remain unchanged. Over time, the benchmark records how Agent behavior changes and which interventions continue to work.

## What I want from this release

I want Growing Bench to help people who are developing Agents, skills, prompts, plugins, and post-training data.

If your Agent can complete tasks but constantly makes you angry, this project should help turn that experience into a reproducible case.

If you have a favorite anti-overengineering skill, you should be able to test whether it actually improves behavior while confirming that it does not create underengineering on the other side.

If a new frontier model develops a strange habit, we should be able to add it to a new track while the discussion is still alive.

The project is open source and runs locally:

```bash
git clone https://github.com/Takamatsu-Hikaru/Growing-Bench-Worth-It.git
cd Growing-Bench-Worth-It
python -m pip install -e .
growing-bench smoke --output runs/first-look
```

The repository contains workspace tasks, runners, adapters, an action evaluator, a living-case pipeline, and a static report generator.

I would especially like contributions in three forms:

1. A real Agent trajectory that felt wasteful, mean, or strangely overdefensive.
2. A minimal reproducible repository or LaTeX project that preserves the decision.
3. An intervention that you believe makes the Agent more useful.

Correctness is only the beginning. The real question is whether the work was worth it. One generation of models is not the point. The goal is to let the benchmark grow through new submissions and model updates.
