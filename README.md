# Agent Router (art)

Cheapest capable wins: explicit routing policy over documented stand-ins, every decision explained and audited.

**SYNTHETIC STAND-IN**: all shipped cost, quality, and latency numbers are invented policy inputs. No real model or tool is called or measured. This project is a working offline policy engine.

## Quickstart

Python 3.10 or newer, CPU only. The runtime uses only the Python standard library. Install from the local repository without fetching dependencies:

```powershell
python -m pip install --no-index --disable-pip-version-check --no-deps --no-build-isolation -e .
art registry
art route --task-type qa --quality-floor 0.9 --store demo/audit
art fixtures --out demo
art simulate --workload demo/workload.json --store demo/audit
art audit --store demo/audit
python -m pytest -q
```

The install requires setuptools already available locally; tests require pytest already available locally. `python -m art.cli` also runs every command without installation. No command performs network requests.

If pip warns that its Scripts directory is outside PATH, add the directory it prints to your session's PATH or use `python -m art.cli` in place of `art`. The installed console script has the same behavior.

## Architecture

```text
CLI (argparse)
  -> registry -> profiles.json -> validated synthetic profiles
  -> router -> support / floor filters -> cost, latency, name ordering
       -> audit -> ~/.art/audit.jsonl
  -> simulate -> workload -> router -> totals / baselines / shares
       -> audit -> one record per simulated task
  -> fixtures -> seed 31 -> synthetic workload.json
```

`art/registry.py` validates data at load time. `art/router.py` returns a complete decision without side effects. `art/simulate.py` calculates with Decimal arithmetic. `art/audit.py` handles persistence. `art/cli.py` connects these components and returns exit status 2 for invalid inputs. `art/fixtures.py` generates reproducible tasks.

## Registry catalogue

**SYNTHETIC STAND-IN: invented numbers, not measurements or vendor prices.** Quality is a single assumed score for each profile's supported tasks. Latency is an assumed value, never a timed execution.

| Profile | USD/task | Quality | Latency ms | Supports |
| --- | ---: | ---: | ---: | --- |
| local-tiny | 0.0002 | 0.62 | 120 | classify, summarize |
| local-small | 0.0010 | 0.78 | 400 | classify, summarize, qa |
| tool-codeexec | 0.0020 | 0.88 | 700 | code, qa |
| tool-websearch | 0.0040 | 0.85 | 1500 | search, qa |
| hosted-standard | 0.0120 | 0.90 | 900 | classify, summarize, qa, search, code |
| hosted-premium | 0.0600 | 0.97 | 1800 | classify, summarize, qa, search, code |

The JSON registry is data rather than routing logic. `--profiles PATH` allows a replacement registry for route, simulate, and registry. Its root contains `label` and a nonempty `profiles` list. Each profile requires a unique nonempty name, finite nonnegative cost, finite quality from 0 through 1, nonnegative integer latency_ms, and a nonempty supports list. Invalid entries produce RegistryError naming the profile and field.

## Routing policy

1. Validate the task type against the registry's supported types. UnknownTaskType lists valid types. Validate a finite quality floor in [0, 1]; otherwise return InvalidQualityFloor.
2. Filter by task-type support.
3. Retain profiles with quality greater than or equal to the floor.
4. Select the lowest cost. Break cost ties by lower latency, then lexicographically earlier name.
5. Explain every rejection, prioritizing unsupported task type, then below floor, then more expensive, then the tie-break reason. List rejected profiles in name order.
6. Append the successful decision with its full justification and UTC timestamp to the audit store.

If no profile qualifies, NoQualifyingProfile names the closest supporting profile and maximum available quality for that task. Unsupported task types receive UnknownTaskType even when the floor is impossible. Failed routes do not create audit entries. Identical inputs and registry data give byte-identical routing and simulation stdout. Audit records deliberately include real event timestamps; these are the sole nondeterministic record fields.

Five hand-computed examples: classify at 0.60 selects local-tiny; summarize at 0.75 selects local-small; qa at 0.85 selects tool-codeexec; search at 0.85 selects tool-websearch; code at 0.90 selects hosted-standard. Each cheaper supported alternative fails the floor, while each remaining qualifying alternative costs more. qa at 0.95 selects hosted-premium.

## Workload schema and fixtures

Workloads are JSON lists of objects with `task_type` and `quality_floor`. The floor may be a JSON number or decimal string. Optional extra metadata is ignored. The shipped generator puts a SYNTHETIC label at the start of each entry, including the first entry, so the file remains valid list-shaped JSON while carrying its provenance.

