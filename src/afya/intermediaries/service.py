"""§CHAN-5's intermediary programme as a service: codes, referrals, and the verification gate.

The section states three things a service can hold: each intermediary gets a code, a referral is
attributed through it, and an incentive is paid for a *verified* referral. What it does not state is
what makes a referral verified, so this module makes the smallest decision that is forced by the
section's own words and reports everything else.

A referral is verified when the person it names arrived **and** the incentive has not already been
paid for that referral. The first half is the word "verified" read literally: without a person
behind the code, the record is the intermediary's claim about their own activity. The second half is
not in the section either, and it is the one a programme with real money in it actually needs — §18.8
puts the disbursement on a *weekly* run, and a weekly run that can pay the same referral twice is a
budget drain reachable by replaying a request.

What the code does not do is invent an amount. §CHAN-5 gives none, so `kes` arrives from the caller
and §18.8's existing 500 KES bound still holds at the telco client, which is the last place the
figure is checkable.
"""
import random

from afya.intermediaries.views import (
	CODE_CARRIED_TOOLS, TOOLS_PROVIDED, Incentive, Intermediary, IntermediaryKind,
	IntermediaryProgramme, Referral, ReferralAttribution,
)
from afya.logmixin import LogMixin

# The alphabet excludes I, O, 0 and 1: a code is read aloud by a CHW to a person standing next to
# them and written on a flip chart by hand, so the characters that are ambiguous in speech or in
# handwriting are not in it. That is a property of how the code is used, not a claim about §CHAN-5.
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
_KIND_PREFIX: dict[IntermediaryKind, str] = {
	IntermediaryKind.chw: 'CHW',
	IntermediaryKind.pharmacy: 'PHA',
	IntermediaryKind.faith_leader: 'FTH',
	IntermediaryKind.boda_sacco: 'BOD',
	IntermediaryKind.market_leader: 'MKT',
	IntermediaryKind.teacher: 'TCH',
	IntermediaryKind.chama_leader: 'CHA',
}


