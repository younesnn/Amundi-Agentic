# Réplication AlphaAgents : rapport (protocole D-065)

> Prototype académique (ESCP, pour Amundi Technology). Ce n'est pas un conseil en investissement.

## Verdict : NON CONCLUANT

Raisons (règles de D-065 §10, appliquées par le code) :

- [risk_averse] multi_agent contre ET : l'intervalle de la différence contient 0
- [risk_averse] multi_agent contre ET : 0 titre(s) diffèrent (moins de 4)
- [risk_averse] multi_agent contre ET : désaccord entre exécutions non mesurable (moins de 2 exécutions)
- [risk_averse] multi_agent contre ET : le multi-agent ne fait pas mieux
- [risk_averse] multi_agent contre valuation_seul : l'intervalle de la différence contient 0
- [risk_averse] multi_agent contre valuation_seul : 0 titre(s) diffèrent (moins de 4)
- [risk_averse] multi_agent contre valuation_seul : désaccord entre exécutions non mesurable (moins de 2 exécutions)
- [risk_averse] multi_agent contre valuation_seul : le multi-agent ne fait pas mieux
- [risk_averse] multi_agent contre fundamental_seul : l'intervalle de la différence contient 0
- [risk_averse] multi_agent contre fundamental_seul : 0 titre(s) diffèrent (moins de 4)
- [risk_averse] multi_agent contre fundamental_seul : désaccord entre exécutions non mesurable (moins de 2 exécutions)
- [risk_averse] multi_agent contre fundamental_seul : le multi-agent ne fait pas mieux
- [risk_neutral] multi_agent contre ET : l'intervalle de la différence contient 0
- [risk_neutral] multi_agent contre ET : 0 titre(s) diffèrent (moins de 4)
- [risk_neutral] multi_agent contre ET : désaccord entre exécutions non mesurable (moins de 2 exécutions)
- [risk_neutral] multi_agent contre ET : le multi-agent ne fait pas mieux
- [risk_neutral] multi_agent contre valuation_seul : l'intervalle de la différence contient 0
- [risk_neutral] multi_agent contre valuation_seul : 0 titre(s) diffèrent (moins de 4)
- [risk_neutral] multi_agent contre valuation_seul : désaccord entre exécutions non mesurable (moins de 2 exécutions)
- [risk_neutral] multi_agent contre valuation_seul : le multi-agent ne fait pas mieux
- [risk_neutral] multi_agent contre fundamental_seul : l'intervalle de la différence contient 0
- [risk_neutral] multi_agent contre fundamental_seul : 0 titre(s) diffèrent (moins de 4)
- [risk_neutral] multi_agent contre fundamental_seul : désaccord entre exécutions non mesurable (moins de 2 exécutions)
- [risk_neutral] multi_agent contre fundamental_seul : le multi-agent ne fait pas mieux

Objet : vérifier la mécanique et la cohérence qualitative avec le papier. Aucune conclusion de performance.

## Modèle et étiquette

- modèle servi `ollama/llama3.1:8b` : dans la marge de contamination : hors échantillon non garanti, sondage de mémoire requis
- les résultats de modèles différents ne sont jamais moyennés.

## Protocole et pré-enregistrement

