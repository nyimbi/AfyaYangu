"""§6.2.3's timestamp rule — the age line the section says builds trust, computed rather than stored.

§6.2.3 is one sentence: "**Timestamp everything.** 'Updated 2 hours ago' builds trust; undated
content destroys it." It was the only one of §6.2's ten principles with nothing behind it.
`ContentItem` carried `reviewed_on_iso`, which is a *date* and belongs to §6.5's review cycle; the
library route served `{slug,title,body,harmony_tag,lang,answers_rank}` and no time at all, so the
section's own example — "Updated 2 hours ago" — could not be rendered by any client. §8.5 lists
"Last updated timestamp" among the dashboard's displayed fields and `dashboard()` answers a county
with no signal with a defaulted row, which reads as live data.

**The age is derived from a stamp, never stored as a phrase.** `updated_at_ms` is an instant the
server records; the line is computed against the caller's clock. A stored "2 hours ago" is wrong an
hour later, and the section exists precisely so that the age a reader is shown can be believed.

**Freshness is not a field the writer may set.** `ContentItem.updated_at_ms` exists because it is
the storage shape, and `upsert_content` overwrites it with the service's own clock on every write —
so a body that arrives carrying a stamp is stored under the server's, not the writer's. The
*sentence* is not a field at all: nothing a caller posts can become the age a reader is shown.

**The line is built server-side because USSD and SMS have nowhere to build it.** §5.4 names "a
single content repository — one source of truth for all messaging" as what the channels share, and
only one of WhatsApp, USSD, SMS and radio can do date arithmetic. So the arithmetic happens here and
the same sentence can be handed to whichever channel is serving it, rather than each channel
rendering the age its own way from an instant it may not even receive.

**An undated item is withheld, not served blank.** Undated content is the thing the section calls
destructive, so it is dropped from the library and named by `undated()` for the reviewer — the same
shape as §6.2.4's withholding of an untranslated life-safety item, and for the same reason: a gap
someone can see beats a message that misleads.

The automated staleness alert §23.2 asks for is §6.5's review cadence and is not restated here. Two
definitions of stale would disagree the first time either one moved.
"""
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# A stamp of zero is "no time recorded", and it is a distinct state from any real instant. An item
# carrying it is undated, which is what §6.2.3 forbids serving — so the sentinel has to be a value no
# clock can produce rather than a plausible-looking default.
UNDATED_MS = 0

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000

# §6.2.3's own example is "Updated 2 hours ago", so the bands run minutes -> hours -> days and the
# hours band is the one the section prints. Under a minute the only honest reading is "just now": a
# device clock and a server clock are not the same clock, and "0 minutes ago" claims a precision
# neither one has.
#
# The Swahili pairs are singular/plural because the noun class governs the verb — "saa 1 iliyopita"
# but "saa 2 zilizopita". A single template would print "saa 1 zilizopita", which is not Swahili.
AGE_TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
	'en': {
		'minutes': ('{n} minute ago', '{n} minutes ago'),
		'hours': ('{n} hour ago', '{n} hours ago'),
		'days': ('{n} day ago', '{n} days ago'),
	},
	'sw': {
		'minutes': ('dakika {n} iliyopita', 'dakika {n} zilizopita'),
		'hours': ('saa {n} iliyopita', 'saa {n} zilizopita'),
		'days': ('siku {n} iliyopita', 'siku {n} zilizopita'),
	},
}

JUST_NOW: dict[str, str] = {'en': 'just now', 'sw': 'sasa hivi'}

# §6.2.3's example line, as a template. English second per §6.2.4's "local language first": the
# Swahili is the primary string and the English is the fallback, which is why `lang` has no default
# on the public functions below.
FRESHNESS_TEMPLATE: dict[str, str] = {'en': 'Updated {age}', 'sw': 'Imesasishwa {age}'}

_BAND_UNIT_MS: dict[str, int] = {'minutes': MINUTE_MS, 'hours': HOUR_MS, 'days': DAY_MS}


class ServedFreshness(BaseModel):
	"""When a thing was last updated, as both a relative and an absolute fact.

	Both travel because they fail in opposite directions. "Updated 2 hours ago" is unreadable the
	moment a page is cached offline, which §16.4's content caching makes routine; an ISO instant is
	unreadable at a glance. A client that has one and not the other is a client that is either
	imprecise or wrong.

	`updated_at_ms` is `gt=0`, so an undated stamp cannot be represented at all — §6.2.3's rule as a
	type rather than as a check someone has to remember.
	"""
	model_config = MODEL_CONFIG
	updated_at_ms: int = Field(gt=0)
	updated_iso: str
	age_ms: int = Field(ge=0)
	age_label: str
	line: str


def band_for(age_ms: int) -> str:
	assert age_ms >= 0, 'an age is not negative'
	if age_ms < HOUR_MS:
		return 'minutes'
	return 'hours' if age_ms < DAY_MS else 'days'


