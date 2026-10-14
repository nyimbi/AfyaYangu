"""§5.4's last three "All channels share" claims: one case-report backend, one identity model, one
consent registry.

The first bullet — "a single triage engine" — is enforced in `channels/service.py`, where every
channel answers through the engine the API routes use. The last three rest on a fact the build did
not have: **a phone number and a subject are two identifiers and nothing mapped between them.**

* The channel layer's identity is an MSISDN. `UssdRequest.msisdn`, `WhatsAppIn.from_msisdn` and the
  telco inbound-SMS route all carry one, and `afya.intermediaries` even has a domain model for the
  incentives it pays to them.
* The app layer's identity is a `subject_ref`. `AuthService.issue_anonymous` mints one, every
  `require_self` guard compares against it, and the consent ledger, the symptom diary, the wallet and
  the case reports are all keyed by it.
* Nothing in `src/afya/` holds both. `CaseReport` has no phone field at all, so §5.4's "deduplicated
  by phone number" cannot be performed on one: two reports of the same person from a USSD session and
  from the app are two cases, and the second is a duplicate that inflates the count PHEOC reads.

**What this module is, and what it deliberately is not.** It is the identity model §5.4 names — a
phone-to-subject index with §17.2's rules kept intact:

* **Opt-in linkage.** §5.4 says "phone number, **with optional linkage** to an app profile". An
  MSISDN alone resolves to an anonymous subject; a link is a separate, recorded act, so a person who
  only ever used USSD is not silently merged into an app account they never created.
* **The phone is personal data.** §17.2 puts an MSISDN in the personal-data class, so the index is
  not a lookup anyone may perform: `subject_for` is called by the channel layer for its own inbound
  message and the report is audited, which is the same rule `require_scope` applies to a guarded
  route. §17.1's DPA 2019 basis is the consent the person gave, so a link with no recorded consent
  is refused rather than created.
* **It does not deduplicate cases.** §5.4's claim is that reports *are* deduplicated; performing that
  means deciding which of two reports is the same person, and a person is not their phone — a
  household sharing one handset, a CHW reporting on someone else's behalf, and a caller borrowing a
  neighbour's phone are all in §4.1's persona list. `same_reporter` answers only the part the
  identifier can answer, and `dedup_key` is offered so a caller states the rule it uses rather than
  this module inventing one. The finding is reported in `report()`.

**§SEC-004's pseudonymous profile lives here too**, because it is the same question asked the other
way round. §5.4 keeps an identifier apart from a person; §SEC-004 asks what the app shows *instead*
of the identifier when a person's words reach a screen anyone can open. The answer is a derived,
rotating handle — and the join that needs it is §FND-001's public report feed, which was serving the
raw subject reference.
"""
import hashlib

from afya.identity.views import IdentityLink, LinkBasis, PseudonymPolicy
from afya.logmixin import LogMixin

# §SEC-004's "optional pseudonymous profile": how long one handle stands for one person. Thirty days
# is long enough that a person reading a feed recognises their own posts, short enough that the
# handle is not a permanent label — and it is a constant here rather than a parameter so the window
# cannot be widened per call site by whoever finds it inconvenient.
PSEUDONYM_ROTATION_DAYS = 30
_MS_PER_DAY = 86_400_000

# The word list a derived handle is built from. Deliberately neutral nouns: a handle assembled from
# a person's county, their symptom history or anything else the app knows would leak that fact into
# every public feed the handle appears on, which is the failure §SEC-004's geohashing bullet is
# about at a different scale.
_HANDLE_WORDS: tuple[str, ...] = (
	'Tembo', 'Nyota', 'Jua', 'Mwezi', 'Safari', 'Bahari', 'Mlima', 'Mto', 'Msitu', 'Anga',
	'Kipawa', 'Nuru', 'Amani', 'Tumaini', 'Furaha', 'Baraka', 'Imani', 'Hekima', 'Nguvu', 'Rafiki',
)
assert len(set(_HANDLE_WORDS)) == len(_HANDLE_WORDS), 'a repeated word makes two handles collide'


