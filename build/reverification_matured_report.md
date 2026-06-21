# Re-Verification Report: 120 Narrow-Matured "Not Located" CIKs

Generated: 2026-06-21

## Summary

- Originally not located: 120
- **Newly verified (on-time): 4**
- **Newly verified (late): 1**
- Still not located: 113
  - No Wayback snapshots available: 45
  - Snapshots checked, no matrix found: 68
- No company URL found in SEC filings: 2

## Root Cause Analysis

### Why stage 09 failed to find these 6 matrices

1. **No website in SEC submissions API**: All 120 CIKs have empty website and
   investorWebsite fields in their SEC submissions data. Stage 09 relied on
   these fields for Wayback URL discovery.
2. **Filing agent URLs mined instead of company URLs**: Stage 09 fallback URL
   mining from cached EDGAR filings picked up filing agent domains (e.g.,
   compsciresources.com) instead of actual company websites, because the
   EXCLUDED_WEBSITE_DOMAINS list did not include all filing agents.
3. **Wayback CDX API rate limiting**: The CDX API became rate-limited from our
   IP after repeated queries, preventing snapshot discovery.
4. **No EDGAR filing**: EDGAR full-text search confirmed that none of the 120
   CIKs filed a Board Diversity Matrix with the SEC. Rule 5606 allowed
   website-only disclosure, which is why the matrix exists only on company
   websites (archived by Wayback).

### How stage 16 fixed it

1. Re-mined company URLs from cached EDGAR filings with expanded exclusion
   list for filing agents, transfer agents, and proxy services.
2. Scored URLs by company name match in hostname (highest signal).
3. Fetched Wayback snapshots directly (bypassing rate-limited CDX API) by
   constructing timestamp-based URLs.
4. Checked root, /investors, and /governance subpages at 3 date offsets.

## Newly Verified (6 CIKs)

### Published On-Time (4)

| CIK | Ticker | Legal Name | Due Date | Pub Date | Source | Conf |
|-----|--------|------------|----------|-----------|--------|------|
| 1844392 | MRAI | Marpai, Inc. | 2022-10-27 | 2022-10-27 | website_archive | 0.65 |
| 1187953 | CELZ | CREATIVE MEDICAL TECHNOLOGY HOLDINGS, IN | 2022-12-06 | 2022-12-06 | website_archive | 0.85 |
| 1875091 | NRSN | NeuroSense Therapeutics Ltd. | 2022-12-09 | 2023-01-08 | website_archive | 0.65 |
| 1748137 | NEOV | NeoVolta Inc. | 2023-07-29 | 2023-07-29 | website_archive | 0.65 |

### Published Late (1)

| CIK | Ticker | Legal Name | Due Date | Pub Date | Source | Conf |
|-----|--------|------------|----------|-----------|--------|------|
| 1872302 | NA | Nano Labs Ltd | 2023-07-12 | 2023-10-10 | website_archive | 0.65 |

## Not Located: No Wayback Snapshots (45 CIKs)

These companies websites were not archived by the Internet Archive around their
due date, so no snapshot could be fetched to verify website-only disclosure.

