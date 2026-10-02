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
  - rapports : date d'acceptation EDGAR, convertie de l'heure de New York en UTC ;
  - XBRL : pour chaque fait, la valeur du dernier dépôt avec `filed < t` ;
  - pas de fondamentaux yfinance en backtest ;
  - score ESG non daté réservé au live test ;
  - agent Sentiment retiré du backtest sous un seuil de couverture des news mesuré en phase 2.

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
- **Justification :** la poche titres consommait environ 94 % des appels (225 sur 239 par date et par profil) pour au plus 5 à 15 % du poids. Passer de 50 à 15 titres divise cette part environ par 3,3.
- **Conséquences :** l'agent Fundamental porte sur 15 titres au plus ; les plafonds par titre de D-019 (1, 2 et 3 %) sont à revoir en phase 4, car moins de titres signifie un poids plus élevé par titre. À répercuter dans L1 (§7, §8, §11.2) avant le pré-enregistrement. Q-16 reste ouverte.