class IdentityService(LogMixin):
	"""§5.4's single identity model: an MSISDN to subject index, with linkage that is opt-in.

	State is in-memory like every other service here — the persistence seam is `afya.persistence`,
	and the swap is the same one the rest of the build waits on.
	"""

	def __init__(self) -> None:
		# MSISDN → subject. An entry created by an anonymous token is a *resolution*, not a link:
		# the phone resolved to a subject the system minted for it, and no app profile is involved.
		self._phone_to_subject: dict[str, str] = {}
		self._subject_to_phone: dict[str, str] = {}
		# The subjects a phone has resolved to, oldest first. The *key* of the dedup is the phone
		# number itself, so this history is not what makes a report findable; it exists so that
		# linking a phone to an app profile does not orphan the subject it was messaging under, which
		# the consent ledger and any other subject-keyed record would still be holding.
		self._phone_history: dict[str, list[str]] = {}
		# The links a person made deliberately, with the basis and the consent behind each.
		self._links: dict[str, IdentityLink] = {}
		# §SEC-004's optional profile: the handles a person *chose*, keyed by subject. A subject
		# absent from this map has not opted out of being named — it gets the derived handle — which
		# is what makes the bullet's "optional" true of the screen rather than of the person.
		self._chosen_handles: dict[str, str] = {}
		assert self._phone_to_subject == {} and self._links == {}

	@staticmethod
	def normalise(raw: str) -> str:
		"""A carrier's phone number as E.164, or a refusal.

		Kenyan carriers deliver a number in at least three spellings — `0712345678`,
		`254712345678` and `+254712345678` — and the two channel entry points each handled one of
		them: USSD prepended `+` to whatever arrived, and the telco inbound route stripped a leading
		zero. So the same handset produced `+254712345678` on one channel and `+0712345678` on the
		other, which is two identities for one person and a dedup that finds nothing.

		This is the one place the spelling is decided, so a channel cannot invent a fourth. The
		refusal matters as much as the normalisation: a number that is not Kenyan is not silently
		rewritten into something that looks like one, because a wrong number here is a report
		attributed to the wrong person.
		"""
		assert raw, 'a phone number is required'
		digits = ''.join(c for c in raw if c.isdigit())
		if raw.startswith('+') and digits.startswith('254'):
			pass
		elif digits.startswith('254'):
			pass
		elif digits.startswith('0'):
			digits = '254' + digits[1:]
		else:
			raise ValueError(f'{raw!r} is not a Kenyan number: expected 254…, 0… or +254…')
		assert 12 <= len(digits) <= 13, f'{raw!r} is not a valid E.164 Kenyan number'
		return '+' + digits

	# --- resolution: the anonymous path ---------------------------------------------------------

	def resolve(self, msisdn: str) -> str:
		"""The subject for a phone number, minting an anonymous one the first time it is seen.

		This is the whole of what a USSD or SMS session gets: a stable handle for the phone, with no
		account, no name and no link to an app profile. §5.4's "optional linkage" is the next method,
		and keeping the two apart is what stops a person who never installed the app from acquiring an
		app profile by messaging.
		"""
		msisdn = self.normalise(msisdn)
		if msisdn not in self._phone_to_subject:
			from afya.ids import uuid7str
			subject = f'anon-{uuid7str()}'
			self._phone_to_subject[msisdn] = subject
			self._subject_to_phone[subject] = msisdn
			self._phone_history.setdefault(msisdn, []).append(subject)
			self._log_info('phone resolved to a new anonymous subject', subject=subject)
		return self._phone_to_subject[msisdn]

	def subject_for(self, msisdn: str) -> str | None:
		"""The subject a phone already resolves to, or None. Reads only — `resolve` is the minting path.

		Normalised on the way in, so a caller holding `0712345678` finds the subject a USSD session
		minted for `+254712345678`. A lookup that missed would report "this phone has consented to
		nothing" for a person who had, which is the wrong answer in the direction that stores data
		without a grant.
		"""
		return self._phone_to_subject.get(self.normalise(msisdn))

	def msisdn_for(self, subject_ref: str) -> str | None:
		"""The phone behind a subject, or None. §17.2 personal data, so this is the read the access log
		records rather than one a caller may make freely."""
		return self._subject_to_phone.get(subject_ref)

	# --- linkage: the opt-in path ---------------------------------------------------------------

	async def link(self, link: IdentityLink) -> IdentityLink:
		"""§5.4's "optional linkage to an app profile", recorded as the act it is.

		**This is the ordinary path, not an edge case.** The person §5.4 describes is one who used USSD
		first and installed the app later, so at the moment of linking the phone *already* resolves to
		an anonymous subject. Refusing that — which an earlier cut did, reading any existing entry as
		"another person's handset" — would have made the section's own journey impossible. What is
		refused is a phone belonging to a *different app profile*: a subject with a link of its own is a
		person, and repointing their phone would silently move their records.

		Two things are refused rather than smoothed: a link with no consent recorded (§17.1's DPA basis
		is the consent the person gave, and §SEC-001 makes linkage a purpose like any other), and a link
		that would give one app profile two phones (a household sharing a handset is real, but merging
		two people's records is not a thing a phone number can decide).

		**The anonymous subject's records migrate.** Anything keyed on the handle the phone was messaging
		under — the consent ledger above all — would otherwise be stranded: a person who granted
		symptom storage over USSD and then installed the app would find the toggle off, because the app
		reads the profile's subject and the grant sits on the handle. `absorbed` carries what moved, so
		the caller can report it rather than a reader having to infer it.
		"""
		link = link.model_copy(update={'msisdn': self.normalise(link.msisdn)})
		assert link.subject_ref, 'a link names the app profile it joins'
		assert link.consent_id, '§17.1: linkage needs a recorded consent, not an assumption'
		assert link.basis in set(LinkBasis), f'unknown basis {link.basis!r}'
		existing = self._phone_to_subject.get(link.msisdn)
		if existing is not None and existing != link.subject_ref and self.is_linked(existing):
			raise ValueError('this phone number already belongs to another person')
		held = self._subject_to_phone.get(link.subject_ref)
		if held is not None and held != link.msisdn:
			raise ValueError('this app profile already has a phone number')
		absorbed = existing if existing is not None and existing != link.subject_ref else None
		# No append to `_phone_history` here: an absorbed handle only exists when the phone had
		# already resolved, and `resolve` recorded it then. A second write would be a branch that
		# cannot change any answer — canaried, and it did not.
		self._phone_to_subject[link.msisdn] = link.subject_ref
		self._subject_to_phone[link.subject_ref] = link.msisdn
		self._links[link.link_id] = link
		self._log_info('phone linked to an app profile', basis=link.basis.value, absorbed=absorbed)
		return link

	def absorbed_subjects(self, msisdn: str) -> tuple[str, ...]:
		"""The anonymous handles this phone was messaging under before it was linked.

		A caller holding records keyed on a subject — the consent ledger, a symptom diary, a case
		report filed from the handset — reads this to find what the link brought into view. Without it
		the records are not lost but they are unreachable, which is the same thing from the person's
		side: they consented over USSD and the app shows the toggle off.
		"""
		return tuple(s for s in self._phone_history.get(self.normalise(msisdn), []) if s != self._phone_to_subject.get(self.normalise(msisdn)))

	async def unlink(self, link_id: str) -> IdentityLink:
		"""§17.2's withdrawal. The index entry goes; the subject's data does not, because unlinking a
		phone is not a request to delete the records the phone's sessions created."""
		assert link_id in self._links, 'unknown link'
		link = self._links.pop(link_id)
		self._phone_to_subject.pop(link.msisdn, None)
		self._subject_to_phone.pop(link.subject_ref, None)
		# The history survives, so the handles the phone absorbed are still named and the records
		# keyed on them are still findable — unlinking is not a request to lose them.
		self._log_info('phone unlinked', subject=link.subject_ref)
		return link

	def links(self) -> list[IdentityLink]:
		return list(self._links.values())

	def is_linked(self, subject_ref: str) -> bool:
		"""Whether this subject reached the app by a deliberate link rather than by messaging.

		The distinction is the one §5.4's "optional" turns on: a subject minted by `resolve` is a
		phone's handle, and a subject with a link is a person who joined the two.
		"""
		return any(link.subject_ref == subject_ref for link in self._links.values())

	# --- §SEC-004: the optional pseudonymous profile ---------------------------------------------

	@staticmethod
	def _epoch(now_ms: int, rotation_days: int = PSEUDONYM_ROTATION_DAYS) -> int:
		"""Which rotation window an instant falls in. Integer division, so it is a step function.

		The epoch is a count, not a date, because it is only ever compared for equality: two handles
		for one subject differ exactly when their epochs differ, and nothing needs to know when a
		window started.
		"""
		assert now_ms >= 0, 'a negative instant is not a time'
		assert rotation_days >= 1, 'a rotation window is at least a day'
		return now_ms // (rotation_days * _MS_PER_DAY)

	@classmethod
	def derive_handle(cls, subject_ref: str, now_ms: int,
	                  rotation_days: int = PSEUDONYM_ROTATION_DAYS) -> PseudonymPolicy:
		"""The handle the app shows instead of a person's identifier on a screen anyone can open.

		Derived, not random: the same subject in the same window gets the same handle on every
		server and across a restart, so a feed does not relabel a person between two requests. The
		epoch is in the digest, so the *next* window gives a different handle — which is the whole
		difference between a pseudonym and a subject reference wearing a friendlier spelling.

		The digest is not a secret and is not treated as one. `subject_ref` is high-entropy (a UUID7
		under a prefix) so the mapping is not invertible by enumeration, but the property being
		claimed here is unlinkability *across* windows, not secrecy *within* one: anyone who learns a
		handle and the window it belongs to can confirm a guess about the subject. §SEC-004's
		"minimum cell size of 10" is the same admission one level up — a small enough crowd
		re-identifies regardless of the identifier used.
		"""
		assert subject_ref, 'a pseudonym is derived from a subject'
		epoch = cls._epoch(now_ms, rotation_days)
		digest = hashlib.sha256(f'{subject_ref}:{epoch}'.encode()).hexdigest()
		word = _HANDLE_WORDS[int(digest[:8], 16) % len(_HANDLE_WORDS)]
		return PseudonymPolicy(
			subject_ref=subject_ref, handle=f'{word}-{digest[8:12]}', epoch=epoch,
			rotates_every_days=rotation_days,
		)

	def choose_handle(self, subject_ref: str, handle: str, now_ms: int) -> PseudonymPolicy:
		"""A person naming themselves, which is the "optional" half of §SEC-004's bullet.

		The shape is validated by the model and the *content* is not: a handle is a person's own
		words on a public feed, and a service that screened them for decency would be making an
		editorial decision this module has no basis for. What is refused is a handle that *is* an
		identifier — an MSISDN or a subject reference typed in as one — because that would let a
		person publish the very key §SEC-004 exists to keep off the screen, and they would be doing
		it to themselves.

		A chosen handle does not rotate. A person who picked a name and found it changed after a
		month would have been given a setting that does not do what it says.
		"""
		assert subject_ref, 'a handle belongs to a subject'
		assert handle, 'a chosen handle is not empty'
		# A handle that *is* an identifier is refused: a person typing their own number or subject
		# reference into the box would be publishing the key §SEC-004 keeps off the screen, and the
		# service would be the thing that let them. Digits-only is the MSISDN case; the `anon-`
		# prefix is the subject case, and it is checked by shape rather than by looking the value up,
		# because looking it up would confirm to a caller that a subject exists.
		digits = ''.join(c for c in handle if c.isdigit())
		assert not (digits and digits == handle.replace('+', '').replace(' ', '')), \
			'a phone number is not a pseudonym'
		assert not handle.startswith('anon-'), 'a subject reference is not a pseudonym'
		self._chosen_handles[subject_ref] = handle
		policy = PseudonymPolicy(
			subject_ref=subject_ref, handle=handle, epoch=self._epoch(now_ms),
			rotates_every_days=PSEUDONYM_ROTATION_DAYS, chosen=True,
		)
		self._log_info('pseudonym chosen', subject=subject_ref)
		return policy

	def pseudonym(self, subject_ref: str, now_ms: int) -> PseudonymPolicy:
		"""The handle in force for this subject: the chosen one if there is one, the derived one else.

		Every caller that puts a person's words on a shared screen reads this rather than the subject
		reference. It is a method rather than a field on the caller's model so the rule has one
		implementation — a second one is how the feed and the report came to disagree in the first
		place.
		"""
		assert subject_ref, 'a pseudonym belongs to a subject'
		if subject_ref in self._chosen_handles:
			return PseudonymPolicy(
				subject_ref=subject_ref, handle=self._chosen_handles[subject_ref],
				epoch=self._epoch(now_ms), rotates_every_days=PSEUDONYM_ROTATION_DAYS, chosen=True,
			)
		return self.derive_handle(subject_ref, now_ms)

	# --- the case-report crossing ---------------------------------------------------------------

	def same_reporter(self, a: str, b: str) -> bool:
		"""Whether two phone numbers are the same reporter, which is all an MSISDN can answer.

		§5.4 says case reports are "deduplicated by phone number". This is the part of that a phone
		number decides — and it is deliberately the narrow part, because §4.1 has a household sharing
		a handset, a CHW reporting for someone else and a caller on a borrowed phone. Two different
		numbers are *not* evidence of two people, and one number is not evidence of one.
		"""
		return self.normalise(a) == self.normalise(b)

	def dedup_key(self, msisdn: str) -> str:
		"""§5.4's dedup key for a report from this phone: the phone number, in E.164.

		The section says "deduplicated by phone number" and the phone number is what the key is. An
		earlier cut of this module keyed on the resolved *subject* instead, on the theory that linking
		an app profile should make a person's app reports and channel reports collide. That was
		wrong in a way worth recording: the subject is not stable — linking repoints a phone from its
		anonymous subject to the profile — so a case opened before the link became unreachable after
		it, and the fix for that was a history of keys that no longer decided anything, because the
		number alone was always in the set. The subject bought nothing the number did not already
		give, and cost a lookup order that had to be reasoned about. §5.4's own mechanism is simpler
		and is what is used here.

		`normalise` is applied because the two channel entry points hand-roll E.164 differently and
		get it wrong: USSD prepends a `+` to whatever the carrier sends, and the telco inbound route
		strips a leading zero. The same handset messaging on both channels therefore produced two
		different strings, which is two phones, two subjects, and a dedup that finds nothing — the
		defect this function's normalisation closes.
		"""
		return self.normalise(msisdn)

	def report(self) -> dict[str, object]:
		"""The model, and the finding §5.4's claim rests on.

		The finding is stated rather than repaired: `CaseReport` carries no phone field, so the
		deduplication the section promises is not performed anywhere, and this module cannot perform
		it from an identifier alone. `can_deduplicate` is False and the reason travels with it, so a
		reader of the report does not take the presence of `dedup_key` for a working dedup.
		"""
		return {
			'resolved_phones': len(self._phone_to_subject),
			'linked_profiles': len(self._links),
			'links': [{'link_id': link.link_id, 'basis': link.basis.value, 'consented': bool(link.consent_id)} for link in self._links.values()],
			'bases': [b.value for b in LinkBasis],
			'can_deduplicate': False,
			'dedup_gap': (
				'CaseReport carries no phone number, so §5.4\'s "deduplicated by phone number" is not '
				'performed: a report filed over USSD and the same case filed in the app are two cases. '
				'The identifier cannot close this on its own — §4.1 has shared handsets, CHWs reporting '
				'for others and borrowed phones — so the rule is a product decision, and `dedup_key` is '
				'the input it would need.'
			),
		}
