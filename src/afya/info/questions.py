"""§6.1's demand-ordered questions, and §6.2.4's rule about the ones that are life-safety.

§6.1 is a table of ten questions "ordered by real demand, not by what health authorities want to
publish", each with the content response it maps to. None of the ten was modelled: the library
existed, the dashboard existed, the triage flow existed, and nothing anywhere said which of them
answers "Is it near me?" — so the ordering that is the section's whole point was absent, and a client
had a flat list of routes with no idea which one a person asks first.

§6.2.4 is the rule this unlocks: "**Local language first**, English second. **Never publish
English-only for a life-safety message.**" The second sentence had no jurisdiction. `ContentItem`
carries a `lang` and `library(lang='en')` serves whatever exists in English, so a life-safety message
could be published in English alone and served to an audience whose first language §3.3 principle 8
says is Swahili. Nothing marked an item life-safety, so the rule could not bite — the same shape as
§6.2's nine prose rules before they became tables.

**Which messages are life-safety is read off §6.1, not judged per item.** §6.1 ranks the questions by
demand and gives each a content response; the ones whose answer decides whether someone seeks care or
infects a household are life-safety, and they are marked in the table below with the section's own
wording as the reason. A per-item boolean an author sets is the thing that fails: whoever is drafting
under time pressure is the last person to mark their own copy as life-safety, and §6.2.4 exists
precisely for the message someone is rushing out.

The two consequences, both enforced in `afya.info.service`:

* **The library does not serve a life-safety item in one language alone.** `library('en')` drops an
  item whose counterpart does not exist, because serving it is the act §6.2.4 forbids — and an item
  held back is visible to the reviewer, whereas an English-only life-safety message read by a Swahili
  speaker is not.
* **`/info/content` refuses to publish one.** The refusal names the counterpart it wants, so the
  drafting screen can say what is missing rather than leaving an author to guess.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class RankedQuestion(BaseModel):
	"""One row of §6.1. `rank` is the section's own order and is the reason the table exists — the
	section is explicit that the order is by real demand, so it is data rather than a listing.

	`life_safety` is what §6.2.4 needs to have a jurisdiction. `why_life_safety` is required whenever
	it is true, so a row cannot claim the flag without stating the consequence that makes it one.
	"""
	model_config = MODEL_CONFIG
	rank: int = Field(ge=1, le=10)
	question: str = Field(min_length=1)
	response: str = Field(min_length=1)
	life_safety: bool
	why_life_safety: str | None = None

	def model_post_init(self, _context: object) -> None:
		assert self.life_safety == bool(self.why_life_safety), (
			f'rank {self.rank}: a life-safety claim needs its reason, and a reason needs the claim'
		)


# §6.1's table, transcribed. The `response` column is the section's own wording for what answers the
# question; `life_safety` is read off whether the answer decides care-seeking or household risk.
RANKED_QUESTIONS: tuple[RankedQuestion, ...] = (
	RankedQuestion(rank=1, question='Is it near me?', response='County and sub-county case map, updated daily',
	               life_safety=True,
	               why_life_safety='Whether the outbreak is in your sub-county decides whether you isolate a feverish child or treat it as malaria.'),
	RankedQuestion(rank=2, question='Is it safe to go to school / market / church / work?',
	               response='Location-specific guidance, not blanket advice', life_safety=True,
	               why_life_safety='A blanket answer sends a household into a gathering that is unsafe, or keeps a child home from a school that is not.'),
	RankedQuestion(rank=3, question='I have a fever right now — what do I do?',
	               response='Triage flow (see 6.3)', life_safety=True,
	               why_life_safety='This is the answer that decides whether someone seeks care in time; §6.3 exists because it is the most dangerous one to get wrong.'),
	RankedQuestion(rank=4, question='How do I protect my family?',
	               response='Household checklist, hygiene guidance, isolation prep', life_safety=True,
	               why_life_safety='Household transmission is where a single case becomes several, and the guidance is what prevents it.'),
	RankedQuestion(rank=5, question="What's true and what's rumour?",
	               response='Myth-busting library, updated daily', life_safety=True,
	               why_life_safety='A false cure or a false transmission route changes what a person does, which is the harm §6.4 exists to answer.'),
	RankedQuestion(rank=6, question="Where do I go if I'm sick, and who do I call?",
	               response='Facility finder, 719 hotline, USSD callback', life_safety=True,
	               why_life_safety='The route to care, and the number to call when there is no time to look for it.'),
	RankedQuestion(rank=7, question='Is there a vaccine or treatment?',
	               response='Honest, current, plain-language status', life_safety=True,
	               why_life_safety='A wrong answer here sends someone to an unproven remedy or keeps them from a free and tested one.'),
	RankedQuestion(rank=8, question='Can I get tested? Where? Is it free?',
	               response='Testing site list with cost and hours', life_safety=True,
	               why_life_safety='Cost and distance are why people do not test, so the answer decides whether they do.'),
	RankedQuestion(rank=9, question='How many cases today, and where?',
	               response='Dashboard, county-level', life_safety=False),
	RankedQuestion(rank=10, question='Is the border / school / church open or closed?',
	               response='Service status feed', life_safety=False),
)

QUESTION_BY_RANK: dict[int, RankedQuestion] = {q.rank: q for q in RANKED_QUESTIONS}
assert set(QUESTION_BY_RANK) == set(range(1, 11)), '§6.1 orders ten questions'

# §6.2.4: 'Local language first, English second. Never publish English-only for a life-safety
# message.' Swahili is the language whose absence makes a message English-only, which is why the
# requirement is stated as the set that must be present rather than as a language to forbid.
REQUIRED_LANGS: tuple[str, ...] = ('en', 'sw')


def life_safety_ranks() -> frozenset[int]:
	return frozenset(q.rank for q in RANKED_QUESTIONS if q.life_safety)


def is_life_safety(rank: int | None) -> bool:
	"""Whether an item answering §6.1's `rank` question is a life-safety message.

	An item that answers none of the ten — choking first aid, a hygiene tip outside the household
	checklist — is not one of the questions §6.1 ranks, and is not claimed as life-safety here. The
	claim is read off the section's own table rather than set per item, because whoever is drafting
	under time pressure is the last person to mark their own copy as life-safety, and §6.2.4 exists
	precisely for the message someone is rushing out.
	"""
	return rank is not None and rank in life_safety_ranks()