| CIK | Ticker | Legal Name | Due Date | Company URLs |
|-----|--------|------------|----------|--------------|
| 1829794 | EMPD | Empery Digital Inc. | 2022-10-06 | https://ir.volcon.com;https://volcon.com |
| 1615055 | - | IsoPlexis Corp | 2022-10-08 | https://investors.isoplexis.com;https://isoplexis. |
| 1419554 | BBLG | Bone Biologics Corp | 2022-10-13 | https://bonebiologics.com |
| 1840229 | INKT | MiNK Therapeutics, Inc. | 2022-10-15 | https://investor.minktherapeutics.com;https://mink |
| 1868734 | - | CinCor Pharma, Inc. | 2023-01-07 | https://cincor.com |
| 1874875 | HOUR | Hour Loop, Inc | 2023-01-07 | https://hourloop.com;https://persalary.com |
| 1861657 | CNTN | Canton Strategic Holdings, Inc | 2023-01-12 | https://annualgeneralmeetings.com;https://hillstre |
| 1872964 | MTEK | Maris Tech Ltd. | 2023-02-02 | https://maristech.com;https://maris-tech.com |
| 1786205 | ACLX | Arcellx, Inc. | 2023-02-04 | https://arcellx.com;https://arc.com |
| 1875558 | NVCT | Nuvectis Pharma, Inc. | 2023-02-04 | https://nuvectis.com;https://pwc.com |
| 1880613 | DRCT | Direct Digital Holdings, Inc. | 2023-02-11 | https://ir.directdigitalholdings.com;https://direc |
| 1872812 | - | TC BioPharm (Holdings) plc | 2023-02-11 | https://ir.tcbiopharm.com;https://tcbiopharm.com |
| 1482541 | BNC | CEA Industries Inc. | 2023-02-14 | https://ceaindustries.com;https://ceaindustrialsup |
| 1835615 | MHUAF | Meihua International Medical T | 2023-02-16 | https://ir.meihuamed.com;https://meihua.com |
| 1851860 | - | SMART FOR LIFE, INC. | 2023-02-16 | https://smartforlife.com;https://smartforlifecorp. |
| 1880438 | ANTX | AN2 Therapeutics, Inc. | 2023-03-25 | https://investor.an2therapeutics.com;https://an2th |
| 1894954 | XPON | Expion360 Inc. | 2023-04-01 | https://investors.expion360.com;https://expion360. |
| 1892274 | GV | Visionary Holdings Inc. | 2023-05-17 | https://visiongroupca.com;https://canada.ca |
| 1816319 | LYTHF | Lytus Technologies Holdings PT | 2023-06-15 | https://lytuscorp.com;https://lyt.com |
| 1674440 | YYAI | AIRWA INC. | 2023-06-16 | https://connexasports.com;https://slingerbag.com |
| 1826376 | GSUN | Golden Sun Technology Group Lt | 2023-06-22 | https://goldensunedugrpltd.com;https://ir.jtyjyjt. |
| 1881472 | MEGL | Magic Empire Global Ltd | 2023-08-05 | https://magicempiregloballtd.com;https://meglmagic |
| 1425355 | SUIG | SUI Group Holdings Ltd. | 2023-08-09 | https://millcityventures3.com;https://pacificstock |
| 1014763 | AIMD | Ainos, Inc. | 2023-08-10 | https://ainos.com;https://aimd.com |
| 1905956 | TGL | TREASURE GLOBAL INC | 2023-08-11 | https://treasureglobalinc.com;https://treasureglob |
| 1921865 | ASPI | ASP Isotopes Inc. | 2023-11-10 | https://investors.aspisotopes.com;https://aspi.com |
| 1892500 | CMND | Clearmind Medicine Inc. | 2023-11-16 | https://clearmindmedicineinc.com;https://clearmind |
| 1884072 | - | Adamas One Corp. | 2023-12-09 | https://adamasone.com |
| 1519449 | SKWD | Skyward Specialty Insurance Gr | 2024-01-13 | https://investors.skywardinsurance.com;https://sky |
| 1939965 | SLMT | Brera Holdings PLC | 2024-01-27 | https://investors.breraholdings.com;https://brera. |
| 1888886 | GPCR | Structure Therapeutics Inc. | 2024-02-03 | https://structuretx.com |
| 1933414 | MLYS | Mineralys Therapeutics, Inc. | 2024-02-10 | https://mineralystx.com |
| 1895618 | GXAI | GAXOS.AI INC. | 2024-02-15 | https://nftgamingcompanyinc.com;https://gaxos.ai |
| 1930179 | ARBB | ARB IOT Group Ltd | 2024-04-05 | https://arbiotgroup.com |
| 1899658 | WLGSF | WANG & LEE GROUP, Inc. | 2024-04-20 | https://wangnlee.com.hk;https://emsd.gov.hk |
| 1951067 | CISS | C3is Inc. | 2024-06-12 | https://c3is.pro |
| 1891856 | GENK | GEN Restaurant Group, Inc. | 2024-06-28 | https://genkoreanbbq.com |
| 1765850 | AURE | Aurelion Inc. | 2024-07-06 | https://prestigewm.hk.com;https://marcumasia.cn |
| 1904286 | MIRA | MIRA PHARMACEUTICALS, INC. | 2024-08-03 | https://mirapharmaceuticals.com;https://web.lumico |
| 1928581 | GMEX | GMEX Robotics Corp | 2024-08-08 | https://fitellcorp.com |
| 1843165 | YHC | LQR House Inc. | 2024-08-10 | https://lqrhouseinc.com;https://lqrhouse.com |
| 1935418 | FMST | Foremost Clean Energy Ltd. | 2024-08-23 | https://foremostlithium.com;https://mrctemiscaming |
| 1963439 | TURB | Turbo Energy, S.A. | 2024-09-22 | https://turbo-e.com;https://fr.enerfip.eu |
| 1922335 | SYRA | Syra Health Corp | 2024-09-29 | https://ir.syrahealth.com;https://syrahealth.com |
| 1963685 | RR | RICHTECH ROBOTICS INC. | 2024-11-17 | https://richtechrobotics.com;https://richtechrobot |