```json
[
  {
    "label": "SYNTHETIC STAND-IN workload; fixed seed 31",
    "task_type": "qa",
    "quality_floor": "0.85"
  }
]
```

Fixtures use a fresh `random.Random(31)` to generate exactly 50 tasks. For each task, choose a task type from classify, summarize, qa, search, code, then a floor from 0.60, 0.75, 0.85, 0.90, 0.95. Decimal strings preserve the intended thresholds. The same generator produces byte-identical files, without using global random state. Malformed entries name their zero-based index and problem. Simulation validates the complete workload before writing any audit records. An empty list prints zero costs, zero violations, and 0.00% savings.

## Simulation baseline and improvement hook

The first shipped run yielded the following selection counts, independently checked by count-times-price arithmetic:

| Profile | Selected tasks | Cost contribution USD |
| --- | ---: | ---: |
| local-tiny | 7 | 0.0014 |
| local-small | 13 | 0.0130 |
| tool-codeexec | 9 | 0.0180 |
| tool-websearch | 7 | 0.0280 |
| hosted-standard | 10 | 0.1200 |
| hosted-premium | 4 | 0.2400 |

Routed total = 0.0014 + 0.0130 + 0.0180 + 0.0280 + 0.1200 + 0.2400 = **USD 0.4204**. Always-premium = 50 x 0.0600 = **USD 3.0000**. Savings = **USD 2.5796**, or 2.5796 / 3 x 100 = **85.986666...%**, displayed as **85.99%**. All totals use exact decimal costs; percentages are displayed to two decimal places.

Routed violations: **0**. Always-premium violations: **0**. Always-cheapest violations: **43**, at total USD 0.0100. A baseline violation means either unsupported task type or quality below the floor, counted once per task. Always-cheapest deliberately uses the globally cheapest profile, local-tiny, for every task; it does not prefilter support. Always-premium requires the named hosted-premium profile, and checks its actual support and quality even if the registry is edited.

The derived output line reports the highest selection share: **local-small, 26.00% (13/50)**. This is the first signal of which assumed profile the policy leans on. Equal selection counts break by name. Empty workloads report none, 0.00%.

## CLI reference

| Command | Options | Behavior |
| --- | --- | --- |
| `art route` | `--task-type TYPE --quality-floor FLOOR [--store DIR] [--profiles PATH]` | Select, explain all rejections, append audit record |
| `art simulate` | `--workload PATH [--store DIR] [--profiles PATH]` | Compare three policies, show savings and share, audit every routed task |
| `art audit` | `[--store DIR] [--format text\|json]` | Read the entire log, print every decision and justification |
| `art registry` | `[--profiles PATH]` | Display the synthetic profile table |
| `art fixtures` | `--out DIR` | Write labelled 50-task workload.json |

Every subcommand accepts `--help`. Store options belong after the subcommand. The default store is `~/.art`, with one UTF-8 JSON object per line in `audit.jsonl`. Audit JSON output is a labelled object containing a `decisions` list, including timestamps, task types, floors, chosen profiles, rejected-with-reason lists, and estimated costs. Text output carries the synthetic banner; the JSON output carries the same banner in its label.

## HONESTY BOUNDARY

The profiles are scripted stand-ins with invented numbers. The router never calls or compares any real model or tool; it applies an explicit policy to documented synthetic profiles. No invented vendor pricing is presented as real. **this is not a benchmark**. Names such as tool-codeexec and hosted-premium identify data profiles only. They do not execute code, search the web, or invoke services. The quality constraint is satisfied against assumed scores, not observed task outcomes. Simulation savings are consequences of these assumptions, not evidence of real operational savings.

## Validation and future work

The pytest suite covers hand-picked selections and explanations, floors, support, latency/name ties, impossible floors, invalid inputs, registry validation, exact decimal math, baseline violations, fixture determinism, persistence, every CLI subcommand, and fixtures-to-simulation integration. The runtime is CPU only with no network, model, or GPU dependencies.

A future operator could replace profiles.json with internally measured numbers and task-specific quality evidence. No such measurements are shipped. Audit rotation is future work: the current reader loads the whole log, and the append-only log grows without bound. Concurrent writers, transactional multi-record persistence, and production monitoring are outside this local tool's scope.

Maintain this project as portfolio evidence and pair it with the cost profiler: the router decides, the profiler measures. Commercialisation belongs within a larger agent-ops offering. For KOML, the lesson is to make routing policy explicit, document assumed numbers, audit each decision, and never present assumptions as measurements.

Publishing is a separate verification step. This build does not publish anything.
