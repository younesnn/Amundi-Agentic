# Hypothèses de travail (H-01 à H-31)

> Prototype académique (ESCP, pour Amundi Technology). Ce n'est pas un conseil en investissement.

**Contexte.** Aucun contact avec Amundi n'est possible et aucune donnée Amundi n'est disponible. Ce fichier remplace l'ancien `QUESTIONS_AMUNDI.md` : chaque question Q-n est devenue l'hypothèse H-n (même numéro, même ordre). Toute valeur qui dépendrait d'Amundi est donc une hypothèse, **testée en sensibilité** quand elle influence les résultats, et **présentée comme « à valider avec Amundi »** dans le plan de déploiement L6 et dans tout rapport.

**Statut de toutes les hypothèses : à valider avec Amundi.** Aucune n'a été confirmée.

**Règles de rédaction.**
- La valeur retenue reprend celle de `DECISIONS.md` (référence D-xxx) quand elle y existe.
- Les sources sont des documents publics dont le titre et le type sont connus ; quand la date, l'URL ou le numéro d'article n'a pas pu être relevé, la mention est « date/URL à vérifier ». Aucun chiffre ni citation de ces sources n'est repris ici : seule la nature du document est indiquée. Cette rédaction a été faite sans accès web.
- Une grille de sensibilité est un plan de test pour la phase 7 : ses valeurs sont des choix d'expérience, pas des faits sur Amundi. Les résultats seront rapportés en entier, y compris défavorables, sans choisir la valeur a posteriori.
- Les anciens identifiants Q-n restent dans `DECISIONS.md` et `PROGRESS.md` (historique, non réécrit) : la table ci-dessous donne la correspondance.

## Table de correspondance Q vers H

| Ancienne question | Hypothèse | Sujet | Sensibilité en phase 7 |
| --- | --- | --- | --- |
| Q-1 | H-01 | Univers exact | non |
| Q-2 | H-02 | Sources de données | non |
| Q-3 | H-03 | Profils clients et ESG | **oui** (voir H-11, H-26) |
| Q-4 | H-04 | LLM autorisés | non |
| Q-5 | H-05 | Horizon et fréquence | **oui** |
| Q-6 | H-06 | Benchmark | **oui** |
| Q-7 | H-07 | Intégration ALTO | non |
| Q-8 | H-08 | Validation humaine | non |
| Q-9 | H-09 | Devise et change | non (limite) |
| Q-10 | H-10 | Coûts de transaction | **oui** |
| Q-11 | H-11 | Risque par profil | **oui** |
| Q-12 | H-12 | Score ESG | **oui** |
| Q-13 | H-13 | Critère de succès de L4 | **oui** |
| Q-14 | H-14 | ESG des ETF | **oui** |
| Q-15 | H-15 | Séries obligataires et monétaires | non |
| Q-16 | H-16 | Poche titres | **oui** |
| Q-17 | H-17 | Modèle figé | non |
| Q-18 | H-18 | Gouvernance | non |
| Q-19 | H-19 | Séries et scores historisés | non |
| Q-20 | H-20 | Devise de cotation de GOLD.PA | **oui** |
| Q-21 | H-21 | Changements d'indice des ETF | non (avertissement) |
| Q-22 | H-22 | Capitalisation ou distribution | **oui** |
| Q-23 | H-23 | Exécution et liquidité | **oui** |
| Q-24 | H-24 | Backtest sur séries raccordées | **oui** |
| Q-25 | H-25 | News historiques | non |
| Q-26 | H-26 | Exclusions normatives | **oui** |
| Q-27 | H-27 | Niveau gratuit en Europe | non |
| Q-28 | H-28 | Confiance des vues issues de LLM | **oui** |
| Q-29 | H-29 | Modèle figé et durée du live test | non (puissance publiée) |
| Q-30 | H-30 | Données et cadre pour l'agent Fundamental | non |
| Q-31 | H-31 | Profils de risque dans les prompts | **oui** (ablation) |

## Sources publiques citées (clés S-x)

Aucune de ces sources n'a été consultée en ligne pour cette rédaction ; seuls le titre et le type sont affirmés.

