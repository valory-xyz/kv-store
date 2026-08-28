# kv-store

Two Open Autonomy packages: a `valory/kv_store` connection (SQLite-backed store via
peewee) and the `valory/kv_store` protocol it speaks. Everything shipped lives under
`packages/valory/`. There is no agent and no service in this repo.

**Keep this file current.** If you hit a trap here that cost you time — a command that
does not behave as documented, a check that fails for reasons unrelated to your change, a
local failure CI never sees — add it below before you finish. The next agent has no
memory of your run.

Prefer durable facts about how this repo is built over descriptions of how a tool
currently behaves — the second kind is stale by the next release, and a confidently wrong
file is worse than a thin one. Verify before you write.

## Rules

- **Do not regenerate the protocol.** The checked-in code is authoritative; see below.
  Avoid `check-generate-all-protocols` — it rewrites the package tree in place.
- **Always `tomte tox`, never bare `tox`.** This repo's `tox.ini` defines no testenvs by
  design; they are rendered by tomte. The `Makefile` uses `tomte tox` throughout.
- **`liccheck` runs a PARANOID strategy** that rejects transitive dependencies whose PyPI
  metadata omits a license, even when the project is permissively licensed. That is what
  the `[Authorized Packages]` entries in `tox.ini` are for; expect to add one after a
  dependency bump.

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

Verify fingerprints with `lock --check` rather than hashing by hand — hand-computed IPFS
hashes will not match unless you reproduce the exact options the tooling uses.

`.gitignore` ignores the `packages/valory/*` package-type directories wholesale and
re-adds individual packages with `!`. A new connection, protocol, skill or contract needs
its own `!` entry or it silently will not be committed.

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
divergences above are intentional, so the check fails permanently by design. Running it is
also destructive — it rewrites the package tree before failing, and does not roll back.

The spec block's **final** `...` terminator is load-bearing. Without it the spec is
silently truncated to its first document, losing the dialogue configuration with no error
raised, and generation fails later for an unrelated-looking reason.

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
