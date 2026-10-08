# service.py — Afya Yangu backend per docs/spec.md
from pydantic import BaseModel, ConfigDict

class HealthResponse(BaseModel):
	model_config = ConfigDict(extra='forbid')
	status: str
