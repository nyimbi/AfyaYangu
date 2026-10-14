"""Seed content corpus for INF library (en/sw), harmonised per §6.2 and governed per §6.5.

Every row carries the owner, reviewer, review date and version §6.5 requires, and is `published`
because it has been through the workflow. The reviewer is a role, not a person's name: the seed is
a stand-in for the MoH corpus and must not read as a signed clinical review by anyone real.
Replace with the MoH-sourced corpus in production.

§6.2.3's timestamp is not set here. `seed_rows()` returns items with no stamp and `InfoService.seed`
stamps each from its own review date — a corpus that claimed to have been updated when the process
started would render "Updated just now" for text written in September, which is the untrustworthy
freshness line §6.2.3 exists to prevent.
"""
from afya.info.myths import MYTHS
from afya.info.views import MYTH_TAG, ContentFormat, ContentItem, ContentStage

# §6.1's fifth question, "What's true and what's rumour?", which every myth row answers. Named here
# rather than repeated on each row because it is the same answer for all of them — a rumour library
# exists to answer exactly that question — and it is a life-safety rank, so it is what drags §6.2.4's
# bilingual-publication rule onto the myth corpus.
MYTH_RANK = 5

# (item_id, title, body, lang, harmony_tag, slug, answers_rank)
#
# `answers_rank` is which §6.1 question the item answers, or None when it answers none of the
# ten. It is what gives §6.2.4 its jurisdiction: ranks 1-8 are the section's life-safety
# questions, so an item answering one of them may not be published in a single language. The
# first-aid and hygiene rows answer no ranked question and are unconstrained.
_ROWS: tuple[tuple[str, str, str, str, str, str, int | None], ...] = (
	('INF-003-en', 'Ebola basics (en)', 'EVD symptoms appear 2-21 days after exposure: fever, severe headache, muscle pain, sore throat, vomiting, diarrhoea. Call 719 immediately with fever plus contact risk.', 'en', 'ebola-library', 'ebola-basics', 3),
	('INF-003-en-2', 'Prevention (en)', 'Wash hands with soap frequently; avoid bushmeat; avoid contact with body fluids; use safe burial practices.', 'en', 'ebola-library', 'prevention', 4),
	('INF-008-en', 'Hygiene: handwashing at five key times (en)', 'Handwashing with soap remains the single most effective hygiene step at home and school. Wash at five key times: after using the toilet, before preparing food, before eating, after cleaning a child, and after handling animals. Treat drinking water by boiling, chlorine or solar disinfection.', 'en', 'tips', 'health-tips', None),
	('INF-009-en', 'Choking first aid (en)', 'Encourage coughing; 5 back blows between shoulder blades then 5 abdominal thrusts; call for help.', 'en', 'first-aid', 'first-aid-choking', None),
	('INF-010-en', 'Safe and dignified burial (en)', 'Traditional washing of EVD bodies spreads the virus. Burial teams follow WHO protocol — dignity is preserved.', 'en', 'burial', 'safe-burial', 4),
	('INF-009-en-2', 'Bleeding first aid (en)', 'Press firmly on the wound with a clean cloth. Do not remove the cloth when it soaks through; add more cloth on top. If the wound is on an arm or leg, raise it above the heart. Use a tourniquet only for severe, life-threatening limb bleeding that pressure cannot stop. Call 719.', 'en', 'first-aid', 'first-aid-bleeding', None),
	('INF-009-en-3', 'Burns first aid (en)', 'Cool the burn under clean running water for 20 minutes. Remove rings, watches and tight clothing before the area swells. Do not apply ice, butter, oil or toothpaste. Cover the burn loosely with a clean, non-fluffy cloth. Do not burst any blisters. Get medical help for large or deep burns.', 'en', 'first-aid', 'first-aid-burns', None),
	('INF-009-en-4', 'Drowning first aid (en)', 'Get the person out of the water safely without becoming a casualty yourself. Check whether they are breathing. If they are not breathing, start CPR at once. Do not try to drain water from the lungs. Every near-drowning needs a clinic, even if the person seems fine afterwards.', 'en', 'first-aid', 'first-aid-drowning', None),
	('INF-009-en-5', 'Fractures first aid (en)', 'Do not move the person if a spine, neck or hip injury is possible. Immobilise the limb in the position you found it. Do not try to straighten the limb. Support it with a splint padded with cloth. Check circulation beyond the injury: press a nail and see if colour returns. Get help.', 'en', 'first-aid', 'first-aid-fractures', None),
	('INF-009-en-6', 'Poisoning first aid (en)', 'Do not make the person vomit. Keep the container, packet or plant and take it to the clinic. If poison touched the skin or eyes, rinse with clean water for 15 to 20 minutes. Call 719. In Kenya pesticides and paraffin are common poisons, especially for children, so store them locked away.', 'en', 'first-aid', 'first-aid-poisoning', None),
	('INF-009-en-7', 'Snakebite first aid (en)', 'Keep the person still and calm; movement spreads the venom. Immobilise the bitten limb and keep it below heart level. Remove rings, bangles and tight clothing. Do not cut, suck or apply a tight band. Get to a hospital with antivenom as fast as possible, and note the time of the bite.', 'en', 'first-aid', 'first-aid-snakebite', None),
	('INF-009-en-8', 'Seizure first aid (en)', 'Protect the person from injury: move hard objects away and cushion the head. Do not restrain them and do not put anything in the mouth. Time the seizure. When it stops, turn the person onto their side. Call 719 if it lasts more than 5 minutes or happens again.', 'en', 'first-aid', 'first-aid-seizure', None),
	('INF-009-en-9', 'Unconsciousness first aid (en)', 'Check whether the person is breathing. If they are breathing, put them in the recovery position on their side so the airway stays clear. Give nothing by mouth. Call 719. Stay with them and keep checking breathing until help arrives.', 'en', 'first-aid', 'first-aid-unconsciousness', None),
	('INF-009-en-10', 'CPR for adults and children (en)', 'Check for a response and for normal breathing. Call 719. Give 30 chest compressions: press hard and fast in the centre of the chest, 5 to 6 cm deep, 100 to 120 times a minute. Then give 2 rescue breaths. Keep going until help arrives. If you cannot or will not give breaths, do compression-only CPR.', 'en', 'first-aid', 'first-aid-cpr', None),
	('INF-009-en-11', 'Shock first aid (en)', 'Shock signs are pale, cold, clammy skin, a rapid weak pulse and confusion. Lay the person down and raise the legs to improve blood flow. Keep them warm with a blanket. Do not give food or drink. Get urgent medical help — shock can kill even when the original injury looks small.', 'en', 'first-aid', 'first-aid-shock', None),
	('INF-010-en-2', 'Who to contact for a safe burial (en)', 'Contact the public health burial team as soon as a death is reported. The team performs the safe, dignified burial; family members should not touch or wash the body. Call 719 or the district burial team number for your area. The team explains each step to the family.', 'en', 'burial', 'burial-contact-team', None),
	('INF-010-en-3', 'Cultural and religious considerations (en)', 'Burial teams work with the family, their faith and their custom. Muslim burial timing, Christian rites and traditional ceremony are all respected within the infection-control requirement. The family is consulted throughout. The body is treated with dignity, and a religious leader may be present at a safe distance.', 'en', 'burial', 'burial-cultural-religious', None),
	('INF-010-en-4', 'Support for grieving families (en)', 'Grief after an Ebola death is made heavier by isolation and stigma. Families may have been in quarantine and unable to be present at the death. Psychosocial support, follow-up visits and the 21-day monitoring period all matter. Do not leave a grieving family alone; link them to counselling and community support.', 'en', 'burial', 'burial-grieving-families', None),
	('INF-010-en-5', 'When the family cannot conduct the burial (en)', 'When the family cannot conduct the burial themselves, the burial team performs it. The family is told where the grave is and may be present at a safe distance. The family can still choose the prayers and hold a memorial later. No family is left without a grave to visit.', 'en', 'burial', 'burial-family-cannot', None),
	('INF-003-en-3', 'Protecting yourself and your family (en)', 'Ebola spreads through direct contact with the blood or body fluids of a person who is sick. Wash your hands with soap, avoid touching anyone with symptoms, and never handle a dead body yourself. Call 719 if anyone at home develops a fever.', 'en', 'ebola-library', 'protect-yourself-and-family', 4),
	('INF-003-en-4', 'If you think you were exposed (en)', 'Stop all contact with others and do not travel. Call 719 at once and say you had contact with a person who is sick. Check your temperature twice a day for 21 days and report any fever immediately.', 'en', 'ebola-library', 'exposed-to-ebola', 3),
	('INF-003-en-5', 'Testing and treatment (en)', 'Get tested early: a blood test at a designated site confirms Ebola, and testing is free at public facilities. There is no proven cure, but early supportive care with fluids, electrolytes and oxygen greatly improves the chance of survival. New treatments are still under trial.', 'en', 'ebola-library', 'testing-and-treatment', 7),
	('INF-003-en-6', 'Stigma and Ebola survivors (en)', 'Ebola spreads by contact, not by being near someone. Do not shun people who have recovered, or the health workers who cared for them. Stigma makes people hide their symptoms and delay care, so fighting it is a public-health measure.', 'en', 'ebola-library', 'stigma', None),
	('INF-003-en-7', 'What happens at an isolation facility (en)', 'An isolation unit is where Ebola care is given safely. You stay in a separate area, staff wear protective equipment, and you can speak to your family by phone. Do not stay at home once you have symptoms: going early improves your chance of recovery.', 'en', 'ebola-library', 'isolation-facility', 6),
	('INF-003-en-8', 'Recovery and survivors (en)', 'Most people who recover from Ebola gain immunity to the strain that infected them and are no longer infectious. Some survivors have lasting effects on the eyes, joints or hearing, so keep attending follow-up clinics. Blood and plasma from survivors has been used to treat others.', 'en', 'ebola-library', 'recovery-and-survivors', None),
	('INF-003-sw', 'Habari za Ebola (sw)', 'Dalili hujitokeza siku 2-21 baada ya kufuatana: homa, maumivu makali ya kichwa, maumivu ya misuli, maumivu ya koo, kutapika, kuharisha. Piga 719 mara moja.', 'sw', 'ebola-library', 'ebola-basics', 3),
	('INF-003-sw-2', 'Kuzuia maambukizi (sw)', 'Osha mikono kwa sabuni; zika nyama ya porini; epuka vimbe vya mwili; maziko salama.', 'sw', 'ebola-library', 'prevention', 4),
	('INF-003-sw-3', 'Kujikinga wewe na familia yako (sw)', 'Ebola huenea kwa kugusa moja kwa moja damu au vimbe vya mwili vya mtu mgonjwa. Osha mikono kwa sabuni, epuka kumgusa mtu mwenye dalili, na usishike mwili wa marehemu mwenyewe. Piga 719 kama mtu nyumbani anapata homa.', 'sw', 'ebola-library', 'protect-yourself-and-family', 4),
	('INF-003-sw-4', 'Ikiwa unadhani umeambukizwa (sw)', 'Acha kuwasiliana na wengine na usisafiri. Piga 719 mara moja na useme ulikuwa karibu na mtu mgonjwa. Pima joto lako mara mbili kwa siku kwa siku 21 na uripoti homa yoyote mara moja.', 'sw', 'ebola-library', 'exposed-to-ebola', 3),
	('INF-003-sw-5', 'Kupimwa na matibabu (sw)', 'Pimwa mapema: kipimo cha damu kwenye kituo kilichotengwa huhakikisha Ebola, na kupimwa ni bure katika vituo vya umma. Hakuna tiba ya uhakika, lakini huduma ya mapema ya msaada — maji, elektroliti na oksijeni — huongeza sana nafasi ya kuishi. Tiba mpya ziko chini ya majaribio.', 'sw', 'ebola-library', 'testing-and-treatment', 7),
	('INF-003-sw-6', 'Unyanyapaa na waokokaji wa Ebola (sw)', 'Ebola huenea kwa kugusa, si kwa kuwa karibu na mtu. Usiwatenge wale waliopona, wala wafanyakazi wa afya waliowahudumia. Unyanyapaa hufanya watu kuficha dalili na kuchelewa kupata matibabu, hivyo kupambana nao ni hatua ya afya ya umma.', 'sw', 'ebola-library', 'stigma', None),
	('INF-003-sw-7', 'Kinachotokea katika kituo cha kutengwa (sw)', 'Kituo cha kutengwa ni mahali ambapo huduma ya Ebola hutolewa kwa usalama. Unakaa katika eneo tofauti, wafanyakazi huvaa vifaa vya kujikinga, na unaweza kuongea na familia yako kwa simu. Usibaki nyumbani ukiwa na dalili: kufika mapema huongeza nafasi yako ya kupona.', 'sw', 'ebola-library', 'isolation-facility', 6),
	('INF-003-sw-8', 'Kupona na waokokaji (sw)', 'Watu wengi wanaopona Ebola hupata kinga dhidi ya aina iliyowaambukiza na hawana tena uwezo wa kuambukiza. Baadhi ya waokokaji hupata athari za kudumu kwenye macho, viungo au kusikia, hivyo endelea kuhudhuria kliniki za ufuatiliaji. Damu na plazima za waokokaji zimetumika kuwatibu wengine.', 'sw', 'ebola-library', 'recovery-and-survivors', None),
	('INF-008-sw', 'Vidokezo vya afya (sw)', 'Kunawa mikono kwa sabuni ni ulinzi mkuu dhidi ya magonjwa nyumbani na shuleni.', 'sw', 'tips', 'health-tips', None),
	('INF-009-sw', 'Msaada wa kwanza: koo (sw)', 'Hamasa mtu kukohoa; migo mitano mgongoni; mitano tumboni; piga msaada wa dharura.', 'sw', 'first-aid', 'first-aid-choking', None),
	('INF-010-sw', 'Maziko salama (sw)', 'Kunawa mwili wa marehemu wa Ebola hueneza virusi. Timu za maziko hufuata WHO; heshima huhifadhiwa.', 'sw', 'burial', 'safe-burial', 4),
	('INF-009-sw-2', 'Msaada wa kwanza: kutokwa na damu (sw)', 'Kaza kidonda kwa nguvu kwa kitambaa safi. Usiondoe kitambaa hicho kinapoloa; ongeza kingine juu yake. Kama kidonda kiko mkononi au mguuni, kiinue juu ya moyo. Tumia kamba ya kukaza (tourniquet) tu kwa kutokwa na damu kali mno kwenye kiungo. Piga 719.', 'sw', 'first-aid', 'first-aid-bleeding', None),
	('INF-009-sw-3', 'Msaada wa kwanza: kuungua (sw)', 'Pooza mahali palipoungua kwa maji safi yanayotiririka kwa dakika 20. Ondoa pete, saa na nguo kali kabla ya eneo kuvimba. Usiweke barafu, siagi, mafuta wala dawa ya meno. Funika kwa kitambaa safi kisichotoa vumbi. Usipasue malengelenge. Tafuta msaada kwa kuungua kubwa.', 'sw', 'first-aid', 'first-aid-burns', None),
	('INF-009-sw-4', 'Msaada wa kwanza: kuzama majini (sw)', 'Mtoe mtu majini kwa usalama bila wewe mwenyewe kuwa mhasiriwa. Angalia kama anapumua. Asipopumua, anza CPR mara moja. Usijaribu kutoa maji kwenye mapafu. Kila aliye karibu kuzama anahitaji kliniki, hata aonekane mzima.', 'sw', 'first-aid', 'first-aid-drowning', None),
	('INF-009-sw-5', 'Msaada wa kwanza: kuvunjika mfupa (sw)', 'Usimsogeze mtu kama jeraha la uti wa mgongo, shingo au nyonga linawezekana. Zuia kiungo kilivyoachwa. Usijaribu kukinyoosha. Kitegemeze kwa kifaa cha kushikilia kilichowekwa kitambaa. Angalia mzunguko wa damu zaidi ya jeraha: kaza ukucha na uone rangi inarudi. Tafuta msaada.', 'sw', 'first-aid', 'first-aid-fractures', None),
	('INF-009-sw-6', 'Msaada wa kwanza: sumu (sw)', 'Usimfanye mtu atapike. Weka chombo, pakiti au mmea na uupeleke kliniki. Sumu ikigusa ngozi au macho, suuza kwa maji safi kwa dakika 15 hadi 20. Piga 719. Kenya dawa za wadudu na mafuta ya taa ni sumu za kawaida, hasa kwa watoto, hivyo zihifadhi mahali pa kufungwa.', 'sw', 'first-aid', 'first-aid-poisoning', None),
	('INF-009-sw-7', 'Msaada wa kwanza: kuumwa na nyoka (sw)', 'Mweke mtu mtulivu na asiende; mwendo hueneza sumu. Zuia kiungo kilichoumwa na ukiweke chini ya kiwango cha moyo. Ondoa pete, bangili na nguo kali. Usikate, usifue wala kufunga kamba kali. Fika hospitali yenye kinga (antivenom) haraka iwezekanavyo, na uandike saa ya kuumwa.', 'sw', 'first-aid', 'first-aid-snakebite', None),
	('INF-009-sw-8', 'Msaada wa kwanza: kifafa (sw)', 'Mlinde mtu dhidi ya jeraha: ondoa vitu vigumu na uweke kitambaa chini ya kichwa. Usimzuie wala kuweka kitu mdomoni. Pima muda wa kifafa. Kinapoisha, mgeuze mtu alale kwa ubavu. Piga 719 kama kinadumu zaidi ya dakika 5 au kinarudia.', 'sw', 'first-aid', 'first-aid-seizure', None),
	('INF-009-sw-9', 'Msaada wa kwanza: kupoteza fahamu (sw)', 'Angalia kama mtu anapumua. Akipumua, mweke katika mkao wa kupona kwa ubavu ili njia ya hewa ibaki wazi. Usimpe kitu chochote mdomoni. Piga 719. Baki naye na uendelee kuangalia kupumua hadi msaada ufike.', 'sw', 'first-aid', 'first-aid-unconsciousness', None),
	('INF-009-sw-10', 'CPR kwa watu wazima na watoto (sw)', 'Angalia kama mtu anaitikia na kama anapumua kawaida. Piga 719. Toa mikandamizo 30 ya kifua katikati ya kifua. Kaza kwa nguvu na kwa haraka, sentimita 5 hadi 6 kwa kina, mara 100 hadi 120 kwa dakika. Kisha toa pumzi 2 za kuokoa. Endelea hadi msaada ufike. Kama huwezi kutoa pumzi, fanya mikandamizo tu.', 'sw', 'first-aid', 'first-aid-cpr', None),
	('INF-009-sw-11', 'Msaada wa kwanza: mshtuko (shock) (sw)', 'Dalili za mshtuko ni ngozi iliyopauka, baridi na yenye jasho, mapigo ya haraka na hafifu, na kuchanganyikiwa. Mlaze mtu chini na uinue miguu ili damu itiririke vizuri. Mweke aendelee kuwa joto kwa blanketi. Usimpe chakula wala kinywaji. Tafuta msaada wa dharura — mshtuko unaweza kuua hata jeraha lionekane dogo.', 'sw', 'first-aid', 'first-aid-shock', None),
	('INF-010-sw-2', 'Nani wa kuwasiliana kwa maziko salama (sw)', 'Wasiliana na timu ya maziko ya afya ya umma mara kifo kinaporipotiwa. Timu hufanya maziko salama yenye heshima; wanafamilia hawapaswi kugusa wala kunawa mwili. Piga 719 au namba ya timu ya maziko ya wilaya yako. Timu huwaeleza familia kila hatua.', 'sw', 'burial', 'burial-contact-team', None),
	('INF-010-sw-3', 'Mambo ya kitamaduni na kidini (sw)', 'Timu za maziko hufanya kazi na familia, imani yao na desturi zao. Muda wa maziko wa Kiislamu, ibada za Kikristo na sherehe za jadi zote huheshimiwa ndani ya sharti la kudhibiti maambukizi. Familia hushauriwa wakati wote. Mwili hushughulikiwa kwa heshima, na kiongozi wa dini anaweza kuwepo kwa mbali salama.', 'sw', 'burial', 'burial-cultural-religious', None),
	('INF-010-sw-4', 'Msaada kwa familia zinazoomboleza (sw)', 'Huzuni baada ya kifo cha Ebola huzidishwa na kutengwa na unyanyapaa. Huenda familia zilikuwa karantini na hazikuweza kuwepo wakati wa kifo. Msaada wa kisaikolojia, ufuatiliaji, na kipindi cha uangalizi wa siku 21 vyote ni muhimu. Usiache familia inayoomboleza peke yake; iunganishe na ushauri na msaada wa jamii.', 'sw', 'burial', 'burial-grieving-families', None),
	('INF-010-sw-5', 'Familia inaposhindwa kufanya maziko yenyewe (sw)', 'Familia inaposhindwa kufanya maziko yenyewe, timu ya maziko huyafanya. Familia huelezwa kaburi lilipo na inaweza kuwepo kwa mbali salama. Familia bado inaweza kuchagua sala na kufanya ukumbusho baadaye. Hakuna familia inayoachwa bila kaburi la kutembelea.', 'sw', 'burial', 'burial-family-cannot', None),
	('INF-008-en-2', 'Nutrition for a healthy family (en)', 'Build meals from what is local and cheap. Use ugali or rice, sukuma wiki or other greens, beans, omena or eggs, and fruit in season. Breastfeed exclusively for the first 6 months. After 6 months add soft mashed family food alongside breast milk. Give vitamin A when the clinic offers it.', 'en', 'tips', 'health-tips-nutrition', None),
	('INF-008-en-3', 'Mental health: stress and anxiety (en)', 'Stress and anxiety are common, and they are treatable. Talk to someone you trust. Keep sleeping and eating regularly. Avoid alcohol as a way to cope. If low mood or worry lasts more than two weeks, get help now. Call 719 or a counselling line. There is no shame in asking for help.', 'en', 'tips', 'health-tips-mental-health', None),
	('INF-008-en-4', 'First aid basics at home (en)', 'Stop bleeding by pressing firmly on the wound with a clean cloth. Cool a burn under running water for 20 minutes. Do not move anyone with a suspected back or neck injury. Call 719 for anything serious. This card is the short version. The full first aid guide is in the app and works offline.', 'en', 'tips', 'health-tips-first-aid', None),
	('INF-008-en-5', 'Child development: what to expect (en)', 'Most babies sit by about 6 months and walk by about 12 months. First words come between 12 and 18 months. Talk, sing and play with your child every day. That is how the brain grows. Take the growth card to every clinic visit. Go to a clinic at once if a child stops feeding, has convulsions, or is very sleepy or floppy.', 'en', 'tips', 'health-tips-child-development', None),
	('INF-008-en-6', 'Living with a chronic disease (en)', 'For high blood pressure and diabetes, take your medicine every day. Take it even when you feel well. Feeling fine is the medicine working. Cut down on salt and on sugary drinks. Keep your clinic appointments. Know your numbers: blood pressure, blood sugar and weight. Bring your card to every visit.', 'en', 'tips', 'health-tips-chronic-disease', None),
	('INF-008-en-7', 'Preventing injuries at home and on the road (en)', 'Wear a helmet on a boda-boda, and make sure children do too. Use seatbelts and a child seat. Never leave a jiko or fire unattended. Keep paraffin and pesticides locked away from food and out of children’s reach. Cover water containers and fence open pits and wells.', 'en', 'tips', 'health-tips-injury-prevention', None),
	('INF-008-en-8', 'Sexual and reproductive health (en)', 'Family planning is free at public clinics, and there are several methods. You can choose the one that suits you. Start antenatal visits early in pregnancy. Condoms protect against both pregnancy and HIV. Young people can ask for adolescent-friendly services without being judged. You have the right to decide about your own body.', 'en', 'tips', 'health-tips-srh', None),
	('INF-008-sw-2', 'Lishe kwa familia yenye afya (sw)', 'Jenga milo kwa vyakula vya hapa na vya bei nafuu. Tumia ugali au wali, sukuma wiki au mboga nyingine, maharage, omena au mayai, na matunda ya msimu. Nyonyesha maziwa pekee kwa miezi 6 ya kwanza. Baada ya miezi 6, ongeza chakula laini cha familia pamoja na maziwa. Toa vitamini A kliniki inapotoa.', 'sw', 'tips', 'health-tips-nutrition', None),
	('INF-008-sw-3', 'Afya ya akili: msongo na wasiwasi (sw)', 'Msongo wa mawazo na wasiwasi ni kawaida, na yanatibika. Zungumza na mtu unayemwamini. Lala na kula kwa mpangilio. Epuka pombe kama njia ya kukabiliana. Kama huzuni au wasiwasi unadumu zaidi ya wiki mbili, tafuta msaada sasa. Piga 719 au namba ya ushauri. Hakuna aibu kuomba msaada.', 'sw', 'tips', 'health-tips-mental-health', None),
	('INF-008-sw-4', 'Misingi ya msaada wa kwanza nyumbani (sw)', 'Zuia kutokwa na damu kwa kukaza kidonda kwa nguvu kwa kitambaa safi. Pooza moto kwa maji yanayotiririka kwa dakika 20. Usimsogeze mtu mwenye jeraha la mgongo au shingo. Piga 719 kwa jambo lolote kubwa. Kadi hii ni toleo fupi. Mwongozo kamili wa msaada wa kwanza uko kwenye app na hufanya kazi bila mtandao.', 'sw', 'tips', 'health-tips-first-aid', None),
	('INF-008-sw-5', 'Ukuaji wa mtoto: nini cha kutarajia (sw)', 'Watoto wengi hukaa kwa takriban miezi 6 na hutembea kwa takriban miezi 12. Maneno ya kwanza huja kati ya miezi 12 na 18. Zungumza, imba na cheza na mtoto wako kila siku. Ndivyo ubongo unakua. Peleka kadi ya ukuaji kila kliniki. Nenda kliniki mara moja kama mtoto anaacha kunyonya, ana kifafa, au ni msinzi sana au legelege.', 'sw', 'tips', 'health-tips-child-development', None),
	('INF-008-sw-6', 'Kuishi na ugonjwa wa kudumu (sw)', 'Kwa shinikizo la damu na kisukari, tumia dawa kila siku. Tumia hata ujisikie mzima. Kujisikia vizuri ni dawa inafanya kazi. Punguza chumvi na vinywaji vyenye sukari nyingi. Hudhuria kliniki kwa wakati. Jue namba zako: shinikizo la damu, sukari ya damu na uzito. Beba kadi yako kila ziara.', 'sw', 'tips', 'health-tips-chronic-disease', None),
	('INF-008-sw-7', 'Kuzuia majeraha nyumbani na barabarani (sw)', 'Vaa kofia ya chuma kwenye boda-boda, na hakikisha watoto wanavaa pia. Tumia mikanda ya usalama na kiti cha mtoto. Usiache jiko au moto bila mtu. Hifadhi mafuta ya taa na dawa za wadudu mahali pa kufungwa, mbali na chakula na mbali na watoto. Funika vyombo vya maji na ziba mashimo na visima wazi.', 'sw', 'tips', 'health-tips-injury-prevention', None),
	('INF-008-sw-8', 'Afya ya uzazi na ngono (sw)', 'Upangaji wa uzazi ni bure katika kliniki za umma, na kuna njia kadhaa. Unaweza kuchagua inayokufaa. Anza ziara za ujauzito mapema. Kondomu hulinda dhidi ya ujauzito na VVU. Vijana wanaweza kuomba huduma rafiki kwa vijana bila kuhukumiwa. Una haki ya kuamua kuhusu mwili wako.', 'sw', 'tips', 'health-tips-srh', None),
)

