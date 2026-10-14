"""§ACC-003's "local-first data storage (SQLite / Room / Core Data)" — the store the clients did not have.

The other six bullets of the section were carried. This one was not, and the audit row's note said
why: `afya.persistence.service:SqliteStore` is the *server's* durability adapter, and §15.2's own
stack table reported the client's local DB as diverged to a SharedPreferences last-good-response
cache — "not an ACID store". §16.1 principle 1 says every user action is written to the local
database first and principle 5 says every queued write survives app restart; a preferences cache
with no transactions, no schema and no key can promise neither.

What the row needed was therefore not more Python. It needed the two native clients to keep their
queue in a database, and it needed one artefact that says what "a store" means so the two clients
cannot diverge from each other or from the server's own `sync_ops`.

The tests here hold the Python end of that:

* the shared contract exists, is versioned, and says what each vector is for;
* the contract's DDL is **the server's** `sync_ops`, column for column. A queue is only replayable
  if the row it holds is the row the server expects, and two tables that agree today are not one
  source of truth;
* both clients actually run the contract rather than a copy of it — asserted by reading their test
  sources, because neither can be executed from here and a Kotlin or Swift test that rebuilt the
  vectors by hand would pass against a store that had drifted;
* the queue is no longer in the preferences cache on either client;
* the audit row resolves.

The Android and iOS suites run the same vectors against real SQLite engines; that is what makes the
contract a measurement rather than a document. Neither runs in this repo's CI, which the docs say.
"""
import json
import re
from pathlib import Path

from afya.refs import resolves

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / 'proto' / 'local_store' / 'contract.json'
KOTLIN_STORE = REPO / 'android' / 'app' / 'src' / 'main' / 'java' / 'ke' / 'go' / 'health' / 'afyayangu' / 'LocalStore.kt'
KOTLIN_TEST = REPO / 'android' / 'app' / 'src' / 'test' / 'java' / 'ke' / 'go' / 'health' / 'afyayangu' / 'LocalStoreContractTest.kt'
SWIFT_STORE = REPO / 'ios' / 'AfyaYangu' / 'LocalStore.swift'
# The DDL lives in its own file on each client, with no platform imports, so the JVM and simulator
# test bundles can run the same strings the device does. That is why the schema is what this gate
# reads and not the store class.
KOTLIN_SCHEMA = REPO / 'android' / 'app' / 'src' / 'main' / 'java' / 'ke' / 'go' / 'health' / 'afyayangu' / 'LocalStoreSchema.kt'
SWIFT_SCHEMA = REPO / 'ios' / 'AfyaYangu' / 'LocalStoreSchema.swift'
SWIFT_TEST = REPO / 'ios' / 'Tests' / 'LocalStoreTests.swift'
ANDROID_CLIENT = REPO / 'android' / 'app' / 'src' / 'main' / 'java' / 'ke' / 'go' / 'health' / 'afyayangu' / 'BackendClient.kt'
SWIFT_CLIENT = REPO / 'ios' / 'AfyaYangu' / 'BackendClient.swift'
SERVER_STORE = REPO / 'src' / 'afya' / 'persistence' / 'service.py'


def _contract() -> dict:
	return json.loads(CONTRACT.read_text(encoding='utf-8'))


def _server_columns() -> list[str]:
	"""The server's `sync_ops` columns, read off the DDL it actually runs."""
	text = SERVER_STORE.read_text(encoding='utf-8')
	match = re.search(r"'CREATE TABLE IF NOT EXISTS sync_ops \((.*?)\)',", text, re.S)
	assert match, 'the server no longer declares a sync_ops table; the contract cites a table that is gone'
	return re.findall(r'(\w+) (?:TEXT|INTEGER)', match.group(1))


def _device_columns(ddl: str) -> list[str]:
	return re.findall(r'(\w+) (?:TEXT|INTEGER)', ddl)


def _device_ddl(path: Path) -> str:
	"""One client's table definition, reassembled from the source it is written in.

	The statement is split across concatenated string literals in both languages, and a column name
	appears in several other statements in the same file (the insert, the defer, the migration). A
	check that searched the whole file would therefore pass against a store whose *table* had lost
	the column — which a canary demonstrated before this helper existed. So the statement is cut out
	and its literals joined, and the columns are read from that.
	"""
	text = path.read_text(encoding='utf-8')
	start = text.index('CREATE TABLE IF NOT EXISTS sync_ops')
	body = text[start:text.index(')', start) + 1]
	joined = re.sub(r'[\t\n]+', ' ', body.replace('"', '').replace('+', ''))
	# A Kotlin string literal ends `"(" +`, so joining leaves a space after the paren the contract
	# does not have. Collapsed here rather than loosened in the comparison: the point is to compare
	# the statement, and a formatting difference is not a schema difference.
	return re.sub(r'\(\s+', '(', ' '.join(joined.split()))


def test_the_contract_is_versioned_and_says_what_each_vector_is_for() -> None:
	"""A vector without a `why` is a test nobody can decide to delete."""
	c = _contract()
	assert c['contract'] == 'afya.local_store.v1'
	assert [s['name'] for s in c['scenarios']] == [
		'committed_rows_are_durable', 'rolled_back_rows_are_gone', 'the_key_refuses_a_duplicate',
	]
	for s in c['scenarios']:
		assert s['why'].strip(), f'{s["name"]} does not say what it is for'
		assert s['statements'] and s['query'] and s['expect'], f'{s["name"]} is not a vector'


