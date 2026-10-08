"""OpenStreetMap Overpass API client — import pharmacies/clinics/hospitals/schools as Places (§18.5 open data)."""
from typing import Any

import httpx

from afya.places.views import Place, PlaceKind
from pydantic import ValidationError

_KIND_MAP: dict[str, PlaceKind] = {
	'pharmacy': PlaceKind.pharmacy, 'clinic': PlaceKind.clinic, 'hospital': PlaceKind.hospital,
	'school': PlaceKind.school, 'doctors': PlaceKind.treatment_unit, 'water_point': PlaceKind.water_point,
}
_BBOX_PAD = 0.25  # ° around county center


def overpass_query(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
	assert min_lat < max_lat and min_lon < max_lon, 'bbox order'
	return f"""[out:json][timeout:25];
(
	node["amenity"~"^(pharmacy|clinic|hospital|school|doctors)$"]({min_lat},{min_lon},{max_lat},{max_lon});
	way["amenity"~"^(pharmacy|clinic|hospital|school|doctors)$"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out center tags 200;"""


def _center(el: dict[str, Any]) -> tuple[float, float] | None:
	if 'lat' in el and 'lon' in el:
		return (float(el['lat']), float(el['lon']))
	if 'center' in el:
		return (float(el['center']['lat']), float(el['center']['lon']))
	return None


def parse_overpass(payload: dict[str, Any]) -> list[Place]:
	"""OSM elements -> Places; skips nameless/mis-tagged; bounded output."""
	out: list[Place] = []
	for el in payload.get('elements', []):
		tags = el.get('tags', {})
		name = tags.get('name')
		osm_id = f"{'N' if el['type'] == 'node' else ('W' if el['type'] == 'way' else 'R')}{el['id']}"
		geom = _center(el)
		kind = _KIND_MAP.get(tags.get('amenity', ''))
		if not (name and geom and kind):
			continue
		try:
			out.append(Place(
				osm_id=osm_id, kind=kind, name=name, lat=geom[0], lon=geom[1],
				opening_hours=tags.get('opening_hours'), phone=tags.get('phone'), website=tags.get('website'),
			))
		except ValidationError:
			continue
	assert len(out) <= 400, 'import bounded'
	return out


class OverpassClient:
	def __init__(self, base_url: str = 'https://overpass-api.de/api', client: httpx.AsyncClient | None = None) -> None:
		self._base = base_url.rstrip('/')
		self._http = client or httpx.AsyncClient(timeout=30)
		assert self._base.startswith('http'), 'valid url'

	async def fetch_places(self, center_lat: float, center_lon: float) -> list[Place]:
		resp = await self._http.post(
			f'{self._base}/interpreter',
			headers={'User-Agent': 'AfyaYangu/2.0 (health companion; contact: moh-dha@health.go.ke)'},
			data={'data': overpass_query(center_lat - _BBOX_PAD, center_lon - _BBOX_PAD, center_lat + _BBOX_PAD, center_lon + _BBOX_PAD)},
		)
		resp.raise_for_status()
		return parse_overpass(resp.json())