## Not Located: Snapshots Checked But No Matrix (68 CIKs)

Wayback snapshots were fetched but did not contain a Board Diversity Matrix.
Possible reasons: (a) matrix on a subpage we did not check, (b) matrix in a
PDF we did not fetch, or (c) company did not publish a matrix.

| CIK | Ticker | Legal Name | Due Date | Snaps | Company URLs |
|-----|--------|------------|----------|-------|--------------|
| 1605888 | ATLN | ATLANTIC INTERNATIONAL CORP. | 2022-08-27 | 6 | https://seqll.com;https://lyneer.com |
| 1836470 | SRAD | Sportradar Group AG | 2022-09-14 | 10 | https://investors.sportradar.com;https:/ |
| 1841675 | ARBK | Argo Blockchain Plc | 2022-09-23 | 12 | https://argoblockchain.com;https://prima |
| 1804469 | GFAI | Guardforce AI Co., Ltd. | 2022-09-30 | 2 | https://guardforceai.com;https://mordori |
| 1856028 | - | Stronghold Digital Mining, Inc | 2022-10-20 | 2 | https://ir.strongholddigitalmining.com;h |
| 1653384 | RWAY | Runway Growth Finance Corp. | 2022-10-21 | 1 | https://investors.runwaygrowth.com;https |
| 1709048 | GFS | GLOBALFOUNDRIES Inc. | 2022-10-28 | 6 | https://investors.gf.com;https://gf.com |
| 1870940 | AIRS | Airsculpt Technologies, Inc. | 2022-10-29 | 5 | https://airsculpt.elitebodysculpture.com |
| 1831283 | LIANY | LianBio | 2022-11-01 | 2 | https://lianbiopharma.com;https://lianbi |
| 1392694 | SURG | SurgePays, Inc. | 2022-11-03 | 2 | https://surgepays.com;https://surgeholdi |
| 1872529 | MDXH | MDxHealth SA | 2022-11-04 | 3 | https://mdxhealth.com |
| 1871149 | - | Real Good Food Company, Inc. | 2022-11-05 | 1 | https://investors.realgoodfoods.com;http |
| 1718224 | BTBD | BT Brands, Inc. | 2022-11-12 | 2 | https://btbrands.com;https://brand.bt.co |
| 1840416 | SSM | Sono Group N.V. | 2022-11-17 | 7 | https://ir.sonomotors.com;https://sonomo |
| 1769697 | FNUC | Frontier Nuclear & Minerals In | 2022-11-19 | 12 | https://snowlakelithium.com;https://nrca |
| 1876581 | IMPP | Imperial Petroleum Inc./Marsha | 2022-11-23 | 12 | https://imperialpetro.com;https://impp.c |
| 1720671 | - | HashiCorp, Inc. | 2022-12-09 | 6 | https://ir.hashicorp.com;https://hashico |
| 1084267 | MOBQ | Mobiquity Technologies, Inc. | 2022-12-10 | 1 | https://mobiquity.com |
| 1838716 | GNTA | Genenta Science S.p.A. | 2022-12-15 | 8 | https://genenta.com;https://clinicaltria |
| 1873835 | IMMX | Immix Biopharma, Inc. | 2022-12-16 | 7 | https://immixbio.com;https://pstvote.com |
| 1070050 | APCX | AppTech Payments Corp. | 2023-01-06 | 12 | https://apptechcorp.com;https://apptech. |
| 1658551 | AMLX | Amylyx Pharmaceuticals, Inc. | 2023-01-07 | 1 | https://investors.amylyx.com;https://amy |
| 1880661 | TPG | TPG Inc. | 2023-01-13 | 2 | https://tpg.com |
| 1777319 | CISO | CISO Global, Inc. | 2023-01-18 | 12 | https://cerberussentinel.com;https://cer |
| 1864943 | FGI | FGI Industries Ltd. | 2023-01-25 | 2 | https://fgi-industries.com |
| 1648087 | AREB | AMERICAN REBEL HOLDINGS INC | 2023-02-08 | 7 | https://americanrebel.com;https://cscp.c |
| 1892322 | HTCR | HeartCore Enterprises, Inc. | 2023-02-10 | 6 | https://heartcore-enterprises.com;https: |
| 1450704 | VIVK | Vivakor, Inc. | 2023-02-15 | 5 | https://vivakor.com |
| 1402328 | SBFM | Sunshine Biopharma Inc. | 2023-02-17 | 2 | https://sunshinebiopharma.com |
| 1888014 | AKAN | AKANDA CORP. | 2023-03-15 | 5 | https://akancorp.com;https://akandacorp. |
| 1737995 | STSS | SkyAI, Inc. | 2023-04-14 | 6 | https://ir.stss.com;https://sharpstechno |
| 1635077 | ACON | Aclarion, Inc. | 2023-04-22 | 6 | https://aclarion.com;https://vstocktrans |
| 1905511 | JCSE | JE Cleantech Holdings Ltd | 2023-04-22 | 3 | https://jecleantech.com.sg;https://jecle |
| 1560293 | TNON | Tenon Medical, Inc. | 2023-04-27 | 4 | https://tenonmed.com;https://tenonmed.co |
| 1141284 | ASNS | ACTELIS NETWORKS INC | 2023-05-13 | 14 | https://actelis.com;https://actelisnetwo |
| 1886799 | - | Bright Green Corp | 2023-05-17 | 12 | https://brightgreen.us;https://virtualme |
| 1849296 | OKYO | OKYO Pharma Ltd | 2023-05-17 | 4 | https://okyopharma.com;https://adr.com |
| 923601 | RIME | Algorhythm Holdings, Inc. | 2023-05-25 | 1 | https://singingmachine.com |
| 1879848 | PEVM | PHOENIX MOTOR INC. | 2023-06-08 | 7 | https://phoenixmotors.com;https://phoeni |
| 1468492 | HSCS | HeartSciences Inc. | 2023-06-15 | 3 | https://heartsciences.com |
| 1885827 | VRAX | Virax Biolabs Group Ltd | 2023-07-21 | 10 | https://viraxbiolabs.com;https://canfite |
| 1886362 | MGAM | Mobile Global Esports, Inc. | 2023-07-29 | 3 | https://mogoesports.com |
| 1913210 | - | Bruush Oral Care Inc. | 2023-08-03 | 3 | https://bruush.com |
| 1885408 | NEXR | Nexera Technologies Ltd | 2023-08-26 | 6 | https://jeffsbrands.com |
| 1892480 | - | Hempacco Co., Inc. | 2023-08-30 | 12 | https://hempaccoinc.com;https://hemp.com |
| 1650101 | ATXG | ADDENTAX GROUP CORP. | 2023-09-01 | 18 | https://addentax.com;https://addentaxgro |
| 1712762 | BIAF | bioAffinity Technologies, Inc. | 2023-09-01 | 6 | https://bioaffinitytech.com;https://view |
| 1898604 | VSTD | Vestand Inc. | 2023-09-09 | 6 | https://ir.yoshiharuramen.com;https://yo |
| 1887673 | WLDS | Wearable Devices Ltd. | 2023-09-13 | 6 | https://wearabledevices.co;https://weara |
| 1807887 | LASE | Laser Photonics Corp | 2023-09-30 | 12 | https://laserphotonics.com;https://laser |
| 1902794 | - | MGO Global Inc. | 2024-01-13 | 1 | https://mgol.com;https://mgoglobalinc.co |
| 1920406 | ASST | Strive, Inc. | 2024-02-03 | 2 | https://assetentitiesinc.com;https://ass |
| 1865127 | - | Lucy Scientific Discovery, Inc | 2024-02-09 | 2 | https://ir.lucyscientific.com;https://lu |
| 1829247 | BFRG | BullFrog AI Holdings, Inc. | 2024-02-14 | 2 | https://ir.bullfrogai.com;https://bullfr |
| 1611282 | - | PishPosh, Inc. | 2024-03-07 | 6 | https://pishposhbaby.com;https://datatra |
| 1938046 | MGRX | MANGOCEUTICALS, INC. | 2024-03-21 | 4 | https://mangoceuticals.com;https://mango |
| 1948455 | ISPR | Ispire Technology Inc. | 2024-04-04 | 4 | https://getispire.com;https://ispiretech |
| 1962481 | BOF | BranchOut Food Inc. | 2024-06-16 | 1 | https://branchoutfood.com;https://securi |
| 1823584 | AENT | ALLIANCE ENTERTAINMENT HOLDING | 2024-06-30 | 2 | https://ncircleentertainment.com;https:/ |
| 1737523 | BGLC | BioNexus Gene Lab Corp | 2024-07-21 | 2 | https://bionexusgenelab.com;https://bglc |
| 1805526 | DFDV | DeFi Development Corp. | 2024-07-25 | 8 | https://ir.janover.co;https://datatracks |
| 1911545 | GITS | Global Interactive Technologie | 2024-08-01 | 2 | https://hanryuholdings.com;https://edgar |
| 1948697 | SPPL | SIMPPLE LTD. | 2024-09-13 | 6 | https://simpple.ai;https://simpple.com.s |
| 1825367 | - | RayzeBio, Inc. | 2024-09-15 | 8 | https://rayzebio.com;https://bms.com |
| 1713210 | ATPC | Agape ATP Corp | 2024-10-11 | 3 | https://atpc.com.my;https://agapeatpgrou |
| 1907108 | LXEO | Lexeo Therapeutics, Inc. | 2024-11-03 | 12 | https://lexeotx.com;https://lexeo.com |
| 1840563 | ELAB | PMGC Holdings Inc. | 2024-11-21 | 1 | https://elevailabsinc.com;https://elevai |
| 1961847 | INHD | INNO HOLDINGS INC. | 2024-12-04 | 4 | https://innoholdings.com;https://innomet |

## Not Located: No Company URL Found (2 CIKs)

No company website URL could be mined from cached SEC filings.

- 1815436 - Advanced Health Intelligence Ltd (due 2022-11-19)
- 1875496 - YanGuFang International Group Co., Ltd (due 2024-03-28)

## Updated Disclosure Audit

| Status | Before | After | Change |
|--------|--------|-------|--------|
| published_on_time | 211 | 216 | +5 |
| published_late | 0 | 1 | +1 |
| ambiguous | 0 | 0 | 0 |
| not_located | 120 | 114 | -6 |
| obligation_voided | 78 | 78 | 0 |