| Clé | Source | Type | Date, URL, article |
| --- | --- | --- | --- |
| S-A | Amundi, politique d'investissement responsable et documents publics sur les exclusions (armes controversées, charbon thermique et autres secteurs) | Politique publique de la société de gestion | date/URL à vérifier ; intitulés exacts à vérifier |
| S-B | Amundi ETF, prospectus et documents d'informations clés (DIC/KID) de chaque ETF cité dans `config/universe.yaml` | Documents réglementaires de produit | date par ETF à vérifier |
| S-C | Règlement (UE) n° 1286/2014 (PRIIPs) et règlement délégué (UE) 2017/653 (déjà cité en L1 §8.2) | Réglementation de l'UE | articles et annexes à vérifier |
| S-D | Règlement (UE) 2019/2088 (SFDR) et ses normes techniques de réglementation | Réglementation de l'UE | articles à vérifier |
| S-E | Règlement (UE) 2019/2089 (indices de référence « transition climatique » et « accord de Paris ») | Réglementation de l'UE | articles à vérifier |
| S-F | Directive 2009/65/CE (OPCVM/UCITS) | Réglementation de l'UE | articles à vérifier |
| S-G | Amundi, rapport annuel ou document d'enregistrement universel | Rapport annuel | exercice et page à vérifier |
| S-H | Directive 2014/65/UE (MiFID II) et règlement (UE) 2024/1689 (AI Act) | Réglementation de l'UE | articles à vérifier avec la conformité |
| S-I | He et Litterman, « The Intuition Behind Black-Litterman Model Portfolios » (Goldman Sachs, 1999) ; Idzorek, « A Step-by-Step Guide to the Black-Litterman Model » | Articles de pratique | éditions et dates à vérifier |
| S-J | Daryanani, « Opportunistic Rebalancing: A New Paradigm for Wealth Managers » (*Journal of Financial Planning*) | Article de pratique (règle 5/25) | année et pages à vérifier |
| S-K | Conventions d'Ottawa (mines antipersonnel) et d'Oslo (armes à sous-munitions) | Traités internationaux | seule l'existence des traités est affirmée |
| S-L | Conditions d'usage des niveaux gratuits de Gemini et de Groq, relevées en D-052 | Conditions d'utilisation | de seconde main, relevé du 2026-10-03 (D-052) |
| S-M | Cahier des charges du projet (`Fiche projet Amundi Agentic.pdf`) et AlphaAgents (arXiv 2508.11152) | Documents fournis | — |
| S-N | Pratiques de marché courantes (sans source unique) | Pratique | à documenter si une source est trouvée |

---

## H-01 — Univers exact

- **Valeur retenue :** multi-actifs par ETF, ETF Amundi quand l'historique gratuit le permet, plus environ 15 actions américaines au plus (D-007, D-029).
- **Justification :** le cahier des charges ne fixe pas l'univers ; les ETF couvrent les classes d'actifs avec des données gratuites.
- **Source :** S-M ; S-B pour la liste des ETF.
- **Alternative plausible :** actions seules, ETF non Amundi, ou poche d'actions européennes.
- **Statut :** à valider avec Amundi.

## H-02 — Sources de données

- **Valeur retenue :** données gratuites uniquement (D-007).
- **Justification :** aucune donnée interne ni Bloomberg n'est disponible.
- **Source :** S-M ; fournisseurs publics (Yahoo Finance, SEC EDGAR, FRED/ALFRED, BCE), conditions d'usage à vérifier.
- **Alternative plausible :** données internes Amundi (prix, ESG, recherche) ou Bloomberg.
- **Statut :** à valider avec Amundi. Effet : couverture ESG, qualité des news, profondeur historique.

## H-03 — Profils clients et ESG

- **Valeur retenue :** prudent, équilibré, dynamique (D-019) ; exclusions : armes controversées, tabac, charbon thermique (D-007).
- **Justification :** trois profils standard de l'allocation ; exclusions normatives usuelles d'une politique d'investissement responsable.
- **Source :** S-A ; S-K pour les armes controversées ; S-N.
- **Alternative plausible :** cinq profils (comme AlphaAgents) ; liste d'exclusions plus large ou plus étroite.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** voir H-11 (paramètres de risque par profil) et H-26 (jeux d'exclusions). Résultats rapportés par profil, sans fusion.