class IntermediaryService(LogMixin):
	def __init__(self) -> None:
		self._by_code: dict[str, Intermediary] = {}
		self._referrals: list[Referral] = []
		self._incentives: list[Incentive] = []
		assert self._by_code == {} and self._referrals == [] and self._incentives == []

	# --- enrolment and codes ------------------------------------------------------------------

	@staticmethod
	def issue_code(kind: IntermediaryKind, taken: set[str] | None = None) -> str:
		"""A §CHAN-5 attribution code for one intermediary.

		The prefix is the kind, so a code read off a flip chart says what the intermediary is without
		a lookup; the body is four characters from an alphabet with no I/O/0/1. Uniqueness is the
		caller's to enforce through `taken`, and `enrol` is the caller that does — a code that
		resolved to two people attributes a referral to neither, which is the whole failure this
		mechanism exists to prevent.
		"""
		taken = taken or set()
		for _ in range(200):
			code = f'{_KIND_PREFIX[kind]}-{"".join(random.choice(CODE_ALPHABET) for _ in range(4))}'
			if code not in taken:
				return code
		raise AssertionError('could not issue a unique intermediary code')

	async def enrol(self, intermediary: Intermediary) -> Intermediary:
		"""Register an intermediary under their code. A duplicate code is refused rather than
		overwriting: the second enrolment would silently reattribute every referral the first one
		earned, and nothing downstream could tell that it had happened."""
		assert intermediary.code not in self._by_code, f'code {intermediary.code} is already issued'
		self._by_code[intermediary.code] = intermediary
		self._log_info('intermediary enrolled', code=intermediary.code, kind=intermediary.kind.value)
		return intermediary

	def intermediary(self, code: str) -> Intermediary:
		assert code in self._by_code, 'unknown intermediary code'
		return self._by_code[code]

	def enrolments(self) -> list[Intermediary]:
		return list(self._by_code.values())

	# --- referrals ----------------------------------------------------------------------------

	async def record_referral(self, referral: Referral) -> Referral:
		"""Attribute a referral to a code. The code must exist — an unattributable referral is not a
		referral — and a person must be named, which is what makes it checkable later."""
		self.intermediary(referral.code)
		assert referral.arrived_subject_ref, 'a referral names the person who arrived'
		self._referrals.append(referral)
		self._log_info('referral recorded', code=referral.code, completed=referral.profile_completed)
		return referral

	def referrals(self, code: str) -> list[Referral]:
		return [r for r in self._referrals if r.code == code]

	def payable(self, code: str) -> list[Referral]:
		"""The referrals an incentive may still be paid for: the profile was completed, and no
		incentive has been paid for this referral yet.

		Both halves matter and they fail differently. Paying an incomplete referral pays for an
		arrival rather than the outcome §20.2 lever 6 names; paying a referral twice is a replay. The
		second is the one a weekly disbursement run actually hits.
		"""
		paid = {i.referral_id for i in self._incentives}
		return [r for r in self.referrals(code) if r.profile_completed and r.referral_id not in paid]

	def is_paid(self, referral_id: str) -> bool:
		return any(i.referral_id == referral_id for i in self._incentives)

	# --- incentives ---------------------------------------------------------------------------

	async def pay_incentive(self, incentive: Incentive, disburser) -> Incentive:  # type: ignore[no-untyped-def]
		"""Pay one §CHAN-5 airtime incentive, through §18.8's telco client.

		The gate is here rather than in the route because this is where the referral is visible: the
		route sees an amount and a phone number, and a caller that posted the same body twice would
		be paid twice. Refused rather than reported, because a second payment is money already gone.

		`disburser` is the telco client, passed in rather than constructed — an unconfigured
		deployment must still be able to hold the programme and refuse the payment, which is a
		different fact from a programme that does not exist.
		"""
		referral = next((r for r in self._referrals if r.referral_id == incentive.referral_id), None)
		assert referral is not None, f'no referral {incentive.referral_id} to pay for'
		assert referral.code == incentive.code, 'the incentive must be attributed to the referral code'
		assert referral.profile_completed, '§20.2 lever 6 pays for profile completion, not arrival'
		assert not self.is_paid(incentive.referral_id), f'{incentive.referral_id} has already been paid'
		reason = f'intermediary referral {incentive.code} {incentive.referral_id}'
		reference = await disburser(incentive.msisdn, incentive.kes, reason)
		paid = incentive.model_copy(update={'reference': str(reference)})
		self._incentives.append(paid)
		self._log_info('incentive paid', code=paid.code, kes=paid.kes, reference=paid.reference)
		return paid

	def incentives(self) -> list[Incentive]:
		return list(self._incentives)

	# --- the programme as one answer ----------------------------------------------------------

	def attribution(self, code: str) -> ReferralAttribution:
		"""One intermediary's record: arrivals, completions, and what has been paid."""
		intermediary = self.intermediary(code)
		rows = self.referrals(code)
		paid = [i for i in self._incentives if i.code == code]
		return ReferralAttribution(
			intermediary=intermediary, referrals=len(rows),
			completed=len([r for r in rows if r.profile_completed]),
			paid_referrals=[i.referral_id for i in paid],
			unpaid_completed=[r.referral_id for r in self.payable(code)],
			kes_paid=sum(i.kes for i in paid),
		)

	def programme(self) -> IntermediaryProgramme:
		"""§CHAN-5's seven kinds and five tools, against what this repo carries.

		`uncarried_tools` is the finding and it is not a defect: a printed flip chart is not code. The
		airtime incentive is *not* among them — `pay_incentive` gates a verified referral and
		disburses through §18.8's bounded telco client, so the capability is here; an unconfigured
		deployment refusing the payment is a different fact from a programme that does not exist,
		which is the distinction `pay_incentive`'s docstring draws. Nor is the training: the content
		is `afya.chw.views:TRAINING_MODULES` and §24.4's matrix carries the audience, format and
		duration.

		`untrained` is the other finding, and it is the one this report was missing. `trained` is a
		per-person fact on every enrolled intermediary and nothing read it, so a programme could
		enrol a hundred people, train none, and report nothing wrong. `POST /intermediaries/enrol`
		sets it; this is what makes the section's training bullet answerable per person.
		"""
		by_kind: dict[str, int] = {k.value: 0 for k in IntermediaryKind}
		for i in self._by_code.values():
			by_kind[i.kind.value] += 1
		uncarried = [t for t in TOOLS_PROVIDED if t not in CODE_CARRIED_TOOLS]
		untrained = sorted(c for c, i in self._by_code.items() if not i.trained)
		trained = len(self._by_code) - len(untrained)
		notes: list[str] = []
		if uncarried:
			notes.append(f'{len(uncarried)} of §CHAN-5\'s five tools are not code')
		if not self._by_code:
			notes.append('no intermediary is enrolled yet')
		elif untrained:
			notes.append(f'{len(untrained)} of {len(self._by_code)} enrolled intermediaries are untrained')
		self._log_info('programme report', intermediaries=len(self._by_code), untrained=len(untrained))
		return IntermediaryProgramme(
			kinds=[k.name for k in IntermediaryKind], tools=list(TOOLS_PROVIDED),
			carried_tools=[t for t in TOOLS_PROVIDED if t in CODE_CARRIED_TOOLS],
			uncarried_tools=uncarried, intermediaries=len(self._by_code),
			trained=trained, untrained=untrained, by_kind=by_kind,
			note='; '.join(notes) if notes else 'all seven kinds enrolled, every intermediary trained',
		)
