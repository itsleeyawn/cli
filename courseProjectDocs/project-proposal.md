# Project Proposal — HTTPie CLI

**Course:** SWEN-777 Software Quality Assurance
**Team:** Leon, Tenzin
**Upstream project:** HTTPie CLI — https://github.com/httpie/cli
**Fork:** https://github.com/itsleeyawn/cli
**Baseline analyzed:** v3.2.4

## Project Overview

HTTPie is a command-line HTTP client written in Python. It wraps the `requests`
library behind a syntax designed to be readable by humans rather than by shell
scripts, and adds colorized and formatted output, persistent sessions,
`wget`-style downloads, and a plugin system for auth and transport. The `http`
and `https` commands are the primary entry points.

We picked it for three reasons.

It is a real production tool with a real user base, not a toy repository, so the
quality problems we find are problems that affect people. It is also small
enough to reason about: our analysis covers 78 source files and 7,039 logical
lines of code, which a three-person team can actually read in a semester rather
than sample from.

Second, it has a substantial existing test suite — 409 test functions across 37
test modules — built on pytest with a local `pytest-httpbin` server. That gives
us something to analyze for oracle quality in the next deliverable instead of
starting from zero coverage.

Third, its architecture creates a natural testability gradient. The CLI parsing,
HTTP client, and output formatting layers are separated, but the entry point
(`core.py`) coordinates all of them, so we expect a small number of heavily
coupled modules surrounded by many easily testable ones. That is a useful shape
for a quality study because it gives us both ends of the spectrum in one
codebase.

## Key Quality Metrics

We are measuring **maintainability** and **testability**. Collection code and
reproduction instructions are in `courseProjectCode/Metrics/`.

### Maintainability

Measured with the Maintainability Index (MI), the standard composite of Halstead
volume, cyclomatic complexity, and lines of code, computed with `radon`. MI is
reported on a 0–100 scale with conventional bands: above 65 is maintainable,
20–65 is moderate risk, below 20 is high risk.

Baseline results:

| Measure | Value |
| --- | --- |
| Files analyzed | 78 |
| Total SLOC | 7,039 |
| Mean MI | 74.04 |
| Median MI | 73.48 |
| Files below MI 65 (moderate risk) | 31 |
| Files below MI 20 (high risk) | 0 |
| Mean cyclomatic complexity per unit | 2.38 |
| Highest cyclomatic complexity in a single unit | 27 (`core.py`) |

The project is healthy on average but not uniformly. Nothing is in the high-risk
band, yet 40% of files sit in the moderate band, and the distribution is skewed:
`cli/argparser.py` (MI 24.67) and `cli/options.py` (MI 38.28) are far worse than
the mean. Argument parsing is doing a large amount of work in one place.

### Testability

There is no single accepted testability metric, so we report the structural
properties that drive test effort and combine them into a defined heuristic
score: average cyclomatic complexity (paths to cover), coupling via resolved
internal and external imports (collaborators to stub or construct), average
parameter count (setup cost per case), and public definition count (entry points
needing their own tests). Each is normalized against a saturation point,
weighted, and subtracted from 100. The weights are our assumption rather than a
published standard; they are declared in one place in the collector and the
sensitivity is something we intend to discuss rather than hide.

Baseline results:

| Measure | Value |
| --- | --- |
| Mean testability score | 75.87 |
| Least testable | `core.py` (20.36) |
|  | `client.py` (36.67) |
|  | `cli/argparser.py` (42.53) |
|  | `output/writer.py` (46.17) |

`core.py` is the clearest finding of the baseline. It scores 20.36 while the
project averages 75.87, it has the highest cyclomatic complexity in the codebase
(27), and it imports 15 internal modules plus 8 third-party ones. It is the
program entry point, so every end-to-end path passes through it, which means it
is simultaneously the hardest unit to isolate and the one most worth isolating.

`cli/argparser.py` is the only module that lands in the bottom five on both
metrics, which makes it our primary candidate for deeper analysis.

### Why these two metrics together

They answer different questions and disagree in informative ways. MI asks how
hard code is to change; our testability score asks how hard it is to verify.
`output/writer.py` is acceptable on MI but poor on testability, because its
problem is coupling rather than internal complexity — a distinction MI alone
would hide. Tracking both lets us argue about which refactorings would actually
improve verifiability rather than just tidy the code.

## Planned Direction

With the baseline established, we intend to extract requirements and analyze the
existing test oracles, establish a baseline build and coverage run, and then
focus deeper testing work on the modules this baseline identified as weakest —
`core.py` and `cli/argparser.py` in particular.

## Note on Reproducibility

The figures above come from HTTPie v3.2.4. Our fork tracks `master`, so rerunning
the collector against the fork will shift the numbers slightly. All reported
results will be regenerated from the fork before the final report, using the
single command documented in `courseProjectCode/Metrics/README.md`.
