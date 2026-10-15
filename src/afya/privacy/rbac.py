"""§17.4's RBAC table — the roles, the scopes, and the two ways a row can be unreachable.

§17.4 is an eight-row table: role, access. `privacy/views.py:_SCOPE` transcribes it as a role → scope
set map, and §17.5's Authorisation row names that map as the enforcement of "RBAC with least
privilege". Nothing checked the table against the routes, so two failures were invisible:

* **A scope no route requires.** `_SCOPE` declares nine scopes; the routes guard on seven. The two
  unguarded ones are `family` and `community_aggregate`, which are §17.4's "Own and linked family
  data" (citizen identified) and "community aggregates" (CHW). A scope with no route is a capability
  the table claims and no caller can reach — the same shape as a §7.3 feature outside the tier map,
  and the same shape as `rollout.ANTIPATTERNS`' declared-and-unperformed brand check. The family case
  is the sharpest: §ALT-002's family board is a Tier 3 feature and its three routes are guarded on
  `self`, so a `family`-scoped token reaches them through a *different* scope than the table gives it.

  `consented_patient` was the third and is no longer unguarded. §17.4's clinician row is "Patients
  who have consented to share", and §10.1's "Provider-side view (for participating facilities)" is
  the sentence that asks for a route serving it: `GET /records/share/{grant_id}/view`, where the
  share the patient issued *is* the consent that makes the row reachable. That is the one case where
  adding the route is the spec's instruction rather than this module inventing an endpoint — which is
  why the other two stay reported. A `family`-scoped caller needs the identity upgrade §15.5 does not
  specify, and a `community_aggregate` route would be a new aggregate surface rather than an existing
  one.

* **A role that can never hold a token.** `RBACRole.citizen_identified` exists, holds `self` and
  `family`, and is never issued: `require_token` resolves any anonymous token to `citizen_anonymous`,
  and the PKCE flow asserts the requested role is in `ISSUABLE_ROLES`, which excludes both citizen
  roles. So §17.4's second row describes a principal the system cannot produce. `citizen_anonymous`
  and `citizen_identified` both being unissuable is correct for one of them — an anonymous token is
  the only citizen token §15.5 defines — and a gap for the other, because §3.3 principle 6's
  "Identity is opt-in" is the sentence that gives the second row a reason to exist.

**Both are reported rather than repaired here.** Adding a route so a scope has a caller would be this
module inventing an endpoint the spec does not ask for, and issuing `citizen_identified` needs an
identity-upgrade flow §15.5 does not specify — the two things are a product decision, and what a
build owes is the finding. `unreachable_scopes()` and `unissuable_roles()` are the two findings, and
`route_scopes()` reads the scopes the routes actually guard on, from the app object rather than from
a list, so the comparison is against what the app serves.
"""
import re
from pathlib import Path

from afya.auth.service import ISSUABLE_ROLES, OPERATIONAL_ROLES
from afya.privacy.views import CITIZEN_ROLES, PURPOSE_FOR_SCOPE, AccessPurpose, RBACRole, _SCOPE

# §17.4's eight rows, transcribed with the Access cell verbatim, so a revision that changes a role's
# access fails here until the map moves with it. The cell is kept as the section writes it rather
# than paraphrased: "Patients who have consented to share" is the rule, and "consented_patient" is
# this codebase's name for it.
ROLE_ACCESS: tuple[tuple[RBACRole, str], ...] = (
	(RBACRole.citizen_anonymous, 'Own data only'),
	(RBACRole.citizen_identified, 'Own and linked family data'),
	(RBACRole.chw, 'Assigned patients, community aggregates'),
	(RBACRole.clinician, 'Patients who have consented to share'),
	(RBACRole.county_officer, 'County case data, aggregate analytics'),
	(RBACRole.pheoc_analyst, 'National case data, aggregate analytics'),
	(RBACRole.sysadmin, 'Infrastructure only; no access to personal data'),
	(RBACRole.auditor, 'Read-only access to audit logs'),
)

