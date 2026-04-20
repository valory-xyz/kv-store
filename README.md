# kv-store

Key-value storage components for [Open Autonomy](https://github.com/valory-xyz/open-autonomy) agents — a connection and protocol that expose a local SQLite-backed key-value store (via [peewee](https://docs.peewee-orm.com/)) to agent skills over the AEA messaging layer.

## What's in this repo

| Package | Public ID | Description |
|---|---|---|
| Connection | `dvilela/kv_store` | SQLite-backed KV store, wired through the AEA connection interface |
| Protocol | `dvilela/kv_store` | Message schema for `get` / `set` / `remove` operations against the store |

Both packages live under `packages/dvilela/`. They were originally implemented across [meme-ooorr](https://github.com/valory-xyz/meme-ooorr) (connection) and [tsunami](https://github.com/dvilelaf/tsunami) (protocol) and extracted here for reuse.

## Requirements

- Python `>=3.10, <3.15`
- [uv](https://docs.astral.sh/uv/)

## Install

```bash
uv sync
source .venv/bin/activate
autonomy packages sync
```

## Development

Common workflows are wired through `make`; see `make help` or the individual `tox` envs in `tox.ini`.

```bash
make format          # black + isort
make code-checks     # black-check, isort-check, flake8, mypy, pylint, darglint
make security        # bandit + safety
make generators      # regenerate protocol code + package hashes
make common-checks-1 # hash + copyright + docs + deps
```

See `CONTRIBUTING.md` for the full pre-PR checklist.

## License

Licensed under Apache License 2.0.
