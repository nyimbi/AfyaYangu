"""Records domain models — family health wallet, immunisations, growth monitoring (REC-001..003)."""
from pydantic import BaseModel, ConfigDict, Field

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class WalletMember(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	name: str | None = None
	dob_iso: str
	is_minor: bool = False
	guardian_ref: str | None = None


class ImmunisationRecord(BaseModel):
	"""One dose that was given — the durable record, and the only one there is.

	`dose_no` is 0-indexed because Kenya's EPI schedule has a real dose 0: OPV0 is the birth dose,
	given within the first two weeks. The field was `ge=1`, so the wallet refused to record the one
	dose every child in the country receives on their first day.

	`card_photo_sha256` is §MON-001's "(with photo of card)" and §9.2's "Immunisation cards (photo
	or digital)", as a digest rather than an image. §18.7's evidence rule and this wallet both keep
	uploads behind a reference, so what travels here is the hash a later reader can check a
	photograph against — the photo itself lives in the media store like every other upload. Optional,
	because a dose given at a campaign post may have no card, and requiring one would refuse the
	dose rather than the photograph.
	"""

	model_config = MODEL_CONFIG
	member_ref: str
	vaccine: str
	dose_no: int = Field(ge=0, le=4)
	given_iso: str
	batch: str | None = None
	card_photo_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


# Kenya's EPI schedule: vaccine -> [(dose_no, due_age_weeks)]. This is the one copy.
#
# It used to exist twice, and the two disagreed. `records` held `dict[str, list[int]]` naming `RV1`
# and `MMR` with IPV at dose 2; `monitoring` held ages and named `RV` and `Measles-Rubella` with IPV
# at dose 1. A dose recorded through the child tracker was therefore invisible to the wallet's gap
# check — the two were keyed on different spellings of the same vaccine — and a certificate and a
# gap list could describe the same child differently. The schedule with ages is the richer fact and
# dose numbers are a projection of it, so it lives here and `monitoring` re-exports it.
#
# Ages are the *earliest* week a dose is due, which is what the EPI schedule is: BCG and OPV0 at
# birth, the six-week set, then nine, ten and a half months, then measles-rubella at nine months and
# again at eighteen. HPV is the two-dose course for girls, ten years apart by a year.
EPI_SCHEDULE: dict[str, list[tuple[int, int]]] = {
	'BCG': [(1, 0)],
	'OPV': [(0, 0), (1, 6), (2, 10), (3, 14)],
	'PCV10': [(1, 6), (2, 10), (3, 14)],
	'DPT-HepB-Hib': [(1, 6), (2, 10), (3, 14)],
	'RV': [(1, 6), (2, 10)],
	'IPV': [(1, 14)],
	'Measles-Rubella': [(1, 39), (2, 78)],
	'Yellow Fever': [(1, 39)],
	'HPV': [(1, 520), (2, 546)],
}


class GrowthRecord(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	age_months: int = Field(ge=0, le=60)
	weight_kg: float = Field(gt=0, le=60)
	height_cm: float = Field(gt=20, le=140)
	# The WHO standards are tabulated separately for boys and girls, and a chart drawn from the
	# wrong column is wrong by more than the deficit it reports — so the sex is required rather than
	# defaulted. `boy`/`girl` are WHO's own column names, not a statement about gender.
	sex: str = Field(default='boy', pattern=r'^(boy|girl)$')
	# The other two measurements §REC-003 names. Optional because a clinic visit may take only some
	# of them, and required would refuse a weight-only visit — but head circumference is the one
	# measurement a growth tracker takes in the first year, so its absence is visible.
	head_circumference_cm: float | None = Field(default=None, gt=20, le=60)
	muac_mm: float | None = Field(default=None, gt=50, le=300)


class GrowthFlag(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	flag: str = Field(pattern=r'^(normal|underweight|stunted)$')


# §REC-003's "milestone checklists", from Annex 9 of Kenya's National Guideline for Integrated
# Management of Acute Malnutrition (2020) — archived at `sources/kenya-imam-guidelines/` and
# checksummed in `sources/INDEX.md`. The guideline prints the checklist as an ASSESS/CLASSIFY chart
# and the bands are its own, including the fact that they meet at their endpoints: "0-2 MONTHS" and
# "2-4 MONTHS" both name month 2.
#
# (band_label, first_month, last_month, ((slug, label), ...)) — the label is the guideline's wording
# verbatim, because it is the sentence a caregiver is asked to agree or disagree with. The slug is
# this deployment's own handle and never reaches a screen.
MILESTONES: tuple[tuple[str, int, int, tuple[tuple[str, str], ...]], ...] = (
	('0-2 months', 0, 1, (
		('social_smile', 'Social smile (baby smiles back)'),
		('follows_colourful_object', 'Baby follows a colourful object dangled before their eyes'),
	)),
	('2-4 months', 2, 3, (
		('head_upright', 'Holds the head upright'),
		('follows_object_or_face', 'Follows the object or face with their eyes'),
		('turns_to_sound', 'Turns the head or responds in any other way to sound'),
		('smiles_when_spoken_to', 'Smiles when you speak'),
	)),
	('4-6 months', 4, 5, (
		('rolls_over', 'Rolls over'),
		('reaches_and_grasps', 'Reaches for and grasps objects with hand'),
		('takes_objects_to_mouth', 'Takes objects to her mouth'),
		('babbles', 'Babbles (makes sounds)'),
	)),
	('6-9 months', 6, 8, (
		('sits_without_support', 'Sits without support'),
		('passes_object_hand_to_hand', 'Moves object from one hand to the other'),
		('repeats_syllables', 'Repeats syllables (bababa, mamama)'),
		('plays_peekaboo', 'Plays peek-a-boo (hide and seek)'),
	)),
	('9-12 months', 9, 11, (
		('steps_with_support', 'Takes steps with support'),
		('pincer_grasp', 'Picks up small object or string with 2 fingers'),
		('says_two_or_three_words', 'Says 2-3 words'),
		('imitates_gestures', 'Imitates simple gestures (claps hands, bye)'),
	)),
	('12-18 months', 12, 17, (
		('walks_without_support', 'Walks without support'),
		('drinks_from_cup', 'Drinks from a cup'),
		('says_seven_to_ten_words', 'Says 7-10 words'),
		('points_to_body_parts', 'Points to some body parts on request'),
	)),
	('18-24 months', 18, 23, (
		('kicks_ball', 'Kicks a ball'),
		('builds_tower_of_three', 'Builds tower with 3 blocks or small boxes'),
		('points_at_pictures', 'Points at pictures on request'),
		('speaks_in_short_sentences', 'Speaks in short sentences'),
	)),
	('24 months and older', 24, 60, (
		('jumps', 'Jumps'),
		('dresses_self', 'Undresses and dresses themselves'),
		('says_first_name', 'Says first name, tells short story'),
		('plays_with_other_children', 'Interested in playing with other children'),
	)),
)


class MilestoneCheck(BaseModel):
	"""What a caregiver reports the child can do, so the guideline's chart can classify it.

	`present` is the milestones observed now and `lost` the ones the child used to do and no longer
	does. The second is a separate input rather than something inferred from history because the
	guideline's own DELAY rule names regression as a criterion in its own right — "Regression of
	milestones" — and regression is precisely the thing a caregiver notices and a series of
	checklists does not, since an earlier checklist recorded the milestone as present.

	`checked_earlier` says the caller also asked about the bands before this one. Annex 9's DELAY
	rule needs a gap in an earlier band as well as the current one, and a caller who did not ask
	cannot supply one — so this defaults to False and the earlier bands are only read when it is set.
	"""

	model_config = MODEL_CONFIG
	member_ref: str
	age_months: int = Field(ge=0, le=60)
	present: list[str] = Field(default_factory=list)
	lost: list[str] = Field(default_factory=list)
	checked_earlier: bool = False


class MilestoneReport(BaseModel):
	"""§REC-003's milestone checklist, classified the way Annex 9 classifies it.

	`status` is the guideline's own three words. `missing_earlier` is reported even when `status` is
	`normal`, because Annex 9's NORMAL rule reads "All milestones for the current age group are
	present" and says nothing about earlier groups — a child can lag one skill from an earlier band
	while having every milestone for their own, and the guideline treats the current band as the
	operative screen. The gap is served rather than dropped, so the classification and the finding
	are both visible.

	`earlier_checked` says whether the earlier bands were assessed at all, and it is load-bearing.
	Annex 9's DELAY rule needs an absence from an *earlier* band as well as the current one, and a
	caregiver reading a checklist is normally asked about the child's own age group. Reading the
	earlier bands as absent by default would classify every child who was asked only about their own
	age as delayed, which is a false positive in the direction that sends families to a clinic. So
	the earlier gap is only counted when the caller said they checked, and `missing_earlier` is
	empty otherwise.
	"""

	model_config = MODEL_CONFIG
	member_ref: str
	age_months: int = Field(ge=0, le=60)
	band: str
	expected: list[dict[str, str]]
	expected_earlier: list[dict[str, str]]
	earlier_checked: bool
	missing: list[str]
	missing_earlier: list[str]
	lost: list[str]
	# `unanswered` is the read half's status: the checklist served for a caregiver to answer, before
	# any answer exists. Without it, `milestones_for` classified an empty answer set and returned
	# `alert` — "one or more skills for this age are not there yet" — for a child nobody had looked
	# at, which is Annex 9's ALERT read as a finding about the child rather than as the instruction
	# to go and assess them. It is the same failure `earlier_checked` guards against, one level up:
	# silence about a child is not evidence about the child, and a screen may not turn the absence
	# of a measurement into a measurement.
	status: str = Field(pattern=r'^(unanswered|normal|alert|delay)$')
	guidance: str

MEDICATION_SCHEDULE: dict[str, list[int]] = {}


class MedReminder(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	drug: str
	times_per_day: int = Field(ge=1, le=6)
	started_iso: str
	channel: str = Field(pattern=r'^(sms|native|whatsapp)$')

# --- Records wallet artifacts: lab results, prescriptions, insurance card (family vault) ---

class LabResult(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	test: str = Field(pattern=r'^(mRDT|widal|hba1c|fbc|viral_load|glucose_f|bp|other)$')
	value: str
	unit: str | None = None
	flag: str = Field(default='unknown', pattern=r'^(normal|abnormal|critical|unknown)$')
	performed_iso: str


class Prescription(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	drug: str
	days: int = Field(ge=1, le=180)
	refills_left: int = Field(ge=0, le=10)
	prescribed_iso: str


class InsuranceCard(BaseModel):
	model_config = MODEL_CONFIG
	member_ref: str
	sha_member_no_hash: str = Field(pattern=r'^[0-9a-f]{8,64}$')
	product: str = Field(pattern=r'^(SHIF|TAIFA|EDU|SHCP)$')
	active: bool


class WalletItem(BaseModel):
	"""One of §9.2's eight "Contents" bullets, and what in the repo carries it.

	`module` is a `module:attr` reference to the model that holds the document, or None where the
	section names a document nothing models. Both are reported: the section lists eight things a
	wallet holds, and a wallet that holds four of them while the payload says "wallet" is the
	claim-with-nothing-behind-it this module keeps finding.
	"""

	model_config = MODEL_CONFIG
	item: str
	module: str | None = None
	resolves: bool = False
	note: str | None = None


class WalletContentsReport(BaseModel):
	model_config = MODEL_CONFIG
	items: list[WalletItem]
	unbacked_items: list[str]
	max_profiles: int
	max_profiles_enforced: bool


# --- §9.2 REC-001/§10.1 REC-002: the wallet as documents, and what can be done with them --------

WALLET_DOC_KINDS: tuple[str, ...] = (
	'immunisation', 'anc', 'lab', 'prescription', 'discharge', 'referral', 'insurance', 'appointment',
)
"""§9.2's eight "Contents" bullets, as the kinds a wallet document can be.

The order is the section's, and the tuple is the closed set: `WalletDocument.kind` is checked
against it, so a ninth kind cannot be invented by a caller and cannot appear in a timeline the
export does not know how to render.
"""


class WalletDocument(BaseModel):
	"""One item in the wallet, whichever of §9.2's eight kinds it is.

	Before this there were five separate row types — `ImmunisationRecord`, `LabResult`,
	`Prescription`, `InsuranceCard` and a `Booking` living in another module — and §10.1's "Timeline
	view of all health events", "Search", "Export to PDF" and "Share" would each have had to be
	written once per type. They are not eight features. They are four operations over one set, and
	the set is what was missing.

	`occurred_iso` is the clinical date and `kind` is what the document is; together they are the
	timeline's sort key, which is why the timeline can be a sort rather than a second store.

	`media_ref` is where a photograph lives, and there is no bytes field. A wallet that held image
	blobs would put every family's documents in the row a query returns, and the repo already keeps
	uploads behind a reference — `ContentItem.media_ref` is the same pattern for the same reason.
	"""

	model_config = MODEL_CONFIG
	doc_id: str = Field(default_factory=lambda: 'DOC-' + uuid7str().replace('-', '').upper()[:12])
	member_ref: str = Field(min_length=1)
	kind: str = Field(pattern=r'^(immunisation|anc|lab|prescription|discharge|referral|insurance|appointment)$')
	title: str = Field(min_length=1)
	occurred_iso: str = Field(min_length=1)
	# Free text a search reads. It is what the document says, in the words of whoever recorded it,
	# because the words a person remembers are rarely the field names.
	detail: str = ''
	facility_id: str | None = None
	# The file, if this document has one — a photographed card, a scanned discharge summary.
	media_ref: str | None = None
	captured_iso: str | None = None
	# The kind's own fields, as the typed model wrote them. This is what makes one envelope
	# lossless: a lab result's `test`/`value`/`unit` live here rather than in eight nullable columns
	# on this model, and `RecordsService.labs()` rebuilds the `LabResult` from them. Without it the
	# envelope would be a second, lossier copy of the typed rows — which is the failure of having
	# two stores, wearing the costume of having one.
	payload: dict[str, object] = {}


class TimelineEntry(BaseModel):
	"""One point on §10.1's timeline: the document, and which member's record it is part of.

	`who` is carried because a family timeline without it is a list of events belonging to nobody,
	which is unreadable the moment a wallet holds more than one person.
	"""

	model_config = MODEL_CONFIG
	occurred_iso: str
	kind: str
	title: str
	who: str
	doc_id: str
	facility_id: str | None = None


class GrowthAssessment(BaseModel):
	"""§REC-003's verdict on one measurement, against the WHO standard rather than a band.

	The z-scores travel with the flag because "underweight" alone cannot be acted on: a child at
	-2.1 and a child at -4.0 are both "underweight" and need different things, and only the number
	tells them apart.
	"""

	model_config = MODEL_CONFIG
	member_ref: str
	age_months: int = Field(ge=0, le=60)
	sex: str = Field(pattern=r'^(boy|girl)$')
	weight_z: float
	height_z: float
	weight_status: str = Field(pattern=r'^(normal|moderate|severe|above)$')
	height_status: str = Field(pattern=r'^(normal|moderate|severe|above)$')
	weight_median_kg: float
	height_median_cm: float
	# The two measurements §REC-003 names beside weight and height. Each is `None` when the visit
	# did not take it — a weight-only visit is a real visit — and the z-score and the category are
	# `None` with it rather than defaulted to a normal reading, which would turn "not measured" into
	# "measured and fine".
	head_circumference_z: float | None = None
	head_circumference_status: str | None = Field(default=None, pattern=r'^(normal|moderate|severe|above)$')
	muac_z: float | None = None
	# The IMAM category, in Kenya's own vocabulary rather than WHO's. `muac_category` is a programme
	# admission decision and `muac_z` is a distance from the reference median; they answer different
	# questions and one does not stand in for the other. `muac_alert` carries the guideline's
	# admission rule when the category is one a health worker must act on, and is `None` otherwise.
	muac_category: str | None = Field(default=None, pattern=r'^(sam|mam|at_risk|normal)$')
	muac_alert: str | None = None
	standard: str


class GrowthChart(BaseModel):
	"""§REC-003's "percentile charts": the child's own series against the WHO reference lines.

	The reference lines are computed from the same LMS parameters as the child's points, so the line
	they are plotted against and the z-score reported for them cannot disagree.
	"""

	model_config = MODEL_CONFIG
	member_ref: str
	sex: str = Field(pattern=r'^(boy|girl)$')
	weight_reference: list[dict[str, float]]
	height_reference: list[dict[str, float]]
	weight_points: list[dict[str, float]]
	height_points: list[dict[str, float]]


class ShareGrant(BaseModel):
	"""§10.1's time-limited share: who may read what, until when, and what they were told.

	One mechanism serves REC-001's "Share via secure link" and REC-002's "Share with a specific
	provider for a limited time". They are the same grant; the second names a recipient and a
	scope. Writing them as two features would have produced two expiry rules, and the one that
	dropped the expiry would be the one nobody noticed.

	`expires_iso` is required, not optional. A share with no end date is the failure §10.1's
	"limited time" names, and a field that defaults to never is a field that will be left at its
	default.
	"""

	model_config = MODEL_CONFIG
	grant_id: str = Field(default_factory=lambda: 'SHARE-' + uuid7str().replace('-', '').upper()[:12])
	member_ref: str = Field(min_length=1)
	# Who holds the link. `recipient` is the named clinician or facility for REC-002's provider
	# share, and None for a link handed to whoever the holder gives it to.
	recipient: str | None = None
	# Which kinds the grant covers. Empty means all of them, which is the REC-001 link case.
	kinds: list[str] = []
	issued_iso: str = Field(min_length=1)
	expires_iso: str = Field(min_length=1)
	# Who disclosed. Defaulted rather than required because the *route* is the authority for this
	# field — it overwrites whatever arrives with the token's own subject, since a grant that said
	# someone else issued it would attribute a disclosure to the wrong person. A required field the
	# server discards is a value the caller types and nothing reads, so it defaults and the service
	# refuses a grant that reaches it with no issuer.
	issued_by: str = ''
	revoked: bool = False
	# The scopes the recipient reads through. `consented_patient` is §17.4's clinician row; a share
	# is the consent that makes that row reachable, which is why it is named here rather than
	# invented at the route.
	scope: str = Field(default='consented_patient', pattern=r'^consented_patient$')


class ShareView(BaseModel):
	"""What a provider sees through a grant, and the two facts that bound it.

	`expires_iso` and `grant_id` are in the payload because a clinician reading a record needs to
	know it is a shared excerpt with an end date, not a record they hold — and because the reader
	who cannot see the expiry is the one who keeps reading after it passes.
	"""

	model_config = MODEL_CONFIG
	grant_id: str
	member_ref: str
	recipient: str | None
	expires_iso: str
	documents: list[WalletDocument]


class VaccinationCertificate(BaseModel):
	"""§10.1's "Vaccination certificates (for travel/school)", rendered from the dose log.

	The certificate is a *view* of `ImmunisationRecord`, not a second store: a certificate that
	kept its own copy of the doses would be able to disagree with the record it certifies.

	`signature` is an HMAC over the certificate's own canonical fields, keyed on the deployment
	secret. It is not a digital signature by a health authority — this deployment holds no such key
	— and calling it one would be a claim the code cannot support. It is a tamper-evident seal: a
	clinic presented with a printed certificate can confirm the deployment issued these fields, and
	cannot confirm anything about the child beyond what the fields say. `issuer` states that in
	words, so a reader of the JSON is not left to infer it.
	"""

	model_config = MODEL_CONFIG
	certificate_id: str
	member_ref: str
	holder_name: str
	dob_iso: str
	purpose: str = Field(pattern=r'^(travel|school|employment)$')
	doses: list[dict[str, str]]
	issued_iso: str
	signature: str
	issuer: str
	note: str


class ExportDocument(BaseModel):
	"""§REC-001/§10.1's export, rendered.

	`content` is the rendered bytes as text and `media_type` says what they are. A PDF is produced
	by `afya.records.pdf` here rather than by a library, because no PDF library is installed and a
	route that returned a `.pdf` filename with JSON inside would be the claim-with-nothing-behind-it
	this module keeps finding.
	"""

	model_config = MODEL_CONFIG
	export_id: str
	member_ref: str
	format: str = Field(pattern=r'^(pdf|json)$')
	media_type: str
	filename: str
	document_count: int
	content: str


class BackupEnvelope(BaseModel):
	"""§REC-001's "Optional encrypted cloud backup" and §10.1's "Encrypted cloud backup", as a fact.

	The wallet is small — a family's documents, not their photographs — so the envelope holds the
	documents themselves and a digest, and the route refuses without the subject's `cloud_backup`
	consent.

	End-to-end encryption is now real rather than asserted: when the caller supplies a passphrase,
	`sealed` holds the wallet sealed under a key derived from it (§SEC-003's scrypt KDF), `cipher`
	reads `aes-256-gcm`, `user_held_key` is true, and `documents` is empty — the ciphertext is the
	backup, and serving the plaintext beside it would undo the encryption it just performed.

	When no passphrase is given the envelope still reports `none`/False and carries the documents,
	because this deployment holds no key it does not also hold the data with. The two cases are
	distinguishable on the payload, which is the point: a reader can tell which one they got.
	"""

	model_config = MODEL_CONFIG
	backup_id: str
	subject_ref: str
	created_iso: str
	document_count: int
	member_count: int
	digest_sha256: str
	cipher: str = Field(pattern=r'^(none|aes-256-gcm)$')
	user_held_key: bool
	consent_category: str
	documents: list[WalletDocument]
	# The sealed wallet, present exactly when a passphrase produced it. `Sealed.to_blob()`'s string,
	# so it survives JSON and a TEXT column alike. A reader without the passphrase has an inert blob.
	sealed: str | None = None
	# What the recipient needs to know to open it: which KDF and cipher, and that the key was never
	# sent here. Stated on the envelope because the person restoring a backup is not the person who
	# wrote the service.
	open_hint: str | None = None
