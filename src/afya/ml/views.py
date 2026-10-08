"""On-device-provenance ML assets — YAMNet (AudioSet 521-class) via ONNX for acoustic cough detection (SENS-002)."""
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)
MODELS_DIR = Path(__file__).resolve().parents[3] / 'models' / 'cough'


class CoughVerdict(BaseModel):
	model_config = MODEL_CONFIG
	cough_frames: int = Field(ge=0)
	cough_events: int = Field(ge=0)
	dominant_class: str
	band: str = Field(pattern=r'^(normal|watch|alert)$')


import csv


def class_map(path: Path) -> list[str]:
	with open(path) as fh:
		return [row['display_name'] for row in csv.DictReader(fh)]