# LyingDocs Test Fixture

A minimal repo for exercising the three Argus backends end-to-end.

## Layout

```
tests/
├── fixture/
│   ├── code/app.py       # trivial calculator module
│   └── docs/README.md    # doc with intentional misalignments
└── configs/
    ├── local.toml        # Argus backend = local
    ├── codex.toml        # Argus backend = codex
    └── claude_code.toml  # Argus backend = claude_code
```

## Planted misalignments

`fixture/docs/README.md` intentionally lies about `fixture/code/app.py`:

| # | Category | What the doc claims | What the code actually does |
|---|---|---|---|
| 1 | LogicMismatch  | `add` returns a formatted string like `"5.00"` | returns an `int` |
| 2 | PhantomSpec    | `subtract(a, b)` is exposed                    | function does not exist |
| 3 | HardcodedDrift | `CALC_PRECISION` env var configures precision  | `DEFAULT_PRECISION = 2` is hardcoded |
| 4 | PhantomSpec    | `python app.py --verbose` prints a call trace  | `main()` takes no arguments |

A working Argus backend should surface at least items 1–3.

## Prerequisites

```bash
export OPENAI_API_KEY="sk-..."   # or whatever your endpoint expects
```

Run every command from the repo root (`/mnt/workspace/lkm/private/lying-docs`).

## Test commands

### 1. Local backend (no external CLI)

```bash
lyingdocs analyze \
  --doc-path tests/fixture/docs \
  --code-path tests/fixture/code \
  --output-dir tests/out/local \
  --config tests/configs/local.toml
```

Expected artifacts in `tests/out/local/`:

- `pipeline.log` — contains `Argus backend=local` and shows iterations of the local agent
- `argus_task_001.txt`, `argus_task_002.txt`, ... — reports produced by the local loop (with file:line refs into `app.py`)
- `Misalignment_Report.md` — final Hermes report citing at least the `add` return-type and `subtract` phantom findings

Quick check:

```bash
grep "Argus backend=local" tests/out/local/pipeline.log
ls tests/out/local/argus_task_*.txt
cat tests/out/local/Misalignment_Report.md
```

### 2. Codex backend

```bash
lyingdocs analyze \
  --doc-path tests/fixture/docs \
  --code-path tests/fixture/code \
  --output-dir tests/out/codex \
  --config tests/configs/codex.toml
```

Expected: `pipeline.log` says `Argus backend=codex: <path>`; `argus_task_NNN.txt` files are written by the `codex exec` subprocess (and `argus_stderr_NNN.txt` exists for debugging).

> If the `codex` binary at `argus.codex.path` is missing, Hermes will receive `[UNAVAILABLE] Codex CLI binary not found ...` on every dispatch — that itself is a valid test of the graceful-degradation path.

### 3. Claude Code backend

```bash
lyingdocs analyze \
  --doc-path tests/fixture/docs \
  --code-path tests/fixture/code \
  --output-dir tests/out/claude_code \
  --config tests/configs/claude_code.toml
```

Expected: `pipeline.log` says `Argus backend=claude_code: <path>`; `argus_task_NNN.txt` files contain the output of `claude -p ...`.

## Mixing models via CLI

The CLI flags override the config file. Example: run Hermes on a cheap planner and Argus locally on a stronger coder:

```bash
lyingdocs analyze \
  --doc-path tests/fixture/docs \
  --code-path tests/fixture/code \
  --output-dir tests/out/split \
  --config tests/configs/local.toml \
  --hermes-model gpt-4o-mini \
  --argus-model gpt-5.4
```

Then confirm both model names appear in `tests/out/split/pipeline.log`.

## Legacy-config rejection smoke test

```bash
printf 'model = "old"\n[codex]\nprovider = "p"\n' > /tmp/legacy.toml
lyingdocs analyze \
  --doc-path tests/fixture/docs \
  --code-path tests/fixture/code \
  --output-dir tests/out/legacy \
  --config /tmp/legacy.toml
```

Expected: immediate exit with a migration error pointing at `[hermes]` / `[argus]`.

## Clean up

```bash
rm -rf tests/out
```
