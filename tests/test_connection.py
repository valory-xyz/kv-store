# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2026 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""Behavioural tests for the kv_store connection.

Each test is structured so it would fail if the corresponding production
fix from issue #12 were reverted, e.g. swapping ``Store.key.in_(keys)``
back to ``Store.key in keys`` makes ``test_read_request_filters_by_keys``
return all rows instead of the requested subset.
"""

import logging
from typing import Tuple
from unittest.mock import MagicMock

import pytest
from aea.mail.base import Envelope

from packages.valory.connections.kv_store import connection as conn_mod
from packages.valory.connections.kv_store.connection import (
    KvStoreConnection,
    KvStoreDialogues,
    PUBLIC_ID,
    Store,
)
from packages.valory.protocols.kv_store.message import KvStoreMessage

SKILL_ADDRESS = "test_author/test_skill:0.1.0"
CONNECTION_ADDRESS = str(PUBLIC_ID)


def _make_connection() -> KvStoreConnection:
    """Construct a KvStoreConnection without invoking AEA framework init.

    The handlers under test rely only on ``self.logger``, ``self.dialogues``
    and ``self.put_envelope``. Bypassing ``BaseSyncConnection.__init__``
    avoids the heavy AEA wiring (identity, crypto_store, event loop) the
    real agent supplies at runtime.
    """
    instance = KvStoreConnection.__new__(KvStoreConnection)
    instance.logger = logging.getLogger("test.kv_store")  # type: ignore[assignment]
    instance.dialogues = KvStoreDialogues(connection_id=PUBLIC_ID)
    instance.put_envelope = MagicMock()  # type: ignore[method-assign]
    return instance


@pytest.fixture()
def fresh_db() -> None:
    """Bind the module-level peewee DB to a fresh in-memory SQLite per test."""
    conn_mod.db.init(":memory:")
    conn_mod.db.connect(reuse_if_open=True)
    conn_mod.db.create_tables([Store])
    try:
        yield
    finally:
        if not conn_mod.db.is_closed():
            conn_mod.db.drop_tables([Store])
            conn_mod.db.close()


@pytest.fixture()
def kv_connection(fresh_db: None) -> KvStoreConnection:  # noqa: ARG001
    """A KvStoreConnection wired to a fresh in-memory DB."""
    return _make_connection()


def _build_read_request(keys: Tuple[str, ...]) -> KvStoreMessage:
    return KvStoreMessage(
        performative=KvStoreMessage.Performative.READ_REQUEST,
        dialogue_reference=("ref0", ""),
        message_id=1,
        target=0,
        keys=keys,
    )


def _build_write_request(data: dict) -> KvStoreMessage:
    return KvStoreMessage(
        performative=KvStoreMessage.Performative.CREATE_OR_UPDATE_REQUEST,
        dialogue_reference=("ref0", ""),
        message_id=1,
        target=0,
        data=data,
    )


def _open_dialogue(dialogues: KvStoreDialogues, message: KvStoreMessage) -> object:
    """Register a peer-initiated message and return the resulting dialogue."""
    message.sender = SKILL_ADDRESS
    message.to = CONNECTION_ADDRESS
    return dialogues.update(message)


# ---------------------------------------------------------------------------
# P0: read_request must filter by the requested keys.
# ---------------------------------------------------------------------------


def test_read_request_filters_by_keys(kv_connection: KvStoreConnection) -> None:
    """A read for a subset of keys returns only that subset.

    Regression for issue #12 P0: ``Store.key in keys`` rendered ``WHERE ?``
    bound to ``True`` and returned every row in the table.
    """
    Store.create(key="a", value="1")
    Store.create(key="b", value="2")
    Store.create(key="c", value="3")

    message = _build_read_request(("a", "b"))
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.read_request(message, dialogue)  # type: ignore[arg-type]

    assert response.performative == KvStoreMessage.Performative.READ_RESPONSE
    assert response.data == {"a": "1", "b": "2"}


def test_read_request_unknown_keys_return_empty_dict(
    kv_connection: KvStoreConnection,
) -> None:
    """Asking for keys that do not exist yields an empty data dict."""
    Store.create(key="a", value="1")
    message = _build_read_request(("missing-1", "missing-2"))
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.read_request(message, dialogue)  # type: ignore[arg-type]

    assert response.performative == KvStoreMessage.Performative.READ_RESPONSE
    assert response.data == {}


def test_read_request_empty_keys_returns_empty_dict(
    kv_connection: KvStoreConnection,
) -> None:
    """An empty key list returns an empty data dict, not the whole table."""
    Store.create(key="a", value="1")
    message = _build_read_request(())
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.read_request(message, dialogue)  # type: ignore[arg-type]

    assert response.performative == KvStoreMessage.Performative.READ_RESPONSE
    assert response.data == {}


# ---------------------------------------------------------------------------
# P1: create_or_update_request must be atomic across all entries.
# ---------------------------------------------------------------------------


def test_create_or_update_inserts_and_updates(
    kv_connection: KvStoreConnection,
) -> None:
    """A mixed batch of inserts and updates lands as one consistent write."""
    Store.create(key="existing", value="old")

    message = _build_write_request({"existing": "new", "fresh": "value"})
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.create_or_update_request(
        message, dialogue  # type: ignore[arg-type]
    )

    assert response.performative == KvStoreMessage.Performative.SUCCESS
    assert Store.get(Store.key == "existing").value == "new"
    assert Store.get(Store.key == "fresh").value == "value"


def test_create_or_update_atomic_on_handler_error(
    kv_connection: KvStoreConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure mid-batch rolls back earlier writes from the same batch.

    Regression for issue #12 P1: prior to ``db.atomic()`` each key was
    committed individually, leaving the store half-applied when the loop
    raised partway through.
    """
    real_create = Store.create
    call_count = {"n": 0}

    def flaky_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("synthetic mid-batch failure")
        return real_create(**kwargs)

    monkeypatch.setattr(Store, "create", flaky_create)

    message = _build_write_request({"k1": "v1", "k2": "v2", "k3": "v3"})
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.create_or_update_request(
        message, dialogue  # type: ignore[arg-type]
    )

    assert response.performative == KvStoreMessage.Performative.ERROR
    assert "synthetic mid-batch failure" in response.message
    assert Store.select().count() == 0