# Which harmony tag a rendition inherits from its parent item. A rendition carries no tag of its own
# — it is the same subject as the text it illustrates — so the tag is read off the parent's slug
# rather than restated on the row, where it could drift from the parent it belongs to.
_PARENT_TAG: dict[str, str] = {
	'first-aid-choking': 'first-aid',
	'first-aid-bleeding': 'first-aid',
	'first-aid-burns': 'first-aid',
	'first-aid-drowning': 'first-aid',
	'first-aid-fractures': 'first-aid',
	'first-aid-poisoning': 'first-aid',
	'first-aid-snakebite': 'first-aid',
	'first-aid-seizure': 'first-aid',
	'first-aid-unconsciousness': 'first-aid',
	'first-aid-cpr': 'first-aid',
	'first-aid-shock': 'first-aid',
	# §INF-003's Format cell: "illustrations, audio versions, video versions".
	'what-is-ebola': 'ebola-library',
	'ebola-basics': 'ebola-library',
	'protect-yourself-and-family': 'ebola-library',
	'prevention': 'ebola-library',
	# §INF-008's Format cell: "30-second videos, audio clips".
	'health-tips': 'tips',
	'health-tips-nutrition': 'tips',
}

# §INF-003's and §INF-008's Format cells ask for renditions of the text — "illustrations", "audio
# versions", "video versions", "30-second videos", "audio clips" — and §INF-009's Description asks
# for "offline first-aid instructions with illustrations". A rendition is not a row in `_ROWS`: it
# has no prose of its own, so it carries the parent item's title and an empty body, and what makes
# it real is `media_ref`, the file it points at. The model refuses a non-text format without one,
# which is what stops "we made an audio version" from being a claim with nothing to play.
#
# (item_id, title, parent_slug, format, media_ref)
_RENDITIONS: tuple[tuple[str, str, str, ContentFormat, str], ...] = (
	('INF-009-illus-choking', 'Choking first aid (illustration)', 'first-aid-choking', ContentFormat.illustration, 'media/first-aid/choking.svg'),
	('INF-009-illus-bleeding', 'Bleeding first aid (illustration)', 'first-aid-bleeding', ContentFormat.illustration, 'media/first-aid/bleeding.svg'),
	('INF-009-illus-burns', 'Burns first aid (illustration)', 'first-aid-burns', ContentFormat.illustration, 'media/first-aid/burns.svg'),
	('INF-009-illus-drowning', 'Drowning first aid (illustration)', 'first-aid-drowning', ContentFormat.illustration, 'media/first-aid/drowning.svg'),
	('INF-009-illus-fractures', 'Fractures first aid (illustration)', 'first-aid-fractures', ContentFormat.illustration, 'media/first-aid/fractures.svg'),
	('INF-009-illus-poisoning', 'Poisoning first aid (illustration)', 'first-aid-poisoning', ContentFormat.illustration, 'media/first-aid/poisoning.svg'),
	('INF-009-illus-snakebite', 'Snakebite first aid (illustration)', 'first-aid-snakebite', ContentFormat.illustration, 'media/first-aid/snakebite.svg'),
	('INF-009-illus-seizure', 'Seizure first aid (illustration)', 'first-aid-seizure', ContentFormat.illustration, 'media/first-aid/seizure.svg'),
	('INF-009-illus-unconsciousness', 'Unconsciousness first aid (illustration)', 'first-aid-unconsciousness', ContentFormat.illustration, 'media/first-aid/unconsciousness.svg'),
	('INF-009-illus-cpr', 'CPR for adults and children (illustration)', 'first-aid-cpr', ContentFormat.illustration, 'media/first-aid/cpr.svg'),
	('INF-009-illus-shock', 'Shock first aid (illustration)', 'first-aid-shock', ContentFormat.illustration, 'media/first-aid/shock.svg'),
	# §INF-003's Format cell: "Short articles (under 200 words), illustrations, audio versions, video
	# versions." The articles are `_ROWS`; these are the other three.
	('INF-003-illus-1', 'How Ebola spreads (illustration)', 'ebola-basics', ContentFormat.illustration, 'media/ebola/what-is-ebola.svg'),
	('INF-003-illus-2', 'Protect your family from Ebola (illustration)', 'protect-yourself-and-family', ContentFormat.illustration, 'media/ebola/protect-your-family.svg'),
	('INF-003-audio-1', 'How Ebola spreads (audio)', 'ebola-basics', ContentFormat.audio, 'media/ebola/what-is-ebola.mp3'),
	('INF-003-audio-2', 'Protecting your family (audio)', 'protect-yourself-and-family', ContentFormat.audio, 'media/ebola/protect-your-family.mp3'),
	('INF-003-audio-3', 'Prevention (audio)', 'prevention', ContentFormat.audio, 'media/ebola/prevention.mp3'),
	('INF-003-video-1', 'Handwashing in 30 seconds (video)', 'prevention', ContentFormat.video, 'media/ebola/prevention-30s.mp4'),
	('INF-003-video-2', 'What Ebola is (video)', 'ebola-basics', ContentFormat.video, 'media/ebola/what-is-ebola.mp4'),
	# §CHAN-004's "Animated explainers on symptoms and prevention." Unlike the rows above, these are
	# not hand-authored files: `afya.info.explainers` generates each from the *parent item's own*
	# sentences, so the asset adds motion to copy §6.5 has already cleared rather than introducing new
	# clinical text. Symptoms (`ebola-basics`) and prevention (`prevention`) are the two subjects the
	# bullet names. Both parents are `ebola-library` articles — English, like every row in this table,
	# because `rendition_rows` stamps each row `en` — and the generator reads the *parent's* `lang` for
	# the captions rather than the row's, so a Swahili parent would be captioned in Swahili without a
	# second row here (and without a second asset the slug-keyed `renditions_of` would hand to both
	# languages of the article at once).
	('INF-003-anim-1', 'Ebola symptoms (animated explainer)', 'ebola-basics', ContentFormat.animation, 'media/explainers/ebola-basics.svg'),
	('INF-003-anim-2', 'Ebola prevention (animated explainer)', 'prevention', ContentFormat.animation, 'media/explainers/prevention.svg'),
	# §INF-008's Format cell: "Short cards, 30-second videos, audio clips." The cards are the
	# `tips`-tagged `_ROWS` — a card is prose, not a rendition — so these are the video and the audio.
	('INF-008-video-1', 'Hand hygiene in 30 seconds (video)', 'health-tips', ContentFormat.video, 'media/tips/hygiene-30s.mp4'),
	('INF-008-video-2', 'Nutrition in 30 seconds (video)', 'health-tips-nutrition', ContentFormat.video, 'media/tips/nutrition-30s.mp4'),
	('INF-008-audio-1', 'Hygiene tips (audio clip)', 'health-tips', ContentFormat.audio, 'media/tips/hygiene.mp3'),
	('INF-008-audio-2', 'Nutrition tips (audio clip)', 'health-tips-nutrition', ContentFormat.audio, 'media/tips/nutrition.mp3'),
)


