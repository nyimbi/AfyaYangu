"""Internal gRPC surface (spec §15.5) — real server, real channel, no mocks."""
import grpc
import pytest

from afya.grpc_api import afya_internal_pb2 as pb
from afya.grpc_api import afya_internal_pb2_grpc as pb_grpc
from afya.grpc_api.service import AfyaInternalService, serve
from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.service import build_services
from afya.triage.service import TriageService


@pytest.fixture
async def server():
	services = build_services()
	services['registry'] = FeatureRegistry()
	services['triage'] = TriageService(services['registry'])  # type: ignore[arg-type]
	srv = await serve(services, 0)
	yield srv, int(getattr(srv, 'afya_port'))
	await srv.stop(None)


@pytest.fixture
async def stub(server):
	srv, port = server
	channel = grpc.aio.insecure_channel(f'localhost:{port}')
	await channel.channel_ready()
	yield pb_grpc.AfyaInternalStub(channel)
	await channel.close()


async def test_health_returns_api_version(stub: pb_grpc.AfyaInternalStub) -> None:
	out = await stub.Health(pb.HealthRequest())
	assert out.status == 'ok' and out.api_version == '2.0.0' and out.tier4_active is False


async def test_lookup_feature_known_and_not_found(stub: pb_grpc.AfyaInternalStub) -> None:
	spec = await stub.LookupFeature(pb.LookupFeatureRequest(feature_id='TRI-001'))
	assert spec.id == 'TRI-001' and spec.tier == 1 and 'native' in spec.channels
	with pytest.raises(grpc.aio.AioRpcError) as exc:
		await stub.LookupFeature(pb.LookupFeatureRequest(feature_id='ZZZ-999'))
	assert exc.value.code() is grpc.StatusCode.NOT_FOUND


async def test_lookup_feature_resolves_spec_alias(stub: pb_grpc.AfyaInternalStub) -> None:
	# REC-006 is the spec id for blood donor matching; the shipped id is REC-004.
	spec = await stub.LookupFeature(pb.LookupFeatureRequest(feature_id='REC-006'))
	assert spec.id == 'REC-004'


async def test_list_features_filters_by_tier(stub: pb_grpc.AfyaInternalStub) -> None:
	all_out = await stub.ListFeatures(pb.ListFeaturesRequest(tier=0))
	assert len(all_out.features) > 50
	t1 = await stub.ListFeatures(pb.ListFeaturesRequest(tier=1))
	assert t1.features and all(f.tier == 1 for f in t1.features)
	assert len(t1.features) < len(all_out.features)
	# Dormant tier-4 features are withheld from the all-tier listing.
	assert not any(f.tier == 4 for f in all_out.features)


async def test_list_features_tier4_withheld_until_activated(server) -> None:
	srv, port = server
	registry = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=True, flag_enabled=True))
	active = grpc.aio.server()
	pb_grpc.add_AfyaInternalServicer_to_server(AfyaInternalService({'registry': registry, 'triage': TriageService(registry)}), active)
	active_port = active.add_insecure_port('[::]:0')
	await active.start()
	channel = grpc.aio.insecure_channel(f'localhost:{active_port}')
	await channel.channel_ready()
	try:
		out = await pb_grpc.AfyaInternalStub(channel).ListFeatures(pb.ListFeaturesRequest(tier=4))
		assert out.features and all(f.tier == 4 for f in out.features)
	finally:
		await channel.close()
		await active.stop(None)


async def test_triage_febrile_case(stub: pb_grpc.AfyaInternalStub) -> None:
	out = await stub.Triage(pb.TriageRequest(symptoms=['fever', 'headache', 'vomiting'], age_years=30, duration_days=2))
	assert out.urgency == 'medium' and out.recommendation
	assert 'vomiting' in out.red_flags


async def test_triage_bleeding_is_high(stub: pb_grpc.AfyaInternalStub) -> None:
	out = await stub.Triage(pb.TriageRequest(symptoms=['bleeding'], age_years=40, pregnant=False, duration_days=1))
	assert out.urgency == 'high'


async def test_activation_status_reports_unmet_keys_when_dormant(stub: pb_grpc.AfyaInternalStub) -> None:
	out = await stub.ActivationStatus(pb.ActivationStatusRequest())
	assert out.tier4_active is False
	assert set(out.unmet_keys) == {'pheoc_authorization', 'dpia_review', 'feature_flag'}
