"""Records service — wallet CRUD, EPI completeness, growth flags, med reminders."""
import hashlib
import hmac
from datetime import date, datetime, timezone

from afya.logmixin import LogMixin
from afya.records.growth import (
	MODERATE_Z, SEVERE_Z, classify, height_reference, height_z, weight_reference, weight_z,
)
from afya.records.growth_standards import WEIGHT_FOR_AGE, HEIGHT_FOR_AGE, LENGTH_FOR_AGE, STANDING_FROM_MONTHS
from afya.records.views import (
	EPI_SCHEDULE, BackupEnvelope, ExportDocument, GrowthAssessment, GrowthChart, GrowthFlag,
	GrowthRecord, ImmunisationRecord, LabResult, MedReminder, Prescription, ShareGrant, ShareView,
	TimelineEntry, VaccinationCertificate, WALLET_DOC_KINDS, WalletContentsReport, WalletDocument,
	WalletItem, WalletMember,
)

MAJORITY_YEARS = 18
"""§17.6's age of majority. Children under 18 require guardian consent for an identified profile
and a guardian controls their records; at 18 control transfers to the individual."""

MAX_WALLET_PROFILES = 10
"""§9.2 REC-001: "Multiple profiles (up to 10)". A number in the section, enforced at enrolment."""

# §9.2 REC-001's "Contents:" bullets, in the section's order, each paired with the model that
# carries it. The section names eight documents a wallet holds; a wallet is what a person opens when
# they have lost the paper, so an item with nothing behind it is a document the app promises to keep
# and cannot. `module` is None where nothing models it — reported, not fabricated.
WALLET_ITEMS: tuple[tuple[str, str | None, str | None], ...] = (
	('Immunisation cards (photo or digital)', 'afya.records.views:ImmunisationRecord',
		'the EPI schedule and the doses given are modelled; the card itself is filed as a `WalletDocument` with a `media_ref` to the photograph'),
	('ANC cards', 'afya.maternal.views:ANCRecord',
		'the eight ANC contacts are modelled against the visit schedule, and the card is filed as a wallet document'),
	('Lab results', 'afya.records.views:LabResult', None),
	('Prescriptions', 'afya.records.views:Prescription', None),
	('Discharge summaries', 'afya.records.views:WalletDocument',
		'the `discharge` kind of the document envelope: a facility writes one and the person files it, which is how the other seven arrive too'),
	('Referral letters', 'afya.intermediaries.views:Referral',
		'the referral is modelled for code attribution, and the letter is filed as the `referral` kind of a wallet document'),
	('Insurance/SHA details', 'afya.records.views:InsuranceCard',
		'the SHA member number is stored as a hash, so the card cannot be reconstructed from it; the card itself is filed as an `insurance` document'),
	('Clinic appointment cards', 'afya.facilities.views:Booking',
		'the booking is modelled and the printed card is filed as an `appointment` document'),
)



def _parse_iso(value: str) -> datetime:
	"""A timestamp as a comparable datetime.

	Accepting a bare date as well as a full timestamp, because the two arrive from different callers
	— a route takes `2026-10-12T09:00:00` and a person types `2026-10-12` — and comparing the two
	as strings puts an expiry at midnight *before* an issue time on the same day, which would refuse
	a share issued the morning it expires.
	"""
	text = value.strip().replace('Z', '+00:00')
	try:
		parsed = datetime.fromisoformat(text)
	except ValueError as exc:
		raise AssertionError(f'{value!r} is not a date or timestamp') from exc
	return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _lab_document(res: LabResult) -> WalletDocument:
	"""A `LabResult` as a wallet document, with its own fields kept in `payload`.

	The typed row is what `labs()` returns and the document is what the timeline, search and export
	read. Keeping the typed fields in `payload` is what makes one envelope lossless rather than a
	second, poorer copy — eight nullable columns on `WalletDocument` would have been the alternative
	and would have made every kind's fields optional for every other kind.
	"""
	return WalletDocument(
		doc_id=f'lab-{res.member_ref}-{res.performed_iso}-{res.test}',
		member_ref=res.member_ref, kind='lab',
		title=f'{res.test} result', occurred_iso=res.performed_iso,
		detail=f'{res.value}{" " + res.unit if res.unit else ""} ({res.flag})',
		payload=res.model_dump(mode='json'),
	)