# The title a myth row carries is the corpus's own short label, and the language's own word for
# "myth" — `Hadithi` in Swahili, not the English word borrowed. The corpus used to title the Swahili
# row "Ishihara: maji ya chumvi", which is a colour-vision test and not a word for anything a reader
# of that row would recognise; a label reaches a screen, so a wrong one is a screen with a wrong
# word on it.
_MYTH_TITLE = {'en': 'Myth: {label} (en)', 'sw': 'Hadithi: {label} (sw)'}


def myth_rows() -> list[ContentItem]:
	"""§INF-004's corpus as library items, one per myth per language.

	`answers_rank=MYTH_RANK` on every row because a rumour correction answers §6.1's fifth question —
	"What's true and what's rumour?" — which §6.2.4 counts as life-safety, so a myth drafted in one
	language only is withheld from the library in both. That is the correct behaviour and it is why
	the corpus asserts both languages per topic.

	`title` is the label and `claim` is the rumour, kept apart because §INF-004's card prints the
	claim under "Rumour:" — a title that *is* the claim would render the rumour twice on the card it
	appears on.
	"""
	return [
		ContentItem(
			item_id=f'INF-004-{m.slug}-{m.lang}', title=_MYTH_TITLE[m.lang].format(label=m.label),
			body=m.fact, lang=m.lang, harmony_tag=MYTH_TAG, slug=m.slug,
			owner=SEED_OWNER, reviewer=SEED_REVIEWER, reviewed_on_iso=SEED_REVIEWED_ON,
			version=SEED_VERSION, stage=ContentStage.published, answers_rank=MYTH_RANK,
			format=ContentFormat.article, claim=m.claim, source=m.source,
		)
		for m in MYTHS
	]