def instant_iso(at_ms: int) -> str:
	"""The stamp as a UTC ISO instant, second-granular.

	UTC and not local time: the reader may be in Nairobi and the server anywhere, and an instant
	rendered in the server's zone is one nobody can compare against their own clock.
	"""
	assert at_ms > UNDATED_MS, 'an undated stamp has no instant'
	return datetime.fromtimestamp(at_ms // 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def instant_ms(iso: str) -> int:
	"""An ISO instant as the epoch milliseconds `instant_iso` renders back — the inverse of that pair.

	The `Z` suffix is stripped before parsing because `datetime.fromisoformat` did not accept it
	before 3.11 and the corpus writes every stamp that way; a naive stamp is read as UTC for the
	reason `instant_iso` gives, that an instant rendered in the server's zone is one nobody can
	compare against their own clock.

	This exists because `midnight_ms` is *not* it. That function reads a **bare date** — a §6.5
	review date, a seed row — and truncates anything longer to its first ten characters, so passing a
	full instant to it returns midnight of that day and two stamps hours apart become one number. A
	`SyncOp.client_ts` is an instant, so truncating it there puts a different reading of the same
	fact next to the `at_iso` in the payload.
	"""
	text = iso.strip().replace('Z', '+00:00')
	parsed = datetime.fromisoformat(text)
	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return int(parsed.timestamp() * 1000)


def midnight_ms(iso: str) -> int:
	"""A bare ISO date as the instant it begins, in UTC.

	A corpus dated by day — §6.5's review date, a seed row — still has to carry §6.2.3's stamp, which
	is an instant. Midnight UTC is the only reading of a bare date that does not depend on the
	server's timezone, the same choice `afya.operations.service._instant` makes for §24.8's deadlines.

	For a full instant use `instant_ms`: this truncates to the first ten characters, which is the
	right answer for a date and the wrong one for a timestamp. `LocationService._window` calls it on
	an instant deliberately — a 21-day window is measured in days, so the day boundary is what it
	wants — which is why the difference is documented here rather than asserted.
	"""
	return int(datetime.fromisoformat(iso[:10]).replace(tzinfo=timezone.utc).timestamp() * 1000)


def iso_add_days(iso: str, days: int) -> str:
	"""A civil date or instant shifted by whole days, as a bare `YYYY-MM-DD`.

	The inverse of `midnight_ms`, and the pair is why this lives here rather than in a fifth copy:
	`afya.monitoring`, `afya.maternal`, `afya.chronic` and `afya.women` each keep a private
	`_iso_add_days`/`_add_days`, which is four answers to "what is 21 days after this date". A
	schedule is a date arithmetic problem, and the module that already converts between the two
	representations of a day is where the arithmetic belongs.

	Day-granular and timezone-free on purpose: `days` is a count of *days of a window*, not of
	24-hour periods, so a window that opens at 23:00 and one that opens at 01:00 on the same date
	ask their day-3 question on the same date. That is what a person reading "day 3" understands.
	"""
	year, month, day = (int(part) for part in iso[:10].split('-'))
	return (datetime(year, month, day) + timedelta(days=days)).strftime('%Y-%m-%d')


def age_label(at_ms: int, now_ms: int, lang: str = 'en') -> str:
	"""§6.2.3's relative age, from two instants.

	A stamp ahead of `now_ms` reads as "just now" rather than as a negative age. Device and server
	clocks drift, and "-1 hours ago" on a screen is a worse lie than rounding to the present —
	it names a direction that is not real. The clamp is the band boundary itself: a negative age is
	below a minute, so it lands in `just now` without a second guard that no input could reach.
	"""
	assert lang in AGE_TEMPLATES, f'unsupported lang {lang}'
	assert at_ms > UNDATED_MS, 'an undated stamp has no age'
	age = now_ms - at_ms
	if age < MINUTE_MS:
		return JUST_NOW[lang]
	band = band_for(age)
	n = max(1, age // _BAND_UNIT_MS[band])
	singular, plural = AGE_TEMPLATES[lang][band]
	return (singular if n == 1 else plural).format(n=n)


def freshness_line(at_ms: int, now_ms: int, lang: str = 'en') -> str:
	"""The sentence §6.2.3 prints: "Updated 2 hours ago"."""
	assert lang in FRESHNESS_TEMPLATE, f'unsupported lang {lang}'
	return FRESHNESS_TEMPLATE[lang].format(age=age_label(at_ms, now_ms, lang))


def freshness(at_ms: int, now_ms: int, lang: str = 'en') -> ServedFreshness:
	return ServedFreshness(
		updated_at_ms=at_ms,
		updated_iso=instant_iso(at_ms),
		age_ms=max(0, now_ms - at_ms),
		age_label=age_label(at_ms, now_ms, lang),
		line=freshness_line(at_ms, now_ms, lang),
	)