def _prescription_document(rx: Prescription) -> WalletDocument:
	"""A `Prescription` as a wallet document. A pharmacy reads the drug, the days and the refills."""
	return WalletDocument(
		doc_id=f'rx-{rx.member_ref}-{rx.prescribed_iso}-{rx.drug}',
		member_ref=rx.member_ref, kind='prescription',
		title=f'Prescription: {rx.drug}', occurred_iso=rx.prescribed_iso,
		detail=f'{rx.days} days, {rx.refills_left} refills left',
		payload=rx.model_dump(mode='json'),
	)


def _immunisation_document(rec: ImmunisationRecord) -> WalletDocument:
	"""An `ImmunisationRecord` as a wallet document — the card §9.2's first bullet names.

	The doc id carries the dose, because a child receives the same vaccine more than once and an id
	built from member, vaccine and date alone would collide on a catch-up visit that gave two doses.
	"""
	return WalletDocument(
		doc_id=f'imm-{rec.member_ref}-{rec.vaccine}-{rec.dose_no}',
		member_ref=rec.member_ref, kind='immunisation',
		title=f'{rec.vaccine} dose {rec.dose_no}', occurred_iso=rec.given_iso,
		detail=f'Batch {rec.batch}' if rec.batch else '',
		payload=rec.model_dump(mode='json'),
	)