def rendition_rows() -> list[ContentItem]:
	"""The non-text renditions, as items. Empty body by construction: a rendition's content is the
	file at `media_ref`, and a body here would be a second copy of the parent's text that nothing
	keeps in step with it.

	Every row is `en`, and that is a limitation rather than a claim: the parents these renditions hang
	off are English articles, and a `sw` parent would need its own row and its own asset. It matters
	where a rendition *speaks* — an explainer's captions are in a language — and the language is read
	off the parent item by `afya.info.explainers`, never off this row, so a Swahili parent cannot be
	captioned in English by a row that says `en`. What a `sw` row would add is a *second* asset, which
	the slug-keyed `renditions_of` would then hand to both languages of the article at once — so the
	per-language rendition is a change to the lookup, not a line in this table.
	"""
	return [
		ContentItem(
			item_id=i, title=t, body='', lang='en', harmony_tag=_PARENT_TAG[parent],
			slug=f'{parent}-{fmt.value}', owner=SEED_OWNER, reviewer=SEED_REVIEWER,
			reviewed_on_iso=SEED_REVIEWED_ON, version=SEED_VERSION, stage=ContentStage.published,
			format=fmt, media_ref=ref, rendition_of=parent,
		)
		for (i, t, parent, fmt, ref) in _RENDITIONS
	]

