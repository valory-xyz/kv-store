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

"""Smoke tests — confirm the kv_store protocol and connection import cleanly.

The repo ships only an AEA protocol + connection (no skills, no agent, no
service); these tests keep the test matrix non-empty so pytest does not exit
with code 5 ("no tests ran") under tomte's canonical envs.
"""


def test_protocol_module_imports() -> None:
    """The kv_store protocol package imports without side-effects."""
    from packages.valory.protocols.kv_store import (  # noqa: F401  pylint: disable=import-outside-toplevel
        dialogues,
        message,
        serialization,
    )


def test_connection_module_imports() -> None:
    """The kv_store connection module imports without side-effects."""
    from packages.valory.connections.kv_store import (  # noqa: F401  pylint: disable=import-outside-toplevel
        connection,
    )
