# kv-store

Two Open Autonomy packages: a `valory/kv_store` connection (SQLite-backed store via
peewee) and the `valory/kv_store` protocol it speaks. Everything shipped lives under
`packages/valory/`. There is no agent and no service in this repo.

**Keep this file current.** If you hit a trap here that cost you time — a command that
does not behave as documented, a check that fails for reasons unrelated to your change, a
local failure CI never sees — add it below before you finish. The next agent has no
memory of your run.

## Traps

- **Never run a bare `tomte tox`, and never `tomte tox -e check-generate-all-protocols`.**
  That env is in tomte's default envlist, so running `tomte tox` with no `-e` triggers it.
  It rewrites the protocol package in place and does not roll back — see *do not
  regenerate it* below for what it destroys and how to recover.
- **Always `tomte tox`, never bare `tox`.** This repo's `tox.ini` defines no `[tox]` or
  `[testenv]` sections; the envs are rendered by tomte. Bare `tox -e <env>` finds nothing.
  The `Makefile` uses `tomte tox` throughout — keep it that way.
- **`liccheck` fails on packages whose PyPI metadata omits a license**, even when the
  project is permissively licensed. `cffi` (MIT-0), `peewee`, `anchorpy`, `based58`,
  `jsonalias` and `httpx` each need an entry under `[Authorized Packages]` in `tox.ini`.
- **A failed `pip install` in the `windows-2025` CI steps reports green.** Those steps run
  under pwsh, which has no errexit, so the failure surfaces later and elsewhere as a
  confusing "tomte not found" in the test step. Linux and macOS steps are safe — Actions
  runs bash with `-eo pipefail`.

## Environment

This is a **uv** repo — no `requirements.txt`, no pip workflow. Setup is in `README.md`;
the short form is `uv sync`, activate `.venv`, then `autonomy packages sync`.

Never `pip install` into `.venv`, and never hand-edit `uv.lock`. Change `pyproject.toml`
and run `uv lock`; CI runs `uv lock --check`, which fails when the two disagree.

Python 3.10 is the floor — CI's lint and lock jobs pin it and the test job matrixes up
to 3.14. See `common_checks.yaml` for the current matrix rather than assuming.

## Verification

Use the `make` targets rather than calling tools directly; they wrap `tomte`, which owns
the canonical tox config. The `Makefile` says what each one runs — what it does not say
is the order:

1. `make format` first, since it rewrites files.
2. `make code-checks` — the non-rewriting `-check` variants plus the static analysers.
3. `make generators` after **any** change under `packages/`.
4. `make common-checks-1`, then `make security`.

`make ci-linter-checks` is the closest local equivalent to CI. For one env in isolation:
`tomte tox -e <env>`. Tests run as `tomte tox -e py3.10-linux` (`-darwin` / `-win`
elsewhere); targets come from `[tool.tomte] pytest_targets` in `pyproject.toml`.

## Touching anything under `packages/`

`autonomy packages lock` (wrapped by `make generators`) rewrites each package's
fingerprints and the hashes in `packages/packages.json`. Skip it and CI fails
`check-hash` and `check-packages`. This includes edits to package READMEs — they are
fingerprinted too. `autonomy packages lock --check` verifies without rewriting.

Verifying a fingerprint by hand needs `wrap=False`; `IPFSHashOnly.get` defaults to
`wrap=True` and will report every entry as a mismatch. Prefer `lock --check`.

`.gitignore` ignores `packages/valory/{contracts,protocols,skills,connections}/*`
wholesale and re-adds individual packages with `!`. Only the `kv_store` connection and
protocol exist here; the other `!` entries are leftovers from the source repos. A new
connection, protocol, skill or contract needs its own `!` entry or it silently will not
be committed. Agents and services are not covered by those globs.

## The kv_store protocol: do not regenerate it

`packages/valory/protocols/kv_store/README.md` holds the protocol spec, and
`autonomy generate-all-protocols` reads it from there. (`aea generate protocol` is a
different thing — it takes an explicit spec-file path and never looks at the README.)
**Do not regenerate.** The committed code diverges from generator output on purpose:

- `kv_store.proto` assigns its `oneof performative` field numbers append-only for wire
  compatibility (`create_or_update_request=5`, `error=6` … `list_response=12`). The
  generator reassigns them alphabetically, which breaks deployed agents.
- `message.py` carries a hand-added `enforce(self.limit >= 0, ...)` the generator omits.
- The proto declares `uint32 limit`; `pt:int` is the nearest AEA primitive, so
  regenerating flips it to `int32`.

tomte ships a `check-generate-all-protocols` env for exactly this consistency check. It
is deliberately **not** wired into the `Makefile` or CI here, and must stay that way: the
divergences above are intentional, so the check would fail permanently by design. The
hand-maintained code is the wire-format source of truth — the spec cannot express
`uint32` and cannot preserve field numbers.

Running that env is also destructive. `autonomy generate-all-protocols --check-clean`
writes the regenerated files into the package tree *before* checking cleanliness and
exiting 1, and does not roll back: it overwrites the six generated files and
`protocol.yaml`, and leaves an untracked `tests/` directory behind. Restore with
`git checkout origin/main -- <files>`, then re-run `autonomy packages lock`.

The spec block's **final** `...` is load-bearing. `SPECIFICATION_REGEX` in
`aea/helpers/protocols.py` is greedy but cannot run past the last `...` in the file, so
dropping it silently truncates the spec to its first document — losing `initiation` and
`end_states` without raising — and generation then dies far away with `list index out of
range`. The separator between the two documents is a bare `---`; only the closing
terminator matters.

## tomte

`tomte` supplies the canonical tox envs. The local `tox.ini` holds only
`[tomte-extensions]` dependency overrides, per-repo pytest and mypy config, and a
liccheck `[Authorized Packages]` allowlist.

Its version is pinned in **three** hand-edited places that must move together:

- `[dependency-groups] dev` in `pyproject.toml`
- `[tool.tomte] tomte_dep_pin` in `pyproject.toml` — what each tox env installs
- the six `pip install 'tomte[tox,cli] @ ...'` lines in
  `.github/workflows/common_checks.yaml` — the *driver* that renders tox.ini

`uv.lock` carries the pin too, but derived; regenerate it with `uv lock`. A fix in
tomte's renderer only reaches CI when the workflow pin moves, so leaving the two kinds
of pin out of step means the bump silently does nothing.
