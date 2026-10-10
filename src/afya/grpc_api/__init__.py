"""Internal gRPC surface (spec §15.5). Named `grpc_api` to avoid shadowing the `grpc` package."""
from afya.grpc_api import afya_internal_pb2, afya_internal_pb2_grpc
from afya.grpc_api.service import API_VERSION, AfyaInternalService, serve

__all__ = ['API_VERSION', 'AfyaInternalService', 'afya_internal_pb2', 'afya_internal_pb2_grpc', 'serve']
