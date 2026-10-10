"""Demo backend on :8123 seeded with facilities, OSM places, alerts, family wallet, CHW tasks.
Run: uv run python examples/serve_demo.py  [--port 8123]
Places come from models/places_fixture.json (live Overpass capture subset); for a full live import:
	POST http://localhost:8123/places/import-osm?county_lat=-1.286&county_lon=36.817
"""
import asyncio
import json
import os
from pathlib import Path

import uvicorn

from afya.alerts.views import CommunityAlert, WaterQuality
from afya.channels.views import ChwTask
from afya.facilities.views import Facility, FacilityKind
from afya.grpc_api.service import serve as serve_grpc
from afya.integrations.overpass import parse_overpass
from afya.records.views import WalletMember
from afya.registry.service import Tier4Activation
from afya.service import build_services, create_app
import sys

sys.argv.append('')


async def seed(svc: dict[str, object]) -> None:
	svc['registry'].__init__(Tier4Activation(authorized_by_pheoc=False, dpia_reviewed=True, flag_enabled=False))  # noqa: PLC2801
	fac = svc['facilities']
	for f in (
		Facility(facility_id='F-KNH', name='Kenyatta National Hospital (ED)', kind=FacilityKind.ed, county='Nairobi', lat=-1.3001, lon=36.8066, ed_status='operational — 41 beds', hours24=True),
		Facility(facility_id='F-KIL', name='Kilimani 24h Pharmacy', kind=FacilityKind.pharmacy, county='Nairobi', lat=-1.2915, lon=36.7812, hours24=True, crowdload=20),
		Facility(facility_id='F-RUA', name='Ruaka Health Centre', kind=FacilityKind.treatment_unit, county='Kiambu', lat=-1.2130, lon=36.7970, ed_status='open, queue 12'),
	):
		await fac.upsert(f)
	fixture = json.loads((Path(__file__).resolve().parents[1] / 'models' / 'places_fixture.json').read_text())
	for p in parse_overpass(fixture):
		await svc['places'].upsert(p)  # type: ignore[union-attr]
	await svc['alerts'].issue(CommunityAlert(alert_id='AL-DEMO00000001', kind='flood', county='Nairobi', headline='Heavy rains expected', body='Avoid floodwater. Boil drinking water. Report diarrhoea to 719.', issued_by='County'))
	await svc['alerts'].issue(CommunityAlert(alert_id='AL-SCHOOL000001', kind='school_closure', county='Nairobi', headline='Schools along Mathare closed', body='Classes suspended around the Mathare catchment on Health Ministry advice.', issued_by='County'))
	records = svc['records']
	await records.add_member(WalletMember(member_ref='GUARD1', dob_iso='1990-05-14'))
	await records.add_member(WalletMember(member_ref='JUNIOR1', dob_iso='2025-04-02', guardian_ref='GUARD1'))
	channels = svc['channels']
	await channels.assign_chw_task(ChwTask(task_id='T-FU-001', chw_ref='CHW1', community='Mathare 3B', kind='followup'))
	await channels.assign_chw_task(ChwTask(task_id='T-REF-001', chw_ref='CHW1', community='Kosovo A', kind='referral'))


async def run() -> None:
	"""REST on `port`, gRPC beside it on `port + 1` (§15.5), both over the same service objects."""
	svc = build_services(db_path='/tmp/afya_demo.db')
	await seed(svc)
	app = create_app(svc)
	port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8123
	grpc_port = int(os.environ.get('AFYA_GRPC_PORT', str(port + 1)))
	server = await serve_grpc(svc, grpc_port)
	config = uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning')
	http = uvicorn.Server(config)
	print(f'REST  http://127.0.0.1:{port}  (docs at /v1/docs)\ngRPC  afya.internal.v1 on 127.0.0.1:{grpc_port}')
	try:
		await http.serve()
	finally:
		await server.stop(grace=0)


def main() -> None:
	asyncio.run(run())


if __name__ == '__main__':
	main()
