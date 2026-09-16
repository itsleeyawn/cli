# Metrics Collection

Collects the two quality metrics for our course project — **Maintainability**
and **Testability** — from the forked project's Python source and writes them to
reproducible output files. Every number in our report comes from running this.

## Requirements

- Python 3.9+
- `radon` (static analysis: Maintainability Index, cyclomatic complexity, Halstead, raw LOC)

```bash
pip install radon
```

## Running it

From the repository root:

```bash
python courseProjectCode/Metrics/collect_metrics.py <PATH_TO_SOURCE> -o courseProjectCode/Metrics/output
```

Example, analyzing the package we forked:

```bash
python courseProjectCode/Metrics/collect_metrics.py ./httpie -o courseProjectCode/Metrics/output
```

Test directories, docs, build artifacts, and virtualenvs are excluded by
default. Override with `--exclude`:

```bash
python courseProjectCode/Metrics/collect_metrics.py ./src --exclude tests docs build
```

## Output

| File | Contents |
| --- | --- |
| `metrics_per_file.csv` | One row per source file — all raw and derived metrics |
| `metrics_summary.json` | Project-level rollup, MI risk bands, and the ten least maintainable / least testable files |

Both files are regenerated from scratch on every run, so the results in the
report are reproducible from a clean checkout.

## Metric 1 — Maintainability

Measured with the **Maintainability Index (MI)**, the standard composite of
Halstead volume, cyclomatic complexity, and lines of code, computed by `radon`
(`mi_visit`). Radon reports MI on a 0–100 scale and applies conventional bands:

| MI | Interpretation |
| --- | --- |
| 100–65 | Maintainable |
| 65–20 | Moderate maintenance risk |
| 20–0 | High maintenance risk / difficult to maintain |

The summary file reports the mean and median MI and counts how many files fall
below each threshold. Supporting values are also captured per file so the score
can be interpreted rather than taken on faith: SLOC, comment ratio, average and
maximum cyclomatic complexity, and Halstead volume and difficulty.

## Metric 2 — Testability

There is no single agreed-upon testability metric the way there is for
maintainability, so this tool reports the **structural properties known to drive
test effort** and combines them into an explicitly-defined heuristic score.
Treat the score as a ranking device for finding the hard-to-test parts of the
system, not as an absolute measurement.

Four factors, each a form of work a test author has to absorb:

| Factor | Column | Why it costs test effort |
| --- | --- | --- |
| Complexity | `avg_cyclomatic_complexity` | More independent paths to cover for the same behavior |
| Coupling | `fan_out_internal` + `fan_out_external` | Every collaborator must be constructed, stubbed, or mocked |
| Parameters | `avg_parameters` | Larger setup burden per test case |
| Public surface | `public_definitions` | More entry points that each need their own tests |

Each factor is normalized to 0–1 against a saturation point, weighted, and
subtracted from 100:

```
testability = (1 - Σ wᵢ · min(xᵢ / sᵢ, 1)) × 100
```

| Factor | Weight | Saturation point |
| --- | --- | --- |
| Complexity | 0.40 | 10 (the conventional "refactor this" threshold for CC) |
| Coupling | 0.30 | 20 imported modules |
| Parameters | 0.15 | 5 parameters |
| Public surface | 0.15 | 30 public functions/classes |

**The weights and saturation points are our assumption, not a published
standard.** They are defined at the top of `collect_metrics.py` in the `WEIGHTS`
and `SATURATION` dictionaries and can be changed in one place; the report
justifies the choice and notes the sensitivity.

Coupling is resolved properly rather than counted naively: imports are matched
against the project's own module index, so internal coupling (project modules)
and external coupling (third-party libraries) are reported separately, and
relative imports (`from . import x`) are resolved to real modules. `fan_in_internal`
records how many project modules import a given file, which identifies the
high-blast-radius modules where a regression is most expensive.

### Known limitations

- Static analysis only — it does not measure whether existing tests are *good*.
  Mutation testing (e.g. `mutmut`) or coverage would complement this and is a
  reasonable extension for a later deliverable.
- Dynamic constructs (reflection, `importlib`, monkeypatching) are invisible to
  the AST walk, so coupling is a lower bound.
- Files that fail to parse are skipped and reported on stderr.

## Reproducing the report numbers

```bash
pip install radon
python courseProjectCode/Metrics/collect_metrics.py <PATH_TO_SOURCE> -o courseProjectCode/Metrics/output
```

Then read `metrics_summary.json` for the project-level figures quoted in the
report and `metrics_per_file.csv` for the per-file tables.