# The seed's stand-in governance. A real deployment replaces all four with the MoH Health Promotion
# Unit's own values; the point here is that the fields are populated rather than blank, so nothing
# can be served that has no owner and no review behind it.
SEED_OWNER = 'MoH Health Promotion Unit'
SEED_REVIEWER = 'Clinical advisory group'
SEED_REVIEWED_ON = '2026-10-01'
SEED_VERSION = 1

# The format a text row is delivered in, by tag. §INF-008 prints "Short cards" and §INF-003 prints
# "Short articles (under 200 words)" for what is, in both cases, prose — a card is a shorter article,
# not a different medium. So the format is a property of the section the row belongs to rather than a
# column on every row: a `tips` row is a card and an `ebola-library` row is an article, and putting
# it here means a new tip cannot be added as an article by forgetting to say otherwise. A tag not
# named falls back to `article`, which is what the default on the model is for.
#
# `mythbusting` is named explicitly even though it falls back to the same `article`: §INF-004 prints
# no Format cell for a *medium* — its Format cell is the Rumour/Fact/Source structure — so the
# delivery format is the default, and saying so here is the difference between "no card was asked
# for" and "a card was asked for and nobody wrote it".
_TAG_FORMAT: dict[str, ContentFormat] = {
	'tips': ContentFormat.card,
	'ebola-library': ContentFormat.article,
	MYTH_TAG: ContentFormat.article,
}


def seed_rows() -> list[ContentItem]:
	return [
		ContentItem(
			item_id=i, title=t, body=b, lang=lang, harmony_tag=tag, slug=slug,
			owner=SEED_OWNER, reviewer=SEED_REVIEWER, reviewed_on_iso=SEED_REVIEWED_ON,
			version=SEED_VERSION, stage=ContentStage.published, answers_rank=rank,
			format=_TAG_FORMAT.get(tag, ContentFormat.article),
		)
		for (i, t, b, lang, tag, slug, rank) in _ROWS
	] + myth_rows()
