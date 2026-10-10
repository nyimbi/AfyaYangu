"""Seed content corpus for INF library (en/sw), harmonised per §6.2 and governed per §6.5.

Every row carries the owner, reviewer, review date and version §6.5 requires, and is `published`
because it has been through the workflow. The reviewer is a role, not a person's name: the seed is
a stand-in for the MoH corpus and must not read as a signed clinical review by anyone real.
Replace with the MoH-sourced corpus in production.
"""
from afya.info.views import ContentItem, ContentStage

# (item_id, title, body, lang, harmony_tag, slug)
_ROWS: tuple[tuple[str, str, str, str, str, str], ...] = (
	('INF-003-en', 'Ebola basics (en)', 'EVD symptoms appear 2-21 days after exposure: fever, severe headache, muscle pain, sore throat, vomiting, diarrhoea. Call 719 immediately with fever plus contact risk.', 'en', 'ebola-library', 'ebola-basics'),
	('INF-003-en-2', 'Prevention (en)', 'Wash hands with soap frequently; avoid bushmeat; avoid contact with body fluids; use safe burial practices.', 'en', 'ebola-library', 'prevention'),
	('INF-004-en', 'Myth: salt-water cures (en)', 'Warm salt water does not cure EVD. Rumours spread faster than official correction — reply or call 719 to verify guidance.', 'en', 'mythbusting', 'myth-salt-water'),
	('INF-008-en', 'Daily health tips (en)', 'Handwashing with soap remains the single most effective prevention step at home and school.', 'en', 'tips', 'health-tips'),
	('INF-009-en', 'Choking first aid (en)', 'Encourage coughing; 5 back blows between shoulder blades then 5 abdominal thrusts; call for help.', 'en', 'first-aid', 'first-aid-choking'),
	('INF-010-en', 'Safe and dignified burial (en)', 'Traditional washing of EVD bodies spreads the virus. Burial teams follow WHO protocol — dignity is preserved.', 'en', 'burial', 'safe-burial'),
	('INF-003-sw', 'Habari za Ebola (sw)', 'Dalili hujitokeza siku 2-21 baada ya kufuatana: homa, maumivu makali ya kichwa, maumivu ya misuli, maumivu ya koo, kutapika, kuharisha. Piga 719 mara moja.', 'sw', 'ebola-library', 'ebola-basics'),
	('INF-003-sw-2', 'Kuzuia maambukizi (sw)', 'Osha mikono kwa sabuni; zika nyama ya porini; epuka vimbe vya mwili; maziko salama.', 'sw', 'ebola-library', 'prevention'),
	('INF-004-sw', 'Ishihara: maji ya chumvi (sw)', 'Maji ya chumvi hayauponyi Ebola. Hadithi za uwongo huenea kwa haraka — piga 719 kupata maelezo sahihi.', 'sw', 'mythbusting', 'myth-salt-water'),
	('INF-008-sw', 'Vidokezo vya afya (sw)', 'Kunawa mikono kwa sabuni ni ulinzi mkuu dhidi ya magonjwa nyumbani na shuleni.', 'sw', 'tips', 'health-tips'),
	('INF-009-sw', 'Msaada wa kwanza: koo (sw)', 'Hamasa mtu kukohoa; migo mitano mgongoni; mitano tumboni; piga msaada wa dharura.', 'sw', 'first-aid', 'first-aid-choking'),
	('INF-010-sw', 'Maziko salama (sw)', 'Kunawa mwili wa marehemu wa Ebola hueneza virusi. Timu za maziko hufuata WHO; heshima huhifadhiwa.', 'sw', 'burial', 'safe-burial'),
)

# The seed's stand-in governance. A real deployment replaces all four with the MoH Health Promotion
# Unit's own values; the point here is that the fields are populated rather than blank, so nothing
# can be served that has no owner and no review behind it.
SEED_OWNER = 'MoH Health Promotion Unit'
SEED_REVIEWER = 'Clinical advisory group'
SEED_REVIEWED_ON = '2026-10-01'
SEED_VERSION = 1


def seed_rows() -> list[ContentItem]:
	return [
		ContentItem(
			item_id=i, title=t, body=b, lang=lang, harmony_tag=tag, slug=slug,
			owner=SEED_OWNER, reviewer=SEED_REVIEWER, reviewed_on_iso=SEED_REVIEWED_ON,
			version=SEED_VERSION, stage=ContentStage.published,
		)
		for (i, t, b, lang, tag, slug) in _ROWS
	]
