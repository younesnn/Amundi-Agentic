# Journal des décisions

Chaque choix technique : options envisagées, choix, justification, date. Seul le chef de projet met ce fichier à jour.

## D-001 — Racine du dépôt (2026-10-02)

- **Options :** créer un sous-dossier `amundi-agentic/` (section 5.2 du prompt) ; utiliser le dossier existant.
- **Choix :** la structure de la section 5.2 est créée directement à la racine du dossier existant.
- **Justification :** consigne de `CLAUDE.md` ; le dossier est déjà le dépôt Git relié à `github.com/younesnn/Amundi-Agentic`.

## D-002 — Gestionnaire d'environnement et version de Python (2026-10-02)

- **Options :** uv ou poetry ; Python 3.11, 3.12 ou 3.14 (seule version installée sur le Mac).
- **Choix :** uv (0.12.17) et Python 3.12 géré par uv (`.python-version`), `requires-python = ">=3.11"`.
- **Justification :** uv est déjà installé et gère aussi l'interpréteur ; poetry ne l'est pas. Python 3.14 est trop récent pour garantir des wheels de cvxpy, de ses solveurs et de LiteLLM ; 3.12 est mature et respecte l'exigence « 3.11+ ». Le fichier `uv.lock` fige les versions pour la reproductibilité.

## D-003 — Emplacement des prompts de rôle (2026-10-02)

- **Options :** `prompts/` (section 5.2) ; un sous-dossier de `prompts/` ; un dossier séparé.
- **Choix :** dossier séparé `agent_prompts/`.
- **Justification :** `prompts/` contient le prompt maître et fait partie des fichiers à ne pas modifier (`CLAUDE.md`). Un dossier séparé évite de mélanger la consigne du projet et les artefacts versionnés du système.

## D-004 — Fournisseurs LLM et adaptateurs (2026-10-02)

- **Constat :** la section 5.2 cite des adaptateurs « anthropic, openai, local », alors que le plan LLM à 0 € (section 2) et `CLAUDE.md` imposent Gemini (niveau gratuit), Ollama et Groq, sans autre fournisseur sans validation, et interdisent `ANTHROPIC_API_KEY`.
- **Choix :** une interface unique `LLMClient` appuyée sur LiteLLM, avec trois configurations actives : Gemini (moteur principal), Ollama `llama3.1:8b` (développement et tests), Groq (relais sur erreur 429). Aucun adaptateur Anthropic ou OpenAI activé.
- **Justification :** le plan à 0 € est la règle la plus précise et la plus récente. L'agnosticisme exigé est conservé : ajouter un fournisseur ne demande qu'une entrée de configuration, ce que la documentation technique (phase 8) décrira. Question ouverte Q-4.
- **Reste à faire (phase 3) :** relever les limites réelles des niveaux gratuits et leur usage des données pour l'entraînement, à l'inscription.
- **Tests de connexion (2026-10-02) :**
  - Gemini : `gemini-flash-latest` et `gemini-flash-lite-latest` répondent.
  - Gemini : `gemini-pro-latest` renvoie une erreur 429 (quotas `FreeTier`). Il faut donc prévoir Flash pour le coordinateur et l'agent Fundamental, comme le prompt le permet.
  - Gemini : `gemini-3.5-flash` et `gemini-3.8-flash` renvoient une erreur 503 (service indisponible, à retester).
  - Groq : `llama-3.3-70b-versatile` n'est plus proposé ; `openai/gpt-oss-120b` et `qwen/qwen3.8-27b` répondent. Le choix du modèle de relais est à trancher en phase 3.
  - Ollama : `llama3.1:8b` répond en local.
  - Données : FRED (série DGS10) et SEC EDGAR (`data.sec.gov`, User-Agent déclaré) répondent.

## D-005 — Outils qualité et CI (2026-10-02)

- **Options :** ruff ou flake8 + black + isort ; mypy maintenant ou plus tard ; GitHub Actions ou autre CI.
- **Choix :** ruff (lint et format) et pytest (`--strict-markers`, couverture via pytest-cov) ; GitHub Actions (`.github/workflows/ci.yml`) avec uv figé en 0.12.17, `uv sync --locked`, une matrice Python 3.11 et 3.12 (pour tenir la promesse `>=3.11`) et des permissions en lecture seule. Les tests marqués `llm` ou `network` sont exclus de la CI. Le typage statique (mypy) est reporté à la phase 3, quand il y aura du code à typer.
- **Justification :** un seul outil rapide pour le lint et le format ; le dépôt est déjà sur GitHub ; la CI doit passer sans clé d'API ni réseau (section 2, « Tests »).

## D-006 — Dépendances ajoutées phase par phase (2026-10-02)

