# Couverture des données (phase 2)

Généré le 2026-10-02T14:08:08+00:00 par `python -m amundi_agentic.data.coverage`. **Ne pas éditer à la main** : chaque chiffre provient du stockage local. Une source absente est indiquée « indisponible ».

## 0. Statut des téléchargements (dernier événement par élément)

| source | ok |
| --- | --- |
| ecb | 5 |
| edgar | 63 |
| edgar_text | 15 |
| esg | 28 |
| fred | 12 |
| fx | 4 |
| gdelt | 8 |
| gdelt_week | n/d |
| prices | 84 |
| rss | 3 |
| xbrl | 15 |

### Éléments en erreur ou indisponibles

| source | element | detail |
| --- | --- | --- |
| prices | ANSS | NoDataError: YFTzMissingError: $ANSS: possibly delisted; no timezone found |
| prices | JNPR | NoDataError: YFTzMissingError: $JNPR: possibly delisted; no timezone found |
| fred | BAMLEC0A0RMEY | série absente de FRED : {"error_code":400,"error_message":"Bad Request.  The series does not exist."} |
| edgar | ANSS | KeyError: 'ticker ANSS absent de la liste EDGAR (société non déclarante ?)' |
| edgar | JNPR | KeyError: 'ticker JNPR absent de la liste EDGAR (société non déclarante ?)' |
| gdelt | AAPL | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="Apple"&sort=datedesc : échec après 5 essais (HTTP 42 |
| gdelt | MSFT | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="MICROSOFT"&sort=datedesc : échec après 5 essais (HTT |
| gdelt | NVDA | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="NVIDIA"&sort=datedesc : échec après 5 essais (HTTP 4 |
| gdelt | AVGO | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="Broadcom"&sort=datedesc : échec après 5 essais (HTTP |
| gdelt | AMD | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="ADVANCED MICRO DEVICES"&sort=datedesc : échec après  |
| gdelt | CSCO | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="CISCO SYSTEMS"&sort=datedesc : échec après 5 essais  |
| gdelt | IBM | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?format=json&maxrecords=100&mode=artlist&query="INTERNATIONAL BUSINESS MACHINES"&sort=datedesc : éch |
| gdelt_week | ZS:3 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260911000000&format=json&maxrecords=5&mode=artlist&query="Zscaler"&sort=datedesc&star |
| gdelt_week | ZS:6 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260821000000&format=json&maxrecords=5&mode=artlist&query="Zscaler"&sort=datedesc&star |
| gdelt_week | ZS:7 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260814000000&format=json&maxrecords=5&mode=artlist&query="Zscaler"&sort=datedesc&star |
| gdelt_week | ORCL:3 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260911000000&format=json&maxrecords=5&mode=artlist&query="ORACLE"&sort=datedesc&start |
| gdelt_week | ORCL:5 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260828000000&format=json&maxrecords=5&mode=artlist&query="ORACLE"&sort=datedesc&start |
| gdelt_week | CRM:0 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20261002000000&format=json&maxrecords=5&mode=artlist&query="Salesforce"&sort=datedesc&s |
| gdelt_week | CRM:1 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260925000000&format=json&maxrecords=5&mode=artlist&query="Salesforce"&sort=datedesc&s |
| gdelt_week | CRM:3 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260911000000&format=json&maxrecords=5&mode=artlist&query="Salesforce"&sort=datedesc&s |
| gdelt_week | CRM:4 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260904000000&format=json&maxrecords=5&mode=artlist&query="Salesforce"&sort=datedesc&s |
| gdelt_week | CRM:5 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260828000000&format=json&maxrecords=5&mode=artlist&query="Salesforce"&sort=datedesc&s |
| gdelt_week | ADBE:1 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260925000000&format=json&maxrecords=5&mode=artlist&query="ADOBE"&sort=datedesc&startd |
| gdelt_week | ADBE:6 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260821000000&format=json&maxrecords=5&mode=artlist&query="ADOBE"&sort=datedesc&startd |
| gdelt_week | ADBE:7 | HttpError: gdelt https://api.gdeltproject.org/api/v2/doc/doc?enddatetime=20260814000000&format=json&maxrecords=5&mode=artlist&query="ADOBE"&sort=datedesc&startd |

## 1. Prix des ETF candidats et de leurs proxys (yfinance)

| classe | role | ticker | statut | devise_yahoo | devise_config | premiere_date | derniere_date | barres | semaines | eligible_260s_des | distribution | trous | splits_declares | split_suspect | aberrantes | doublons | figees | avant_fenetre |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| actions_etats_unis | primary | 500.PA | ok | EUR | EUR | 2010-06-08 | 2026-09-30 | 4174 | 851 | 2015-06-02 | acc | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_etats_unis | proxy | SPY | ok | USD | USD | 1993-01-29 | 2026-10-01 | 8476 | 1757 | 1998-01-23 | dist | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_europe | primary | MEU.PA | ok | EUR | EUR | 2008-01-02 | 2026-09-30 | 4796 | 978 | 2012-12-26 | acc | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_europe | proxy | VGK | ok | USD | USD | 2005-03-10 | 2026-10-01 | 5425 | 1125 | 2010-03-04 | dist | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_japon | primary | JPN.PA | ok | EUR | EUR | 2008-01-02 | 2026-09-30 | 4795 | 978 | 2012-12-26 | dist | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_japon | proxy | EWJ | ok | USD | USD | 1996-03-18 | 2026-10-01 | 7685 | 1593 | 2001-03-12 | dist | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| actions_emergents | primary | AEEM.PA | ok | EUR | EUR | 2010-11-30 | 2026-09-30 | 4049 | 826 | 2015-11-24 | acc | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| actions_emergents | proxy | EEM | ok | USD | USD | 2003-04-14 | 2026-10-01 | 5905 | 1224 | 2008-04-07 | dist | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| souverain_euro | primary | MTD.PA | ok | EUR | EUR | 2009-01-02 | 2026-09-30 | 4538 | 926 | 2013-12-27 | acc | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| souverain_euro | alternative | EGOV.PA | ok | EUR | EUR | 2016-11-11 | 2026-09-30 | 2530 | 516 | 2021-11-05 | a_verifier | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| credit_ig_euro | primary | CRP.PA | ok | EUR | EUR | 2009-04-02 | 2026-09-30 | 4471 | 913 | 2014-03-27 | acc | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| haut_rendement_euro | primary | AHYE.PA | ok | EUR | EUR | 2013-09-03 | 2026-09-30 | 3347 | 682 | 2018-08-28 | a_verifier | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| or | primary | GOLD.PA | ok | USD | EUR | 2019-05-23 | 2026-09-30 | 1884 | 384 | 2024-05-16 | a_verifier | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| or | proxy | GLD | ok | USD | USD | 2004-11-18 | 2026-10-01 | 5501 | 1141 | 2009-11-12 | a_verifier | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| matieres_premieres | primary | COMO.PA | ok | EUR | EUR | 2008-01-02 | 2026-09-30 | 4797 | 978 | 2012-12-26 | acc | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| matieres_premieres | proxy | DBC | ok | USD | USD | 2006-02-06 | 2026-10-01 | 5196 | 1077 | 2011-01-31 | dist | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| monetaire_euro | primary | C3M.PA | ok | EUR | EUR | 2009-06-22 | 2026-09-30 | 4421 | 901 | 2014-06-16 | acc | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| monetaire_euro | alternative | CSH2.PA | ok | EUR | EUR | 2025-03-17 | 2026-09-30 | 392 | 80 | 2030-03-11 | a_verifier | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_monde | control | CW8.PA | ok | EUR | EUR | 2009-06-16 | 2026-09-30 | 4424 | 902 | 2014-06-10 | acc | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_monde | proxy | URTH | ok | USD | USD | 2012-01-12 | 2026-10-01 | 3701 | 768 | 2017-01-05 | dist | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| actions_monde | proxy | ACWI | ok | USD | USD | 2008-03-28 | 2026-10-01 | 4658 | 966 | 2013-03-22 | dist | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Tickers cités dans l'univers : 21 ; avec données : 21 ; indisponibles : 0. « eligible_260s_des » = première barre + 260 semaines (L1 §9.1) : c'est une date calendaire, PAS un décompte de semaines réellement cotées. Les colonnes trous/aberrantes/figees ne comptent que les signalements depuis 2013-01-01 ; `avant_fenetre` cumule ceux d'avant ; les « figées » structurelles (liste en config) sont rangées à part en §7. `distribution` : acc/dist/a_verifier (config) ; `dist_ecart` : incohérence avec les dividendes enregistrés.

### Date de début du backtest permise par les données (260 semaines avant t)

| classe | ETF_primaire_seul | avec_proxy_USD_converti | serie_EUR_publique | debut_au_plus_tot |
| --- | --- | --- | --- | --- |
| actions_etats_unis | 2015-06-02 | 1998-01-23 | aucune | 1998-01-23 |
| actions_europe | 2012-12-26 | 2010-03-04 | aucune | 2010-03-04 |
| actions_japon | 2012-12-26 | 2001-03-12 | aucune | 2001-03-12 |
| actions_emergents | 2015-11-24 | 2008-04-07 | aucune | 2008-04-07 |
| souverain_euro | 2013-12-27 | interdit (D-011) | taux seulement : reconstruction requise | 2013-12-27 |
| credit_ig_euro | 2014-03-27 | interdit (D-011) | aucune | 2014-03-27 |
| haut_rendement_euro | 2018-08-28 | interdit (D-011) | aucune avant l'ETF (série depuis 2023-10-02) | 2018-08-28 |
| or | 2024-05-16 | 2009-11-12 | aucune | 2009-11-12 |
| matieres_premieres | 2012-12-26 | 2011-01-31 | aucune | 2011-01-31 |
| monetaire_euro | 2014-06-16 | interdit (D-011) | 2003-12-29 | 2003-12-29 |

Le début global est limité par la classe la plus tardive (colonne `debut_au_plus_tot`). `serie_EUR_publique` : première date de la série EUR la plus ancienne + 260 semaines.

**Début global du backtest : 2018-08-28**, classe limitante `haut_rendement_euro` ; sans cette classe : 2014-03-27 (classe suivante : `credit_ig_euro`). Avec les seuls ETF primaires, sans proxy : 2024-05-16.

### Liquidité depuis 2018-01-01 (valeur échangée = volume x clôture, devise de cotation)

| ticker | role | devise_cotation | jours_depuis | valeur_mediane_par_jour | valeur_p10 | part_jours_sans_volume |
| --- | --- | --- | --- | --- | --- | --- |
| 500.PA | primary | EUR | 2240 | 948725 | 231846 | 0.0268 |
| SPY | proxy | USD | 2199 | 30366949557 | 17289599963 | 0 |
| MEU.PA | primary | EUR | 2240 | 486937 | 115805 | 0.00134 |
| VGK | proxy | USD | 2199 | 210082956 | 108065418 | 0 |
| JPN.PA | primary | EUR | 2240 | 132256 | 14097 | 0.00536 |
| EWJ | proxy | USD | 2199 | 385804756 | 212107261 | 0 |
| AEEM.PA | primary | EUR | 2240 | 1408319 | 280696 | 0.0344 |
| EEM | proxy | USD | 2199 | 1734174693 | 922517148 | 0 |
| MTD.PA | primary | EUR | 2240 | 161409 | 13937 | 0.00536 |
| EGOV.PA | alternative | EUR | 2240 | 34701 | 0 | 0.114 |
| CRP.PA | primary | EUR | 2240 | 173747 | 5043 | 0.0964 |
| AHYE.PA | primary | EUR | 2240 | 95330 | 1105 | 0.0848 |
| GOLD.PA | primary | EUR | 1884 | 1107655 | 229096 | 0.0127 |
| GLD | proxy | USD | 2199 | 1387185526 | 709835338 | 0 |
| COMO.PA | primary | EUR | 2240 | 196754 | 43028 | 0.0058 |
| DBC | proxy | USD | 2199 | 26236749 | 9859611 | 0 |
| C3M.PA | primary | EUR | 2240 | 21046 | 0 | 0.371 |
| CSH2.PA | alternative | EUR | 392 | 3009061 | 1534339 | 0 |
| CW8.PA | control | EUR | 2240 | 1836389 | 367581 | 0.0344 |
| URTH | proxy | USD | 2199 | 19674635 | 2326176 | 0 |
| ACWI | proxy | USD | 2199 | 282215317 | 121106779 | 0 |

La valeur médiane par jour mesure le volume de la ligne de cotation lue sur Yahoo, pas la liquidité réelle de l'ETF (marché primaire, apporteurs de liquidité, autres places) ; `part_jours_sans_volume` compte les jours à volume nul ou absent.

### Contrôle croisé ETF primaire / proxy converti en EUR (fixing BCE)

| classe | primaire | proxy | jours_communs | debut | fin | ratio_moyen | coef_variation | derive_annuelle | erreur_suivi_hebdo_annualisee |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| actions_etats_unis | 500.PA | SPY | 4062 | 2010-06-08 | 2026-09-30 | 0.203 | 0.0113 | -0.00206 | 0.0602 |
| actions_europe | MEU.PA | VGK | 4669 | 2008-01-02 | 2026-09-30 | 3.75 | 0.157 | -0.0238 | 0.0987 |
| actions_japon | JPN.PA | EWJ | 4668 | 2008-01-02 | 2026-09-30 | 2.72 | 0.0243 | -0.00329 | 0.0862 |
| actions_emergents | AEEM.PA | EEM | 3940 | 2010-11-30 | 2026-09-30 | 0.129 | 0.0155 | 0.00236 | 0.075 |
| or | GOLD.PA | GLD | 1831 | 2019-05-23 | 2026-09-30 | 0.428 | 0.00849 | 0.00228 | 0.0675 |
| matieres_premieres | COMO.PA | DBC | 4670 | 2008-01-02 | 2026-09-30 | 1.27 | 0.0607 | 0.0026 | 0.103 |

Ratio = primaire (EUR, ajusté dividendes) / proxy (USD ajusté, converti au fixing BCE du jour, report borné). `derive_annuelle` : moyenne des 60 derniers jours sur celle des 60 premiers, annualisée ; `erreur_suivi_hebdo_annualisee` : écart-type des écarts de rendements log hebdomadaires (vendredi) x racine de 52. Un ratio stable (faible coefficient de variation) confirme la devise de cotation du primaire ; l'écart de suivi inclut la différence d'indice, de réplication, de fiscalité et d'horaire de cotation.

### Composition de chaque série de classe par date (primaire ou proxy)

| classe | segment | source | debut | fin |
| --- | --- | --- | --- | --- |
| actions_etats_unis | 1 | proxy SPY converti en EUR (BCE) : SYNTHÉTIQUE | 1993-01-29 | 2010-06-07 |
| actions_etats_unis | 2 | ETF primaire 500.PA (réel) | 2010-06-08 | 2026-09-30 |
| actions_europe | 1 | proxy VGK converti en EUR (BCE) : SYNTHÉTIQUE | 2005-03-10 | 2008-01-01 |
| actions_europe | 2 | ETF primaire MEU.PA (réel) | 2008-01-02 | 2026-09-30 |
| actions_japon | 1 | proxy EWJ converti en EUR (BCE) : SYNTHÉTIQUE | 1996-03-18 | 2008-01-01 |
| actions_japon | 2 | ETF primaire JPN.PA (réel) | 2008-01-02 | 2026-09-30 |
| actions_emergents | 1 | proxy EEM converti en EUR (BCE) : SYNTHÉTIQUE | 2003-04-14 | 2010-11-29 |
| actions_emergents | 2 | ETF primaire AEEM.PA (réel) | 2010-11-30 | 2026-09-30 |
| souverain_euro | 1 | ETF primaire MTD.PA seul (réel, aucun proxy admis) | 2009-01-02 | 2026-09-30 |
| credit_ig_euro | 1 | ETF primaire CRP.PA seul (réel, aucun proxy admis) | 2009-04-02 | 2026-09-30 |
| haut_rendement_euro | 1 | ETF primaire AHYE.PA seul (réel) ; aucune série EUR publique avant l'ETF | 2013-09-03 | 2026-09-30 |
| or | 1 | proxy GLD converti en EUR (BCE) : SYNTHÉTIQUE | 2004-11-18 | 2019-05-22 |
| or | 2 | ETF primaire GOLD.PA (réel) | 2019-05-23 | 2026-09-30 |
| matieres_premieres | 1 | proxy DBC converti en EUR (BCE) : SYNTHÉTIQUE | 2006-02-06 | 2008-01-01 |
| matieres_premieres | 2 | ETF primaire COMO.PA (réel) | 2008-01-02 | 2026-09-30 |
| monetaire_euro | 1 | ETF primaire C3M.PA (réel) ; série EUR publique antérieure : ecb:EONIA | 2009-06-22 | 2026-09-30 |

Le début global du backtest dépend de proxys USD convertis (séries synthétiques avant la date de l'ETF) pour : actions_emergents, actions_etats_unis, actions_europe, actions_japon, matieres_premieres, or. Avant la première date de l'ETF primaire, ces classes ne reposent donc pas sur le fonds retenu.

### Creux (drawdowns) du benchmark proxy, calculés par script

500.PA, clôtures en EUR (EUR), creux d'au moins 15%, fenêtres 2014-03-27, 2018-08-28 jusqu'à la dernière barre. ETF capitalisant : le prix inclut les dividendes réinvestis (équivaut à un rendement total). Variation de DGS10 entre le pic et le creux (points de base) ; un creux dont la fenêtre commence au milieu d'un épisode est tronqué à son plus haut dans la fenêtre.

| fenetre | pic_date | creux_date | amplitude | recuperation | variation_taux_pb | hausse_des_taux |
| --- | --- | --- | --- | --- | --- | --- |
| 2014-03-27 -> 2026-09-30 | 2015-04-15 | 2015-08-24 | -0.172 | 2015-11-25 | 10 | True |
| 2014-03-27 -> 2026-09-30 | 2015-12-01 | 2016-02-11 | -0.184 | 2016-07-19 | -52 | False |
| 2014-03-27 -> 2026-09-30 | 2018-10-03 | 2018-12-27 | -0.158 | 2019-04-01 | -38 | False |
| 2014-03-27 -> 2026-09-30 | 2020-02-19 | 2020-03-23 | -0.337 | 2021-01-07 | -80 | False |
| 2014-03-27 -> 2026-09-30 | 2022-01-04 | 2022-06-16 | -0.171 | 2022-08-16 | 162 | True |
| 2014-03-27 -> 2026-09-30 | 2025-02-19 | 2025-04-09 | -0.233 | 2025-10-27 | -19 | False |
| 2018-08-28 -> 2026-09-30 | 2018-10-03 | 2018-12-27 | -0.158 | 2019-04-01 | -38 | False |
| 2018-08-28 -> 2026-09-30 | 2020-02-19 | 2020-03-23 | -0.337 | 2021-01-07 | -80 | False |
| 2018-08-28 -> 2026-09-30 | 2022-01-04 | 2022-06-16 | -0.171 | 2022-08-16 | 162 | True |
| 2018-08-28 -> 2026-09-30 | 2025-02-19 | 2025-04-09 | -0.233 | 2025-10-27 | -19 | False |

## 2. Prix de la poche titres (liste de démonstration)

| ticker | statut | premiere_date | derniere_date | barres | trous | splits_declares | split_suspect | aberrantes | doublons | devise_yahoo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ZS | ok | 2018-03-16 | 2026-10-01 | 2148 | 0 | 0 | 0 | 3 | 0 | USD |
| AAPL | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 4 | 1 | 0 | 0 | USD |
| MSFT | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 8 | 0 | 0 | 0 | USD |
| NVDA | ok | 1999-01-22 | 2026-10-01 | 6966 | 0 | 6 | 1 | 1 | 0 | USD |
| AVGO | ok | 2009-08-06 | 2026-10-01 | 4315 | 0 | 1 | 0 | 0 | 0 | USD |
| ORCL | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 7 | 1 | 1 | 0 | USD |
| CRM | ok | 2004-06-23 | 2026-10-01 | 5605 | 0 | 1 | 0 | 1 | 0 | USD |
| ADBE | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 4 | 0 | 0 | 0 | USD |
| AMD | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 1 | 1 | 0 | 0 | USD |
| CSCO | ok | 1990-02-16 | 2026-10-01 | 9222 | 0 | 9 | 0 | 0 | 0 | USD |
| INTC | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 5 | 0 | 1 | 0 | USD |
| QCOM | ok | 1991-12-13 | 2026-10-01 | 8761 | 0 | 4 | 0 | 0 | 0 | USD |
| TXN | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 4 | 0 | 0 | 0 | USD |
| IBM | ok | 1990-01-02 | 2026-10-01 | 9255 | 0 | 3 | 0 | 1 | 0 | USD |
| NOW | ok | 2012-06-29 | 2026-10-01 | 3584 | 0 | 1 | 0 | 0 | 0 | USD |

## 3. Macro (FRED/ALFRED et BCE)

| serie | statut | premiere_obs | derniere_obs | observations | premier_millesime | disponibilite | lignes_millesimes | obs_revisees | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fred:DGS10 | ok | 1962-01-02 | 2026-09-30 | 16172 | 1962-01-03 | lag_rule (H) | 16172 | 0 | Rendement Trésor US 10 ans |
| fred:DGS1MO | ok | 2001-07-31 | 2026-09-30 | 6294 | 2001-08-01 | lag_rule (H) | 6294 | 0 | Trésor US 1 mois (taux sans risque de la réplication, L1 §9.3) |
| fred:DGS2 | ok | 1976-06-01 | 2026-09-30 | 12580 | 1976-06-02 | lag_rule (H) | 12580 | 0 | Trésor US 2 ans |
| fred:T10Y2Y | ok | 1976-06-01 | 2026-10-01 | 12581 | 1976-06-02 | lag_rule (H) | 12581 | 0 | Pente 10 ans - 2 ans |
| fred:VIXCLS | ok | 1990-01-02 | 2026-09-30 | 9285 | 1990-01-03 | lag_rule (H) | 9285 | 0 | VIX |
| fred:CPIAUCSL | ok | 1947-01-01 | 2026-08-01 | 955 | 1972-07-21 | ALFRED | 3103 | 658 | Prix à la consommation US, révisé |
| fred:UNRATE | ok | 1948-01-01 | 2026-08-01 | 943 | 1960-03-15 | ALFRED | 2197 | 703 | Chômage US, révisé |
| fred:GDPC1 | ok | 1947-01-01 | 2026-04-01 | 318 | 1991-12-04 | ALFRED | 4186 | 318 | PIB réel US, révisé |
| fred:BAMLH0A0HYM2 | ok | 2023-10-02 | 2026-09-30 | 786 | 2023-10-03 | lag_rule (H) | 786 | 0 | ICE BofA US High Yield OAS (licence ICE : fenêtre glissante) |
| fred:BAMLHE00EHYITRIV | ok | 2023-10-02 | 2026-09-30 | 786 | 2023-10-03 | lag_rule (H) | 786 | 0 | ICE BofA Euro High Yield, rendement total (fenêtre ICE de 3 ans : NON utilisé comme série de rendement, D-034) |
| fred:BAMLHE00EHYIOAS | ok | 2023-10-02 | 2026-09-30 | 786 | 2023-10-03 | lag_rule (H) | 786 | 0 | ICE BofA Euro High Yield, OAS (fenêtre ICE de 3 ans, D-034) |
| fred:BAMLEC0A0RMEY | indisponible | n/d | n/d | n/d | n/d | n/d | n/d | n/d | ICE BofA Euro Corporate, rendement effectif (existence à vérifier) |
| fred:ECBESTRVOLWGTTRMDMNRT | ok | 2019-10-01 | 2026-10-01 | 1794 | 2019-10-02 | lag_rule (H) | 1794 | 0 | €STR sur FRED (existence à vérifier) |
| ecb:ESTR | ok | 2019-10-01 | 2026-10-01 | 1794 | n/d | lag_rule (H) | aucun millésime | n/d | €STR, depuis 2019-10-01 |
| ecb:EONIA | ok | 1999-01-04 | 2021-12-31 | 5890 | n/d | lag_rule (H) | aucun millésime | n/d | EONIA, 1999-01-04 à 2021-12-31 |
| ecb:YC_SPOT_10Y | ok | 2004-09-06 | 2026-10-01 | 5643 | n/d | lag_rule (H) | aucun millésime | n/d | Courbe zéro-coupon AAA zone euro 10 ans |
| ecb:YC_SPOT_2Y | ok | 2004-09-06 | 2026-10-01 | 5643 | n/d | lag_rule (H) | aucun millésime | n/d | Courbe zéro-coupon AAA zone euro 2 ans |
| ecb:YC_SPOT_7Y | ok | 2004-09-06 | 2026-10-01 | 5643 | n/d | lag_rule (H) | aucun millésime | n/d | Courbe zéro-coupon AAA zone euro 7 ans |

Le retard de publication des séries BCE est le délai déclaré en config (H), pas une mesure. Pour les séries FRED, `premier_millesime` est la date de capture ALFRED la plus ancienne : avant elle, `realtime_start` est un rétro-remplissage, pas un vrai millésime.

### Change BCE (EXR)

| devise | statut | premier | dernier | fixings | trous_sup_seuil |
| --- | --- | --- | --- | --- | --- |
| USD | ok | 1999-01-04 | 2026-10-01 | 7105 | 0 |
| JPY | ok | 1999-01-04 | 2026-10-01 | 7105 | 0 |
| GBP | ok | 1999-01-04 | 2026-10-01 | 7105 | 0 |
| CHF | ok | 1999-01-04 | 2026-10-01 | 7105 | 0 |

## 4. Dépôts SEC EDGAR et XBRL (liste de démonstration)

| ticker | statut | sic | 10-K | 10-Q | 8-K | premier_depot_utc | dernier_depot_utc | textes_depuis_text_since | faits_xbrl | premier_filed_xbrl |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ZS | ok | 7371 | 9 | 25 | 60 | 2018-05-03 | 2026-09-24 | 19/19 | 903 | 2018-06-07 |
| AAPL | ok | 3571 | 30 | 98 | 233 | 1994-01-26 | 2026-07-31 | 19/19 | 2008 | 2009-07-22 |
| MSFT | ok | 7372 | 33 | 98 | 281 | 1994-02-14 | 2026-09-02 | 19/19 | 2178 | 2009-10-23 |
| NVDA | ok | 3674 | 25 | 83 | 243 | 1999-06-15 | 2026-09-03 | 19/19 | 2106 | 2009-08-20 |
| AVGO | ok | 3674 | 8 | 26 | 121 | 2018-03-23 | 2026-09-09 | 19/19 | 854 | 2018-06-14 |
| ORCL | ok | 7372 | 21 | 62 | 204 | 2006-02-10 | 2026-09-14 | 19/19 | 1491 | 2009-09-21 |
| CRM | ok | 7372 | 22 | 67 | 286 | 2004-08-19 | 2026-09-17 | 19/19 | 2377 | 2009-08-25 |
| ADBE | ok | 7372 | 32 | 96 | 233 | 1995-02-17 | 2026-09-22 | 20/20 | 2195 | 2009-06-26 |
| AMD | ok | 3674 | 29 | 98 | 424 | 1994-01-27 | 2026-09-28 | 19/19 | 1637 | 2010-08-04 |
| CSCO | ok | 3576 | 31 | 95 | 407 | 1995-03-13 | 2026-09-02 | 19/19 | 1969 | 2009-11-18 |
| INTC | ok | 3674 | 33 | 98 | 445 | 1994-03-25 | 2026-08-12 | 19/19 | 1485 | 2009-08-03 |
| QCOM | ok | 3663 | 28 | 92 | 261 | 1996-05-13 | 2026-09-08 | 19/19 | 2079 | 2009-07-22 |
| TXN | ok | 3674 | 28 | 99 | 312 | 1994-01-28 | 2026-09-17 | 19/19 | 1793 | 2009-07-29 |
| IBM | ok | 3570 | 29 | 98 | 565 | 1994-03-28 | 2026-10-02 | 19/19 | 1393 | 2009-07-28 |
| NOW | ok | 7372 | 14 | 43 | 124 | 2012-08-01 | 2026-07-22 | 19/19 | 1461 | 2012-08-10 |

### Pool de réplication (révision Wikipédia 1197645693, 2024-01-21T10:48:32Z)

Titres du secteur dans le pool : 64 ; avec un 10-K ou 10-Q accepté avant le 2024-02-01 : 62 ; avec des prix en janvier 2024 : 62 ; **utilisables (les deux)** : 62 ; titres dont les données n'ont pas pu être téléchargées : 2 (ANSS, JNPR : absents de Yahoo ou d'EDGAR, typiquement sociétés rachetées ou radiées, d'où un biais du survivant). ZS (titre nommé par le papier) : dans le pool : non ; admissible hors pool (dépôt avant coupure : oui, prix de janvier 2024 : oui).

## 5. News (RSS, GDELT)

| source | articles | premier | dernier | first_seen_min |
| --- | --- | --- | --- | --- |
| ecb_press | 15 | 2026-09-21 | 2026-10-01 | 2026-10-02 |
| fed_press | 20 | 2026-08-13 | 2026-09-30 | 2026-10-02 |
| gdelt | 748 | 2026-08-13 | 2026-10-02 | 2026-10-02 |
| sec_press | 25 | 2026-08-18 | 2026-10-01 | 2026-10-02 |

### Couverture par actif (articles GDELT étiquetés au ticker ; semaines sondées une à une avec `--gdelt-weeks`, présence d'au moins un article)

| actif | societe | articles | premier | dernier | etat_gdelt | semaines_avec_article | part_semaines |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ZS | Zscaler, Inc. | 110 | 2026-08-20 | 2026-10-02 | sondé | 7/7 | 1 |
| AAPL | Apple Inc. | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| MSFT | MICROSOFT CORP | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| NVDA | NVIDIA CORP | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| AVGO | Broadcom Inc. | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| ORCL | ORACLE CORP | 125 | 2026-08-14 | 2026-10-02 | sondé | 6/6 | 1 |
| CRM | Salesforce, Inc. | 120 | 2026-08-13 | 2026-10-02 | sondé | 6/6 | 1 |
| ADBE | ADOBE INC. | 126 | 2026-08-14 | 2026-10-02 | sondé | 7/7 | 1 |
| AMD | ADVANCED MICRO DEVICES INC | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| CSCO | CISCO SYSTEMS, INC. | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| INTC | INTEL CORP | 96 | 2026-10-01 | 2026-10-02 | sondé | non sondé | n/d |
| QCOM | QUALCOMM INC/DE | 0 | n/d | n/d | sondé (zéro article) | non sondé | n/d |
| TXN | TEXAS INSTRUMENTS INC | 100 | 2026-09-03 | 2026-10-01 | sondé | non sondé | n/d |
| IBM | INTERNATIONAL BUSINESS MACHINES CORP | 0 | n/d | n/d | NON SONDÉ (erreur ou non lancé : pas un zéro article) | non sondé | n/d |
| NOW | ServiceNow, Inc. | 71 | 2026-09-29 | 2026-10-02 | sondé | non sondé | n/d |

### Couverture par date (articles par mois, toutes sources)

| mois | articles |
| --- | --- |
| 2026-08 | 68 |
| 2026-09 | 379 |
| 2026-10 | 361 |

### Profondeur historique de GDELT DOC (sondage)

| months_back | window_start | window_end | articles | earliest_seendate | status |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-08-26 | 2026-09-02 | 5 | 20260826T041500Z | ok |
| 3 | 2026-06-27 | 2026-07-04 | 5 | 20260627T163000Z | ok |
| 6 | 2026-03-29 | 2026-04-05 | 5 | 20260402T021500Z | ok |
| 12 | 2025-09-30 | 2025-10-07 | 5 | 20250930T024500Z | ok |
| 24 | 2024-10-05 | 2024-10-12 | 5 | 20241005T014500Z | ok |
| 36 | 2023-10-11 | 2023-10-18 | 5 | 20231012T033000Z | ok |
| 60 | 2021-10-21 | 2021-10-28 | 5 | 20211021T050000Z | ok |
| 84 | 2019-11-01 | 2019-11-08 | 5 | 20191101T090000Z | ok |
| 120 | 2016-11-16 | 2016-11-23 | 0 | n/d | erreur: gdelt : réponse non JSON ('Invalid query start date.\n') |

Fenêtre de collecte : 2026-08-13 à 2026-10-02. Aucun article antérieur au premier jour de collecte n'existe pour les flux RSS ; la couverture historique des news du backtest dépend donc de la profondeur GDELT mesurée.

## 6. ESG

**Score ESG : 0/28 actifs (0%)** (l'endpoint gratuit de scores n'a rien renvoyé).

### Matrice actif x critère (trois états)

- `determine_par_donnee` : donnée directe (indicateur fournisseur) ;
- `suppose_par_regle` : déduit d'une règle (code SIC, méthodologie d'indice déclarée d'après le nom, non vérifiée) ;
- `inconnu` : aucune information.

| actif | type | tobacco | thermal_coal | controversial_weapons |
| --- | --- | --- | --- | --- |
| ZS | stock | suppose_par_regle | suppose_par_regle | inconnu |
| AAPL | stock | suppose_par_regle | suppose_par_regle | inconnu |
| MSFT | stock | suppose_par_regle | suppose_par_regle | inconnu |
| NVDA | stock | suppose_par_regle | suppose_par_regle | inconnu |
| AVGO | stock | suppose_par_regle | suppose_par_regle | inconnu |
| ORCL | stock | suppose_par_regle | suppose_par_regle | inconnu |
| CRM | stock | suppose_par_regle | suppose_par_regle | inconnu |
| ADBE | stock | suppose_par_regle | suppose_par_regle | inconnu |
| AMD | stock | suppose_par_regle | suppose_par_regle | inconnu |
| CSCO | stock | suppose_par_regle | suppose_par_regle | inconnu |
| INTC | stock | suppose_par_regle | suppose_par_regle | inconnu |
| QCOM | stock | suppose_par_regle | suppose_par_regle | inconnu |
| TXN | stock | suppose_par_regle | suppose_par_regle | inconnu |
| IBM | stock | suppose_par_regle | suppose_par_regle | inconnu |
| NOW | stock | suppose_par_regle | suppose_par_regle | inconnu |
| 500.PA | etf | inconnu | inconnu | inconnu |
| MEU.PA | etf | inconnu | inconnu | inconnu |
| JPN.PA | etf | inconnu | inconnu | inconnu |
| AEEM.PA | etf | inconnu | inconnu | inconnu |
| MTD.PA | etf | inconnu | inconnu | inconnu |
| EGOV.PA | etf | inconnu | inconnu | inconnu |
| CRP.PA | etf | suppose_par_regle | suppose_par_regle | suppose_par_regle |
| AHYE.PA | etf | inconnu | inconnu | inconnu |
| GOLD.PA | etf | inconnu | inconnu | inconnu |
| COMO.PA | etf | inconnu | inconnu | inconnu |
| C3M.PA | etf | inconnu | inconnu | inconnu |
| CSH2.PA | etf | inconnu | inconnu | inconnu |
| CW8.PA | etf | inconnu | inconnu | inconnu |

### Totaux par critère

- tabac : 0/28 déterminé par donnée, 16/28 supposé par règle, 12/28 inconnu.
- charbon thermique : 0/28 déterminé par donnée, 16/28 supposé par règle, 12/28 inconnu.
- armes controversées : 0/28 déterminé par donnée, 1/28 supposé par règle, 27/28 inconnu.

**Tous critères (84 cellules) : 0 déterminé par donnée, 33 supposé par règle, 51 inconnu.** Actifs avec au moins une exclusion détectée : 1. L'ancien indicateur « exclusion déterminée » (57%) signifiait seulement « une règle a été appliquée » : il n'est plus présenté comme une couverture. « Sans exclusion détectée » n'est pas une preuve d'absence d'exposition (SIC approximatif ; aucune règle SIC pour les armes controversées ; contenu des ETF inconnu). Les instantanés ne sont pas historisés : en strict point-in-time ils ne sont servis qu'après leur date de collecte.

## 7. Contrôle qualité (signalements, aucune correction appliquée)

| zone | type | gravite | nombre |
| --- | --- | --- | --- |
| depuis 2013-01-01 (utile) | currency | warning | 1 |
| depuis 2013-01-01 (utile) | distribution | info | 5 |
| depuis 2013-01-01 (utile) | outlier | warning | 8 |
| depuis 2013-01-01 (utile) | short_history | info | 8 |
| depuis 2013-01-01 (utile) | short_history | warning | 1 |
| depuis 2013-01-01 (utile) | split | info | 61 |
| depuis 2013-01-01 (utile) | split | warning | 4 |
| depuis 2013-01-01 (utile) | stale | warning | 2 |
| avant 2013-01-01 (hors fenêtre utile) | outlier | warning | 26 |
| avant 2013-01-01 (hors fenêtre utile) | stale | warning | 3 |
| structurel (liste en config) | stale | warning | 68 |

Faux positifs structurels déclarés (config) : C3M.PA (ETF monétaire : cours quasi constant par construction (capitalisation de quelques centimes)) ; CSH2.PA (ETF monétaire : cours quasi constant par construction) ; URTH (ETF peu liquide à son lancement (2012) : voir le volume dans le tableau de liquidité).

### Détail (fenêtre utile ; erreurs et avertissements regroupés, hors historique court)

| sujet | type | gravite | occurrences | debut | detail |
| --- | --- | --- | --- | --- | --- |
| AEEM.PA | stale | warning | 1 | 2013-12-12 | 5 clôtures identiques consécutives |
| GOLD.PA | currency | warning | 1 | n/d | devise Yahoo USD différente de la devise attendue EUR |
| COMO.PA | stale | warning | 1 | 2023-08-30 | 10 clôtures identiques consécutives |
| ZS | outlier | warning | 1 | 2020-05-29 | rendement quotidien de +29.4% |
| ZS | outlier | warning | 1 | 2020-12-03 | rendement quotidien de +26.4% |
| ZS | outlier | warning | 1 | 2026-05-27 | rendement quotidien de -31.5% |
| AAPL | split | warning | 1 | 2000-09-29 | saut de cours de -52% sans split déclaré (volume x22.4 : mouvement probablement réel) |
| NVDA | split | warning | 1 | 2000-03-07 | saut de cours de +42% sans split déclaré (volume x4.2 : mouvement probablement réel) |
| NVDA | outlier | warning | 1 | 2016-11-11 | rendement quotidien de +29.8% |
| ORCL | split | warning | 1 | 1992-12-23 | saut de cours de +44% sans split déclaré (volume x7.8 : mouvement probablement réel) |
| ORCL | outlier | warning | 1 | 2025-09-10 | rendement quotidien de +35.9% |
| CRM | outlier | warning | 1 | 2020-08-26 | rendement quotidien de +26.0% |
| AMD | split | warning | 1 | 2016-04-22 | saut de cours de +52% sans split déclaré (volume x15.8 : mouvement probablement réel) |
| INTC | outlier | warning | 1 | 2024-08-02 | rendement quotidien de -26.1% |
| IBM | outlier | warning | 1 | 2026-07-14 | rendement quotidien de -25.2% |

### Distribution à vérifier (config : a_verifier)

| ticker | detail |
| --- | --- |
| EGOV.PA | distribution à vérifier (0 dividendes enregistrés) |
| AHYE.PA | distribution à vérifier (0 dividendes enregistrés) |
| GOLD.PA | distribution à vérifier (0 dividendes enregistrés) |
| GLD | distribution à vérifier (0 dividendes enregistrés) |
| CSH2.PA | distribution à vérifier (0 dividendes enregistrés) |

## 8. Licences et limites (texte qualitatif relevé le 2026-10-02, non calculé ; détail dans la proposition D-0xx)

| source | licence_et_limites |
| --- | --- |
| yfinance | Non officielle (Yahoo) ; usage personnel/recherche ; pas de redistribution ; instable. |
| FRED/ALFRED | Clé gratuite ; séries ICE BofA limitées par licence à une fenêtre glissante ; pas de redistribution des séries tierces. |
| BCE (SDMX) | Réutilisation libre avec mention de la source ; pas de millésimes. |
| SEC EDGAR | Domaine public ; User-Agent obligatoire ; 10 requêtes/s maximum. |
| GDELT | Libre avec citation ; 1 requête / 5 s ; fenêtre de recherche glissante. |
| RSS | Propriété des éditeurs ; recherche seulement ; historique nul. |
| ESG (SIC, yfinance, méthodologie) | SIC public ; scores Yahoo/Sustainalytics non garantis, non historisés. |
| Wikipédia (pool) | CC BY-SA 4.0 ; révision datée. |
