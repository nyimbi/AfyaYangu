"""§ACC-003's local-store contract: the statements both device clients must execute.

The vectors are JSON rather than Python because two native clients in two languages have to read
them and neither can import Python. This module is the Python end of the same file — it parses the
contract, asserts it is the shape all three readers expect, and gives the audit row something to
cite.

The file lives in `proto/`, beside `afya_internal.proto`, because that is where this repo keeps the
artefacts the clients share rather than the ones the server runs. It is read from the repo rather
than packaged, the way `afya.rollout.service` reads its own tree: the wheel is the server, and a
device's build reads the contract from the checkout that built it.
"""
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / 'proto' / 'local_store' / 'contract.json'

# The statements the clients execute, in the order the file states them. A Kotlin test, a Swift test
# and this module read the same file, so a change here is a change to what all three run.
CONTRACT: dict[str, Any] = json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))

# The queue's schema, stated once in the file and executed by both clients before their scenario's
# own statements. It was three copies inside the one file until a canary mutation matched all three:
# a contract that duplicates its own schema has already started to drift.
DDL: str = CONTRACT['ddl']

SCENARIOS: list[dict[str, Any]] = CONTRACT['scenarios']

SCENARIO_NAMES: tuple[str, ...] = tuple(s['name'] for s in SCENARIOS)

# The queue's columns, as the contract's own DDL declares them. `afya.persistence.service:sync_ops`
# declares the same ones, and `tests/ci/test_acc003.py` holds the two together: a device queue whose
# row the server's `SyncOp` refuses fails at the replay, which is the moment the queue exists for.
QUEUE_COLUMNS: tuple[str, ...] = (
	'op_id', 'dataset', 'server_version', 'client_ts', 'server_ts', 'payload', 'attempt', 'synced',
	'retry_at_ms',
)

assert CONTRACT['contract'] == 'afya.local_store.v1', 'the contract names its own version'
assert SCENARIO_NAMES == (
	'committed_rows_are_durable', 'rolled_back_rows_are_gone', 'the_key_refuses_a_duplicate',
), 'the three properties §16.1 and a write-ahead queue rest on'
assert all(s['why'] for s in SCENARIOS), 'every vector says what it is for'
assert all(s['statements'] and s['query'] and s['expect'] for s in SCENARIOS), \
	'a vector is not a vector without them'
assert all('CREATE TABLE' not in st for s in SCENARIOS for st in s['statements']), \
	'the schema is stated once at the top level, not restated per scenario'
