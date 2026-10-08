"""Unified POI model (OSM-normalised) + direction guidance — 'how do I get there?'
Map UI opens the platform maps app (Apple/Google) via deep link; no embedded SDK dependency.
"""
from enum import Enum

from afya.facilities.service import haversine_km

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class PlaceKind(str, Enum):
	pharmacy = 'pharmacy'
	clinic = 'clinic'
	hospital = 'hospital'
	school = 'school'
	treatment_unit = 'treatment_unit'
	testing_site = 'testing_site'
	vaccination_point = 'vaccination_point'
	water_point = 'water_point'


class Place(BaseModel):
	model_config = MODEL_CONFIG
	osm_id: str = Field(pattern=r'^(N|W|R)\d+$')
	kind: PlaceKind
	name: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	county: str | None = None
	opening_hours: str | None = None
	phone: str | None = None
	website: str | None = None


class Directions(BaseModel):
	model_config = MODEL_CONFIG
	place_id: str
	place_name: str
	distance_km: float
	bearing_deg: int
	walk_minutes: int
	guidance: str
	apple_maps_url: str
	google_maps_url: str


class PlacesService:
	def __init__(self) -> None:
		self._places: dict[str, Place] = {}
		assert self._places == {}

	async def upsert(self, p: Place) -> int:
		assert p.osm_id, 'osm id required'
		self._places[p.osm_id] = p
		return len(self._places)

	def nearest(self, lat: float, lon: float, kinds: set[PlaceKind] | None = None, limit: int = 5) -> list[tuple[Place, float]]:
		from afya.facilities.service import haversine_km
		pool = [p for p in self._places.values() if not kinds or p.kind in kinds]
		assert pool, 'no places imported yet'
		return sorted(((p, haversine_km(lat, lon, p.lat, p.lon)) for p in pool), key=lambda x: x[1])[:limit]

	def count(self) -> int:
		return len(self._places)

	@staticmethod
	def directions(place: Place, lat: float, lon: float) -> Directions:
		import math
		dist = haversine_km(lat, lon, place.lat, place.lon)
		dy = 110_574.0 * (place.lat - lat)
		dx = 111_320.0 * (place.lon - lon) * math.cos(math.radians(lat))
		bearing = int(((math.degrees(math.atan2(dx, dy)) % 360) // 5) * 5)
		cardinal = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][min(7, (bearing + 22) // 45 % 8)]
		walk = int(dist * 12)  # ~12 min per km average
		return Directions(
			place_id=place.osm_id, place_name=place.name,
			distance_km=round(dist, 2), bearing_deg=bearing, walk_minutes=walk,
			guidance=f'{place.name} is {dist:.1f} km {cardinal} of you (~{walk} min walk). Follow the map link for step-by-step navigation.',
			apple_maps_url=f'https://maps.apple.com/?daddr={place.lat},{place.lon}&dirflg=w',
			google_maps_url=f'https://www.google.com/maps/dir/?api=1&destination={place.lat},{place.lon}',
		)