## H-04 — LLM autorisés

- **Valeur retenue :** niveaux gratuits externes (Gemini, Groq) et Ollama local pour le prototype ; hébergement interne visé en production (D-004, D-008).
- **Justification :** budget LLM de 0 € ; données d'entrée publiques seulement (EX-NF-08).
- **Source :** S-L ; S-H pour les obligations de la production.
- **Alternative plausible :** LLM hébergé chez Amundi dès le prototype, ou fournisseur payant avec garanties contractuelles.
- **Statut :** à valider avec Amundi (conformité et sécurité des systèmes d'information).

## H-05 — Horizon et fréquence

- **Valeur retenue :** horizon de 3 à 5 ans ; revue mensuelle de l'allocation, poche titres trimestrielle sur l'historique long (D-007, D-020, D-039).
- **Justification :** cadence d'une allocation tactique modérée, compatible avec le budget d'appels (D-029).
- **Source :** S-N ; règle 5/25 de dérive : S-J.
- **Alternative plausible :** revue trimestrielle seule, ou hebdomadaire.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** fréquence de revue {mensuelle (base), trimestrielle} pour l'allocation ; déclencheurs {tous actifs (base), dérive seule, aucun} ; seuil de dérive 5/25 contre 3/15 et 7/35. Mesures : rotation, coûts, tracking error.

## H-06 — Benchmark

- **Valeur retenue :** 60 % actions monde / 40 % obligations pour le profil équilibré ; 30/70 pour prudent ; 80/20 pour dynamique (D-007, D-019, L1 §8.1). Contrôle externe : 60 % Amundi MSCI World + 40 % obligations souveraines euro (L1 §8.1).
- **Justification :** repère de pratique courante pour un portefeuille diversifié ; sert aussi de prior à Black-Litterman.
- **Source :** S-N ; S-B pour les ETF du contrôle externe.
- **Alternative plausible :** indice composite maison d'Amundi, 100 % actions pour le profil dynamique, ou benchmark en monnaie couverte.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** part actions du benchmark décalée de {-10, 0, +10} points pour chaque profil (les bornes de classe de L1 §8.3 restent admissibles ou sont signalées) ; benchmark de contrôle CW8 + MTD ; équipondération 1/N des classes. Mesure : rang de la stratégie contre chaque benchmark, rapporté sans choix a posteriori.

## H-07 — Intégration ALTO

- **Valeur retenue :** service d'API générique décrit dans L6 ; aucun format propriétaire supposé.
- **Justification :** aucune documentation des API ALTO n'est disponible.
- **Source :** aucune source publique consultée ; à documenter avec Amundi Technology.
- **Alternative plausible :** format d'échange imposé par ALTO (vues, poids, fiches).
- **Statut :** à valider avec Amundi.

## H-08 — Validation humaine

- **Valeur retenue :** le gérant valide, modifie ou rejette chaque proposition, avec trace (L1 §10.4).
- **Justification :** principe de contrôle humain d'un système d'aide à la décision.
- **Source :** S-H (supervision humaine, à examiner avec la conformité).
- **Alternative plausible :** double validation (gérant puis risque) ou comité.
- **Statut :** à valider avec Amundi.

## H-09 — Devise et change

- **Valeur retenue :** EUR, sans couverture de change (D-011).
- **Justification :** devise de référence d'un investisseur de la zone euro ; couverture non modélisable avec les données gratuites.
- **Source :** S-N.
- **Alternative plausible :** classes de parts couvertes, ou devise de référence autre que l'euro.
- **Statut :** à valider avec Amundi. Limite documentée, pas de test de sensibilité (pas de séries de couverture).

## H-10 — Coûts de transaction

- **Valeur retenue :** 2 à 25 points de base aller simple selon la classe (L1 §10.3), plus 2 points de base de change ; exécution à la clôture de t (D-020, D-038).
- **Justification :** ordres de grandeur supposés pour des ETF UCITS liquides ; les frais de gestion sont déjà dans les cours.
- **Source :** S-B (frais courants dans les DIC, à vérifier) ; S-C (coûts affichés dans les DIC) ; S-N pour les fourchettes d'achat-vente.
- **Alternative plausible :** coûts réels d'exécution d'Amundi (négociés, par fixing), retenue à la source corrigée.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** multiplicateur des coûts {0 (référence brute), 1 (base), 2, 3 (stress de D-020)} ; coût de change {0, 2, 4} points de base ; exécution {clôture de t (base), ouverture de t+1}. Mesures : performance nette, rotation, point où la stratégie passe sous le benchmark.

## H-11 — Risque par profil

- **Valeur retenue :** D-019 : volatilité plafond 7 / 11 / 16 %, TE max 2 / 3 / 4 %, rotation mensuelle max 5 / 7,5 / 10 % ; volatilité en plafond strict ; SR* = 0,35 ; bornes de L1 §8.3.
- **Justification :** repères de classes de risque PRIIPs (S-C) et bandes autour du benchmark ; ordre de grandeur supposé des mandats tactiques.
- **Source :** S-C ; S-I pour δ (He et Litterman) ; S-N.
- **Alternative plausible :** volatilité en cible et non en plafond ; bornes du mandat réel d'Amundi.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** volatilité plafond × {0,8 ; 1 ; 1,2}, soit 5,6 / 7 / 8,4 % (prudent), 8,8 / 11 / 13,2 % (équilibré), 12,8 / 16 / 19,2 % (dynamique) ; TE max × {0,5 ; 1 ; 1,5} ; rotation × {0,5 ; 1 ; 2} ; SR* {0,25 ; 0,35 ; 0,45} (grille déjà inscrite en L1 §8.2) ; bornes de classe élargies ou resserrées de 5 points. Mesures : fréquence de contraintes actives, performance nette, stabilité des poids.

## H-12 — Score ESG

- **Valeur retenue :** scores gratuits partiels et exclusions par secteur (D-022) ; en pratique aucun score exploitable, contrainte CT-06 suspendue (D-035).
- **Justification :** aucune source gratuite n'est utilisable et historisée.
- **Source :** S-A ; S-D.
- **Alternative plausible :** score ESG propriétaire d'Amundi, historisé.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** avec et sans la contrainte ESG sectorielle (jeux de H-26) ; la contrainte de score reste hors test tant qu'aucune donnée n'existe. Mesure : coût de la contrainte (écart de performance nette et de risque).

## H-13 — Critère de succès de L4

- **Valeur retenue :** démonstration de la mécanique, contrôle du risque, coûts et explicabilité ; pas de preuve d'un alpha (D-025). Effet minimal détectable publié : IR_min ≈ 2,8/√T ; correction de Holm sur 9 tests principaux ; règles de rapport de D-064.
- **Justification :** avec un historique hors échantillon court, aucun alpha modeste n'est détectable.
- **Source :** S-M ; méthodes citées en D-025 (bootstrap stationnaire de Politis et Romano, 1994 ; correction de Holm).
- **Alternative plausible :** Amundi attend une preuve de performance sur une durée de live test plus longue.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** le critère est présenté sous deux lectures sans choisir : (a) critère de mécanique (100 % des contraintes respectées, journaux complets) ; (b) critère de performance : ratio d'information net de coûts comparé à des seuils {0 ; 0,5 ; 1,0} et à IR_min pour la durée T réellement disponible. Rapport de la puissance, jamais d'un « succès » seul.

## H-14 — ESG des ETF

- **Valeur retenue :** les exclusions d'un ETF découlent de la méthodologie de son indice ; on préfère les variantes ESG ou PAB ; source manuelle appuyée sur un document (D-022, D-048).
- **Justification :** aucune source gratuite ne donne le contenu des ETF de façon historisée.
- **Source :** S-B (prospectus, DIC et page de l'indice) ; S-D (classification SFDR) ; S-E (indices PAB et CTB).
- **Alternative plausible :** transparence titre par titre fournie par Amundi.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** univers d'ETF {tous (base), ETF à variante ESG/PAB seulement, ETF classés SFDR article 8 ou 9 seulement} ; mesure : écart de performance et de risque, nombre de classes encore couvertes.

## H-15 — Séries obligataires et monétaires

- **Valeur retenue :** BCE et ICE sur FRED, sinon début retardé (D-011, D-034).
- **Justification :** seules séries gratuites disponibles en euros.
- **Source :** S-M (fournisseurs publics) ; conditions de réutilisation à vérifier.
- **Alternative plausible :** valeurs liquidatives ou indices historiques fournis par Amundi.
- **Statut :** à valider avec Amundi. Effet : date de début du backtest.

## H-16 — Poche titres

- **Valeur retenue :** actions américaines, environ 15 titres au plus, 5 à 15 % du portefeuille selon le profil, décisions trimestrielles sur l'historique long, mensuelles ensuite (D-029, D-039, L1 §8.3).
- **Justification :** seules les sociétés déposant à la SEC ont des 10-K et 10-Q gratuits et datés ; la poche consomme environ 94 % du budget d'appels (D-029).
- **Source :** S-M (AlphaAgents) ; EDGAR (SEC).
- **Alternative plausible :** titres européens, poche absente, plafond par titre différent.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** taille de la poche {0 % (allocation par ETF seule), base du profil, base × 2 dans les bornes admises} ; plafond par titre {1, 2, 3 %} de D-019 décalé de ±1 point ; fréquence {trimestrielle, mensuelle} sur la période récente. Mesure : contribution de la poche à la performance et au risque.

## H-17 — Modèle figé

- **Valeur retenue :** niveau gratuit avec alias de modèle (D-008, D-024) ; dates de fin d'entraînement relevées en D-052 (de seconde main).
- **Justification :** pas d'accès à un modèle à version figée.
- **Source :** S-L.
- **Alternative plausible :** version de modèle figée et documentée fournie ou autorisée par Amundi.
- **Statut :** à valider avec Amundi. Effet : contamination et reproductibilité ; les résultats antérieurs à la borne sont étiquetés « contaminés » (D-025, D-064).

## H-18 — Gouvernance

- **Valeur retenue :** l'équipe valide les paramètres gelés et les révisions de prompts, avec trace dans `DECISIONS.md` (D-027).
- **Justification :** pas d'interlocuteur chez Amundi ; la trace écrite et le pré-enregistrement tiennent lieu de contrôle.
- **Source :** S-H pour le cadre de gouvernance à examiner avec la conformité ; S-N.
- **Alternative plausible :** comité de risque de modèle d'Amundi.
- **Statut :** à valider avec Amundi (voir L6).

## H-19 — Séries et scores historisés

- **Valeur retenue :** exclusions par SIC et méthodologie d'indice ; ETF comme séries de rendement ; backtest en euros court (début 2018-08 avec le haut rendement, 2014-03 sans) (D-034, D-035).
- **Justification :** aucune série historisée d'indices en euros ni score ESG gratuit.
- **Source :** S-B ; fournisseurs publics.
- **Alternative plausible :** séries d'indices et scores historisés fournis par Amundi.
- **Statut :** à valider avec Amundi. Effet : CT-06, date de début du backtest, longueur de la période hors échantillon.

## H-20 — Devise de cotation de GOLD.PA

- **Valeur retenue :** EUR (D-038), alors que Yahoo étiquette USD.
- **Justification :** le nom du produit et la place de cotation (suffixe .PA) suggèrent l'euro ; non confirmé.
- **Source :** S-B (prospectus et DIC de l'ETC, devise de cotation à vérifier).
- **Alternative plausible :** cotation en USD, conversion nécessaire.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** Σ, Π et poids de la classe « or » recalculés sous {EUR (base), USD converti en EUR}. Mesure : écart de volatilité de la classe et de poids optimaux.

## H-21 — Changements d'indice des ETF

- **Valeur retenue :** séries Yahoo prises telles quelles, avec avertissement (D-046) ; changement d'indice de CRP.PA daté du 2023-01-11 dans `tests/data/test_esg_etf_sources.py` et `config/esg_etf_sources.yaml`.
- **Justification :** pas de valeurs liquidatives ni d'indices historiques alternatifs.
- **Source :** S-B (avis aux porteurs et prospectus, dates à vérifier).
- **Alternative plausible :** séries reconstituées par indice, ou fenêtre limitée à la période après le changement.
- **Statut :** à valider avec Amundi. Avertissement dans L1 R-11, pas de test dédié.

## H-22 — Capitalisation ou distribution

- **Valeur retenue :** colonne `distribution` de `config/universe.yaml` (acc, dist ou a_verifier) ; « dist » seulement si des dividendes sont enregistrés.
- **Justification :** Yahoo n'indique pas la politique de distribution de façon fiable.
- **Source :** S-B (DIC et prospectus : politique de distribution).
- **Alternative plausible :** traitement en rendement total pour tous les ETF.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** ETF « a_verifier » traités {en capitalisation (base), en distribution avec réinvestissement}. Mesure : écart de rendement total par ETF et sur le portefeuille.

## H-23 — Exécution et liquidité

- **Valeur retenue :** coûts de L1 §10.3, exécution à la clôture de t ; plafond de participation au volume à fixer en phase 4.
- **Justification :** AHYE.PA et C3M.PA sont signalés comme peu liquides (D-046, constat non rejoué).
- **Source :** S-N ; rapport de couverture `docs/couverture_donnees.md` (liquidité mesurée).
- **Alternative plausible :** exécution par fixing, taille d'encours réelle d'Amundi.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** plafond de participation au volume journalier médian {1 ; 5 ; 10 %} ; coûts des ETF peu liquides × {1 ; 2 ; 3} ; taille de portefeuille fictive {10 ; 100 ; 1 000 millions d'euros}. Mesure : faisabilité (jours d'exécution) et performance nette.

## H-24 — Backtest sur séries raccordées

- **Valeur retenue :** rendement total simulé par raccord d'un proxy accepté, étiqueté « non investissable » avant la première date de l'ETF primaire (D-046).
- **Justification :** sans raccord, certaines classes n'atteignent pas 260 semaines avant 2024.
- **Source :** S-B ; fournisseurs publics.
- **Alternative plausible :** backtest limité aux séries d'ETF réels.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** début du backtest {avec raccords (base), ETF réels seuls, soit 2024-05 pour l'or}. Mesure : écart de résultats rapporté, résultats « investissables » et « non investissables » séparés.

## H-25 — News historiques

- **Valeur retenue :** l'agent Sentiment est hors backtest (D-044).
- **Justification :** les sources gratuites ne datent pas la publication de façon fiable dans le passé.
- **Source :** S-M.
- **Alternative plausible :** archive interne d'actualités datées.
- **Statut :** à valider avec Amundi.

## H-26 — Exclusions normatives

- **Valeur retenue :** armes controversées, tabac, charbon thermique par SIC et méthodologie d'indice ; armes controversées non détectables par SIC (D-035).
- **Justification :** exclusions usuelles d'une politique d'investissement responsable ; liste exacte d'Amundi non disponible.
- **Source :** S-A ; S-K pour les armes controversées.
- **Alternative plausible :** liste d'Amundi plus longue (autres secteurs ou seuils de chiffre d'affaires).
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** jeux d'exclusions {aucune ; base (tabac, charbon thermique par SIC) ; base élargie à d'autres codes SIC à définir dans `config/esg.yaml`}. Mesure : nombre de titres exclus, écart de performance et de risque de la poche titres.

