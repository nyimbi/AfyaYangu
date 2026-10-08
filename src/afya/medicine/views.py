"""Medicine domain models (MED-001..004, §18.7 PPB)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class VerifyRequest(BaseModel):
	model_config = MODEL_CONFIG
	batch_number: str = Field(min_length=4, max_length=40)
	gtin: str = Field(pattern=r'^\d{6,14}$')


class VerifyResult(BaseModel):
	model_config = MODEL_CONFIG
	genuine: bool
	source: str
	notes: str | None = None


class InteractionPair(BaseModel):
	model_config = MODEL_CONFIG
	a: str
	b: str
	severity: str = Field(pattern=r'^(minor|moderate|major)$')
	note: str


class DoseRequest(BaseModel):
	model_config = MODEL_CONFIG
	drug: str
	weight_kg: float = Field(gt=1, le=300)
	mg_per_kg: float = Field(gt=0, le=100)


class DoseResult(BaseModel):
	model_config = MODEL_CONFIG
	drug: str
	total_mg: float
	warns: list[str]


class StockReport(BaseModel):
	model_config = MODEL_CONFIG
	report_id: str = Field(pattern=r'^STOCK-[A-Z0-9]{6,}$')
	facility_id: str
	drug: str
	in_stock: bool
	reported_by: str