assert len(ROLE_ACCESS) == 8, '§17.4 has eight rows'
assert {r for r, _ in ROLE_ACCESS} == set(RBACRole), 'every role is a §17.4 row'
assert {r for r, _ in ROLE_ACCESS} == set(_SCOPE), 'every §17.4 role carries a scope set'

_SERVICE = Path(__file__).resolve().parents[1] / 'service.py'
# A scope reaches a route two ways, and both must be read. A route guard carries it as
# `require_scope('assigned')`; `require_self` and `require_self_or_guardian` carry `self` by
# checking `dataset='self'` inside the guard itself, which is why the dataset literal is matched too.
# Reading only the route-level call is the checker that enumerates one of the two ways to write the
# thing it checks — and the first version of this had a `GUARD_SCOPES = ('self',)` constant that
# papered over the gap, which made the assertion that `self` was found vacuous: the canary that
# emptied the constant still passed, because six routes also carry `require_scope('self')` literally.
#
# The optional second group is §17.4's purpose argument. It was added in the same commit that added
# the first `purpose=`, and it is load-bearing: the paren-adjacent form
# `require_scope\('([a-z_]+)'\)` does not match `require_scope('assigned', purpose='case_management')`
# at all, so every purpose-bearing route would silently drop out of `route_scopes()` — which feeds
# `unreachable_scopes()` and the auditor's own report, turning a carried scope into a reported gap.
# A checker that stops seeing its subject does not fail; it reports the opposite of the truth.
_SCOPE_CALL = re.compile(r"require_scope\('([a-z_]+)'(?:\s*,[^)]*)?\)")
_DATASET_CALL = re.compile(r"dataset='([a-z_]+)'")
_ANY_CALL = re.compile(r'require_any_scope\(\s*\(([^)]*)\)')
# The purpose a route declares, for `undocumented_access()`. Same reasoning as `_SCOPE_CALL`: read
# from the source, because a hand-kept list of which routes declare a purpose would agree with
# whatever it was written beside rather than with the routes.
_PURPOSE_CALL = re.compile(r"require_scope\('([a-z_]+)'(?:\s*,\s*purpose='([a-z_]+)')?\)")


def route_scopes(source: str | None = None) -> frozenset[str]:
	"""The scopes the routes guard on, read from `service.py`.

	Read from the source rather than from a hand-kept list, because a list is the thing that drifts:
	the whole finding is that `_SCOPE` and the routes disagree, and a second list would agree with
	whichever of the two it was written beside. Three spellings contribute: a route's
	`require_scope('x')`, the `dataset='x'` literal inside a guard helper (which is how `self`
	reaches a route), and each scope named by a `require_any_scope` site.
	"""
	text = source if source is not None else _SERVICE.read_text(encoding='utf-8')
	found = set(_SCOPE_CALL.findall(text)) | set(_DATASET_CALL.findall(text))
	for group in _ANY_CALL.findall(text):
		found |= {tok.strip().strip("'\"") for tok in group.split(',') if tok.strip()}
	return frozenset(found)


def declared_scopes() -> frozenset[str]:
	"""Every scope §17.4's table gives some role."""
	return frozenset(s for scopes in _SCOPE.values() for s in scopes)


def unreachable_scopes(source: str | None = None) -> list[str]:
	"""Declared scopes no route requires, sorted. The finding, not a defect to fix in place."""
	return sorted(declared_scopes() - route_scopes(source))


def roles_with_scope(scope: str) -> list[RBACRole]:
	"""Which §17.4 roles the table gives a scope. Used to say who is affected by a gap."""
	return [role for role, scopes in _SCOPE.items() if scope in scopes]


def route_purposes(source: str | None = None) -> list[tuple[str, str | None]]:
	"""Every `require_scope` site as `(scope, purpose)`, with `None` where none is declared.

	A **list**, not a mapping keyed by scope. The mapping was the fail-open shape: 38 `assigned`
	sites collapse to one key, so three routes declaring a purpose would have made the gate pass
	while thirty-five declared none — a check satisfied by the one good case among many, which is
	the same defect as a blocklist assertion that enumerates one spelling of the thing it guards.
	Every site is returned so the caller can count them.
	"""
	text = source if source is not None else _SERVICE.read_text(encoding='utf-8')
	return [(scope, purpose or None) for scope, purpose in _PURPOSE_CALL.findall(text)]