## H-27 — Niveau gratuit en Europe

- **Valeur retenue :** usage de recherche, données publiques non confidentielles (D-052).
- **Justification :** conditions relevées de seconde main : usage à revérifier (D-052, L1 R-14).
- **Source :** S-L.
- **Alternative plausible :** offre payante avec garanties de non-réutilisation des données.
- **Statut :** à valider avec Amundi (voir L6).

## H-28 — Confiance des vues issues de LLM

- **Valeur retenue :** confiance constante par défaut dans Ω ; l'« indice d'accord de processus » est mesuré à part (D-063).
- **Justification :** la confiance du débat n'est pas calibrée ; l'accord des agents d'un même modèle ne prouve rien.
- **Source :** S-I (Idzorek pour la sémantique d'inclinaison de la vue) ; S-M.
- **Alternative plausible :** confiance variable, plafonnée bas.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** confiance constante c × {0,5 ; 1 ; 1,5} plafonnée par c_max gelée, contre la confiance issue du débat ; aucune valeur réestimée sur les résultats (D-063). Mesure : inclinaison des poids, performance nette, table de fiabilité.

## H-29 — Modèle figé et durée du live test

- **Valeur retenue :** Gemini gratuit à alias ; durée du live test à définir ; environ 780 observations indépendantes pour distinguer 55 % de 50 % (D-063).
- **Justification :** aucune garantie de version figée ; la puissance statistique est publiée.
- **Source :** S-L.
- **Alternative plausible :** modèle figé de bout en bout pendant un live test long.
- **Statut :** à valider avec Amundi.

## H-30 — Données et cadre pour l'agent Fundamental

- **Valeur retenue :** lecture qualitative des dépôts EDGAR, sans valorisation (D-066).
- **Justification :** aucun flux horodaté de documents internes ni cadre de multiples cibles.
- **Source :** EDGAR (SEC) ; S-M.
- **Alternative plausible :** cadre de valorisation maison avec multiples cibles.
- **Statut :** à valider avec Amundi.

## H-31 — Profils de risque dans les prompts

- **Valeur retenue :** profil dans le prompt pour la réplication seulement ; ablation « avec profil » contre « sans profil + contraintes » choisie avant les runs (D-066).
- **Justification :** éviter le triple comptage de la volatilité (prompt, facteur h, optimiseur).
- **Source :** S-M (AlphaAgents) ; D-066.
- **Alternative plausible :** profils uniquement par contraintes, ou aussi par vues neutres au profil.
- **Statut :** à valider avec Amundi.
- **Test de sensibilité prévu en phase 7 :** deux configurations {prompt avec profil, prompt sans profil et contraintes}, au moins 3 exécutions chacune ; mesure : écart de poids comparé au bruit entre exécutions.

---

## Hypothèses à sensibilité : récapitulatif des grilles

| Hypothèse | Paramètre | Grille |
| --- | --- | --- |
| H-03, H-11 | Volatilité plafond | × {0,8 ; 1 ; 1,2} de 7 / 11 / 16 % |
| H-11 | TE max, rotation, SR*, bornes | TE × {0,5 ; 1 ; 1,5} ; rotation × {0,5 ; 1 ; 2} ; SR* {0,25 ; 0,35 ; 0,45} ; bornes ± 5 points |
| H-05 | Fréquence et déclencheurs | mensuelle / trimestrielle ; déclencheurs tous / dérive seule / aucun ; 5/25, 3/15, 7/35 |
| H-06 | Benchmark | part actions {-10, 0, +10} points ; CW8 + MTD ; 1/N |
| H-10 | Coûts | × {0 ; 1 ; 2 ; 3} ; change {0 ; 2 ; 4} points de base ; exécution clôture t / ouverture t+1 |
| H-12, H-26 | Exclusions ESG | aucune / base / base élargie |
| H-13 | Critère de L4 | mécanique ; IR net contre {0 ; 0,5 ; 1,0} et IR_min |
| H-14 | Univers ESG des ETF | tous / ESG ou PAB / SFDR 8 ou 9 |
| H-16 | Poche titres | {0 %, base, base × 2} ; plafond par titre ± 1 point ; trimestrielle / mensuelle |
| H-20 | Devise de GOLD.PA | EUR / USD converti |
| H-22 | Distribution | capitalisation / distribution avec réinvestissement |
| H-23 | Liquidité | participation {1 ; 5 ; 10 %} ; coûts peu liquides × {1 ; 2 ; 3} ; taille {10 ; 100 ; 1 000 M€} |
| H-24 | Séries raccordées | avec raccord / ETF réels seuls |
| H-28 | Confiance de vue | c × {0,5 ; 1 ; 1,5} plafonné ; débat contre constante |
| H-31 | Profil en prompt | avec / sans profil, 3 exécutions au moins |