- date de décision 2024-02-01, suivi jusqu'au 2024-05-31 inclus ; fenêtre mesurée : 2024-02-01 à 2024-05-31 (84 séances) ; prix servis comme `as_of` du 2024-06-01
- pré-enregistrement : conforme (SHA-256 d5418d8b115a150f6798d8b96c44f70a8d2ec55ca48ad9e043ccc4b811ec3f4f)
- SHA-256 de la graine du tirage : d7458cc2854316191485a831d14dbb2b9313ee4cdf2194c2d2995997834e88f5 ; graine vérifiée contre l'enregistrement : oui
- taux sans risque fred:DGS1MO : moyenne annuelle 5.50 % ; devise USD, prix adj_close
- un seul rééquilibrage (achat et conservation, équipondéré à l'entrée) ; coûts de transaction non modélisés (performance surestimée)
- agent Sentiment exclu (D-044) ; agents votants : valuation, fundamental

## Univers

- pool daté : 64 titres, 62 utilisables ; titre hors pool : ZS (ajouté d'office)
- titres sans données, exclus par la règle fixée d'avance : ANSS (aucune donnée de prix dans le stockage (société radiée ou absente de la source)), JNPR (aucune donnée de prix dans le stockage (société radiée ou absente de la source))
- tirage primaire (15 titres) : ZS, AMAT, NVDA, CTSH, NTAP, CRM, IT, QCOM, IBM, GEN, PTC, EPAM, ADI, KEYS, KLAC
- remplacements pour échec technique : {'TRMB': 'KLAC'}
- titres évalués : 16

## Décisions et performance : exécution baseline, profil risk_averse

| Portefeuille | BUY | SELL | exclus | Rendement cumulé | Volatilité ann. | Sharpe [IC 95 %] | Perte max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Valuation seul (trésorerie) | 0 | 14 | 1 | 1.78 % | 0.00 % | n/d | 0.00 % |
| Fundamental seul (trésorerie) | 0 | 5 | 10 | 1.78 % | 0.00 % | n/d | 0.00 % |
| ET (sans débat) (trésorerie) | 0 | 5 | 10 | 1.78 % | 0.00 % | n/d | 0.00 % |
| OU (sans débat) (trésorerie) | 0 | 5 | 10 | 1.78 % | 0.00 % | n/d | 0.00 % |
| Multi-agent (débat) (trésorerie) | 0 | 5 | 10 | 1.78 % | 0.00 % | n/d | 0.00 % |
| Référence : 15 titres équipondérés | - | - | - | 7.55 % | 20.57 % | 0.93 [-1.96 ; 5.95] | -10.82 % |
| Référence : tous les titres évalués équipondérés | - | - | - | 7.47 % | 19.83 % | 0.96 [-1.99 ; 6.00] | -10.57 % |
| Référence : trésorerie | - | - | - | 1.78 % | 0.00 % | n/d | 0.00 % |

Sensibilité « abstention = BUY » (les titres abstenus sont inclus au portefeuille ; analyse principale : exclus) :

| Portefeuille | BUY (principal) | BUY (abstention = BUY) | Rendement cumulé (abstention = BUY) |
| --- | --- | --- | --- |
| Valuation seul | 0 | 1 | -37.70 % |
| Fundamental seul | 0 | 10 | 7.81 % |
| ET (sans débat) | 0 | 10 | 7.81 % |
| OU (sans débat) | 0 | 10 | 7.81 % |
| Multi-agent (débat) | 0 | 10 | 7.81 % |

Taux d'abstention (aucun vote retenu au tour 0) : valuation 6.2 % (1/16) ; fundamental 62.5 % (10/16).

Portefeuille de même taille tiré au hasard (distribution exacte sur le tirage primaire) :

| Portefeuille | m | combinaisons | exacte | médiane | centiles 5 / 95 | part des aléatoires au moins aussi bons |
| --- | --- | --- | --- | --- | --- | --- |
| Valuation seul | 0 | - | - | - | - | trésorerie : sans tirage |
| Fundamental seul | 0 | - | - | - | - | trésorerie : sans tirage |
| ET (sans débat) | 0 | - | - | - | - | trésorerie : sans tirage |
| OU (sans débat) | 0 | - | - | - | - | trésorerie : sans tirage |
| Multi-agent (débat) | 0 | - | - | - | - | trésorerie : sans tirage |

## Décisions et performance : exécution baseline, profil risk_neutral

| Portefeuille | BUY | SELL | exclus | Rendement cumulé | Volatilité ann. | Sharpe [IC 95 %] | Perte max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Valuation seul (trésorerie) | 0 | 10 | 5 | 1.78 % | 0.00 % | n/d | 0.00 % |
| Fundamental seul (trésorerie) | 0 | 3 | 12 | 1.78 % | 0.00 % | n/d | 0.00 % |
| ET (sans débat) (trésorerie) | 0 | 2 | 13 | 1.78 % | 0.00 % | n/d | 0.00 % |
| OU (sans débat) (trésorerie) | 0 | 2 | 13 | 1.78 % | 0.00 % | n/d | 0.00 % |
| Multi-agent (débat) (trésorerie) | 0 | 2 | 13 | 1.78 % | 0.00 % | n/d | 0.00 % |
| Référence : 15 titres équipondérés | - | - | - | 7.55 % | 20.57 % | 0.93 [-1.96 ; 5.95] | -10.82 % |
| Référence : tous les titres évalués équipondérés | - | - | - | 7.47 % | 19.83 % | 0.96 [-1.99 ; 6.00] | -10.57 % |
| Référence : trésorerie | - | - | - | 1.78 % | 0.00 % | n/d | 0.00 % |

Sensibilité « abstention = BUY » (les titres abstenus sont inclus au portefeuille ; analyse principale : exclus) :

| Portefeuille | BUY (principal) | BUY (abstention = BUY) | Rendement cumulé (abstention = BUY) |
| --- | --- | --- | --- |
| Valuation seul | 0 | 5 | 6.38 % |
| Fundamental seul | 0 | 12 | 4.37 % |
| ET (sans débat) | 0 | 13 | 2.92 % |
| OU (sans débat) | 0 | 13 | 2.92 % |
| Multi-agent (débat) | 0 | 13 | 2.92 % |

Taux d'abstention (aucun vote retenu au tour 0) : valuation 33.3 % (5/15) ; fundamental 80.0 % (12/15).

Portefeuille de même taille tiré au hasard (distribution exacte sur le tirage primaire) :

| Portefeuille | m | combinaisons | exacte | médiane | centiles 5 / 95 | part des aléatoires au moins aussi bons |
| --- | --- | --- | --- | --- | --- | --- |
| Valuation seul | 0 | - | - | - | - | trésorerie : sans tirage |
| Fundamental seul | 0 | - | - | - | - | trésorerie : sans tirage |
| ET (sans débat) | 0 | - | - | - | - | trésorerie : sans tirage |
| OU (sans débat) | 0 | - | - | - | - | trésorerie : sans tirage |
| Multi-agent (débat) | 0 | - | - | - | - | trésorerie : sans tirage |

## Titres dont les prix s'arrêtent avant la fin du suivi

Aucun.

## Différences appariées (bootstrap stationnaire, exécution baseline)

| Profil | Comparaison | Différence de rendement cumulé | IC 95 % | Titres différents | Désaccord entre exécutions | Contient 0 |
| --- | --- | --- | --- | --- | --- | --- |
| risk_averse | multi_agent contre ET | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_averse | multi_agent contre OU | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_averse | multi_agent contre valuation_seul | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_averse | multi_agent contre fundamental_seul | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_averse | multi_agent contre ref15 | -5.77 % | [-29.43 % ; 14.46 %] | 15 | n/d | oui |
| risk_neutral | multi_agent contre ET | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_neutral | multi_agent contre OU | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_neutral | multi_agent contre valuation_seul | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_neutral | multi_agent contre fundamental_seul | 0.00 % | [0.00 % ; 0.00 %] | 0 | n/d | oui |
| risk_neutral | multi_agent contre ref15 | -5.77 % | [-29.43 % ; 14.46 %] | 15 | n/d | oui |

Intervalle large publié même s'il est inexploitable (15 titres du même secteur, une fenêtre de quatre mois).

## Tirages secondaires (rééchantillonnage du pool évalué, sans appel LLM)

1000 tirages de 14 titres plus ZS. Ils mesurent la variance du choix des titres, pas celle du marché.

Profil risk_averse, exécution baseline :

| Portefeuille | Tirage primaire | Médiane | Centile 5 | Centile 95 |
| --- | --- | --- | --- | --- |
| Valuation seul | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| Fundamental seul | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| ET (sans débat) | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| OU (sans débat) | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| Multi-agent (débat) | 1.78 % | 1.78 % | 1.78 % | 1.78 % |

Multi-agent moins ET : médiane 0.00 %, centiles 5 / 95 : 0.00 % / 0.00 % ; part des tirages positifs : 0.000.

Profil risk_neutral, exécution baseline :

| Portefeuille | Tirage primaire | Médiane | Centile 5 | Centile 95 |
| --- | --- | --- | --- | --- |
| Valuation seul | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| Fundamental seul | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| ET (sans débat) | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| OU (sans débat) | 1.78 % | 1.78 % | 1.78 % | 1.78 % |
| Multi-agent (débat) | 1.78 % | 1.78 % | 1.78 % | 1.78 % |

Multi-agent moins ET : médiane 0.00 %, centiles 5 / 95 : 0.00 % / 0.00 % ; part des tirages positifs : 0.000.

## Exécutions : accord et plancher de bruit

| Profil | Exécution | Titres | Accord avec baseline | IC de Wilson 95 % | Kappa |
| --- | --- | --- | --- | --- | --- |

Accord entre les deux agents au tour 0 (même décision BUY ou SELL) :

| Exécution | Profil | Titres | Fréquence | IC de Wilson 95 % |
| --- | --- | --- | --- | --- |
| baseline | risk_averse | 6 | 1.000 | [0.610 ; 1.000] |
| baseline | risk_neutral | 2 | 1.000 | [0.342 ; 1.000] |

## Journal de qualité

| Exécution | Agent | Débats | Rejet d'ancrage | Abstention | Erreur JSON | Panne | Voix unique (débat) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | valuation | 31 | 19.4 % | 0.0 % | 0.0 % | 0.0 % | 58.1 % |
| baseline | fundamental | 31 | 22.6 % | 6.5 % | 41.9 % | 0.0 % | 58.1 % |

Modèle servi : dev = ollama/llama3.1:8b.

## Comparaison qualitative avec le papier (aucun chiffre du papier)

Titres, modèle, outils et agent Sentiment diffèrent du papier : seule une lecture qualitative est possible.

| Comportement décrit par le papier | Observé ici (baseline) | Lecture |
| --- | --- | --- |
| Le profil risk-averse retient moins de titres que le risk-neutral | BUY multi-agent : 0 (averse) contre 0 (neutre) | indéterminé |
| Risk-averse : le multi-agent est plus resserré que les agents seuls | BUY : multi-agent 0, Valuation 0, Fundamental 0 | indéterminé |
| Risk-averse : écarte les titres les plus volatils | aucun titre BUY ou volatilité absente | indéterminé |
| Le risk-neutral obtient un rendement cumulé plus élevé que le risk-averse (multi-agent) | 1.78 % (neutre) contre 1.78 % (averse), sans inférence | indéterminé |
| Risk-averse : le multi-agent subit une perte maximale plus faible que les agents seuls | multi-agent 0.00 %, Valuation 0.00 %, Fundamental 0.00 % | différent |

## Limites

- 15 titres d'un même secteur, une seule fenêtre de quatre mois : puissance statistique pratiquement nulle ; aucune conclusion de performance.
- Pool daté de janvier 2024 : biais du survivant ; données de prix actuelles.
- Décisions prises avec des prix en EUR (couche de données), performance mesurée en USD : voir protocole.
- Fundamental : lecture qualitative de dépôts par un LLM ; ET et OU exigent les deux votes ; le multi-agent est mécaniquement plus conservateur à deux votants.
- Contrôle de mémoire (anonymisation, sondage) et réplication jumelle post-coupure : non faits.
- La trajectoire du Sharpe glissant est dans `sharpe_glissant.csv` ; elle n'a pas d'intervalle et n'est pas reprise ici.