def test_the_contract_table_is_the_servers_table() -> None:
	"""A queue is replayable only if the row it holds is the row the server expects.

	The device table and `afya/persistence/service.py:sync_ops` must carry the same columns. This is
	the assertion that stops the contract becoming a schema of its own: a device that queued a shape
	the server's `SyncOp` refuses would fail at the replay, which is the moment the queue exists for.
	"""
	ddl = _contract()['ddl']
	assert _device_columns(ddl) == _server_columns(), (
		'the device queue and the server queue have drifted apart:\n'
		f'  device: {_device_columns(ddl)}\n  server: {_server_columns()}'
	)


def test_both_clients_run_the_shared_contract_rather_than_a_copy() -> None:
	"""Two clients that agree today are not one source of truth.

	Neither client can be executed from here, so this reads their test sources for the contract path.
	A client test that rebuilt the vectors by hand would pass against a store whose real statements
	had drifted — which is the failure the shared file exists to make impossible.
	"""
	# The read, not a mention. The first version of this assertion matched the path anywhere in the
	# file, and a canary proved it blind: the path also appears in the test's own doc comment, so
	# pointing the *read* at a copy of the contract still satisfied it. Match the call that opens the
	# file, in each language's own spelling.
	READS = {
		KOTLIN_TEST: r'dir\.resolve\("proto/local_store/contract\.json"\)',
		SWIFT_TEST: r'appendingPathComponent\("proto/local_store/contract\.json"\)',
	}
	for path, pattern in READS.items():
		text = path.read_text(encoding='utf-8')
		assert re.search(pattern, text), f'{path.name} does not read the shared contract'
		assert 'scenarios' in text, f'{path.name} reads the file but not its vectors'
	for path in (KOTLIN_STORE, SWIFT_STORE, KOTLIN_SCHEMA, SWIFT_SCHEMA):
		assert path.exists(), f'{path.name} is missing, so one client has no store'
	# And the store executes the schema file's statements rather than its own copy of them: a client
	# that kept a second DDL beside this one is the drift the shared file exists to prevent.
	for store, schema in ((KOTLIN_STORE, 'LocalStoreSchema.DDL'), (SWIFT_STORE, 'LocalStoreSchema.ddl')):
		assert schema in store.read_text(encoding='utf-8'), f'{store.name} does not execute {schema}'


def test_the_clients_run_the_contracts_ddl_not_a_schema_of_their_own() -> None:
	"""Each client's store must carry the contract's own first statement.

	The vector asserts the *behaviour*; this asserts the artefact. A client that ran different DDL
	and happened to pass the vectors would be a client whose schema the contract does not describe.
	"""
	from afya.persistence.local_store import DDL, QUEUE_COLUMNS
	ddl = DDL
	# The statement is written as a concatenation in both languages, so this compares the column
	# names each store declares against the contract's list rather than one literal string. Every
	# column, not a sample: a store missing `retry_at_ms` would pass a spot check and fail at the
	# first deferred op.
	for path in (KOTLIN_SCHEMA, SWIFT_SCHEMA):
		device = _device_ddl(path)
		assert _device_columns(device) == list(QUEUE_COLUMNS), (
			f'{path.name} declares a queue the contract does not describe:\n'
			f'  device:   {_device_columns(device)}\n  contract: {list(QUEUE_COLUMNS)}'
		)
		assert device == re.sub(r'\(\s+', '(', ddl), f'{path.name} declares a table the contract does not:\n  {device}\n  {ddl}'


def test_the_queue_left_the_preferences_cache_on_both_clients() -> None:
	"""The row's actual finding. §15.2 called it "a last-good-response cache, not an ACID store".

	A response cache belongs in preferences and stays there. The *queue* does not: it is the thing
	§16.1 promises survives a restart, and a JSON array rewritten whole cannot promise that.
	"""
	for path in (ANDROID_CLIENT, SWIFT_CLIENT):
		text = path.read_text(encoding='utf-8')
		assert 'LocalStore(' in text, f'{path.name} does not use the local store'
		assert not re.search(r'prefs\.getString\("queue"|defaults\.(?:array|string)\(forKey: "queue"\)', text), (
			f'{path.name} still keeps the write queue in the preferences cache'
		)


def test_the_client_backoff_matches_the_servers_cap() -> None:
	"""§16.2's backoff, on the side that waits.

	The device schedules its own retry, so the cap has to be the server's own figure — 600 s, from
	`afya.sync.service:backoff_delay_s` — or a handset that has been offline overnight wakes to a
	delay the server never intended. Asserted on both clients because the two were written
	separately and a number like this is exactly what drifts.
	"""
	from afya.sync.service import backoff_delay_s
	assert backoff_delay_s(30) == 600.0, 'the server cap moved; update both clients and this gate'
	for path in (ANDROID_CLIENT, SWIFT_CLIENT):
		text = path.read_text(encoding='utf-8')
		assert '600' in text, f'{path.name} does not cap the backoff at the server figure'


def test_the_audit_row_resolves() -> None:
	"""The row this unit closed, and the reference it cites, walked rather than read."""
	from afya.content_audit.service import content_report
	report = content_report()
	acc = next(f for f in report.features if f.feature_id == 'ACC-003')
	row = next(b for b in acc.bullets if b.bullet.startswith('Local-first'))
	assert row.kind == 'carried', row.note
	assert resolves(row.carried_by), f'the row cites {row.carried_by}, which does not resolve'
	assert not any('ACC-003' in u for u in report.unresolved), 'the ACC-003 reference rotted'


def test_no_spec_feature_code_reaches_the_store_contract() -> None:
	"""The standing rule: feature ids are backend identifiers and must not reach anything served."""
	assert not re.search(r'\bACC-\d{3}\b', CONTRACT.read_text(encoding='utf-8'))