def age_years(dob_iso: str, today: date) -> int:
	"""Whole years between a date of birth and today, from the dates rather than from a constant.

	The earlier version of this computed months as `(2026 - year) * 12 + (10 - month)`, which is
	the same arithmetic with the clock written into it: correct for an October 2026 run and wrong
	everywhere else, and wrong in the one direction that matters. It made a child born in 2008 read
	as 18 forever, so §17.6's transfer of control never fired; it also aged nobody, so a 17-year-old
	enrolled in 2026 was still a minor in 2030.
	"""
	year, month, day = (int(p) for p in dob_iso.split('-')[:3])
	born = date(year, month, day)
	return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class RecordsService(LogMixin):
	def __init__(self) -> None:
		self._members: dict[str, WalletMember] = {}
		self._imm: list[ImmunisationRecord] = []
		self._reminders: list[MedReminder] = []
		self._labs: list[LabResult] = []
		self._rx: list[Prescription] = []
		self._growth: list[GrowthRecord] = []
		# The wallet's documents. §9.2's eight kinds live here, not in eight lists: the timeline,
		# the search, the export and the share are all operations over this one set, and they were
		# four features only because the set did not exist.
		self._documents: list[WalletDocument] = []
		self._grants: dict[str, ShareGrant] = {}
		assert self._members == {} and self._documents == [] and self._grants == {}

	async def add_member(self, member: WalletMember, today: date | None = None) -> WalletMember:
		"""Enrol a member, and set the flag §17.6 hangs ownership on.

		`today` is optional so a caller that has no clock (a test, a replay) can say what day it is;
		the default reads the real one, because a service that refuses to know the date cannot
		implement an age-dependent rule at all.
		"""
		today = today or date.today()
		if member.guardian_ref and member.guardian_ref != member.member_ref:
			# §9.2 REC-001: "Multiple profiles (up to 10)". The cap is on the wallet, so it is
			# enforced where a member joins one rather than reported later — a wallet that accepted
			# an eleventh profile would be a section claim nothing kept.
			held = sum(1 for m in self._members.values() if m.guardian_ref == member.guardian_ref)
			assert held < MAX_WALLET_PROFILES, (
				f'§9.2 caps a wallet at {MAX_WALLET_PROFILES} profiles; {member.guardian_ref} already holds {held}')
		if age_years(member.dob_iso, today) < MAJORITY_YEARS:
			member.is_minor = True
			assert member.guardian_ref, 'minors require guardian_ref (spec 17.6)'
			assert member.guardian_ref != member.member_ref, 'self-guardianship invalid'
		else:
			# §17.6 "At age 18, control transfers to the individual." A member who is already 18 is
			# their own controller, so a guardian recorded on them is not an owner — it is a
			# guardian_ref that `owns` would honour and must not.
			member.is_minor = False
			assert member.guardian_ref in (None, member.member_ref), \
				'an adult controls their own records (spec 17.6)'
		self._members[member.member_ref] = member
		return member

	def immunisation_gaps(self, member_ref: str, today: date | None = None) -> list[str]:
		assert member_ref in self._members, 'unknown member'
		given = {(r.vaccine, r.dose_no) for r in self._imm if r.member_ref == member_ref}
		age = age_years(self._members[member_ref].dob_iso, today or date.today()) * 12
		return [
			f'{vac} dose {dose}'
			for vac, doses in EPI_SCHEDULE.items()
			for dose in doses
			if dose <= age and (vac, dose) not in given
		]

	def owns(self, subject_ref: str, member_ref: str, today: date | None = None) -> bool:
		"""Whether `subject_ref` may read `member_ref`'s records: a person reads their own, and a
		guardian reads the *minors* in their wallet (§17.6). This is the single ownership rule every
		family-record route binds to, so a route cannot invent a looser one.

		The minor test is the load-bearing part and it used to be absent. §17.6's fourth line — "At
		age 18, control transfers to the individual" — makes guardianship a relation with an end
		date, and a rule that read only `guardian_ref == subject_ref` gave a guardian perpetual
		access to a child's record. A 30-year-old's health history was readable by whoever enrolled
		them as a minor, which is the failure the line exists to prevent.

		The age is computed from the date of birth on every call rather than read off `is_minor`.
		That flag records what was true when the member was enrolled, and a flag is the wrong place
		for a rule whose whole content is that it stops being true: a wallet enrolled in 2026 would
		carry a seventeen-year-old as a minor in 2030, and the transfer would happen only if someone
		re-enrolled them. `today` is optional for the same reason it is on `add_member`.

		The reverse is not granted: a member does not read their guardian's records, and no route
		here offers that, so nothing depends on it.
		"""
		if subject_ref == member_ref:
			return True
		member = self._members.get(member_ref)
		if member is None or member.guardian_ref != subject_ref:
			return False
		return age_years(member.dob_iso, today or date.today()) < MAJORITY_YEARS

	def transfers_at(self, member_ref: str, today: date | None = None) -> str | None:
		"""§17.6's transfer date, or None for a member who is already their own controller.

		A route serving a guardian needs to answer "when does this stop" as well as "may I read it",
		and the answer is a date rather than a boolean: a guardian told "no" without a date has no
		way to know whether the record moved or they mistyped a reference.
		"""
		assert member_ref in self._members, 'unknown member'
		member = self._members[member_ref]
		if age_years(member.dob_iso, today or date.today()) >= MAJORITY_YEARS:
			return None
		year, month, day = (int(p) for p in member.dob_iso.split('-')[:3])
		return date(year + MAJORITY_YEARS, month, day).isoformat()

	def assert_owns(self, subject_ref: str, member_ref: str) -> None:
		assert self.owns(subject_ref, member_ref), 'these records belong to someone else'

	async def record_immunisation(self, rec: ImmunisationRecord) -> None:
		self._imm.append(rec)
		if rec.member_ref in self._members:
			await self.add_document(_immunisation_document(rec))
		self._log_info('immunisation recorded', member=rec.member_ref, vaccine=rec.vaccine)

	def growth_flag(self, rec: GrowthRecord) -> GrowthFlag:
		"""The one-word verdict, kept because callers hold it; `assess_growth` is the real answer.

		This used to be the whole feature: a table of low/high weights and median heights at six
		ages, typed into the function. It is now a summary of the WHO z-score, so the word and the
		number cannot disagree — and the two classifications do differ, which is the point. At 12
		months a boy weighing 7.7 kg is exactly -2 SD by WHO and was `normal` under the band, because
		the band's low bound was 7.0 * 0.75.
		"""
		assessment = self.assess_growth(rec)
		worst = min(assessment.weight_z, assessment.height_z)
		if worst < SEVERE_Z:
			flag = 'underweight' if assessment.weight_z <= assessment.height_z else 'stunted'
		elif worst < MODERATE_Z:
			flag = 'underweight' if assessment.weight_z <= assessment.height_z else 'stunted'
		else:
			flag = 'normal'
		return GrowthFlag(member_ref=rec.member_ref, flag=flag)

	def assess_growth(self, rec: GrowthRecord) -> GrowthAssessment:
		"""§REC-003's verdict, against the WHO standard at the child's own age.

		The z-scores travel with the classification because the word alone cannot be acted on: a
		child at -2.1 and a child at -4.0 are both undernourished and need different things, and only
		the number separates them.
		"""
		weight_z_score = weight_z(rec.sex, rec.age_months, rec.weight_kg)
		height_z_score = height_z(rec.sex, rec.age_months, rec.height_cm)
		weight_median = {row[0]: row[2] for row in WEIGHT_FOR_AGE[rec.sex]}[rec.age_months]
		height_table = LENGTH_FOR_AGE if rec.age_months < STANDING_FROM_MONTHS else HEIGHT_FOR_AGE
		height_median = {row[0]: row[2] for row in height_table[rec.sex]}[rec.age_months]
		return GrowthAssessment(
			member_ref=rec.member_ref, age_months=rec.age_months, sex=rec.sex,
			weight_z=round(weight_z_score, 3), height_z=round(height_z_score, 3),
			weight_status=classify(weight_z_score), height_status=classify(height_z_score),
			weight_median_kg=weight_median, height_median_cm=height_median,
			standard='WHO Child Growth Standards (2006), LMS parameters',
		)

	def growth_chart(self, member_ref: str, sex: str) -> GrowthChart:
		"""§REC-003's "percentile charts": the child's series against the WHO reference lines.

		Both come from the same LMS parameters, so the line a point is plotted against and the
		z-score reported for that point are one computation read two ways. A chart drawn from WHO's
		printed rounded SD columns and a verdict computed from the transform would disagree in the
		third decimal, which is exactly where a classification boundary sits.
		"""
		assert member_ref in self._members, 'unknown member'
		points = [r for r in self._growth if r.member_ref == member_ref]
		return GrowthChart(
			member_ref=member_ref, sex=sex,
			weight_reference=weight_reference(sex), height_reference=height_reference(sex),
			weight_points=[{'month': r.age_months, 'kg': r.weight_kg} for r in points],
			height_points=[{'month': r.age_months, 'cm': r.height_cm} for r in points],
		)

	async def record_growth(self, rec: GrowthRecord) -> GrowthAssessment:
		"""Store the measurement and return the verdict. A chart needs a series, not one reading."""
		assert rec.member_ref in self._members, 'unknown member'
		self._growth.append(rec)
		await self.add_document(WalletDocument(
			doc_id=f'growth-{rec.member_ref}-{rec.age_months}', member_ref=rec.member_ref,
			kind='appointment', title=f'Growth check at {rec.age_months} months',
			occurred_iso=date.today().isoformat(),
			detail=f'{rec.weight_kg} kg, {rec.height_cm} cm',
		))
		return self.assess_growth(rec)

	def wallet_contents(self) -> WalletContentsReport:
		"""§9.2 REC-001's eight "Contents" bullets, each crossed against what carries it.

		The section lists eight things a family health wallet holds. Seven have a model in this repo
		(immunisation cards, ANC cards, lab results, prescriptions, insurance details — five, in
		fact, once the ANC record in `maternal` and the insurance card here are both counted), and
		the eighth, discharge summaries, has one now: the `discharge` kind of `WalletDocument`, which
		is where a person files the paper a facility handed them. `unbacked_items` is empty as a
		result, and the field stays because the report's job is to say what is unbacked on the day it
		is asked, not to remember that it once was.

		`resolves` is False for a `module:attr` that does not import, which is a different finding
		from `module is None`: the first is a reference that rotted, the second is a document nobody
		built.
		"""
		from afya.refs import resolves
		items: list[WalletItem] = []
		for item, module, note in WALLET_ITEMS:
			items.append(WalletItem(item=item, module=module,
				resolves=resolves(module) if module else False, note=note))
		return WalletContentsReport(
			items=items,
			unbacked_items=[i.item for i in items if i.module is None],
			max_profiles=MAX_WALLET_PROFILES,
			max_profiles_enforced=True,
		)

	def wallet(self, guardian_ref: str) -> dict[str, object]:
		assert guardian_ref in self._members, 'unknown guardian'
		kids = [m for m in self._members.values() if m.guardian_ref == guardian_ref]
		return {
			'guardian': self._members[guardian_ref].model_dump(mode='json'),
			'members': [m.model_dump(mode='json') for m in kids],
			'gaps': {m.member_ref: self.immunisation_gaps(m.member_ref) for m in kids},
		}

	async def add_reminder(self, reminder: MedReminder) -> MedReminder:
		self._reminders.append(reminder)
		return reminder

	def reminders_for(self, member_ref: str) -> list[MedReminder]:
		return [r for r in self._reminders if r.member_ref == member_ref]

	def __init_labs(self) -> None:
		self._labs: list[LabResult] = []
		self._rx: list[Prescription] = []

	async def add_lab(self, res: LabResult) -> None:
		if not hasattr(self, '_labs'):
			self.__init_labs()
		self._labs.append(res)
		if res.flag == 'critical':
			self._log_warn('critical lab result', test=res.test)
		if res.member_ref in self._members:
			await self.add_document(_lab_document(res))

	def labs(self, member_ref: str) -> list[LabResult]:
		if not hasattr(self, '_labs'):
			self.__init_labs()
		return [l for l in self._labs if l.member_ref == member_ref]

	async def add_prescription(self, rx: Prescription) -> None:
		if not hasattr(self, '_rx'):
			self.__init_labs()
		self._rx.append(rx)
		if rx.member_ref in self._members:
			await self.add_document(_prescription_document(rx))

	def prescriptions(self, member_ref: str) -> list[Prescription]:
		if not hasattr(self, '_rx'):
			self.__init_labs()
		return [r for r in self._rx if r.member_ref == member_ref]

	# --- §9.2/§10.1: the wallet's documents, and the operations over them ------------------------

	async def add_document(self, doc: WalletDocument) -> WalletDocument:
		"""File one document in the wallet.

		`doc_id` is asserted unique rather than overwritten. A wallet that silently replaced a
		document on a repeated id would lose the earlier one at the moment a retry happened — and a
		wallet exists precisely so that a lost document is not lost.
		"""
		assert doc.member_ref in self._members, f'{doc.member_ref} is not in any wallet'
		assert all(d.doc_id != doc.doc_id for d in self._documents), f'{doc.doc_id} is already filed'
		self._documents.append(doc)
		self._log_info('wallet document filed', member=doc.member_ref, kind=doc.kind)
		return doc

	def documents(self, member_ref: str, kinds: list[str] | None = None) -> list[WalletDocument]:
		"""One member's documents, newest first, optionally narrowed to some of §9.2's kinds."""
		assert member_ref in self._members, 'unknown member'
		held = [d for d in self._documents if d.member_ref == member_ref]
		if kinds:
			held = [d for d in held if d.kind in kinds]
		return sorted(held, key=lambda d: (d.occurred_iso, d.doc_id), reverse=True)

	def timeline(self, subject_ref: str, today: date | None = None) -> list[TimelineEntry]:
		"""§10.1's "Timeline view of all health events", across everyone in the caller's wallet.

		The timeline is a sort over the documents rather than a second store, which is why it cannot
		drift from the wallet: a separate event log would have to be written on every path that files
		a document, and the path that forgot would produce a timeline missing an event the wallet
		holds.

		It covers the wallet's *members*, which is the set `owns` already defines — the caller and
		the minors in their care. A member who has turned 18 drops out on their own birthday,
		because the ownership rule is asked per member rather than once for the wallet.
		"""
		entries: list[TimelineEntry] = []
		for member in self._members.values():
			if not self.owns(subject_ref, member.member_ref, today):
				continue
			for doc in self.documents(member.member_ref):
				entries.append(TimelineEntry(
					occurred_iso=doc.occurred_iso, kind=doc.kind, title=doc.title,
					who=member.member_ref, doc_id=doc.doc_id, facility_id=doc.facility_id,
				))
		return sorted(entries, key=lambda e: (e.occurred_iso, e.doc_id), reverse=True)

	def search(self, subject_ref: str, query: str) -> list[WalletDocument]:
		"""§REC-001's "Search", over every document the caller may read.

		Searched across the whole wallet rather than one member at a time, because the question a
		person brings to a wallet is "where is that card", not "where is that card for this child".
		The match is case-insensitive across the title, the detail and the kind, which is what a
		person actually remembers: the word on the card, not the field it was filed under.
		"""
		assert query.strip(), 'an empty search matches everything, which is not a search'
		needle = query.strip().lower()
		out: list[WalletDocument] = []
		for member in self._members.values():
			if not self.owns(subject_ref, member.member_ref):
				continue
			for doc in self.documents(member.member_ref):
				haystack = f'{doc.title} {doc.detail} {doc.kind}'.lower()
				if needle in haystack:
					out.append(doc)
		return out

	# --- §REC-001/§10.1 sharing: one grant, two features ------------------------------------------

	async def grant_share(self, grant: ShareGrant) -> ShareGrant:
		"""Issue a time-limited share.

		§REC-001's "secure link" and §10.1's "share with a specific provider for a limited time" are
		the same grant: the second names a recipient and narrows the kinds. Written as two features
		they would have produced two expiry rules, and the one that dropped the expiry would be the
		one nobody noticed.

		The expiry is checked here and not defaulted. A grant whose `expires_iso` does not parse, or
		which has already passed at issue, is a share that never was one — and a caller who receives
		a grant id for an expired grant has been told they shared something they did not.
		"""
		assert grant.member_ref in self._members, 'unknown member'
		assert grant.issued_by, 'a share must name who issued it (§17.1 accountability)'
		issued = _parse_iso(grant.issued_iso)
		expires = _parse_iso(grant.expires_iso)
		assert expires > issued, (
			f'a share must end after it begins: {grant.issued_iso} to {grant.expires_iso}'
		)
		assert all(k in WALLET_DOC_KINDS for k in grant.kinds), (
			f'{sorted(set(grant.kinds) - set(WALLET_DOC_KINDS))} is not a wallet document kind'
		)
		assert grant.grant_id not in self._grants, f'{grant.grant_id} is already a grant'
		self._grants[grant.grant_id] = grant
		self._log_info('wallet shared', member=grant.member_ref, recipient=grant.recipient,
		               expires=grant.expires_iso)
		return grant

	def share_view(self, grant_id: str, at_iso: str) -> ShareView:
		"""What a provider reads through a grant, refused once the grant has ended.

		The refusal is the feature. A time-limited share whose reader is not actually stopped at the
		limit is an unlimited share with an expiry field on it, and the field is the part that gets
		tested while the limit is the part that matters.
		"""
		assert grant_id in self._grants, 'unknown grant'
		grant = self._grants[grant_id]
		assert not grant.revoked, 'this share was withdrawn'
		at = _parse_iso(at_iso)
		assert at <= _parse_iso(grant.expires_iso), (
			f'this share ended on {grant.expires_iso}'
		)
		return ShareView(
			grant_id=grant.grant_id, member_ref=grant.member_ref, recipient=grant.recipient,
			expires_iso=grant.expires_iso,
			documents=self.documents(grant.member_ref, grant.kinds or None),
		)

	async def revoke_share(self, grant_id: str) -> ShareGrant:
		"""§17.1's withdrawal, applied to a share: consent that cannot be taken back is not consent."""
		assert grant_id in self._grants, 'unknown grant'
		grant = self._grants[grant_id]
		self._grants[grant_id] = grant.model_copy(update={'revoked': True})
		return self._grants[grant_id]

	def grants_for(self, member_ref: str) -> list[ShareGrant]:
		"""Every share ever issued over this member, live and dead.

		Dead grants are returned because a person asking "who has seen my record" is asking about
		the past, and a list that dropped the expired ones would answer with the wrong tense.
		"""
		return sorted((g for g in self._grants.values() if g.member_ref == member_ref),
		              key=lambda g: g.issued_iso, reverse=True)

	def grants_for_member(self, grant_id: str) -> ShareGrant:
		"""One grant by its id, for the caller that has to check who it belongs to before acting.

		`revoke_share` takes an id alone, which is right for the service — the id is the whole
		handle — and wrong for a route, where an id is a value a caller can guess. The route reads
		the grant through this, checks ownership, and only then withdraws it.
		"""
		assert grant_id in self._grants, 'unknown grant'
		return self._grants[grant_id]

	# --- §REC-001/§10.1 export and backup ---------------------------------------------------------

	def export(self, subject_ref: str, member_ref: str, fmt: str, at_iso: str) -> ExportDocument:
		"""§REC-001's "PDF export" and §10.1's "Export to PDF for school, travel, or employment".

		The PDF is rendered by `afya.records.pdf` here rather than by a library, because none is
		installed and a route returning a `.pdf` filename with JSON inside it would be exactly the
		claim-with-nothing-behind-it this module keeps finding. The JSON form is served too, because
		a school office and a software system want different things from the same export.
		"""
		assert fmt in ('pdf', 'json'), f'{fmt} is not an export format'
		self.assert_owns(subject_ref, member_ref)
		docs = self.documents(member_ref)
		member = self._members[member_ref]
		who = member.name or member_ref
		if fmt == 'json':
			import json
			content = json.dumps({
				'member_ref': member_ref, 'name': member.name, 'dob_iso': member.dob_iso,
				'exported_at': at_iso,
				'documents': [d.model_dump(mode='json') for d in docs],
			}, indent=2, ensure_ascii=False)
			media, suffix = 'application/json', 'json'
		else:
			from afya.records.pdf import render
			lines: list[str] = [f'{who} — date of birth {member.dob_iso}', f'Exported {at_iso}', '']
			if not docs:
				lines.append('No documents are filed in this wallet yet.')
			for doc in docs:
				lines.append(f'{doc.occurred_iso}  {doc.title}')
				if doc.detail:
					lines.extend(f'    {part}' for part in doc.detail.split('\n'))
				if doc.facility_id:
					lines.append(f'    Facility: {doc.facility_id}')
				lines.append('')
			content = render(f'Health record — {who}', lines).decode('latin-1')
			media, suffix = 'application/pdf', 'pdf'
		return ExportDocument(
			export_id=f'EXP-{member_ref}-{at_iso}', member_ref=member_ref, format=fmt,
			media_type=media, filename=f'health-record-{member_ref}.{suffix}',
			document_count=len(docs), content=content,
		)

	async def backup(self, subject_ref: str, member_ref: str, at_iso: str,
	                 consented: bool) -> BackupEnvelope:
		"""§REC-001's "Optional encrypted cloud backup" and §10.1's "Encrypted cloud backup".

		Two things make this a backup rather than a claim.

		It refuses without the subject's consent. `cloud_backup` is a §SEC-001 category with its own
		revocation consequences, and a backup that ran regardless would be the consent label with
		nothing enforcing it — the shape the audit row named.

		It states its own cipher. `retention.encryption_posture()` asserts `cloud_backup_e2e=True`
		and `user_held_key=True` as design properties, and §SEC-003 asks for both. This deployment
		holds no key it does not also hold the data with, so a service here cannot implement
		end-to-end encryption and must not say it has: `cipher` is `none` and `user_held_key` is
		False, and the finding stays open rather than being closed by a boolean three modules away.
		"""
		assert consented, 'encrypted cloud backup needs the cloud_backup consent (spec SEC-001)'
		self.assert_owns(subject_ref, member_ref)
		docs = self.documents(member_ref)
		import json
		blob = json.dumps([d.model_dump(mode='json') for d in docs],
		                  sort_keys=True, separators=(',', ':')).encode()
		return BackupEnvelope(
			backup_id=f'BAK-{member_ref}-{at_iso}', subject_ref=subject_ref, created_iso=at_iso,
			document_count=len(docs), member_count=1,
			digest_sha256=hashlib.sha256(blob).hexdigest(), cipher='none', user_held_key=False,
			consent_category='cloud_backup', documents=docs,
		)

	# --- §10.1 vaccination certificates -----------------------------------------------------------

	def vaccination_certificate(self, subject_ref: str, member_ref: str, purpose: str,
	                            at_iso: str, secret: str) -> VaccinationCertificate:
		"""§10.1's certificate, rendered from the dose log rather than from a second store.

		A certificate that kept its own copy of the doses could disagree with the record it
		certifies, and the disagreement would surface at a border post. So the doses are read from
		`_imm` and the certificate is a view.

		The seal is an HMAC over the certificate's canonical fields, keyed on the deployment secret.
		It is not a signature by a health authority and the payload says so in `issuer` and `note`:
		this deployment holds no signing key issued by MoH, and a document that implied one would be
		forged authority rather than a tamper-evident seal.
		"""
		assert purpose in ('travel', 'school', 'employment'), f'{purpose} is not a purpose'
		self.assert_owns(subject_ref, member_ref)
		member = self._members[member_ref]
		doses = [
			{'vaccine': r.vaccine, 'dose': str(r.dose_no), 'given_iso': r.given_iso,
			 'batch': r.batch or ''}
			for r in sorted((r for r in self._imm if r.member_ref == member_ref),
			                key=lambda r: (r.given_iso, r.vaccine, r.dose_no))
		]
		canonical = '|'.join([
			member_ref, member.dob_iso, purpose, at_iso,
			';'.join(f'{d["vaccine"]}:{d["dose"]}:{d["given_iso"]}' for d in doses),
		])
		signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
		return VaccinationCertificate(
			certificate_id=f'VAC-{member_ref}-{at_iso}', member_ref=member_ref,
			holder_name=member.name or member_ref, dob_iso=member.dob_iso, purpose=purpose,
			doses=doses, issued_iso=at_iso, signature=signature,
			issuer='Afya Yangu (deployment seal, not a Ministry of Health signature)',
			note=(
				'This certificate reproduces the doses recorded in this wallet. The seal shows the '
				'deployment issued these fields unaltered; it does not attest to anything beyond them.'
			),
		)

	def certificate_seal_holds(self, cert: VaccinationCertificate, secret: str) -> bool:
		"""Whether a certificate's seal matches its fields — the check a clinic would run.

		Present so the seal is a mechanism rather than a string: a certificate whose signature is
		never verified is a random hex digest printed at the bottom of a page.
		"""
		canonical = '|'.join([
			cert.member_ref, cert.dob_iso, cert.purpose, cert.issued_iso,
			';'.join(f'{d["vaccine"]}:{d["dose"]}:{d["given_iso"]}' for d in cert.doses),
		])
		expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
		return hmac.compare_digest(expected, cert.signature)
