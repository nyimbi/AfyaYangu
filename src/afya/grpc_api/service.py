"""gRPC servicer for the internal service-to-service surface (spec §15.5).

The servicer is a thin adapter: every RPC delegates to the same services the FastAPI
front door uses (FeatureRegistry, TriageService), so a second wire protocol cannot
drift from the first. Nothing here reimplements triage or the tier-4 gate.
"""
from collections.abc import Mapping

import grpc

from afya.grpc_api.afya_internal_pb2 import (
	ActivationStatusRequest, ActivationStatusResponse, FeatureSpec, HealthRequest, HealthResponse,
	ListFeaturesRequest, ListFeaturesResponse, LookupFeatureRequest, TriageRequest, TriageResponse,
)
from afya.grpc_api.afya_internal_pb2_grpc import AfyaInternalServicer, add_AfyaInternalServicer_to_server
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry, Tier
from afya.triage.service import TriageService
from afya.triage.views import TriageInput

# The triage RPC carries no thermometer reading, so the algorithm is entered at the
# standard adult temperature. Fever is expressed through the symptom list instead.
DEFAULT_TEMPERATURE_C = 36.5
API_VERSION = '2.0.0'


def _to_proto(spec: object) -> FeatureSpec:
	"""FeatureSpec registry model -> wire message. `object` because the registry model and
	the generated message share a name but no base; fields are read duck-typed."""
	assert spec is not None
	out = FeatureSpec(id=spec.id, name=spec.name, tier=int(spec.tier), channels=list(spec.channels))  # type: ignore[attr-defined]
	assert out.id == spec.id  # type: ignore[attr-defined]
	return out


class AfyaInternalService(LogMixin, AfyaInternalServicer):
	"""Async servicer. Subclasses the generated base so `add_..._to_server` accepts it."""

	def __init__(self, services: Mapping[str, object]) -> None:
		self._registry: FeatureRegistry = services['registry']  # type: ignore[assignment]
		self._triage: TriageService = services['triage']  # type: ignore[assignment]
		assert isinstance(self._registry, FeatureRegistry) and isinstance(self._triage, TriageService), 'registry and triage required'
		self._log_info('grpc servicer ready', tier4_active=self._registry.tier4_active())

	async def Health(self, request: HealthRequest, context: grpc.aio.ServicerContext) -> HealthResponse:
		assert request is not None
		out = HealthResponse(status='ok', api_version=API_VERSION, tier4_active=self._registry.tier4_active())
		assert out.status == 'ok'
		return out

	async def LookupFeature(self, request: LookupFeatureRequest, context: grpc.aio.ServicerContext) -> FeatureSpec:
		assert request.feature_id, 'feature_id required'
		try:
			spec = self._registry.get(request.feature_id)
		except KeyError:
			self._log_warn('grpc feature lookup miss', feature_id=request.feature_id)
			await context.abort(grpc.StatusCode.NOT_FOUND, f'no such feature: {request.feature_id}')
		out = _to_proto(spec)
		assert out.id == spec.id
		return out

	async def ListFeatures(self, request: ListFeaturesRequest, context: grpc.aio.ServicerContext) -> ListFeaturesResponse:
		assert request.tier >= 0, 'tier is a non-negative int; 0 means all'
		if request.tier == 0:
			available = self._registry.available()
		else:
			available = [f for f in self._registry.by_tier(Tier(request.tier)) if f.tier is not Tier.tier4 or self._registry.tier4_active()]
		out = ListFeaturesResponse(features=[_to_proto(f) for f in available])
		assert all(request.tier == 0 or f.tier == request.tier for f in out.features)
		return out

	async def Triage(self, request: TriageRequest, context: grpc.aio.ServicerContext) -> TriageResponse:
		assert request.age_years >= 0 and request.duration_days >= 0, 'age and duration are non-negative'
		inp = TriageInput(symptoms=list(request.symptoms), temperature_c=DEFAULT_TEMPERATURE_C)
		result = self._triage.assess(inp)
		red_flags = sorted({'bleeding', 'vomiting', 'diarrhoea'} & set(request.symptoms))
		out = TriageResponse(urgency=result.risk_level.value, recommendation=result.recommendation, red_flags=red_flags)
		assert out.urgency and out.recommendation, 'urgency and recommendation required'
		return out

	async def ActivationStatus(self, request: ActivationStatusRequest, context: grpc.aio.ServicerContext) -> ActivationStatusResponse:
		assert request is not None
		activation = self._registry.activation
		out = ActivationStatusResponse(tier4_active=self._registry.tier4_active(), unmet_keys=list(activation.unmet_keys()))
		assert out.tier4_active == (not out.unmet_keys)
		return out


async def serve(services: Mapping[str, object], port: int) -> grpc.aio.Server:
	"""Start an async gRPC server bound to `port` (0 = ephemeral) and register the servicer."""
	assert isinstance(services, Mapping) and port >= 0, 'services mapping and non-negative port required'
	server = grpc.aio.server()
	add_AfyaInternalServicer_to_server(AfyaInternalService(services), server)
	bound = server.add_insecure_port(f'[::]:{port}')
	assert bound > 0, 'failed to bind gRPC port'
	await server.start()
	# grpc.aio.Server exposes no port accessor, so the bound port (the OS-chosen one when
	# port=0) is carried on the object for callers that need to dial it back.
	server.afya_port = bound  # type: ignore[attr-defined]
	return server
