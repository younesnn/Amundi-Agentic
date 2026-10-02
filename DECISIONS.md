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