def undocumented_access(source: str | None = None) -> list[str]:
	"""The `require_scope` sites that reach another person's data and declare no purpose.

	§17.4's second sentence, reported in the shape `unreachable_scopes()` already has and for the
	same reason: it reports itself rather than being a list somebody maintains. A site is named when
	`PURPOSE_FOR_SCOPE` says its scope needs a purpose and it declares none, so a new `assigned`
	route added without one appears the moment it exists, and the `self`/`family`/aggregate routes
	stay out by construction rather than by exemption.

	**Every site is judged, not one per scope** — a scope with one documented route and nine
	undocumented ones is a 10% gate, and a gate that reports clean on it is worse than none.
	"""
	return sorted(
		f'{scope}:{purpose}' if purpose else scope
		for scope, purpose in route_purposes(source)
		if scope in PURPOSE_FOR_SCOPE and purpose is None
	)


def unknown_purposes(source: str | None = None) -> list[str]:
	"""Purposes a route declares that are not members of `AccessPurpose`.

	The route declares its purpose as a string so there is one spelling, read from the source by
	`route_purposes`; this is what stops that spelling being a typo. Without it `purpose='case_managment'`
	would be accepted by the guard, written into the ledger as a value nothing recognises, and read
	back by an auditor as a purpose — a misspelling in the one column whose whole job is to be
	answerable. Fails the gate rather than a request.
	"""
	known = {p.value for p in AccessPurpose}
	return sorted({p for _, p in route_purposes(source) if p is not None and p not in known})


def unissuable_roles() -> list[RBACRole]:
	"""Roles with a §17.4 row that no path in the system can produce a token for.

	`citizen_anonymous` is here for a reason that is not a gap — §15.5 issues anonymous tokens and
	`require_token` resolves them to that role by construction. `citizen_identified` is the gap: no
	flow issues it, so the row describes a principal that cannot exist, and the `family` scope it
	alone holds is therefore unreachable by any caller. Both are returned because the *fact* is the
	same and the caller decides which is which; `identity_gap()` names the one that is a gap.
	"""
	issuable = ISSUABLE_ROLES | OPERATIONAL_ROLES | {RBACRole.citizen_anonymous}
	return sorted((r for r in RBACRole if r not in issuable), key=lambda r: r.value)


def identity_gap() -> RBACRole | None:
	"""The role whose absence is a gap rather than a design. §3.3 principle 6 says "Identity is
	opt-in" — which is the sentence that gives §17.4's second row a reason to exist — and nothing
	implements the opt-in, so the row is a claim with no principal behind it."""
	gaps = [r for r in unissuable_roles() if r is not RBACRole.citizen_anonymous]
	assert len(gaps) <= 1, f'expected at most one identity gap, found {gaps}'
	return gaps[0] if gaps else None


def report(source: str | None = None) -> dict[str, object]:
	"""§17.4's table against the routes and the token-issuing paths.

	Both findings travel with the table they are about, because either alone reads as a complete
	answer: a scope no route requires looks fine next to a role list, and a role no path issues looks
	fine next to a route list. Together they say which row of §17.4 has no implementation.
	"""
	gap = identity_gap()
	return {
		'roles': [{'role': r.value, 'access': access, 'scopes': sorted(_SCOPE[r])} for r, access in ROLE_ACCESS],
		'guarded_scopes': sorted(route_scopes(source)),
		'unreachable_scopes': [
			{'scope': s, 'roles': [r.value for r in roles_with_scope(s)]}
			for s in unreachable_scopes(source)
		],
		'unissuable_roles': [r.value for r in unissuable_roles()],
		'identity_gap': gap.value if gap else None,
		'citizen_roles': sorted(r.value for r in CITIZEN_ROLES),
		# §17.4's second sentence, reported the way the first two findings are: a scope that reaches
		# another person's data with no purpose declared, and the purposes a route may declare.
		'undocumented_access': undocumented_access(source),
		'unknown_purposes': unknown_purposes(source),
		'purposes': sorted(p.value for p in AccessPurpose),
	}
