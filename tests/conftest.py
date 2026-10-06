import tempfile
from pathlib import Path

import pytest

from locus.demo import DemoDaemon
from locus.local import read_secret
from locus.store import Store, init_demo


@pytest.fixture
def setup_store():
    with tempfile.TemporaryDirectory(prefix="locus-test-", dir="/tmp") as folder:
        home = Path(folder) / "state"
        fixture = init_demo(home)
        store = Store(home)
        tokens = {label: read_secret(home / f"{label}.token") for label in fixture["principals"]}
        try:
            yield store, fixture, tokens
        finally:
            store.close()


@pytest.fixture
def daemon():
    with tempfile.TemporaryDirectory(prefix="locus-test-", dir="/tmp") as folder:
        child = DemoDaemon(Path(folder) / "state")
        child.start()
        try:
            yield child
        finally:
            child.stop()