def test_create_or_update_returns_error_when_db_raises(
    kv_connection: KvStoreConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB-layer exception is converted to an ERROR reply, not propagated."""

    def boom(**_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(Store, "create", boom)

    message = _build_write_request({"only": "key"})
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.create_or_update_request(
        message, dialogue  # type: ignore[arg-type]
    )

    assert response.performative == KvStoreMessage.Performative.ERROR
    assert "db unavailable" in response.message


# ---------------------------------------------------------------------------
# P1: read_request must handle DB errors with an ERROR reply.
# ---------------------------------------------------------------------------


def test_read_request_returns_error_when_db_raises(
    kv_connection: KvStoreConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB exception during read is converted to an ERROR reply.

    Regression for issue #12 P1: previously the exception escaped
    ``read_request`` and ``on_send``, leaving the caller hanging.
    """

    def boom(*_args, **_kwargs):
        raise RuntimeError("read failure")

    monkeypatch.setattr(Store, "select", boom)

    message = _build_read_request(("a",))
    dialogue = _open_dialogue(kv_connection.dialogues, message)

    response = kv_connection.read_request(message, dialogue)  # type: ignore[arg-type]

    assert response.performative == KvStoreMessage.Performative.ERROR
    assert "read failure" in response.message


# ---------------------------------------------------------------------------
# P1: on_send must always reply when a dialogue exists.
# ---------------------------------------------------------------------------


def test_on_send_drops_message_when_dialogue_cannot_be_built(
    kv_connection: KvStoreConnection, caplog: pytest.LogCaptureFixture
) -> None:
    """An unpairable message logs and does not crash on_send.

    Regression for issue #12 P1: ``on_send`` previously crashed when it
    tried to call ``getattr(self, performative.value)`` for a reply-only
    performative used as an initial message. We now detect the failed
    dialogue association first and short-circuit cleanly.
    """
    # READ_RESPONSE is not in KvStoreDialogue.INITIAL_PERFORMATIVES, so
    # dialogues.update() returns None when it arrives as the first message.
    orphan = KvStoreMessage(
        performative=KvStoreMessage.Performative.READ_RESPONSE,
        dialogue_reference=("ref0", ""),
        message_id=1,
        target=0,
        data={},
    )
    orphan.sender = SKILL_ADDRESS
    orphan.to = CONNECTION_ADDRESS
    envelope = Envelope(to=CONNECTION_ADDRESS, sender=SKILL_ADDRESS, message=orphan)

    with caplog.at_level(logging.ERROR, logger="test.kv_store"):
        kv_connection.on_send(envelope)

    assert kv_connection.put_envelope.call_count == 0
    assert any("Could not associate dialogue" in rec.message for rec in caplog.records)


# Note: the protocol's INITIAL_PERFORMATIVES restrict initial messages to
# READ_REQUEST and CREATE_OR_UPDATE_REQUEST; any other initial performative
# causes dialogues.update() to return None and is exercised by the
# `test_on_send_drops_message_when_dialogue_cannot_be_built` test above.
# There is no realistic path that pairs a dialogue and then hands the
# connection an unknown performative, so no separate test is needed.


def test_on_send_replies_error_when_handler_raises(
    kv_connection: KvStoreConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the dispatched handler raises, on_send replies with ERROR.

    Regression for issue #12 P1: previously a handler exception escaped
    ``on_send`` so no envelope was ever placed back on the queue.
    """

    def exploding_handler(_message, _dialogue):
        raise RuntimeError("handler boom")

    monkeypatch.setattr(kv_connection, "read_request", exploding_handler)

    request = _build_read_request(("a",))
    request.sender = SKILL_ADDRESS
    request.to = CONNECTION_ADDRESS
    envelope = Envelope(to=CONNECTION_ADDRESS, sender=SKILL_ADDRESS, message=request)

    kv_connection.on_send(envelope)

    assert kv_connection.put_envelope.call_count == 1
    response = kv_connection.put_envelope.call_args[0][0].message
    assert response.performative == KvStoreMessage.Performative.ERROR
    assert "handler boom" in response.message


def test_on_send_happy_path_round_trips_a_read(
    kv_connection: KvStoreConnection,
) -> None:
    """A normal READ_REQUEST round-trips through on_send to put_envelope."""
    Store.create(key="hello", value="world")

    request = _build_read_request(("hello",))
    request.sender = SKILL_ADDRESS
    request.to = CONNECTION_ADDRESS
    envelope = Envelope(to=CONNECTION_ADDRESS, sender=SKILL_ADDRESS, message=request)

    kv_connection.on_send(envelope)

    assert kv_connection.put_envelope.call_count == 1
    response = kv_connection.put_envelope.call_args[0][0].message
    assert response.performative == KvStoreMessage.Performative.READ_RESPONSE
    assert response.data == {"hello": "world"}


# ---------------------------------------------------------------------------
# P2: TextField accepts payloads larger than the old CharField cap.
# ---------------------------------------------------------------------------


def test_value_field_accepts_long_payloads(
    kv_connection: KvStoreConnection,
) -> None:
    """A value larger than 255 chars survives a write/read round-trip.

    Regression for issue #12 P2: the previous CharField default capped at
    255 chars; TextField has no length cap.
    """
    long_value = "x" * 4096

    write_msg = _build_write_request({"big": long_value})
    write_dialogue = _open_dialogue(kv_connection.dialogues, write_msg)
    write_response = kv_connection.create_or_update_request(
        write_msg, write_dialogue  # type: ignore[arg-type]
    )
    assert write_response.performative == KvStoreMessage.Performative.SUCCESS

    read_msg = _build_read_request(("big",))
    read_dialogue = _open_dialogue(kv_connection.dialogues, read_msg)
    read_response = kv_connection.read_request(
        read_msg, read_dialogue  # type: ignore[arg-type]
    )

    assert read_response.data == {"big": long_value}