- **Choix :** en phase 0, seules les dépendances de développement (pytest, pytest-cov, ruff) sont installées. Chaque bibliothèque métier (pandas, yfinance, LiteLLM, cvxpy, LangGraph ou AutoGen, Streamlit…) est ajoutée dans la phase qui l'utilise, avec sa justification ici.
- **Justification :** éviter de figer des choix (notamment le cadre d'orchestration, comparé en phase 1) avant de les avoir étudiés.

## D-007 — Hypothèses de cadrage en attendant Amundi (2026-10-02)

Le cahier des charges ne précise pas ces points. Hypothèses de travail tirées du prompt maître, à confirmer (questions Q-1 à Q-6 de `QUESTIONS_AMUNDI.md`) :

| Sujet | Hypothèse de travail | Question |
| --- | --- | --- |
| Univers | ETF liquides par classe (actions Europe, États-Unis, Japon, émergents ; souverain ; crédit IG ; haut rendement ; or et matières premières ; monétaire), ETF Amundi quand l'historique gratuit le permet, plus une poche de 15 à 50 actions | Q-1 |
| Données | Sources gratuites uniquement (yfinance, SEC EDGAR, FRED, BCE, RSS, GDELT) | Q-2 |
| Profils et ESG | Prudent, équilibré, dynamique ; exclusions normatives : armes controversées, tabac, charbon thermique | Q-3 |
| LLM | Niveaux gratuits externes pour le prototype ; modèle hébergé en interne visé en production | Q-4 |
| Horizon et rééquilibrage | Horizon de 3 à 5 ans ; revue mensuelle plus déclencheurs | Q-5 |
| Benchmark | 60 % actions monde / 40 % obligations, décliné par profil | Q-6 |

Les valeurs chiffrées (volatilité cible, bornes, δ, coûts) seront proposées et justifiées en phase 1.

## D-008 — Modèles LLM retenus (2026-10-02)

- **Options :** celles du plan à 0 € (section 2 du prompt), confrontées aux tests de connexion du 2026-10-02 (voir D-004).
- **Choix**, déclaré dans `config/llm.yaml` et jamais dans le code :

| Rôle | Modèle (identifiant LiteLLM) |
| --- | --- |
| Moteur principal, tous les agents (coordinateur et Fundamental compris) | `gemini/gemini-flash-latest` |
| Tâches simples (résumés de news, extraction) | `gemini/gemini-flash-lite-latest` |
| Relais sur erreur 429 | `groq/openai/gpt-oss-120b` |
| Développement et tests | `ollama/llama3.1:8b` |

- **Justification :** Gemini Pro est indisponible au niveau gratuit (erreur 429 dès le premier appel) ; le prompt prévoit alors Flash pour le coordinateur et Fundamental. `llama-3.3-70b-versatile` n'est plus proposé par Groq ; `openai/gpt-oss-120b` est le plus gros modèle disponible qui répond. Validé par Younes le 2026-10-02.
- **Limite :** les alias `*-latest` peuvent changer de version sous-jacente. Chaque exécution doit donc enregistrer la version réellement servie (C7, phase 3).
- **Dépendance ajoutée :** PyYAML, pour lire `config/` (D-006).

---

Décisions D-009 à D-027 : phase 1 (L1 v1.1). Toutes les valeurs chiffrées sont des **hypothèses de conception (H)**, détaillées et justifiées dans `docs/L1_specifications.md`. Elles seront figées par le pré-enregistrement (D-027) avant toute évaluation. Les relectures (`reviewer-tester`, `financial-critic`) ont conduit à réviser D-014 et D-017 à D-020.

## D-009 — Cadre d'orchestration (2026-10-02)

- **Options :** LangGraph ; AutoGen AgentChat (cadre du papier) ; boucle Python sans cadre.
- **Choix :** LangGraph, utilisé comme simple ordonnanceur ; tous les appels LLM passent par `LLMClient`.
- **Justification :** LangGraph l'emporte sur les trois critères du prompt (L1 §13) :
  - contrôle des boucles : arêtes conditionnelles décidées par notre code ;
  - traçabilité : état typé et points de reprise ;
  - multi-fournisseurs : il appelle directement notre `LLMClient`.
  AutoGen est en mode maintenance : `autogen-agentchat` 0.7.5 date du 2025-09-30, et son README renvoie vers Microsoft Agent Framework (vérifié sur PyPI et GitHub le 2026-10-02 ; `langgraph` 1.2.12 du 2026-09-21). C'est un écart avec le papier, justifié. La dépendance sera ajoutée en phase 3 (D-006).

## D-010 — Modèles de données partagés (2026-10-02)

- **Options :** schémas dans `agents/` ; module partagé.
- **Choix :** `src/amundi_agentic/schemas.py` et `cli.py`, en ajout à la structure de la section 5.2.
- **Justification :** éviter que `portfolio/` dépende de `agents/`. Le test `test_dependances_entre_modules` contrôle ces dépendances.

## D-011 — Devise de référence et séries (2026-10-02)

- **Options :** univers en USD ; univers en EUR avec proxys USD partout ; univers en EUR avec des règles par classe.
- **Choix :**
  - devise de référence : EUR ;
  - ETF Amundi quand ils ont 5 ans d'historique ;
  - proxys USD convertis au cours BCE seulement pour les actions, l'or et les matières premières ;
  - obligations et monétaire : séries en EUR (€STR ou EONIA capitalisé, courbes BCE, indices ICE BofA Euro sur FRED, à vérifier en phase 2), sinon début du backtest retardé ;
  - dates de jonction publiées.
- **Justification :** un proxy USD de taux introduit un autre marché et le risque de change, qui domineraient ces classes défensives (`financial-critic`). Question Q-9.

## D-012 — Une seule construction Black-Litterman (2026-10-02)

- **Options :** une construction sur l'univers joint (ETF et titres) ; deux optimisations emboîtées.
- **Choix :** une seule construction sur l'univers joint ; le monétaire est l'actif résiduel, hors des vues et hors de Σ.
- **Justification :**
  - c'est l'architecture cible du prompt ;
  - elle capte la covariance entre la poche titres et l'ETF S&P 500 ;
  - la volatilité quasi nulle du monétaire ferait exploser les écarts de poids.

## D-013 — Estimation de Σ (2026-10-02)

- **Options :** rendements quotidiens ou hebdomadaires ; cible de Ledoit-Wolf identité, corrélation constante ou par blocs ; Σ ou Σ+M dans l'optimiseur.
- **Choix :**
  - rendements hebdomadaires en EUR sur 5 ans (260 semaines communes) ;
  - Ledoit-Wolf vers l'identité (Ledoit et Wolf, 2004) ;
  - Σ EWMA (demi-vie de 13 semaines) pour le plafond de volatilité ;
  - Σ et non Σ+M, ce qui est documenté comme une limite.
- **Justification :**
  - les places ferment à des heures différentes, ce qui fausse les corrélations quotidiennes ;
  - la corrélation constante ne convient pas à un univers multi-classes ;
  - avec Σ, le portefeuille sans vue redonne exactement le benchmark.
- **Conséquence :** τ = 0,05 n'influence pas les poids (démontré en L1 §7.5) ; aucune sensibilité à τ n'est testée.

## D-014 — Des niveaux de décision aux rendements attendus Q (2026-10-02, révisée après relecture)

- **Options :** montant fixe en points de base par niveau ; κσ avec κ fixe (v1.0) ; κ calibré sur le budget de tracking error.
- **Choix :**
  - Q = Π + n·κ(t)·σ_i, avec n ∈ {−2, −1, +1, +2} ; une vue neutre n'est pas transmise ;
  - κ(t) = TE_max·SR*/(c_max·σ_b(t)·√N) avec N = 9 ;
  - plancher σ_i ≥ 0,02 ;
  - κ_t propre à la poche titres ;
  - Q en décimal partout.
- **Justification :** avec un κ fixe, chaque vue consommait la même tracking error. La TE maximale était saturée dès une ou deux vues, et la poche titres revenait à une équipondération (`financial-critic`). Deux tests vérifient la monotonie de la confiance, avec la TE active et inactive.

## D-015 — Du consensus à la confiance (2026-10-02)

- **Choix :**
  - c = clip(c_max·A·g·ρ·h), avec c_max = 0,8 ;
  - Ω par la forme fermée d'Idzorek ;
  - la confiance que chaque agent s'attribue est journalisée, mais n'entre pas dans le calcul ;
  - les alertes de risque (h) sont calculées par seuils Python (`tools/risk.py`), jamais par le LLM.
- **Justification :** le prompt demande que la confiance croisse avec la force du consensus. Comme les agents partagent un même LLM, leur unanimité est une information faible. Son apport est donc mesuré par l'ablation « confiance constante », le score de Brier et le taux d'unanimité au tour 0, avant et après la date de fin d'entraînement.

## D-016 — Règles du débat (2026-10-02)

- **Choix :**
  - au plus 2 tours de débat (R_max = 2, plafond du prompt pour le budget) ;
  - consensus calculé en Python ;
  - une vue contestée est bornée à ±1 ;
  - avocat du diable tournant, dont le vote compte ;
  - un débat par date pour l'allocation, un débat par titre.

## D-017 — Contraintes de l'optimiseur (2026-10-02, révisée)

- **Choix :**
  - contraintes CT-01 à CT-10 (L1 §7.6), dont deux ajouts :
    - CT-08 : tracking error maximale ;
    - CT-07 : plafond de volatilité = max(σ_cible, σ_b court terme) ;
  - score ESG du portefeuille au moins égal à celui du benchmark ;
  - ordre de relâchement : rotation, puis TE, puis volatilité ; l'ESG n'est jamais relâché ;
  - fréquence d'activation de chaque contrainte publiée.
- **Justification :**
  - le benchmark doit rester admissible, ce qui garantit le retour au benchmark sans vue ;
  - la TE matérialise le budget de risque actif ;
  - le texte de L1 explique ce que l'admissibilité garantit, et ce qu'elle ne garantit pas.

## D-018 — Méthodes de comparaison (2026-10-02)

- **Options :** chaque méthode avec ses propres règles ; toutes sous les mêmes contraintes.
- **Choix :**
  - toutes les méthodes projetées sur CT-01 à CT-10, avec une variante au même risque ex ante ;
  - Markowitz : μ = Q si l'actif a une vue, Π sinon ;
  - 1/N et parité de risque calculées sur les classes d'actifs.
- **Justification :** une comparaison à contraintes ou à risque différents rendrait toute conclusion « BL > X » indéfendable (`financial-critic`).

## D-019 — Profils clients (2026-10-02, H)

| Profil | Benchmark actions/obligations | Volatilité plafond | TE max | Rotation max mensuelle | Plafond par titre |
| --- | --- | --- | --- | --- | --- |
| Prudent | 30/70 | 7 % | 2 % | 5 % | 1 % |
| Équilibré | 60/40 | 11 % | 3 % | 7,5 % | 2 % |
| Dynamique | 80/20 | 16 % | 4 % | 10 % | 3 % |

- **Paramètres communs :**
  - δ = SR*/σ_b avec SR* = 0,35 ;
  - part obligataire répartie 50/50 entre souverain et crédit IG ;
  - bornes par classe : L1 §8.3 ;
  - la poche titres compte dans la zone États-Unis.
- **Justification :** ordres de grandeur détaillés en L1 §8. Aucune de ces valeurs n'est recalée sur l'échantillon. Questions Q-6 et Q-11.

## D-020 — Rééquilibrage (2026-10-02, révisée, H)

- **Choix :**
  - revue au premier jour ouvré du mois ;
  - déclencheur de dérive selon la règle 5/25, la partie relative ne s'appliquant qu'aux poids cibles d'au moins 4 % ;
  - déclencheur sur un changement de vue d'au moins 2 crans ;
  - déclencheur sur le régime de volatilité (centiles 80/50 sur 156 semaines) ;
  - exécution à la clôture de t, avec une variante à t+1 ;
  - coûts de 2 à 25 points de base selon la classe, plus 2 points de base de change ;
  - robustesse testée à ×2, scénario de stress à ×3 ;
  - retenue à la source documentée.
- **Question :** Q-10.

## D-021 — Réplication AlphaAgents (2026-10-02)

- **Choix :**
  - pool de titres tech américains daté de janvier 2024 ;
  - Zscaler (seul titre nommé par le papier) plus 14 titres tirés au hasard ;
  - hash de la graine consigné avant le tirage ;
  - règle de remplacement fixée à l'avance.
- **Justification :** le papier ne nomme pas ses 15 titres (vérifié dans le PDF). Les résultats sont étiquetés « contaminés » (antérieurs à la fin d'entraînement des modèles), et la comparaison au papier reste qualitative.

## D-022 — ESG des ETF (2026-10-02)

- **Choix :** les exclusions et le score d'un ETF découlent de la méthodologie de son indice ; on préfère les variantes ESG ou PAB.
- **Justification :** aucune source gratuite ne donne le contenu des ETF de façon historisée. La limite est documentée (Q-14).

## D-023 — Point-in-time par source (2026-10-02)

- **Choix :**
  - coupure à t 00:00, heure de Paris ;
  - macro : millésimes ALFRED ;
  - rapports : date d'acceptation EDGAR, convertie de l'heure de New York en UTC (**remplacé par D-031** : le champ de l'API est lu comme UTC brut, règle prudente) ;
  - XBRL : pour chaque fait, la valeur du dernier dépôt avec `filed < t` ;
  - pas de fondamentaux yfinance en backtest ;
  - score ESG non daté réservé au live test ;
  - agent Sentiment retiré du backtest sous un seuil de couverture des news mesuré en phase 2 (**remplacé par D-044** : retrait sans condition de seuil).

## D-024 — Modes d'exécution LLM (2026-10-02, complète D-008)

- **Choix :**
  - mode **interactif** : relais Gemini → Groq sur erreur 429 ;
  - mode **évaluation** : un seul modèle par run, aucun relais, pause sur 429 puis reprise depuis le cache, arrêt si `modele_servi` change.
- **Justification :** mélanger des modèles dans une série d'évaluation casserait son homogénéité et le contrôle du look-ahead bias (`financial-critic`).
- **Validé par Younes le 2026-10-02 :** en mode évaluation, identifiant de modèle à version figée plutôt que l'alias `*-latest` de D-008. Déclaré dans `config/llm.yaml` (section `evaluation`) :
  - `gemini/gemini-3.8-flash` (principal) et `gemini/gemini-3.5-flash-lite` (tâches simples) ;
  - `gemini-flash-lite-latest` se résout bien en `gemini-3.5-flash-lite` (champ `modelVersion` de l'API, 2026-10-02) ;
  - `gemini-flash-latest` renvoyait une erreur 503 ce jour-là : on ignore vers quelle version il pointe, d'où le choix de la version la plus récente qui répond.
  - Le service Gemini gratuit est instable (erreurs 503 intermittentes sur plusieurs modèles) : la phase 3 devra gérer les erreurs 503 en plus des 429.
  - Reste à faire avant le pré-enregistrement : relever la date de fin d'entraînement de ces versions (D-025).

## D-025 — Objet de L4 et niveau de preuve (2026-10-02)

- **Choix :**
  - L4 évalue la mécanique, le contrôle du risque, les coûts et l'explicabilité ; il ne cherche pas à prouver un alpha ;
  - effet minimal détectable publié (IR_min ≈ 2,8/√T) ;
  - aucune conclusion de performance avant la date de fin d'entraînement du modèle ; les résultats antérieurs sont étiquetés « contaminés » ;
  - liste fermée de 9 tests principaux, avec correction de Holm ;
  - bootstrap stationnaire (Politis et Romano, 1994) ;
  - exécutions répétées avec paraphrase des prompts et température 0,7.
- **Justification :** avec 1,5 an hors échantillon, seul un ratio d'information supérieur à environ 2 serait détectable. Annoncer un alpha serait indéfendable. Question Q-13.

## D-026 — Protocole d'anonymisation (2026-10-02)

- **Choix :** protocole complet en L1 §11.5 :
  - agent Valuation seulement, prix rebasés à 100, noms masqués, dates relatives ;
  - deux indicateurs (taux d'accord, écart de taux de réussite), comparés en différence de différences avant et après la date de fin d'entraînement ;
  - sondage direct de la mémoire du modèle ;
  - échantillon fixé à l'avance (H).

## D-027 — Pré-enregistrement (2026-10-02)

- **Choix :**
  - avant le premier run d'évaluation, on hashe paramètres, graines, prompts et paraphrases, tests principaux, plan réduit et échantillon d'anonymisation (`runs/preregistration/`) ;
  - le hash est consigné ici ;
  - un run dont la configuration ne correspond pas au hash est refusé ;
  - aucun réglage sur la période hors échantillon ni sur le live test ;
  - toutes les sensibilités sont rapportées.
- **Justification :** éviter le surapprentissage et le rapport sélectif (`financial-critic`).

## D-028 — Arborescence des tests (2026-10-02)

- **Options :** un `__init__.py` dans chaque sous-dossier de tests ; `--import-mode=importlib` ; tests à plat.
- **Choix :** `--import-mode=importlib` dans `addopts` de `pyproject.toml` (validé par Younes).
- **Justification :** autorise des sous-dossiers de tests (`tests/data/`, `tests/portfolio/`…) avec des noms de fichiers identiques, sans `__init__.py`.

## D-029 — Plan réduit de budget d'appels LLM (2026-10-02, H)

- **Choix**, validé par Younes et pré-enregistré avec D-027 :
  - **Poche titres limitée à environ 15 titres**, en particulier pour la réplication AlphaAgents (15 actions tech). L1 prévoyait 15 à 50 titres : la borne haute est abandonnée.
  - **Décisions trimestrielles sur l'historique long**, mensuelles sur la période récente (levier prévu par la section 2 du prompt).
  - Les autres leviers du prompt restent disponibles : un appel par classe d'actifs plutôt que par actif, 2 tours de débat au maximum.
- **Justification et correction (2026-10-02, relevée par l'`architect`) :** la poche titres consomme environ 94 % des appels (225 sur 239 par date et par profil). **Le chiffre de 239 était déjà calculé avec 15 titres** : limiter la poche à 15 titres est donc conforme au plan de L1 mais **ne réduit pas ce budget**. Ma première rédaction (« passer de 50 à 15 titres divise cette part environ par 3,3 ») était exacte seulement par rapport à la borne haute de 50 titres abandonnée (764 appels contre 239). Le vrai levier d'économie est la **cadence** :
  - formule : N_main(S) = 14 + 15·S, avec les paramètres de L1 §11.2 ;
  - en trimestriel : 4 × 239 = 956 appels par an d'historique long ; en mensuel : 12 × 239 = 2 868.
- **Mise à jour (D-044, L1 v1.3) :** l'agent Sentiment étant retiré du backtest, le budget d'appels du backtest est N_main = 11 + 12·S, soit **191 appels** par date et par profil pour S = 15 (calcul, paramètres de L1 §11.2) ; le chiffre de 239 reste celui du live, Sentiment inclus. En trimestriel : 4 × 191 = 764 appels par an d'historique long ; en mensuel : 12 × 191 = 2 292.
- **Conséquences :** les plafonds par titre de D-019 (1, 2 et 3 %) sont à revoir en phase 4 (D-040). L1 répercute D-029. Q-16 reste ouverte.

---

Décisions D-030 à D-038 : phase 2 (couche de données). Les chiffres cités sortent de `docs/couverture_donnees.md` (généré par script, recalculé de façon indépendante par le `reviewer-tester` : aucun écart sur 15 valeurs).

## D-030 — Stockage, cache et reprise (2026-10-02)

- **Options :** Parquet (pyarrow) ; DuckDB.
- **Choix :** Parquet, un fichier par jeu de données dans `.cache/data/store`, écritures atomiques ; cache HTTP disque permanent, clé de cache sans secret, dans `.cache/data/http` ; points de reprise par jour et par élément ; journal d'événements.
- **Justification :** aucune jointure SQL n'est nécessaire à ce volume ; pas de serveur ni de dépendance supplémentaire ; fichiers inspectables. Les données téléchargées (environ 850 Mo) restent hors de Git.
- **Dépendances ajoutées (D-006) :** pandas 3.0.6 (traitement tabulaire), pyarrow 25 (Parquet), requests (client HTTP avec User-Agent, TLS, `Retry-After`), yfinance 1.7.0 (prix), feedparser (flux RSS mal formés).

## D-031 — Accès point-in-time, précisions de D-023 (2026-10-02, révisée après revue)

- **Règles :** coupure à t 00:00, heure de Paris ; une donnée disponible exactement à t est exclue.
  - **Prix :** séances strictement antérieures à t ; splits et dividendes pris en compte seulement s'ils sont connus à t.
  - **Macro FRED :** `realtime_start` < t (millésimes ALFRED). Pour les séries de marché sans millésimes (DGS10, VIX…), disponibilité = date + **1 jour ouvré** (H).
  - **Macro BCE :** fin de période + délai (H).
  - **XBRL :** `filed` < t, départage chronologique.
  - **News :** date de publication ; pour GDELT, `seendate` (instant de première observation, étiquetée comme telle).
  - **ESG :** instantané daté par collecte ; servi en mode strict seulement après sa date, sinon en mode `non_pit` marqué.
- **Dépôts EDGAR, horodatage (constat du `reviewer-tester`, qui corrige celui du `data-engineer`) :** le champ `acceptanceDateTime` de l'API `submissions` est suffixé « Z » mais n'est pas toujours un UTC. Comparé à l'en-tête SGML et à la page d'index, il vaut :
  - un vrai UTC pour MSFT et NVDA ;
  - un UTC en retard de 4 h supplémentaires pour AAPL ;
  - un écart variable d'un dépôt à l'autre pour JPM.
  La « correction » de 4 à 5 h servait donc certains dépôts avant leur acceptation : une fuite de futur, touchant 22 % des dépôts du stockage.
- **Choix :** lire la valeur brute comme UTC (`raw_as_utc`), jamais antérieure à l'instant réel dans les trois régimes observés. C'est la règle prudente : un dépôt peut être servi quelques heures trop tard, jamais trop tôt. **Cela remplace le littéral de D-023** (« heure de New York convertie en UTC »).
- **Limite :** les prix servis sont ceux du dernier téléchargement, ajustés des seuls splits et dividendes connus à t. Une correction rétroactive de Yahoo ne se voit pas (limite connue de yfinance).

## D-032 — Contrôle qualité (2026-10-02)

- **Choix :** on signale, on ne corrige et on n'interpole jamais. Seuils (H) dans `config/data.yaml` : trou de plus de 5 jours ouvrés, rendement aberrant au-delà de 25 %, saut au-delà de 40 %, 5 clôtures identiques, 260 semaines d'historique.
- **Constat :** les 4 « splits suspectés » (AAPL 2000-09-29, AMD 2016-04-22, NVDA 2000-03-07, ORCL 1992-12-23) sont de vrais mouvements de cours accompagnés d'un pic de volume. Le contrôle est reclassé en avertissement avec un test de volume.

## D-033 — Licences et limites d'usage (2026-10-02, vérifiées par `config/data.yaml`)

| Source | Licence et limites | Observations du 2026-10-02 |
| --- | --- | --- |
| yfinance | Bibliothèque non officielle sur des endpoints Yahoo ; usage personnel et recherche, pas de redistribution, aucun SLA | Endpoint ESG mort (404). Pause de 1,5 s entre tickers |
| FRED et ALFRED | Clé gratuite, 120 requêtes/min ; séries ICE sous licence tierce, limitées à 3 ans glissants, sans redistribution | Plafond de 2000 millésimes par requête |
| BCE (data-api) | Réutilisation libre avec mention de la source | Pas de millésimes |
| SEC EDGAR | Domaine public ; User-Agent déclaré obligatoire ; 10 requêtes/s au plus (6 configurées) | Liste ticker→CIK courante, donc biais du survivant |
| GDELT | Usage libre avec citation ; 1 requête / 5 s demandée | 429 persistants malgré 11 s entre requêtes |
| RSS (Fed, BCE, SEC) | Sources institutionnelles, usage de recherche | Aucun historique avant la première collecte (2026-08-13) |
| Wikipédia (pool de titres) | CC BY-SA 4.0 | Révision datée 1197645693 (2024-01-21) |

Pour le plan de déploiement (L6) : en production, Amundi aurait ses propres sources sous licence ; ces sources gratuites sont réservées au prototype.

## D-034 — Séries en euros et date de début du backtest (2026-10-02) — **corrige L1 §9.1 et D-011**

- **Constat :**
  - les indices ICE BofA Euro n'existent pas sur FRED en rendement total long : seul l'Euro High Yield existe, depuis 2023-10-02 seulement (fenêtre glissante de 3 ans imposée par la licence) ; l'Euro Corporate et l'Euro Government n'existent pas ;
  - monétaire capitalisé : EONIA (1999-01-04 à 2021-12-31, clé BCE `EON/D.EONIA_TO.RATE`) puis €STR (depuis 2019-10-01), faisable depuis 2003-12 avec 260 semaines ;
  - courbes zéro-coupon AAA zone euro (BCE) depuis 2004-09-06 : ce sont des taux, pas un rendement total, et leur reconstruction n'est pas faite.
- **Choix :** les séries de rendement total sont les ETF eux-mêmes, plus le monétaire capitalisé EONIA puis €STR. Aucun indice ICE n'est utilisé. Reconstruire un rendement total obligataire à partir de la courbe BCE est écarté pour l'instant : on ne l'invente pas.
- **Date de début du backtest** (260 semaines d'historique avant t, mesuré par script) :
  - **2018-08-28** avec le haut rendement (AHYE.PA, seul historique réel en euros) ;
  - **2014-03-27** sans la classe haut rendement (limite : crédit IG, CRP.PA ; puis souverain 2013-12-27) ;
  - **2024-05-16** si l'on exige des ETF primaires sans proxy (limite : GOLD.PA).
- **Question ouverte :** garder le haut rendement (début 2018-08, période hors échantillon plus courte) ou en faire un actif optionnel (début 2014-03). Je recommande de décider en phase 4, avec les profils. Q-15 et Q-19.

## D-035 — ESG : aucun score gratuit exploitable (2026-10-02) — **corrige L1 §9.4, R-04 et D-022**

- **Constat :** couverture des scores ESG : **0 % des 28 actifs** (l'endpoint `sustainability` de yfinance renvoie 404). Une règle d'exclusion est applicable à 16 actifs sur 28 (57 %), ce qui **n'est pas une couverture** : aucune exclusion n'est déterminée par une donnée (matrice actif × critère du rapport : armes controversées 0 déterminé / 1 supposé / 27 inconnu ; tabac 0 / 16 / 12 ; charbon thermique 0 / 16 / 12) :
  - titres : 15 sur 15 par code SIC EDGAR (proxy, pas une mesure de chiffre d'affaires) ; aucune exclusion détectée sur ce pool tech ;
  - ETF : 1 sur 13 (CRP.PA, indice « Paris Aligned » déduit du nom Yahoo, non vérifié au prospectus) ; AHYE.PA (indice ESG) marqué « contenu inconnu ».
- **Choix :** l'ESG du prototype repose sur les exclusions normatives (SIC et méthodologie d'indice), jamais sur un score. **La contrainte CT-06 (score ESG minimal) n'est pas alimentée** et est documentée comme telle, sans masquer la limite (section 2 du prompt).
- **Conséquence :** la contrainte « score au moins égal à celui du benchmark » de D-017 est suspendue tant qu'aucune source n'existe. Q-12, Q-14 et Q-19.

## D-036 — News et sentiment en backtest (2026-10-02)

- **Constat :**
  - les flux RSS ne donnent que les articles récents (15 à 25 par flux) et n'ont aucun historique avant la première collecte ;
  - GDELT DOC accepte des fenêtres explicites jusqu'à 2019-11 au moins (« Invalid query start date » pour 2016-11) : l'hypothèse de L1 (« environ 3 mois ») est vraie du défaut, pas des fenêtres explicites ;
  - GDELT donne la date de première observation (`seendate`), pas la date de publication ; débit très limité (429) ;
  - couverture hebdomadaire mesurée sur 4 titres seulement (8 semaines récentes) : 6/6 à 7/7 semaines avec au moins un article.
- **Choix :** le seuil de couverture qui conditionne le retrait de l'agent Sentiment (D-023) se calculera sur des sondages hebdomadaires pour chaque titre et chaque semaine, pas sur les 100 derniers articles. Si le sondage complet coûte trop d'heures au rythme de GDELT, l'agent Sentiment est retiré du backtest et conservé en live (EX-O1-17). Seuil à fixer au pré-enregistrement (D-027).

## D-037 — Poche titres et pool de réplication (2026-10-02)

- **Constat :** pool daté (révision Wikipédia du 2024-01-21, S&P 500, secteur IT) : 64 titres, dont 62 utilisables (dépôt EDGAR accepté avant 2024-02-01 et prix en janvier 2024). ANSS et JNPR sont absents de Yahoo et d'EDGAR (sociétés rachetées : biais du survivant). **ZS n'est pas dans le pool** : il est ajouté hors pool, comme L1 le prévoit.
- **Choix :** le connecteur accepte n'importe quelle liste de tickers ; la liste de 15 titres de `config/universe.yaml` est une démonstration, pas le tirage de réplication (phase 3, D-021, D-029).
- **Limite (`reviewer-tester`) :** un pool de janvier 2024 sélectionne les titres avec la connaissance de 2024. Utilisé pour un backtest démarrant en 2018, il ajoute un biais du survivant plus fort que les deux seuls titres radiés. À contrôler en phase 7 ; les résultats de la réplication sont déjà étiquetés « contaminés » (D-025).

## D-038 — Prix : date de séance et cours ajustés (2026-10-02)

- **Choix :** un prix servi à t est la clôture d'une séance strictement antérieure à t. L1 écrit « clôtures jusqu'à t−1 » (§3.3), « dernier jour ouvré avant t » (§11.3) et « exécution à la clôture de t » (§10.1) : ces trois phrases se concilient ainsi (décision prise avec les données de t−1, exécution au cours de la clôture de t, qui n'est pas visible au moment de la décision). L1 sera clarifié.
- **ETF retenus (proposition, non figée) :** les ETF primaires de L1 §9.1 (500.PA, MEU.PA, JPN.PA, AEEM.PA, MTD.PA, CRP.PA, AHYE.PA, GOLD.PA, COMO.PA, C3M.PA), avec CW8.PA en contrôle ; EGOV.PA et CSH2.PA en alternatives (CSH2.PA a trop peu d'historique). GOLD.PA est étiqueté USD par Yahoo ; la configuration le traite en EUR (cotation à Paris, corrélation des écarts de rendement avec GOLD/GLD et EUR/USD compatible), à confirmer au prospectus (Q-20).

## D-039 — Cadence : allocation mensuelle, poche titres trimestrielle sur l'historique long (2026-10-03, décision de Younes) — **remplace la version du 2026-10-02**

- **Choix :**
  - **allocation (ETF) : décisions mensuelles sur tout l'historique** ;
  - **poche titres : cadence trimestrielle sur l'historique long**, mensuelle sur la période récente ;
  - la frontière entre les deux est gelée au pré-enregistrement (H : au plus tard à la date de fin d'entraînement du modèle, pour que la période hors échantillon soit mensuelle pour les deux niveaux) ;
  - les déclencheurs de dérive et de régime de volatilité restent actifs entre deux dates ; le déclencheur de changement de vue n'est évalué qu'aux dates de décision de chaque niveau.
- **Justification :** la poche titres consomme la quasi-totalité des appels (D-029) ; l'allocation, peu coûteuse, garde la cadence mensuelle du prompt. Cela corrige ma lecture du 2026-10-02 (cadence trimestrielle aux deux niveaux), que Younes n'avait pas voulue.
- **Conséquence :** la fréquence de l'allocation étant plus élevée, la rotation mensuelle maximale de D-019 s'applique à l'allocation à chaque date, et à la poche titres à chaque date de décision de la poche. Budget d'appels à recalculer dans L1 §11.2 (allocation mensuelle sur tout l'historique, titres trimestriels avant la frontière).

## D-040 — Plafonds par titre à recalibrer (2026-10-02, H)

- **Choix :** les plafonds de D-019 (1, 2 et 3 %) sont provisoires. Avec 15 titres au plus, une poche de 5 à 15 % donne un poids moyen de 0,33 %, 0,67 % et 1 % (calcul, pas une mesure). Règle candidate : u = k·U_poche/15 avec k ≈ 2 (H), à fixer en phase 4 avant le pré-enregistrement ; κ_t suit u_titre par construction.

## D-041 — Début du backtest reporté en phase 4 (2026-10-02)

- **Choix :** décision entre 2018-08-28 (avec le haut rendement) et 2014-03-27 (sans) reportée en phase 4, puis gelée par le pré-enregistrement (EX-O2-13). La variante 2024-05-16 (sans proxy) est écartée : moins de 3 ans de données, incompatible avec EX-O3-07.
- **Remarque :** le choix du début n'allonge pas la période hors échantillon, qui ne dépend que de la date de fin d'entraînement ; il change la période « contaminée » (environ 4,4 ans de plus sans le haut rendement). Règle de jonction EONIA/€STR (chevauchement 2019-10-01 à 2021-12-31) à documenter en phase 4.

## D-042 — Source des chiffres de données (2026-10-02)

- **Choix :** `docs/couverture_donnees.md` (généré par script) est la source des chiffres de données de L1 ; aucune valeur n'y est recopiée sans renvoi. CT-06 reste suspendue (D-035).

---

Décisions D-043 à D-047 : suites de la revue du `financial-critic` sur la couche de données (verdict « acceptable avec réserves »).

## D-043 — Rejouabilité des données (2026-10-02)

- **Constat (`financial-critic`) :** le stockage écrasait les jeux de données lors d'un retraitement et ne gardait que le dernier `fetched_at`, sans manifeste ni hash. Une correction rétroactive de Yahoo était invisible, et L1 R-17 (« stockage horodaté par collecte ») était inexact pour les prix.
- **Choix :**
  - instantané brut append-only par date de collecte (`.cache/data/snapshots/`) ;
  - manifeste `data_manifest.json` à chaque exécution : SHA-256 des jeux de données, plages de dates, versions des bibliothèques, hash de la configuration ;
  - le hash du manifeste est lié au pré-enregistrement (D-027).
- **Limite assumée :** ce qui a été téléchargé avant la mise en place des instantanés n'est pas rejouable à l'identique. Les 191 instantanés actuels sont tous « reconstruits depuis le stockage le 2026-10-02 » : ils figent l'état courant, pas le brut reçu à l'origine (un retraitement Yahoo passé est déjà absorbé). La rejouabilité commence réellement à la prochaine collecte. Le cache HTTP permanent conserve en plus les réponses brutes déjà reçues de FRED, de la BCE, d'EDGAR, des flux RSS et de GDELT. Seules les collectes à partir de maintenant le seront. Le live test dépend de cet instantané quotidien.

## D-044 — Agent Sentiment hors backtest (2026-10-02) — **précise D-036**

- **Constat :** RSS sans historique ; GDELT limité par des 429 persistants (8 titres sur 15 sans article). Le sondage hebdomadaire par titre sur tout l'historique n'est pas réaliste, et un seuil « au moins 1 article par semaine » est trivial pour une grande capitalisation.
- **Choix :** l'agent Sentiment est **retiré du backtest**, sans condition de seuil. On perd toute évaluation chiffrée de son apport historique, et L4 le dit.
- **Évaluation en live :** portefeuille « avec » et « sans » Sentiment exécutés en parallèle (ombre) dès le premier jour ; instantané quotidien brut des flux RSS et GDELT ; corrélation de rang entre sentiment et rendement à 1 semaine, avec intervalle et mention de la puissance (moins de 400 observations après 6 mois). La différence live n'est pas présentée comme un gain.

## D-045 — Règle de début du backtest (2026-10-02, H) — **précise D-041**

- **Constat :** reporter le choix du début « avec les profils » (phase 4) l'exposait à un choix après avoir vu des résultats. La fenêtre 2018-08-28 contient 4 creux de 500.PA (EUR, ETF capitalisant) d'au moins 15 % (2018-T4 −15,8 %, 2020 −33,7 %, 2022 −17,1 % avec une hausse du DGS10 de 162 points de base, 2025 −23,3 %) ; 2014-03-27 en ajoute deux (2015 −17,2 % et 2015-16 −18,4 %), dont un seul avec hausse des taux faible (+10 points de base). Source : tableau « Creux » de `docs/couverture_donnees.md`, généré par script (seuil de 15 % : H). Le second creux de 2022 (environ −15 %) cité par le `financial-critic` n'apparaît pas dans le script : un seul épisode de 2022, récupéré le 2022-08-16.
- **Choix :** règle fondée uniquement sur la disponibilité des données, fixée avant tout run LLM :
  - **début principal : 2018-08-28**, avec la classe haut rendement ;
  - **sensibilité obligatoire : 2014-03-27**, haut rendement exclu et poids renormalisés, toujours rapportée ; le meilleur des deux n'est jamais choisi après coup ;
  - critère minimal : au moins 2 creux du benchmark d'au moins 15 % et au moins une phase de hausse des taux.
- **Validée par Younes le 2026-10-03, avec deux compléments :**
  - **la classe haut rendement est conservée** dans le cas principal ;
  - **toute période de performance construite sur des séries synthétiques (proxys raccordés avant l'ETF primaire, par exemple l'or avant 2019-05-23, ou toute classe avec proxy USD converti) porte l'étiquette « non investissable »** dans les tableaux, graphiques et textes de L4 et de l'interface. Les périodes sur séries d'ETF réels ne la portent pas.

## D-046 — Points de la couche de données reportés (2026-10-02)

| Point (revue du critique) | Phase | Gravité |
| --- | --- | --- |
| Règle de raccord des séries proxy (or avant 2024-05 : GLD converti raccordé à GOLD.PA, raccord sur rendements, chevauchement et erreur de suivi publiés ; P&L sur proxy étiqueté « non investissable ») | 4 | Bloquante pour L4 |
| Fenêtre de Σ de la poche titres (ZS n'a 260 semaines qu'en 2023-03) : fenêtre minimale avec shrinkage, ou titres exclus de Σ avant éligibilité | 4 | Bloquante pour la poche titres |
| Cash de référence (€STR) distinct de l'actif détenu (C3M.PA, rendements négatifs 2015-2022) ; jonction EONIA/€STR (EONIA = €STR + 8,5 pb) | 4 | Non bloquante |
| Benchmark et portefeuille construits sur les mêmes séries raccordées | 4 | Importante |
| Biais du survivant du pool 2024 : pool reconstruit à chaque date (révisions Wikipédia), mesure du biais, étiquette « contaminé » avant 2024-02 | 7 | Importante |
| Fuites implicites : SIC courant, noms courants dans les requêtes GDELT, indice courant des ETF ; anonymisation à étendre aux noms et indices cités | 3, 7 | Importante |
| IR_min avec correction de Holm (environ 3,6/√T, 30 % de plus que 2,8/√T) et bootstrap en blocs | L1, 7 | Non bloquante |
| Cadence trimestrielle/mensuelle confondue avec la frontière de contamination dans le test d'anonymisation : même cadence des deux côtés | L1, 7 | Importante |
| Date de fin d'entraînement des modèles à relever (la fraction contaminée de 2018-08 à 2026-09, soit 8,1 ans, n'est pas calculable : de 6,4 ans si 2025-01 à 6,9 ans si 2025-06 selon les scénarios du critique) | 3, avant le pré-enregistrement | Bloquante pour le pré-enregistrement |
| ETF dont l'indice a changé (CRP.PA « Climate Paris Aligned », AHYE.PA « ESG ») : prospectus et dates de changement | 2 (doc), L1 | Importante |
| Liquidité et coûts : AHYE.PA et C3M.PA peu liquides ; plafond de participation au volume | 4, 7 | Importante |
| Seconde source gratuite de contrôle des prix et règle d'arrêt en cas de panne de yfinance pendant le live test | 9 (L6) | Importante |
| `manifest.py` : `fetched_at` des jeux dérivés vient du journal d'événements ; relancer un téléchargement sans changement de données peut changer `manifest_sha256`. Exclure `fetched_at` du contenu haché ou le tirer des instantanés avant de lier le hash au pré-enregistrement | 3, avant D-027 | Importante |
| `store.snapshot` : une collecte identique à un instantané « reconstruit » du même jour reste étiquetée « reconstruit » ; `_origin.json` réécrit en place, non atomique entre processus | 3 | Non bloquante |
| Jours fériés fédéraux (Columbus, Veterans) : FRED est vide à ces dates dans le stockage, sauf le vendredi 2023-11-10 (Veterans observé) : le calendrier retarde alors d'une séance (prudent, pas de fuite) ; à vérifier avec le réseau | 7 | Non bloquante |

## D-047 — Vérité des chiffres de données (2026-10-02)

- **Choix :** tout chiffre de données cité dans `DECISIONS.md` ou L1 renvoie à un script ou est marqué (H) ou « calcul ». Les valeurs non rejouables ont été retirées ou sont étiquetées comme constat d'un relecteur (`reviewer-tester` pour les 22 % de dépôts EDGAR ré-indexés, `financial-critic` pour les mesures de régimes et de liquidité).
- **Corrige :** l'argument « corrélation de −0,3 » pour GOLD.PA, non rejouable (le critique trouve −0,68 sur différences hebdomadaires). Il est remplacé par le contrôle croisé GOLD.PA / (GLD converti en euros) du rapport de couverture.

---

Décisions du 2026-10-03 (validation de la phase 2 par Younes).

## D-048 — Source ESG manuelle et historisée par ETF, en phase 3 (2026-10-03, décision de Younes) — **complète D-035 et D-022**

- **Constat :** aucun score ESG gratuit exploitable (0 sur 28 actifs) ; les exclusions des ETF sont déduites du nom Yahoo ou de l'indice, sans vérification (matrice ESG : armes controversées 0 déterminé / 1 supposé / 27 inconnu).
- **Choix :** ajouter en phase 3 une **source ESG manuelle et historisée par ETF**, alimentée à la main depuis la documentation du fonds (prospectus, DIC/KID, fiche produit, page de l'indice) :
  - classification **SFDR (article 6, 8 ou 9)** ;
  - **indice suivi**, avec le caractère ESG, Paris-Aligned (PAB) ou Climate Transition (CTB) de l'indice ;
  - pour chaque valeur : **source (URL ou référence du document), date du document, date d'effet, date de saisie**, et une version datée si la valeur change (historisation append-only, comme les instantanés de D-043) ;
  - une valeur sans document n'est **pas saisie** : elle reste `inconnu` (aucune valeur déduite d'un nom ou d'une habitude).
- **Usage :** alimente la matrice ESG du rapport de couverture (états `determine_par_donnee` quand un document le prouve) et l'agent ESG ; sert à étudier une contrainte d'allocation sur la part d'ETF article 8 ou 9 (à proposer en phase 4, pas décidée ici). Point-in-time : une valeur n'est servie qu'à partir de sa date d'effet connue.
- **Limites :** SFDR classe des produits, ce n'est pas un score ESG ; une classification article 8 n'implique pas l'exclusion des armes controversées. CT-06 reste suspendue (D-035) tant qu'aucun score n'existe. Q-14 et Q-26 restent ouvertes.

## D-049 — Règle sur les tests (2026-10-03, décision de Younes)

- **Choix :** aucun test ne peut être supprimé ou affaibli sans l'accord du `reviewer-tester` (règle ajoutée à `CLAUDE.md`). Un test qui devient faux parce que le code change est réécrit par le `reviewer-tester`.
- **Origine :** pendant la phase 2, le `data-engineer` a supprimé un test du `reviewer-tester` après une correction. Le test a été réécrit par son propriétaire.

## D-050 — Graphe de connaissances graphify (2026-10-03)

- **Choix :**
  - graphify 0.9.65 est installé (`uv tool`), avec `.graphifyignore` (secrets, `.cache/`, `data_store/`, `runs/`, environnements, `uv.lock`) ;
  - mise à jour en mode code seulement (`graphify update .`, hooks Git `post-commit` et `post-checkout`), **sans LLM** ; les hooks ont été lus : aucun appel de LLM ;
  - `graphify-out/` n'est modifié que par graphify (règle de `CLAUDE.md` reformulée) ;
  - versionnés : `graph.json`, `GRAPH_REPORT.md`, `manifest.json` ; ignorés : `graph.html`, `cache/`, `.graphify_*`.
- **Nommage des communautés :** uniquement avec Ollama en local (`llama3.1:8b`, `--missing-only`), jamais avec une API ; abandonné s'il exige une clé.


## D-051 — Organisation de la phase 3 (2026-10-03)

- **Choix :** première vague de 4 tâches indépendantes, chacune dans son worktree Git (règle 1 de `CLAUDE.md`) :
  1. socle LLM (`schemas.py`, `LLMClient`, mock, cache, relais, mode évaluation) : `agents-engineer` ;
  2. outils de calcul financier (`tools/`) : **`quant`**, et non `agents-engineer` : ce sont des formules financières à tester contre des valeurs calculées à la main ; l'écart avec le tableau de `CLAUDE.md` est volontaire ;
  3. source ESG manuelle par ETF (D-048) : `data-engineer` ;
  4. relevé des quotas, des dates de fin d'entraînement et des conditions d'usage des niveaux gratuits : agent de recherche en lecture seule.
- **Suite prévue :** RAG et résumé avec réflexion ; agents, prompts, coordinateur et débat ; réplication AlphaAgents (15 actions tech, 1er février 2024) ; puis extension multi-actifs. Chaque branche passe par le `reviewer-tester` avant fusion, puis par le `financial-critic` pour les parties chiffrées.
- **CI :** `actions/checkout@v7`, `astral-sh/setup-uv@v10.2.0` (pas de tag de version majeure `v10`), runner `ubuntu-24.04` épinglé (le label `ubuntu-latest` migre vers Ubuntu 26 le 2026-10-19). Vérifié vert sur Python 3.11 et 3.12.

## D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)

Relevé fait par un agent de recherche le 2026-10-03, **à partir de pages officielles lues par un outil qui les résume** : les citations sont de seconde main et à revérifier à l'œil avant de figer le pré-enregistrement (D-027). « Non trouvé » signifie que rien n'a été trouvé, pas qu'il n'existe rien.

### Limites du niveau gratuit

| Fournisseur et modèle | Limites | Source et réserve |
| --- | --- | --- |
| Groq `openai/gpt-oss-120b` | 30 requêtes/min, 1 000 requêtes/jour, 8 000 tokens/min, 200 000 tokens/jour (niveau gratuit, par organisation) | https://console.groq.com/docs/rate-limits ; page sans date de mise à jour |
| Gemini (les 4 identifiants de `config/llm.yaml`) | **non trouvé** : la page officielle ne donne aucun chiffre ; les limites se lisent dans Google AI Studio, **page réservée aux comptes connectés** (https://aistudio.google.com/rate-limit). Limites par projet, « not guaranteed » | https://ai.google.dev/gemini-api/docs/rate-limits |

- **Action pour Younes :** relever dans l'AI Studio les limites (requêtes/min, tokens/min, requêtes/jour) de `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-flash-latest` et `gemini-flash-lite-latest`. Sans elles, la faisabilité du budget d'appels de L1 §11.2 (environ 9 060 appels par profil sur 8,1 ans) ne peut pas être tranchée.
- **Conséquence pour le relais Groq :** avec 8 000 tokens/min et 200 000 tokens/jour, le relais est inutilisable pour de longs prompts (extraits de rapports 10-K du RAG) et plafonné à quelques centaines d'appels par jour. Le relais sert aux appels courts seulement.

### Date de fin d'entraînement (borne de contamination de D-025)

| Modèle | Fin d'entraînement | Mise à disposition | Fiabilité |
| --- | --- | --- | --- |
| `gemini-3.8-flash` | **mars 2026 pour certains domaines, janvier 2025 pour d'autres** (la fiche ne dit pas quels domaines) | 2026-09-02 | carte du modèle DeepMind, lue |
| `gemini-3.5-flash-lite` | mars 2026 pour la plupart des domaines, janvier 2025 pour d'autres | 2026-07-21 | carte du modèle DeepMind, lue |
| `openai/gpt-oss-120b` | juin 2024 | août 2025 | **indirecte** : exemple du format Harmony dans la documentation officielle, pas la fiche du modèle |
| `llama3.1:8b` | décembre 2023 | 2024-07-23 | fiche de modèle de Meta, lue |

- **Alias `*-latest` :** `gemini-flash-latest` pointait vers `gemini-3.5-flash` depuis le 2026-05-19 (journal des modifications de l'API) ; on ignore s'il a été déplacé vers 3.8 depuis. La cible de `gemini-flash-lite-latest` n'est pas indiquée. Les alias sont donc à proscrire pour toute évaluation (déjà acté par D-024).
- **Conséquence sur la période hors échantillon** (calcul, fenêtre de données jusqu'au 2026-09-30) :
  - Gemini 3.8 Flash, borne prudente mars 2026 : **environ 6 mois** hors échantillon ; en prenant janvier 2025 pour les connaissances générales : environ 1,7 an. L'évaluation de performance ne repose donc que sur quelques mois de données vraiment hors échantillon, plus le live test. Cela confirme D-025 (L4 démontre la mécanique, pas un alpha).
  - **La réplication AlphaAgents (décision au 2026-02-01 sur des données de janvier 2024) est postérieure à la date de fin d'entraînement de `llama3.1:8b` (décembre 2023)** : avec ce modèle, elle serait réellement hors échantillon, à la qualité d'un modèle de 8 milliards de paramètres. Avec Gemini, elle est contaminée (D-025).
  - `gpt-oss-120b` (juin 2024) donnerait environ 2,3 ans hors échantillon, mais ses quotas Groq ne permettent pas un backtest.
- **Décision à prendre par Younes (phase 3, compte rendu) :** quel modèle pour les exécutions d'évaluation et la réplication (Gemini à version figée, `llama3.1:8b` local, ou les deux comparés comme l'ablation par fournisseur de la section 5.1 du prompt).

### Conditions d'utilisation des niveaux gratuits

| Fournisseur | Entraînement sur les données | Zone géographique | Source |
| --- | --- | --- | --- |
| Gemini (gratuit) | **Oui** : « Google uses the content you submit … to provide, improve, and develop Google products » ; des relecteurs humains peuvent lire les entrées et les sorties ; ne pas envoyer d'informations sensibles ou confidentielles | **EEE, Suisse, Royaume-Uni : services payants uniquement** « when making API Clients available to users » dans ces zones | https://ai.google.dev/gemini-api/docs/terms ; page de tarifs : « Content used to improve our products : Yes » |
| Groq | Non, par contrat : source **secondaire** seulement, la page officielle ne l'aborde pas ; journaux conservés jusqu'à 30 jours | aucune restriction trouvée | https://console.groq.com/docs/your-data |
| Ollama / Llama 3.1 | sans objet (local) | aucune restriction vue | licence « Llama 3.1 Community License » |

- **Risque juridique à instruire (L6, Q-27) :** la clause de Google vise la mise à disposition d'API Clients à des utilisateurs de l'EEE ; notre usage de recherche par une équipe étudiante n'est probablement pas visé tel quel, mais ce n'est pas établi. En production chez Amundi, le niveau gratuit est inutilisable (données envoyées pour l'entraînement, zone EEE). Les données du projet (prix, macro, dépôts publics) ne sont pas confidentielles. À faire relire par ESCP ou Amundi.
- **Signalement des erreurs :** 429 `RESOURCE_EXHAUSTED` (Gemini) et 429 avec en-tête `retry-after` (Groq), 503 `UNAVAILABLE` (les deux) ; Gemini n'indique ni `retry-after` ni délai : backoff exponentiel obligatoire.

## D-053 — Première vague de la phase 3 fusionnée ; valeurs de configuration LLM (2026-10-05)

- **Fusionné dans `main`** (chaque branche relue par le `reviewer-tester`, tests adverses et mutations) :
  - socle LLM : `schemas.py`, `LLMClient`, mock, cache cloisonné par mode et profil, quotas sous `flock`, mode évaluation sans relais ;
  - outils de calcul (`tools/`) ;
  - source ESG manuelle par ETF (D-048), avec registre d'empreintes versionné et archives des réponses de l'API de la gestionnaire.
- **Défauts trouvés par les revues et corrigés avant fusion** (liste utile pour L4 et la gouvernance du risque de modèle) :
  - cache : une réponse relayée par Groq pouvait ressortir en mode évaluation ;
  - fichier de modèle figé corrompu ignoré en silence ; mode évaluation exécutable sur Ollama ;
  - perte de comptes de quotas avec 4 processus ou plus ;
  - masquage de secrets incomplet (Bearer en base64, Basic, Digest) ;
  - ESG : entrée antidatée acceptée (fuite du futur), `corrige` ignoré ;
  - outils : régime de volatilité dépendant d'un paramètre de rejeu, ratios absurdes sur séries plates, `source_id` instable entre `float` et `np.float64`.
- **Valeurs inscrites dans `config/llm.yaml`** (D-052) :
  - limites du relais Groq `openai/gpt-oss-120b` : 30 requêtes/min, 1 000/jour, 8 000 tokens/min (la limite de 200 000 tokens/jour n'a pas de champ) ; limites Gemini non publiées, restent `null` ;
  - `training_cutoff` (fin de mois, borne prudente) : `gemini-3.8-flash` et `gemini-3.5-flash-lite` 2026-03-31, `openai/gpt-oss-120b` 2024-06-30 (indice indirect), `llama3.1:8b` 2023-12-31.
- **Modèle d'embeddings local** `nomic-embed-text` installé (`ollama pull`, 274 Mo) pour le RAG en profil dev ; l'identifiant d'embedding Gemini de production reste à tester.
- **CI :** `fetch-depth: 0` (les tests d'append-only lisent l'historique Git) ; les tests dépendant du temps doivent être robustes sur un runner à 2 cœurs (le test de verrou à seuil de 0,5 s a échoué avec 0,54 s ; réécrit par le `reviewer-tester`).
- **Reportés** : `ToolMeta.to_dict` doit passer ses paramètres par `canonical_params` avant l'écriture des sources dans le journal ; date « jour réel » de l'ESG à unifier sur Paris (UTC pour les instantanés, locale pour le registre) ; variation de 1,04 % en un jour de C3M.PA le 2025-07-22 à vérifier avec la couche de données ; `DEFAULT_REPLAY_WEEKS`, `MIN_ANNUALIZED_VOLATILITY`, `MIN_ABS_DRAWDOWN` à geler dans `config/debate.yaml` et au pré-enregistrement.

## D-054 — Nettoyage de la couche de données : date de Paris, plafonds par classe, C3M.PA (2026-10-06)

- **Date de la source ESG :** la date « du jour » de `snapshot` et de `lock` est celle de **Paris** (`Europe/Paris`, cohérente avec la coupure de D-031), horloge injectable, horloge naïve refusée. Le nom du dossier d'instantané du stockage reste daté en UTC : le reviewer a vérifié qu'il n'en découle aucun défaut fonctionnel (le contrôle compare tous les instantanés), seulement un décalage d'affichage entre 00:00 et 02:00 à Paris.
- **Règle de qualité `class_abs_return` (hypothèses H, `config/data.yaml`) :** plafond de rendement quotidien absolu par classe, signalement seulement (D-032 : on ne corrige jamais) :
  - C3M.PA et CSH2.PA (monétaires) : 1 % ;
  - MTD.PA, EGOV.PA, CRP.PA (obligataire souverain et crédit IG) : 3 %, exemption mars 2020 ;
  - AHYE.PA (haut rendement) : 5 %, exemption mars 2020.
  - Le plafond est une borne incluse, avec une tolérance de 1e-9 ; un retour d'au moins 60 % du saut le lendemain est annoncé comme « écart de cotation probable » ; un volume absent est signalé « volume inconnu » sans faire échouer le contrôle. L'exemption de mars 2020 masque le signalement, pas la volatilité réelle (CRP.PA : 4 jours au-dessus de 3 %, AHYE.PA : 3 jours au-dessus de 5 %).
  - Recalculé de façon indépendante par le `reviewer-tester` : **un seul jour hors exemption sur les 6 ETF**, C3M.PA le 2025-07-22.
- **C3M.PA, 2025-07-22 (−1,04 % en un jour, retour de +0,71 % le lendemain) : classification « indéterminé, écart de cotation probable ».**
  - Preuves : cours bruts sans dividende ni split, aucun trou, fixing €STR stable, CSH2.PA, EGOV.PA et MTD.PA calmes le même jour, une variation de 1 % étant incompatible avec un fonds de bons du Trésor 0-6 mois.
  - Seule la valeur liquidative officielle du 22/07/2025 (page produit de l'ETF sur amundietf.fr, ou Euronext) permet de trancher ; **non obtenue** (les pages sont rendues côté client, un essai de requête a renvoyé 400). Ne pas présenter le volume comme preuve : plusieurs séances voisines ont un volume comparable.
  - Effet : volatilité de C3M.PA 0,383 % sur 1 an, 1,167 % sur 3 ans (0,998 % sans cette séance), 1,002 % sur 5 ans (0,887 % sans). La volatilité à 3 ans est donc peu représentative ; utiliser aussi la fenêtre de 1 an. Les 0,80 % restants viennent d'autres séances (avril 2025, 18-23 juillet 2025).
  - **Plafond de C3M.PA maintenu à 1 %** : un plafond de 0,6 % signalerait aussi les 21 et 23/07 et le 11/04/2025 ; à rediscuter si la valeur liquidative confirme un écart de cotation récurrent.
- **Garde-fou de volatilité des outils (`MIN_ANNUALIZED_VOLATILITY = 1e-4`) :** reste bien calibré, aucune fenêtre réelle ne passe sous 3,8e-4 (C3M.PA sur 63 séances, juillet 2019).
- **Reste à faire :** obtenir la valeur liquidative officielle (question Q-21 étendue) ; chercher l'éventuel avis de changement d'indice de C3M.PA avant avril 2026.

---

Décisions D-055 à D-066 : phase 3, agents, RAG, débat (2026-10-06). Les agents ont proposé D-054 à D-061 sous d'autres numéros : renumérotés ici.

## D-055 — Agents « outils d'abord » et contrôle d'ancrage

- **Choix :** le harnais exécute les outils de chaque agent (`tools/`, RAG, résumé), enregistre un `ToolCall` par appel et injecte les résultats avec leur `source_id` ; le LLM ne produit qu'une `View` structurée qui les commente. **Aucun chiffre ne vient du LLM** : le contrôle d'ancrage (`agents/grounding.py`) rejette toute vue dont un chiffre n'est pas retrouvé dans les sorties d'outils ou les textes sources (nombres en chiffres, en lettres FR et EN, décimales parlées, séparateurs exotiques, ancrage par actif), avec 2 redemandes puis rejet motivé et abstention.
- **Écart avec le papier :** AlphaAgents laissait le LLM appeler ses outils (AutoGen). Ici l'appel des outils est déterministe, ce qui rend la vérification « l'agent Valuation utilise bien ses outils » triviale (chaque vue porte ses `ToolCall`) et rejouable.
- **Limites mesurées (`reviewer-tester`) :** le contrôle est un filet de sécurité, pas une preuve.
  - Entiers nus de 3 chiffres ou moins : non contrôlés ; petits mots-nombres sans unité : acceptés.
  - Coïncidence accidentelle d'un chiffre inventé avec un ancrage : 2,4 % (entier avec %), 2,0 % (1 décimale), 0,2 % (2 décimales) avec 14 ancrages d'outil réels ; **jusqu'à 27 % (entier avec %) avec 200 ancrages d'outil** (la tolérance relative de 1 % est conservée pour les valeurs d'outil).
  - Pour les textes de rapports ou d'articles : comparaison exacte, sans tolérance.
  - **Dette (`xfail` strict)** : l'unité écrite d'un ancrage de texte n'est pas retenue, donc une erreur d'unité d'un facteur 1 000 (« 12,7 millions » pour « 12 700 million ») serait acceptée.
- **Source des chiffres décisionnels :** les outils, jamais le LLM.

## D-056 — Débat : arbitrage groupé, pannes, voix unique (précise D-016)

- **Arbitrage groupé :** un seul appel d'arbitrage par débat pour toutes les vues contestées (repli : médiane tronquée vers 0), sinon l'allocation aurait coûté jusqu'à 9 arbitrages et dépassé K_a ≤ 2.
- **Pannes du fournisseur :** révision manquée = vote précédent conservé et journalisé ; collaboration échouée = débat non terminé, les autres débats sont conservés ; quota épuisé ou pause = arrêt propre, la même commande reprend depuis le cache.
- **Voix unique** (décision du lead, à reporter dans L1 §6) : si moins de `min_votants_valides` = 2 votants valides restent pour un actif, statut `voix_unique`, niveau borné à ±1, confiance plafonnée à 0,32, aucun tour de débat, **non transmis** à la construction du portefeuille par défaut (`transmettre_voix_unique: false`). Un agent seul ne porte jamais la confiance d'un consensus.
- **Plafond de confiance du découpage en repli :** quand le RAG signale un découpage par sections en repli (INTC), la confiance **finale** est plafonnée à 0,4 (H) par l'orchestrateur, journalisée (`DebateOutcome.plafonnee_par`) et visible dans le rapport ; une limite ne relève jamais une confiance plus basse.
- **Confiance :** c = clip(c_max·A·g·ρ·h) calculée en Python (L1 §6.4) ; l'auto-confiance des agents est journalisée mais n'entre pas dans le calcul (vérifié par test).

## D-057 — Agent ESG (précise D-035, D-048)

- **Choix :** agent déterministe (règles et données) ; veto sur exclusion normative détectée (SIC pour les titres, états `determine_par_donnee`, `suppose_par_regle`, `inconnu` pour les ETF) ; **aucun veto d'ETF par défaut** (`esg.etf_criteres_requis` vide, H : aucune exclusion d'ETF n'est « déterminée » sauf CRP.PA et AHYE.PA) ; score absent signalé ; le LLM (`light`) ne fait qu'expliquer un veto et ne peut ni le lever ni le créer.
- **Point-in-time :** un enregistrement ESG observé à t ou après est ignoré ; un enregistrement marqué non point-in-time n'est accepté qu'en mode interactif (`esg.accepter_non_point_in_time`, H), jamais en évaluation, et le rapport le signale. Une allocation dont tous les actifs sont vetoed est écartée proprement, les titres sont traités.

## D-058 — Orchestration, configuration et délais

- `DebateLog` est étendu (appels, rejets, risque, ESG, hashes de prompts) et `RiskAssessment.regime_volatilite` devient optionnel (`None` si non calculable).
- **Orchestrateur :** `langgraph` (D-009) ou `boucle`, interchangeables par `debate.orchestrateur` ; les deux donnent exactement le même débat (testé sur 15 combinaisons graine × profil) ; `langgraph` n'est importé que dans `debate/orchestrator.py`, jamais pour un appel LLM. LangGraph apporte peu pour un flux linéaire : la traçabilité vient du `DebateLog`.
- **`config/debate.yaml`** : tous les paramètres sont des hypothèses (H) avec leur source (L1, outil du quant), gelés au pré-enregistrement avec `DEFAULT_REPLAY_WEEKS` = 52 et les seuils d'alerte de risque ; `MIN_ANNUALIZED_VOLATILITY` et `MIN_ABS_DRAWDOWN` restent dans `tools/finance.py`.
- **Délai LLM :** 120 s est insuffisant pour Ollama local (`llama3.1:8b`, CPU) avec des prompts de 2 000 jetons ou plus ; réglage par configuration (`defaults.timeout_s`, `--llm-config`). Un débat d'une classe d'actifs a pris 1 144 s avec Ollama ; un run complet de plusieurs titres prendrait des heures.
- **Coût en appels** (calcul, `R_max = 2`) : allocation 4 à 9, un titre 3 à 8, une date avec 15 titres 49 à 129. L1 §11.2 donne 11 et 180 car il comptait les appels du RAG comme appels LLM ; ici Fundamental lit directement les passages et seuls les embeddings du RAG s'ajoutent. Les embeddings comptent dans les quotas.

## D-059 — RAG, résumé et évaluation (tâche A)

- **RAG par sections de 10-K et 10-Q** (`tools/rag.py`) : vérifié sur 286 dépôts réels de 15 sociétés tech.
  - Table des matières ignorée ; états financiers des 10-Q rattachés à Part I Item 1 ; NVDA et ORCL : états financiers sous l'Item 15 ; QCOM : `Annexe-F` détachée ; IBM : Items 7, 7A, 8 « par renvoi ».
  - **Repli « Document » visible** (`section_fallback`) quand le préambule dépasse 80 000 caractères ou qu'il y a moins de 3 sections lisibles : seul Intel (19 dépôts) en relève.
  - Seuils (H) calibrés sur 15 sociétés tech : `min_substantial_sections` = 3 peut basculer à tort en repli un petit émetteur (biotech, banques, émetteurs étrangers) ; gelé à 3 (honnête et visible), à revérifier sur d'autres secteurs.
  - Un dépôt n'est servi que s'il est accepté **strictement avant** t ; filtre appliqué à l'indexation et à chaque requête.
- **Résumé avec réflexion** (`tools/summarize.py`) : 1 + 2 appels par tour ; citations validées (alias `N1..Nn`), contrôle de présence des chiffres, texte externe encapsulé et neutralisé (y compris le brouillon et la critique réinjectés : injection de second ordre) ; défense de base, une reformulation passe.
- **Évaluation du RAG** (`evaluation/rag_eval.py`) : **pas de Ragas ni d'Arize Phoenix** (dépendances lourdes, juge OpenAI par défaut, incompatibles avec le budget 0 € et la règle « tout appel LLM passe par `LLMClient` ») ; fidélité et pertinence par juge LLM via `LLMClient`, plus rappel à k et rang réciproque ; **les scores d'un juge de 8 milliards de paramètres sont indicatifs** (mesuré : fidélité 0,75, pertinence 0,83 à 1,0 sur 4 cas de calibration avec des erreurs), champ `indicatif` partout. Écart avec le papier (qui utilisait Phoenix).
- **`config/text_tools.yaml`** (valeurs H) : paramètres du RAG, du résumé, du juge, préfixes d'embedding par profil.
- L1 prévoyait un seul prompt `summarize_reflect_v1.md` et `evaluation/reasoning.py` ; la réalisation est de trois prompts (résumer, critiquer, affiner) et `evaluation/rag_eval.py` : L1 à aligner. Les ventes d'initiés relèvent des formulaires 4 (hors RAG), pas du 10-K.

## D-060 — Dette technique et limites connues de la phase 3

| Point | Gravité | Phase |
| --- | --- | --- |
| Unité écrite d'un ancrage de texte non retenue (erreur d'un facteur 1 000 acceptée) | Moyenne | 3 (suite), `xfail` strict |
| Taux de coïncidences de chiffres d'outil avec beaucoup d'ancrages (jusqu'à 27 % pour un entier avec %) | Moyenne | 3 (suite) |
| `transmettre_voix_unique` lu par l'orchestrateur mais la construction du portefeuille n'existe pas encore | Faible | 4 |
| Mode `--live` (Sentiment votant) exercé seulement avec le mock ; `summarize_news` jamais exercé sur de vraies news | Moyenne | 3 (suite) |
| Embedding de production (`gemini/gemini-embedding-001`) non testé ; Gemini jamais appelé en phase 3 | Moyenne | 3 (suite) |
| Durée de la suite (150 s en local, 2 500 tests) | Faible | continu |
| Seuils de repli du RAG (3 sections, 80 000, 1 500) calibrés sur 15 sociétés tech | Faible | 7 |
| Sources de vues : traçabilité par actif corrigée, mais jamais exercée sur de vraies données avec un vrai LLM | Moyenne | 3 (suite) |

## D-061 — Protocole de revue des agents (gouvernance du risque de modèle)

- Chaque branche passe par le `reviewer-tester` (tests adverses indépendants, mutations, essai sur vraies données en lecture seule) avant fusion ; ses tests sont protégés par D-049.
- Bilan de la phase 3 : les défauts bloquants listés en D-053 et dans les comptes rendus ont été trouvés en revue (tests adverses, mutations, essais sur vraies données, revue du critique).
- Constat de fiabilité des outils de développement : les agents ont été interrompus plusieurs fois par la limite de session ; chaque reprise a été vérifiée contre l'état réel des fichiers avant de continuer, et un agent a produit des fichiers corrompus (apostrophes coupées par des sauts de ligne dans 3 prompts, réparées).

---

Décisions D-062 à D-066 : revue du `financial-critic` sur la phase 3 (verdict « acceptable avec réserves » pour clore la phase, « non probant » pour toute conclusion de L4 sur la confiance, le multi-agent contre les agents seuls et la qualité du raisonnement du RAG).

## D-062 — Ollama tronquait les prompts en silence (2026-10-06) — **défaut trouvé par le critique, confirmé par le lead**

- **Constat :** aucun `num_ctx` n'était fixé. Test du lead (Ollama 0.35.0, `llama3.1:8b`) : un prompt de 40 190 caractères (environ 9 000 jetons) est évalué à **2 050 jetons** avec la valeur par défaut ; la consigne placée au début est perdue (réponse « Je suis prêt à répondre ») ; avec `num_ctx` = 16 384, le serveur évalue 9 041 jetons et la réponse est correcte (« ZEBRE »), au prix d'un temps plus long (149 s contre 28 s sur ce test, rechargement du modèle compris).
- **Conséquence :** toute exécution réelle avec Ollama faite avant cette date a pu l'être avec des prompts coupés à environ 2 000 jetons, sans erreur. **Sont à refaire ou à considérer comme non valides pour les prompts longs :** la calibration du juge du RAG (fidélité 0,75, pertinence 0,83 : D-059), le débat d'allocation réel de 1 144 s (D-058), les tests `llm` des agents et du RAG. Les tests par défaut (mock) ne sont pas concernés.
- **Choix :** `num_ctx` explicite dans `config/llm.yaml` (H : 16 384, à valider selon la mémoire) transmis à Ollama ; **comptage des jetons évalués renvoyés par le serveur** (`prompt_eval_count`) comparé à une estimation du prompt envoyé, et **échec franc** (`PromptTronque`) si l'écart dépasse un seuil (H) ; jetons évalués et `num_ctx` enregistrés dans l'`ExecutionRecord`. À corriger avant toute exécution Ollama de la réplication.

## D-063 — La « confiance » du débat est un indice d'accord de processus (2026-10-06)

- **Constat (critique) :** c = clip(c_max·A·g·ρ·h) est une fonction du processus (statut, tours, alerte), pas de l'évidence. Les agents partagent le même LLM et le même gabarit de prompt : leur accord mêle corrélation des erreurs, biais haussier commun et mémoire du modèle. Une unanimité au tour 0 donne c = 0,8 sans contradicteur. Une calibration est invérifiable aujourd'hui : contaminée avant la fin d'entraînement, environ 6 mois après ; distinguer 55 % de 50 % de réussite demande environ 780 observations indépendantes (calcul : (2,8)²·0,25/0,05²).
- **Choix :**
  - dans tous les textes, c s'appelle **« indice d'accord de processus »**, jamais « probabilité » ni « confiance calibrée » ;
  - **par défaut dans Black-Litterman (phase 4), c est constant** ou plafonné bas ; l'ablation « c constant » (EX-O5-04) devient la configuration par défaut et non une option ; le c du débat n'entre dans Ω que si une table de fiabilité hors échantillon montre un pouvoir de discrimination ;
  - la valeur de c_max, de g, de ρ et de h est gelée avant tout run (D-027) et **jamais réestimée sur les résultats** ; la sémantique d'Idzorek (inclinaison vers la vue) diffère de celle d'un taux de réussite (Brier) : à écrire dans L1 ;
  - mesures prévues en phase 7 (rapportées même si défavorables) : table de fiabilité par statut avec intervalle de Wilson, Brier de c contre Brier de c constant et contre le taux de base, taux d'unanimité au tour 0 contre un accord permuté (vote Valuation du titre i contre vote Fundamental du titre j), part de POSITIF et kappa, effet de l'avocat du diable mesuré par un contrôle sans avocat sur une part fixée d'avance (25 % des débats) et un test placebo (majorité falsifiée).

## D-064 — Règles de rapport de L4 (2026-10-06)

- **Formulations interdites** dans tout rapport, interface ou documentation : « le multi-agent bat les agents seuls », « confirme les résultats d'AlphaAgents », « le débat réduit la pensée de groupe » (non mesurée), « confiance calibrée » ou « probabilité de succès » pour c, « alpha », « surperformance » hors intervalle, « robuste », « validé », « hors échantillon » pour un résultat de Gemini antérieur à juin 2026 (borne prudente : fin d'entraînement mars 2026 plus 3 mois de marge), « conforme ESG », « analyse fondamentale » pour l'agent Fundamental (écrire : « lecture qualitative de dépôts par un LLM »), « prouve la qualité du raisonnement » (juge de 8 milliards de paramètres), tout Sharpe ou ratio d'information présenté sans son intervalle.
- **Peut s'affirmer** : la mécanique fonctionne de bout en bout, les contraintes sont respectées, les journaux sont complets, les coûts et durées sont mesurés, l'écart au benchmark est décrit sans inférence, la réplication est « non concluante » si les règles du protocole le disent.
- Un résultat de Gemini avant la fin d'entraînement est étiqueté « contaminé » ; celui de `llama3.1:8b` pour février à mai 2024 est « hors échantillon sous réserve d'un sondage de mémoire ».

## D-065 — Protocole de réplication AlphaAgents révisé (2026-10-06) — **remplace la version de D-021 et de L1 §9.3**

Objet : vérifier la mécanique et la cohérence qualitative avec le papier ; **aucune conclusion de performance**. Puissance statistique pratiquement nulle (15 titres du même secteur sur une seule fenêtre de 4 mois : ratio d'information détectable d'environ 4,9 ; il faut au moins 12 bonnes décisions sur 15 pour p ≈ 0,018).
1. **Pré-enregistrement avant tout run** (D-027) : pool, graine hashée, mapping BUY/SELL, règle d'abstention, profils, température, nombres de tirages et d'exécutions, règles de rapport, hashes des prompts et des configs ; toute déviation crée une version datée.
2. **Cible :** décision au 2024-02-01 (données de janvier 2024 ; dépôts acceptés avant), suivi du 2024-02-01 au 2024-05-31, taux sans risque FRED DGS1MO.
3. **Univers évalué :** les titres du pool utilisables (62) plus Zscaler (hors pool), une fois par profil et par exécution, **autant que le budget le permet** ; le tirage primaire de 14 titres plus ZS (graine hashée avant le tirage) est un sous-ensemble ; les tirages secondaires (jusqu'à 1 000) rééchantillonnent le pool déjà évalué, **sans appel LLM en plus**, et mesurent la variance du choix des titres (pas celle du marché).
4. **Un seul débat par titre, profil et exécution** donne tout : le tour 0 de chaque agent = portefeuille « Valuation seul » et « Fundamental seul » ; le consensus final = « multi-agent » ; agrégations sans débat **ET** (BUY si les deux sont positifs) et **OU**.
5. **Mapping :** niveau final > 0 = BUY, autre = SELL (pas de HOLD, comme dans le papier). **Abstention, rejet d'ancrage ou `voix_unique` = titre exclu des portefeuilles « signal »** (jamais SELL implicite) ; sensibilité « abstention = SELL » rapportée ; portefeuille vide = trésorerie au DGS1MO. Le multi-agent est mécaniquement plus conservateur à K = 2 (médiane arrondie vers 0) : c'est pourquoi ET et OU sont comparés.
6. **Références :** les 15 titres équipondérés, les 62 équipondérés, la distribution exacte des portefeuilles aléatoires de même taille.
7. **Exécutions :** baseline (température 0), 2 paraphrases de prompts (température 0), 5 exécutions à température 0,7, sans cache entre elles ; le désaccord entre exécutions (kappa) est le plancher de bruit. Avec Ollama seul, seules la baseline et quelques exécutions sur le tirage primaire de 15 titres sont réalistes (extrapolation d'une seule mesure faite avec le défaut D-062 : à remesurer).
8. **Contrôle de mémoire (modèles Gemini) :** Valuation anonymisée (prix rebasés à 100, étiquettes tirées au hasard, dates relatives), test de ré-identification, sondage direct de rendements mensuels et de niveaux d'indice, et **réplication jumelle post-coupure** (mêmes règles, décision le 2026-06-01, suivi jusqu'au 2026-09-30, fenêtre fixée par la règle « dernière fenêtre complète de 4 mois à la date du pré-enregistrement »). Fundamental n'est pas anonymisable : « non contrôlable » pour Gemini. **Non fait en phase 3** : exige des appels Gemini (quotas inconnus).
9. **Inférence :** bootstrap stationnaire par blocs de 5 séances (H), permutation exacte pour la sélection, intervalles de Wilson sur les fréquences d'accord ; intervalle large publié même s'il est inexploitable.
10. **Règles de rapport :** « non concluant » si l'intervalle d'une différence contient 0, si moins de 4 titres diffèrent entre les portefeuilles comparés, si l'écart est inférieur au désaccord entre exécutions, ou si le multi-agent ne bat pas la règle ET ; le multi-agent n'est dit « meilleur » que si ces conditions sont réunies sur les deux profils et sur les modèles testés ; les modèles de l'ablation par fournisseur restent séparés, jamais moyennés.
11. **Journal :** taux de rejet d'ancrage, d'abstention, d'erreur JSON et de `voix_unique` par agent et par exécution ; prompts hashés ; `modele_servi` ; arrêt si le modèle servi change.
12. **Comparaison avec le papier :** qualitative seulement (titres, modèle, outils et agent Sentiment différents) ; aucun chiffre côté à côté.

## D-066 — Autres réserves du critique retenues (2026-10-06)

| Point | Décision | Phase |
| --- | --- | --- |
| Avocat du diable : « vote sincère » non contraint ; K = 2 : la position majoritaire (médiane vers 0) n'est tenue par aucun | mesurer (placebo, contrôle sans avocat, accord permuté) plutôt que supposer | 7 |
| Profils : 5 paragraphes de prose ; risk-seeking ≈ risk-neutral dans le papier | test de différenciation avant d'en dépendre (5 profils × 3 exécutions à température 0,7 sur au moins 30 titres × 3 dates, comparé au bruit entre exécutions) ; réduire le nombre de profils si l'écart n'excède pas le bruit | 3 (suite), 4 |
| Triple comptage de la volatilité (prompt de profil, facteur h, optimiseur) | le profil n'entre dans le prompt que pour la réplication ; dans le système principal, ablation « prompt sans profil + contraintes » contre « prompt avec profil », choisie **avant** les runs | 4 |
| Seuils d'alerte à rang centile : fréquence d'alerte quasi mécanique (environ 20 % modérée, 5 % élevée) | publier la fréquence réelle par classe et par année ; sensibilité (0,70/0,90 ; VIX 20/30) rapportée sans choisir a posteriori | 7 |
| Quadrants macro 2 % / 2 % peu informatifs | publier la répartition 2018-2026 ; pas d'argument de performance | 7 |
| Plafond de repli (0,4) pénalise toute la vue (Valuation incluse) ; non-monotonie avec voix unique (0,32) et vue contestée | plafonner la contribution de Fundamental seulement, ou documenter la non-monotonie | 4 |
| RAG : questions en français sur des 10-K en anglais ; évolution des marges et du cash non comparable par top-k ; aucune mesure de valorisation | questions en anglais ; variations calculées en Python depuis XBRL passées en `ToolCall` ; Fundamental = « lecture qualitative » | 3 (suite) |
| `max_filings` = 4 : les facteurs de risque viennent d'un 10-K vieux de jusqu'à 11 mois | date de dépôt de chaque passage dans le prompt ; âge du dernier dépôt publié par titre | 3 (suite) |
| Juge du RAG : 4 cas, intervalle de Wilson 3/4 d'environ 0,30 à 0,95 | ne jamais citer comme preuve de qualité ; pour L4, 50 affirmations étiquetées à la main, accord juge/humain (kappa) avec intervalle, juge à version figée | 7 |
| La consigne « tu ne connais rien après cette date » n'est pas un contrôle de look-ahead | ne jamais la citer comme garde-fou ; le contrôle passe par l'anonymisation et le sondage ; vérifier que l'API Gemini est appelée sans outil de recherche | 3, 7 |
| `runs/preregistration` et une commande de pré-enregistrement n'existent pas | à créer avant la réplication | 3 (suite) |
| Phase 3 : aucun appel Gemini réel, un seul débat réel avec Ollama (avec le défaut D-062) | pilote réel de quelques titres avec Ollama (contexte corrigé) pour mesurer les taux de rejet d'ancrage, d'erreur JSON et de `voix_unique` | 3 (suite) |
| D-061 : « jamais par les auteurs » | formulation ramenée à ce qui est listé en D-053 | fait |

## D-067 — Corrections du protocole de réplication après revue du harnais (2026-10-07) — **précise D-065**

- **Éligibilité du pool** (§3) : elle ne lit que des données **strictement antérieures à t** (prix suffisants avant t, au moins un 10-K ou 10-Q accepté avant t). La règle « suivi complet requis » du premier jet lisait le compte de séances après t : un titre radié ou absorbé plus tard était écarté a posteriori (biais du survivant lié à la performance) ; elle est **supprimée**. Un titre dont les prix s'arrêtent avant la fin du suivi **n'est jamais exclu ni remplacé** : le portefeuille garde sa **dernière valeur connue** jusqu'à la fin (`pool.titre_sans_prix_en_fin_de_suivi: derniere_valeur_connue`), et le rapport les liste (aucun parmi les 62 titres utilisables au 2026-10-07).
- **Sensibilité à l'abstention** (§5) : « abstention = SELL » est **remplacée par « abstention = BUY »** : un portefeuille ne contient que des BUY, donc compter une abstention comme SELL ne change rien (prouvé par test). Le taux d'abstention par agent, profil et exécution est affiché à côté.
- **Bandeau d'essai :** tout rapport issu de `--mock`, `--mock-llm` ou `--synthetic-data` commence par un bandeau « ESSAI DE MÉCANIQUE » (kappa = 1 et désaccord = 0 par construction : aucune valeur d'évaluation).
- **Marge de contamination** (3 mois, H) appliquée : un résultat n'est dit « hors échantillon sous réserve » que si la décision est postérieure à la fin d'entraînement plus 3 mois. **Pour `llama3.1:8b` (fin 2023-12-31) et une décision au 2024-02-01 : « dans la marge de contamination : hors échantillon non garanti, sondage de mémoire requis »** (correction de D-052, qui le disait hors échantillon sans réserve).
- **Formulations interdites :** liste dans `config/replication.yaml` (`rapport_interdit`, 26 motifs, texte normalisé avant balayage) ; limites résiduelles connues (« fundamental analyses », « success probability », « probabilité de réussite », « group-think reduced »).
- **Vérifié par le `reviewer-tester` :** tirage primaire recalculé à l'identique (graine 20240201, SHA-256 `d7458cc2…`) ; calculs recalculés à la main ; **« meilleur » jamais obtenu sur du bruit pur** (0 sur 200 jeux dans 3 configurations, 0 sur 100 dans 2 autres) ; 10 mutations tuées.
- **Délai LLM :** `defaults.timeout_s` passe de 120 à 900 s (H) avant le premier pré-enregistrement.
- **Limites connues :** désaccord entre exécutions nul avec le mock (condition vide) ; la dernière version du pré-enregistrement n'est protégée que par Git ; ET et OU excluent un titre dont un des deux votes manque ; l'abstention réelle de Fundamental reste à mesurer avec un vrai modèle.


## D-068 — Générations sans fin avec un petit modèle : borne de sortie (2026-10-07) — **trouvé par le pilote de réplication**

- **Constat (pilote Ollama, `llama3.1:8b`, contexte 16 384 corrigé, D-062) :** sur 6 appels de chat de l'agent Fundamental, **4 ont expiré à 900 s** (une heure perdue) et 2 ont réussi (305 s pour 7 471 jetons, 107 s pour 9 499 jetons). Les 4 échecs étaient **le même prompt** (8 719 jetons) répété à l'identique par les nouvelles tentatives : à température 0, la génération est déterministe, donc un prompt qui part en génération sans fin y retombe à chaque tentative. Aucune longueur maximale de sortie n'était fixée (`max_output_tokens: null`) : le modèle écrit jusqu'au contexte plein.
- **Choix :** `defaults.max_output_tokens: 2048` (H) dans `config/llm.yaml` (une vue, un rapport ou un arbitrage tient largement dessous), vérifié par un appel réel (plafond de 60 jetons respecté par Ollama). Le délai par défaut reste 900 s (D-067).
- **Reste à faire :** (1) une nouvelle tentative **à l'identique** après un délai dépassé est inutile à température 0 : adapter la politique de relance (par exemple une seule relance, puis échec franc, ou relance à une température légèrement supérieure en mode interactif seulement) ; (2) `preregister` ne hache que la section `evaluation` de `llm.yaml` : y inclure `defaults` (borne de sortie, délai, graine, température) ; (3) mesurer le taux de sorties tronquées par la borne (une vue coupée n'est pas un JSON valide : elle sera rejetée et redemandée).
- **Pré-enregistrement :** aucune nouvelle version : `preregister` répond « état identique à 2026-10-07.json » (la version 1 avait déjà été écrite avec `timeout_s: 900` ; la borne de sortie n'est pas dans le périmètre haché, d'où le point (2)). La borne est donc **hors empreinte** : elle est consignée ici et dans le journal des appels.


## D-069 — Première réplication réelle sur Ollama (dev) : mécanique validée, résultat non concluant (2026-10-07)

- **Exécution :** `replicate --run --llm-profile dev --mode interactif --univers primaire --executions baseline`, `llama3.1:8b` local (contexte 16 384, sortie bornée à 2 048 jetons, D-062/D-068), 32 débats (2 profils × 16 titres : TRMB remplacé par KLAC pour échec technique, règle du protocole), 4,2 h de calcul. Traces versionnées dans `runs/replication/dev_ollama_20261007/` (rapport, tableaux, journal des appels).
- **Résultat :** verdict **non concluant** (attendu : une seule exécution, aucun BUY). **Aucun BUY** pour aucune stratégie : tous les portefeuilles sont en trésorerie (1,78 %), contre 7,5 % pour la référence équipondérée. Ce n'est **pas** un résultat sur la valeur des agents : c'est une limite du petit modèle.
- **Cause mesurée :** l'agent Fundamental est **abstenu au tour 0 dans 62,5 % (profil averse) et 80 % (neutre)** des titres, par sorties JSON non conformes ou rejets d'ancrage ; statuts des débats : 18 `voix_unique`, 8 `unanime`, 6 sans décision. Le multi-agent ne peut donc pas être distingué des stratégies à un seul agent (0 titre qui diffère).
- **Ce que cela valide :** la chaîne complète (pré-enregistrement conforme, tirage reproduit, données point-in-time, débat, portefeuilles, bootstrap, règles « non concluant », bannière du modèle dans la marge de contamination) fonctionne de bout en bout sur données réelles.
- **Suite :** (1) la vraie réplication nécessite un modèle plus capable (Gemini, évaluation, versions figées) et ≥ 2 exécutions : décision de Younes sur l'usage de Gemini et quotas à lire dans AI Studio ; (2) pour Ollama, réduire les rejets de Fundamental (prompt plus court, une vue par appel) : amélioration possible mais hors pré-enregistrement ; (3) politique de relance des délais déterministes (D-068).
