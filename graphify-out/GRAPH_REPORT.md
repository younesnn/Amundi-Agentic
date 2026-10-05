# Graph Report - Amundi Agentic  (2026-10-03)

## Corpus Check
- 73 files · ~90,365 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 4, .example 1)

## Summary
- 1215 nodes · 2695 edges · 94 communities (68 shown, 26 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 348 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eb8de05f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- LLMClient abstraction (provider-agnostic, temperature 0, Pydantic outputs)
- Fiche de revision - AlphaAgents (papier BlackRock)
- Fiche de revision - Markowitz et Black-Litterman
- Multi-agent Debate (Round Robin to consensus)
- Deliverable: Deployment plan & integration into Amundi processes
- Agent Risk Tolerance Profiles (risk-averse / risk-neutral)
- Fiche de revision - Projet Amundi Agentic AI
- Deliverable: Performance analysis report (backtesting & live testing)
- test_connectors.py
- test_rejouabilite_analyses.py
- prix
- Journal des décisions
- test_pit.py
- Academic prototype disclaimer (not investment advice)
- pipeline.py
- test_revue_pit_adverse.py
- test_specifications.py
- NewsConnector
- FredConnector
- Couverture des données (phase 2)
- test_revue_rejouabilite.py
- test_revue_robustesse.py
- test_socle_revue.py
- .snapshot
- test_http_store.py
- coverage.py
- FilingsConnector
- Report
- pit.py
- PricesConnector
- settings.py
- test_revue_corrections.py
- ParquetStore
- test_config.py
- ts
- ny_local_to_utc
- manifest.py
- DataSettings
- PointInTimeStore
- pit_prices
- pytest
- EsgConnector
- add_us_business_days
- 11. Exigences non fonctionnelles
- _TextExtractor
- 7. Construction Black-Litterman
- _Tables
- HttpClient
- 5. Schémas de données (Pydantic, `schemas.py`)
- test_dependances_entre_modules
- Prompt maître — Système agentique Amundi
- L1 — Spécifications fonctionnelles et techniques
- 6. Flux du débat
- redact
- edgar_acceptance_to_utc
- EcbConnector
- Projet Amundi Agentic — instructions pour Claude Code
- 10. Règles de rééquilibrage
- 9. Univers
- Avancement
- Amundi Agentic
- SessionJson
- 3. Architecture
- HttpError
- 8. Profils clients
- agent_prompts/README.md
- app/README.md
- config/README.md
- QUESTIONS_AMUNDI.md
- agents/__init__.py
- debate/__init__.py
- evaluation/__init__.py
- explain/__init__.py
- amundi_agentic/__init__.py
- llm/__init__.py
- portfolio/__init__.py
- rebalancing/__init__.py
- tools/__init__.py
- Matrice de traçabilité : exigences → composants → tests
- D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)
- amundi-agentic
- 13. Choix du cadre d'orchestration : LangGraph ou AutoGen
- FausseSession
- MissingSecretError
- test_points_de_reprise_jamais_dans_les_donnees_servies
- test_aucun_secret_ecrit_dans_les_fichiers_du_depot_de_donnees
- test_ecriture_atomique_un_echec_laisse_l_ancien_fichier

## God Nodes (most connected - your core abstractions)
1. `ParquetStore` - 99 edges
2. `Fiche de revision - AlphaAgents (papier BlackRock)` - 66 edges
3. `Journal des décisions` - 53 edges
4. `Fiche de revision - Projet Amundi Agentic AI` - 45 edges
5. `prix()` - 35 edges
6. `HttpClient` - 33 edges
7. `DataSettings` - 31 edges
8. `Prompt maître — Système agentique Amundi` - 30 edges
9. `Fiche de revision - Markowitz et Black-Litterman` - 29 edges
10. `Report` - 26 edges

## Surprising Connections (you probably didn't know these)
- `Baseline: equal weight (AlphaAgents)` --semantically_similar_to--> `Equal-weight Portfolio from Agent Picks`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `Sentiment Agent (allocation level, macro news RSS/GDELT)` --semantically_similar_to--> `Sentiment Agent`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `Macro Agent (allocation: FRED/ECB regime indicators)` --semantically_similar_to--> `Macro Economist Agent (future)`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `Valuation / Momentum Agent (multi-asset ETFs)` --semantically_similar_to--> `Valuation Agent`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `yfinance (ETF/stock prices, fundamentals)` --semantically_similar_to--> `Yahoo Finance Price & Volume Data`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Limits undermining AlphaAgents backtest validity** — fiches_fiche_alphaagents_blackrock_look_ahead_bias, fiches_fiche_alphaagents_blackrock_small_sample_limitation, fiches_fiche_alphaagents_blackrock_no_transaction_costs, fiches_fiche_alphaagents_blackrock_llm_non_determinism, fiches_fiche_alphaagents_blackrock_groupthink_risk, papier_blackrock_tech_stock_experiment [EXTRACTED 1.00]
- **AlphaAgents specialist agents debate to consensus via group chat** — papier_blackrock_fundamental_agent, papier_blackrock_sentiment_agent, papier_blackrock_valuation_agent, papier_blackrock_group_chat_assistant, papier_blackrock_multi_agent_debate, papier_blackrock_stock_analysis_report [EXTRACTED 1.00]
- **Black-Litterman pipeline: agent views to portfolio weights** — papier_blackrock_multi_agent_debate, fiches_fiche_markowitz_black_litterman_agent_views_mapping, fiches_fiche_markowitz_black_litterman_views_p_q, fiches_fiche_markowitz_black_litterman_view_uncertainty_omega, fiches_fiche_markowitz_black_litterman_equilibrium_returns_pi, fiches_fiche_markowitz_black_litterman_posterior_returns_mu_bl, papier_blackrock_mean_variance_optimization, fiches_fiche_markowitz_black_litterman_real_constraints, fiche_projet_amundi_agentic_deliv_portfolio_construction_module [EXTRACTED 1.00]
- **L4 evaluation protocol** — prompts_prompt_maitre_amundi_walk_forward_backtest, prompts_prompt_maitre_amundi_evaluation_metrics, prompts_prompt_maitre_amundi_ablations, prompts_prompt_maitre_amundi_bootstrap_robustness, prompts_prompt_maitre_amundi_training_cutoff_split, prompts_prompt_maitre_amundi_anonymization_test, prompts_prompt_maitre_amundi_weekly_paper_trading, prompts_prompt_maitre_amundi_reasoning_quality_review [EXTRACTED 1.00]
- **Phase 0-9 delivery sequence** — prompts_prompt_maitre_amundi_phase_0, prompts_prompt_maitre_amundi_phase_1, prompts_prompt_maitre_amundi_phase_2, prompts_prompt_maitre_amundi_phase_3, prompts_prompt_maitre_amundi_phase_4, prompts_prompt_maitre_amundi_phase_5, prompts_prompt_maitre_amundi_phase_6, prompts_prompt_maitre_amundi_phase_7, prompts_prompt_maitre_amundi_phase_8, prompts_prompt_maitre_amundi_phase_9 [EXTRACTED 1.00]
- **Zero-cost LLM stack** — prompts_prompt_maitre_amundi_litellm, prompts_prompt_maitre_amundi_ollama_local_model, prompts_prompt_maitre_amundi_groq_free_tier, prompts_prompt_maitre_amundi_gemini_free_tier, prompts_prompt_maitre_amundi_quota_fallback_429, prompts_prompt_maitre_amundi_disk_response_cache, prompts_prompt_maitre_amundi_quota_log [EXTRACTED 1.00]
- **Extending stock selection to optimized portfolio construction** — fiche_projet_amundi_agentic_obj_optimized_portfolio_construction, fiche_projet_amundi_agentic_deliv_portfolio_construction_module, papier_blackrock_mean_variance_optimization, papier_blackrock_black_litterman, papier_blackrock_confidence_weighted_allocation, papier_blackrock_risk_tolerance_profiles [INFERRED 0.75]
- **Brief objectives mapped to AlphaAgents mechanisms (recommend, explain, evaluate)** — fiche_projet_amundi_agentic_obj_investment_recommendations, fiche_projet_amundi_agentic_obj_transparency_explainability, fiche_projet_amundi_agentic_obj_benchmark_evaluation, papier_blackrock_role_based_multi_agent_system, papier_blackrock_discussion_logs, papier_blackrock_backtesting [INFERRED 0.85]
- **Open design questions to clarify with Amundi** — fiches_fiche_projet_amundi_oq_investment_universe, fiches_fiche_projet_amundi_oq_data_sources, fiches_fiche_projet_amundi_oq_client_profile, fiches_fiche_projet_amundi_oq_llm_hosting, fiches_fiche_projet_amundi_oq_rebalancing_frequency, fiches_fiche_projet_amundi_oq_benchmark, fiche_projet_amundi_agentic_deliv_specifications [INFERRED 0.85]

## Communities (94 total, 26 thin omitted)

### Community 0 - "LLMClient abstraction (provider-agnostic, temperature 0, Pydantic outputs)"
Cohesion: 0.12
Nodes (32): Agent-based Risk Assessment, Open question: Accessible data sources (Bloomberg, Amundi internal), Arize Phoenix, Bloomberg Financial News, RAG Evaluation (faithfulness & relevance), Valuation Agent, Yahoo Finance Price & Volume Data, Sentiment Agent (allocation level, macro news RSS/GDELT) (+24 more)

### Community 1 - "Fiche de revision - AlphaAgents (papier BlackRock)"
Cohesion: 0.14
Nodes (30): Fiche de revision - AlphaAgents (papier BlackRock), Annualized Return & Volatility formulas (252 days), Summarization vs RAG choice for news, AlphaAgents: LLM-based Multi-Agents for Equity Portfolio Construction, BlackRock, Inc., Cognitive Bias Mitigation (Behavioral Finance), FinAgent, Financial Report RAG Tool (+22 more)

### Community 2 - "Fiche de revision - Markowitz et Black-Litterman"
Cohesion: 0.21
Nodes (26): Deliverable: Portfolio construction module, Objective: Optimized portfolios under risk constraints, diversification and client objectives, Fiche de revision - Markowitz et Black-Litterman, Mapping agent BUY/SELL recommendations to views Q, Black & Litterman (Goldman Sachs, 1990-1992), Covariance Matrix Sigma, Efficient Frontier, Equilibrium (implied) Returns Pi = delta Sigma w_mkt (+18 more)

### Community 3 - "Multi-agent Debate (Round Robin to consensus)"
Cohesion: 0.14
Nodes (17): Binary BUY/SELL decision (no HOLD), Groupthink Risk (forced consensus), Reproducibility / LLM Non-determinism, Zscaler ('Company Z') debate example (BUY -> SELL consensus), Improving Factuality via Multiagent Debate (Du et al. 2023), Multi-agent Debate (Round Robin to consensus), Baseline: equal weight (AlphaAgents), Baseline: Markowitz on same views (+9 more)

### Community 4 - "Deliverable: Deployment plan & integration into Amundi processes"
Cohesion: 0.19
Nodes (15): ALTO (Amundi Leading Technology & Operations), Deliverable: Deployment plan & integration into Amundi processes, Claude (LLM), End-to-end target system (recommendation -> construction -> rebalancing -> evaluation -> integration), Open question: Allowed LLMs (external vs internally hosted for confidentiality), GPT-4o, ALTO integration as API service with human validation before orders, End-of-phase report format (done, criteria, decisions, limits, questions, next) (+7 more)

### Community 5 - "Agent Risk Tolerance Profiles (risk-averse / risk-neutral)"
Cohesion: 0.23
Nodes (14): Personalized Investment Recommendations (client objectives), Drawdown, Qualitative risk profile injected in prompt (vs quantitative constraints), Risk-averse underperformance in bull market (risk/return trade-off), Combining short-term and long-term signals, Small Sample / No Statistical Significance (15 stocks, 4 months), Risk Aversion Coefficient lambda / delta, Open question: Client type, risk profiles and constraints (ESG, exclusions) (+6 more)

### Community 6 - "Fiche de revision - Projet Amundi Agentic AI"
Cohesion: 0.10
Nodes (49): Fiche projet Amundi Agentic (3rd-year project 2025-2026), Agentic AI System for Portfolio Construction, Amundi Asset Management, Amundi Technology, Deliverable: Functional prototype of recommendation agents, Deliverable: Functional & technical specifications, Deliverable: Technical documentation & user guide for asset managers, ESG Integration in Investment Processes (+41 more)

### Community 7 - "Deliverable: Performance analysis report (backtesting & live testing)"
Cohesion: 0.35
Nodes (11): Deliverable: Performance analysis report (backtesting & live testing), Look-ahead Bias (LLM training data after test period), Live Testing (real-period run), Back-testing as Down-stream Metric, Rolling Sharpe Ratio, Sharpe Ratio, Anonymization test (names and dates masked) for memorization, Metrics (Sharpe, Sortino, max drawdown, Calmar, TE, IR, turnover, ESG, LLM cost) (+3 more)

### Community 8 - "test_connectors.py"
Cohesion: 0.15
Nodes (18): _client(), _frame_yf(), Connecteurs : analyse des réponses (fixtures minuscules et synthétiques),…, test_edgar_fetch_filings_et_textes_reprise(), test_edgar_user_agent_exige_et_envoye(), test_esg_connecteur_titres_et_etf(), test_fred_fetch_series_cle_hors_cache_et_stockage(), test_fred_serie_de_marche_disponibilite_par_regle_de_delai() (+10 more)

### Community 9 - "test_rejouabilite_analyses.py"
Cohesion: 0.06
Nodes (56): 1. Besoins par objectif, O1 — Agents qui recommandent à partir d'analyses quantitatives et qualitatives (L2), O2 — Portefeuilles optimisés sous contraintes (L3), O3 — Mise à jour et ajustement automatiques (L3), O4 — Transparence et explicabilité (L2, L5), O5 — Évaluation face à des benchmarks traditionnels (L4), Exigences détaillées O1 à O5, numpy (+48 more)

### Community 10 - "prix"
Cohesion: 0.08
Nodes (47): QualityIssue, check_dated_series(), check_duplicates(), check_prices(), _d(), DataFrame, date, Contrôle qualité : trous, splits, doublons, valeurs aberrantes, séries trop… (+39 more)

### Community 11 - "Journal des décisions"
Cohesion: 0.04
Nodes (50): D-001 — Racine du dépôt (2026-10-02), D-002 — Gestionnaire d'environnement et version de Python (2026-10-02), D-003 — Emplacement des prompts de rôle (2026-10-02), D-004 — Fournisseurs LLM et adaptateurs (2026-10-02), D-005 — Outils qualité et CI (2026-10-02), D-006 — Dépendances ajoutées phase par phase (2026-10-02), D-007 — Hypothèses de cadrage en attendant Amundi (2026-10-02), D-008 — Modèles LLM retenus (2026-10-02) (+42 more)

### Community 12 - "test_pit.py"
Cohesion: 0.07
Nodes (38): _esg(), _fred(), _index(), _news(), Accès point-in-time as_of(t) : aucune donnée publiée à la coupure de t ou après…, Accepté 17:30 à New York le 31/01 = 22:30 UTC : avant la coupure du 01/02…, Pour de nombreuses dates t, aucune source ne sert une donnée datée à la coupure…, Sans le recalage, le rendement du 03/01 au 04/01 passerait de +9 % à -45 %… (+30 more)

### Community 14 - "pipeline.py"
Cohesion: 0.11
Nodes (30): calendar, collections_abc, datetime, feedparser, gzip, hashlib, html_parser, io (+22 more)

### Community 15 - "test_revue_pit_adverse.py"
Cohesion: 0.15
Nodes (16): _esg(), Revue indépendante de la phase 2 : tests adverses sur les fuites de futur…, Série mensuelle : la disponibilité part de la FIN de période (pas du début) +…, Observation du vendredi en règle `date + 1 jour` : servie dès t = samedi + 1…, Retraitement déposé par 10-K/A (absent de l'index) : valeur d'origine jusqu'à…, Deux dépôts le même jour sur la même clé : le résultat ne doit pas dépendre de…, test_esg_non_pit_ne_masque_pas_un_instantane_pit(), test_esg_strict_sert_le_dernier_instantane_avant_t_pas_apres() (+8 more)

### Community 16 - "test_specifications.py"
Cohesion: 0.09
Nodes (34): ast, fnmatch, Pattern, _cellules(), _colonne(), _composant_prevu(), _config_prevue(), _developper_accolades() (+26 more)

### Community 17 - "NewsConnector"
Cohesion: 0.16
Nodes (16): _gdelt_json(), _is_json(), _item_id(), NewsConnector, parse_gdelt(), parse_rss(), DataFrame, date (+8 more)

### Community 18 - "FredConnector"
Cohesion: 0.20
Nodes (12): FredConnector, merge_vintage_chunks(), parse_fred_observations(), DataFrame, date, Observations actuelles (sans millésimes), paginées., Observations FRED -> DataFrame. Un marqueur « . » (valeur absente) devient NaN…, Fusionne les lignes (date, valeur) contiguës dans le temps réel, coupées par le… (+4 more)

### Community 19 - "Couverture des données (phase 2)"
Cohesion: 0.08
Nodes (25): 0. Statut des téléchargements (dernier événement par élément), 1. Prix des ETF candidats et de leurs proxys (yfinance), 2. Prix de la poche titres (liste de démonstration), 3. Macro (FRED/ALFRED et BCE), 4. Dépôts SEC EDGAR et XBRL (liste de démonstration), 5. News (RSS, GDELT), 6. ESG, 7. Contrôle qualité (signalements, aucune correction appliquée) (+17 more)

### Community 20 - "test_revue_rejouabilite.py"
Cohesion: 0.11
Nodes (27): 11.3 bis Instantanés et manifeste des données (D-043), 12. Risques et parades, shutil, data_manifest(), Manifeste déterministe du stockage dérivé, des instantanés et des…, df(), Horloge, mk() (+19 more)

### Community 21 - "test_revue_robustesse.py"
Cohesion: 0.13
Nodes (21): cl(), parametrize, R, Revue indépendante de la phase 2 : robustesse réseau, secrets, atomicité,…, Sess, test_404_non_rejoue_et_timeout_epuise_les_essais(), test_article_gdelt_commun_a_deux_actifs_garde_les_deux_etiquettes(), test_codes_transitoires_rejoues_puis_succes() (+13 more)

### Community 22 - "test_socle_revue.py"
Cohesion: 0.12
Nodes (13): subprocess, _fichiers_commitables(), parametrize, Path, Tests complémentaires du socle (revue phase 0) : CI, version de Python, secrets., Fichiers suivis ou non ignorés : ce qui partirait dans un `git add -A`., Aucune valeur pré-remplie, y compris hors suffixe KEY (ex. User-Agent avec…, ANTHROPIC_API_KEY ne doit apparaître que pour être interdite, jamais être lue. (+5 more)

### Community 23 - ".snapshot"
Cohesion: 0.17
Nodes (7): D-046 — Points de la couche de données reportés (2026-10-02), DataFrame, datetime, Path, Fusionne `df` dans le jeu ; la dernière ligne l'emporte sur une clé identique.…, Écrit les données brutes reçues dans `snapshots/<source>/<AAAA-MM-…, Tous les instantanés d'un jeu, avec colonnes snapshot_date et origin (ordre…

### Community 24 - "test_http_store.py"
Cohesion: 0.20
Nodes (17): requests, client(), FauxResp, Cache disque, débit, backoff, secrets (jamais dans le cache) ; stockage Parquet…, test_404_non_rejoue(), test_backoff_exponentiel_sur_429_puis_succes(), test_cache_persiste_entre_clients(), test_echec_definitif_apres_max_essais_non_mis_en_cache() (+9 more)

### Community 25 - "coverage.py"
Cohesion: 0.14
Nodes (18): argparse, collections, main(), Interface en ligne de commande (D-010). Phase 2 : sous-commande `data`. amundi-…, main(), Path, Rapport de couverture des données, généré par script (aucun chiffre écrit à la…, write_report() (+10 more)

### Community 26 - "FilingsConnector"
Cohesion: 0.26
Nodes (7): FilingsConnector, parse_company_facts(), parse_company_tickers(), DataFrame, Télécharge le texte des 10-K et 10-Q (reprise : les textes déjà stockés sont…, _rows_from_columns(), test_parse_company_tickers_et_facts()

### Community 27 - "Report"
Cohesion: 0.21
Nodes (4): _fmt(), md_table(), Date de début du backtest permise par classe (260 semaines d'historique avant…, Report

### Community 28 - "pit.py"
Cohesion: 0.17
Nodes (15): Couche de données (phase 2). Connecteurs de données gratuites, stockage Parquet…, EsgRecord, Filing, LookAheadError, NewsItem, NewsQuery, Modèles de données de la couche `data/` (sans dépendance vers un autre module…, Une donnée publiée à la coupure de t ou après a été demandée ou servie. (+7 more)

### Community 29 - "PricesConnector"
Cohesion: 0.15
Nodes (15): Fetcher, NoDataError, normalize(), PricesConnector, DataFrame, date, Path, RuntimeError (+7 more)

### Community 30 - "settings.py"
Cohesion: 0.12
Nodes (16): dataclasses, os, Catégories d'exclusion dont un intervalle SIC contient `sic` (règles `enforce:…, sic_exclusions(), load_dotenv(), load_yaml(), Any, Chemins, configuration et secrets. Les secrets ne sont jamais affichés ni… (+8 more)

### Community 31 - "test_revue_corrections.py"
Cohesion: 0.14
Nodes (13): sys, _feries_federaux(), _jour_ouvre_suivant(), date, Contre-vérification indépendante des corrections de la revue phase 2 (B1, N1,…, Premier jour ouvré américain STRICTEMENT après d (week-end et fériés exclus)., Tout .py de tests/data visible en premier niveau doit avoir un nom spécifique…, Fériés fédéraux américains calculés par règles (indépendant de pandas), avec… (+5 more)

### Community 32 - "ParquetStore"
Cohesion: 0.17
Nodes (5): Recalcule `accepted_utc` de tous les index depuis `acceptance_raw` (sans…, reindex_acceptance(), ParquetStore, Ajoute un événement (ok, error, unavailable). `detail` doit déjà être expurgé…, test_reindexation_sans_reseau_selon_le_mode()

### Community 33 - "test_config.py"
Cohesion: 0.11
Nodes (8): 4. Agents et prompts de rôle, Grandes lignes des prompts de rôle (fichiers `agent_prompts/<agent>_v1.md` en phase 3), Configuration LLM : modèles déclarés dans config/, jamais codés en dur (C1,…, Tests complémentaires de config/llm.yaml (revue de D-008)., La config ne nomme que des variables d'environnement, jamais une valeur de clé., test_variables_d_environnement_et_non_valeurs(), test_aucun_nom_de_modele_dans_le_code(), yaml

### Community 34 - "ts"
Cohesion: 0.18
Nodes (12): cutoff_utc(), date, Timestamp, Instant de coupure : t 00:00 heure de Paris, en UTC., Timestamp, ts(), test_acceptation_mode_brut_toujours_posterieur_ou_egal(), test_coupure_hiver_et_ete() (+4 more)

### Community 35 - "ny_local_to_utc"
Cohesion: 0.18
Nodes (11): ny_local_to_utc(), datetime, Timestamp, Heure de New York (sans fuseau) -> UTC. Règle de D-023 pour un horodatage en…, parametrize, Règle prudente (raw_as_utc) : l'instant servi n'est jamais antérieur à…, test_acceptation_par_defaut_jamais_anterieure_a_l_instant_reel(), test_heure_new_york_vers_utc_hiver_et_ete() (+3 more)

### Community 36 - "manifest.py"
Cohesion: 0.31
Nodes (9): pathlib, platform, pyarrow_parquet, _describe(), _entries(), _event_key(), Path, Manifeste des données (rejouabilité) : hash de chaque jeu, versions, hash des… (+1 more)

### Community 37 - "DataSettings"
Cohesion: 0.15
Nodes (14): make_http_client(), DataSettings, Path, env(), fixture, _faux(), FauxPrix, fixture (+6 more)

### Community 38 - "PointInTimeStore"
Cohesion: 0.40
Nodes (4): PointInTimeStore, test_fred_alfred_gdpc1_millesimes(), Chemin réel : `fetch_series` (réponse simulée) puis `as_of`, attendu issu du…, test_n1_jours_feries_via_fetch_series_puis_as_of()

### Community 39 - "pit_prices"
Cohesion: 0.15
Nodes (17): pit_prices(), Barres connues à t, recalées des seuls splits et dividendes connus à t., _monde_brut(), parametrize, Split daté t-1 : connu (prix post-split). Split daté t : inconnu, prix pré-…, Invariant prudent : l'instant servi n'est jamais antérieur à l'instant brut lu…, Prix BRUTS (non ajustés) tels que cotés à chaque séance, avec splits et…, Ce que Yahoo sert : clôtures ajustées des splits connus à la date de… (+9 more)

### Community 40 - "pytest"
Cohesion: 0.17
Nodes (13): 11.1 Tableau, Contraintes transverses du prompt maître, importlib, pytest, test_requete_identique_servie_par_le_cache(), test_fournisseurs_gratuits_uniquement(), parametrize, Tests du socle (phase 0) : structure du dépôt et hygiène des secrets. (+5 more)

### Community 41 - "EsgConnector"
Cohesion: 0.32
Nodes (4): enforced(), EsgConnector, datetime, VendorFetcher

### Community 42 - "add_us_business_days"
Cohesion: 0.20
Nodes (9): CustomBusinessDay, add_us_business_days(), Series, Jours ouvrés américains (fériés fédéraux exclus), sans dépendance nouvelle., `dates` + n jours ouvrés américains, vectorisé (équivalent à `dates +…, us_business_days(), test_lag_rule_saute_les_jours_feries_americains(), test_jours_ouvres_vectorises_identiques_a_pandas() (+1 more)

### Community 43 - "11. Exigences non fonctionnelles"
Cohesion: 0.33
Nodes (6): 11.2 Budget d'appels, 11.3 Point-in-time : règles par source, 11.4 Objet de l'évaluation (L4) et limites de preuve, 11.5 Protocole d'anonymisation (EX-O5-06), 11.6 Pré-enregistrement (EX-O5-12), 11. Exigences non fonctionnelles

### Community 44 - "_TextExtractor"
Cohesion: 0.22
Nodes (4): html_to_text(), HTMLParser, _TextExtractor, test_html_to_text_retire_scripts_et_entete_ixbrl()

### Community 45 - "7. Construction Black-Litterman"
Cohesion: 0.22
Nodes (9): 7.1 Univers de l'optimisation, 7.2 Covariance Σ, 7.3 A priori, 7.4 Vues : P, Q et calibration de κ, 7.5 Ω (Idzorek) et τ, 7.6 Optimisation (cvxpy), 7.7 Attribution par vue (pour `explain/attribution.py`), 7.8 Méthodes de comparaison (+1 more)

### Community 46 - "_Tables"
Cohesion: 0.22
Nodes (5): parse_constituents_html(), HTMLParser, Symboles du premier tableau ayant les colonnes Symbol et GICS Sector, filtrés…, _Tables, test_analyse_du_tableau_de_constituants()

### Community 47 - "HttpClient"
Cohesion: 0.30
Nodes (4): HttpClient, HttpResponse, Any, GET avec cache. `ttl_s=None` : le cache n'expire jamais (reproductibilité).

### Community 48 - "5. Schémas de données (Pydantic, `schemas.py`)"
Cohesion: 0.25
Nodes (8): 5.1 Décision à 5 niveaux, 5.2 `Source` et `View` (section 3.4 du prompt), 5.3 Autres sorties d'agents, 5.4 Journal de débat, 5.5 Proposition de rééquilibrage, 5.6 Fiche d'explication, 5.7 Enregistrement d'exécution, 5. Schémas de données (Pydantic, `schemas.py`)

### Community 49 - "test_dependances_entre_modules"
Cohesion: 0.25
Nodes (8): D-010 — Modèles de données partagés (2026-10-02), 15. Plan de tests, _imports(), Path, Modules importés, imports relatifs résolus par rapport à `paquet` (ex.…, L1 3.2 : aucun SDK de fournisseur hors de llm/ ; portfolio/ n'importe ni llm ni…, _sdk_interdit(), test_dependances_entre_modules()

### Community 50 - "Prompt maître — Système agentique Amundi"
Cohesion: 0.29
Nodes (6): 1. Rôle, mission et contexte, 2. Règles de travail et garde-fous, 3. Architecture cible, 4. Les phases, 5. Évaluation, dépôt et compte rendu, Prompt maître — Système agentique Amundi

### Community 51 - "L1 — Spécifications fonctionnelles et techniques"
Cohesion: 0.33
Nodes (5): 14. Écarts avec AlphaAgents, 16. Entrées proposées pour `DECISIONS.md` et `QUESTIONS_AMUNDI.md`, 2. Cas d'usage du gérant, L1 — Spécifications fonctionnelles et techniques, Sommaire

### Community 52 - "6. Flux du débat"
Cohesion: 0.33
Nodes (6): 6.1 Déroulé, 6.2 Règle de consensus, 6.3 Avocat du diable tournant, 6.4 Du consensus à la confiance d'Idzorek, 6.5 Journalisation, 6. Flux du débat

### Community 53 - "redact"
Cohesion: 0.18
Nodes (12): Retire des secrets d'un texte : motifs `api_key=...` et valeurs connues de…, redact(), _guard(), faire(), cfg(), pit(), fixture, Fabriques de données synthétiques pour les tests de la couche `data/` (aucun… (+4 more)

### Community 54 - "edgar_acceptance_to_utc"
Cohesion: 0.18
Nodes (13): edgar_acceptance_to_utc(), parse_filings(), Horodatage `acceptanceDateTime` de l'API submissions lu comme UTC (règle…, test_parse_filings_ecarte_un_depot_sans_acceptation(), parametrize, test_b1_config_par_defaut_et_mode_corrected_supprime(), test_b1_defaut_jamais_avant_acceptation_reelle(), test_n7_depots_du_meme_jour_departages_par_acceptation_pas_par_accn() (+5 more)

### Community 55 - "EcbConnector"
Cohesion: 0.24
Nodes (5): FxConnector, EcbConnector, parse_ecb_csv(), CSV SDMX de la BCE -> colonnes date (début de période), period_end, value., test_parse_ecb_csv_quotidien_et_mensuel()

### Community 56 - "Projet Amundi Agentic — instructions pour Claude Code"
Cohesion: 0.33
Nodes (5): graphify, Projet Amundi Agentic — instructions pour Claude Code, Rappels non négociables, Règles d'orchestration, Ton équipe (sous-agents dans `.claude/agents/`)

### Community 57 - "10. Règles de rééquilibrage"
Cohesion: 0.40
Nodes (5): 10.1 Calendrier et déclencheurs, 10.2 Volume de vues, 10.3 Coûts de transaction (aller simple, en points de base, H), 10.4 Limite de rotation et file de validation, 10. Règles de rééquilibrage

### Community 58 - "9. Univers"
Cohesion: 0.40
Nodes (5): 9.1 Classes d'actifs et ETF candidats, 9.2 Poche actions individuelles, 9.3 Les 15 titres de la réplication AlphaAgents, 9.4 ESG des ETF, 9. Univers

### Community 59 - "Avancement"
Cohesion: 0.40
Nodes (4): Avancement, Phase 0 — 2026-10-02, Phase 1 — 2026-10-02, Phase 2 — 2026-10-02

### Community 60 - "Amundi Agentic"
Cohesion: 0.40
Nodes (4): Amundi Agentic, Installation, Organisation, État

### Community 61 - "SessionJson"
Cohesion: 0.20
Nodes (5): Session factice : renvoie une charge utile selon la fin de l'URL., Resp, SessionAvecErreurs, SessionJson, test_fred_serie_inexistante_signalee_indisponible()

### Community 62 - "3. Architecture"
Cohesion: 0.50
Nodes (4): 3.1 Vue d'ensemble, 3.2 Modules (conformes à la section 5.2, D-003, D-004), 3.3 Interfaces principales (signatures, pseudo-code), 3. Architecture

### Community 63 - "HttpError"
Cohesion: 0.29
Nodes (5): Session, HttpError, Path, RuntimeError, Échec définitif d'une requête (message expurgé de tout secret).

### Community 64 - "8. Profils clients"
Cohesion: 0.50
Nodes (4): 8.1 Benchmark par profil, 8.2 δ, volatilité plafond, tracking error, rotation, 8.3 Bornes par classe (H, en % du portefeuille), 8. Profils clients

### Community 78 - "Matrice de traçabilité : exigences → composants → tests"
Cohesion: 0.40
Nodes (4): Exigences non fonctionnelles sans contrainte C dédiée, Livrables, Matrice de traçabilité : exigences → composants → tests, Objectifs du cahier des charges

### Community 79 - "D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)"
Cohesion: 0.50
Nodes (4): Conditions d'utilisation des niveaux gratuits, D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03), Date de fin d'entraînement (borne de contamination de D-025), Limites du niveau gratuit

### Community 88 - "13. Choix du cadre d'orchestration : LangGraph ou AutoGen"
Cohesion: 0.50
Nodes (4): 13.1 Relevé (2026-10-02, en ligne de commande), 13.2 Comparaison sur les trois critères, 13.3 Choix proposé, 13. Choix du cadre d'orchestration : LangGraph ou AutoGen

### Community 90 - "MissingSecretError"
Cohesion: 0.67
Nodes (3): MissingSecretError, RuntimeError, Variable d'environnement absente (seul le NOM de la variable est indiqué,…

## Ambiguous Edges - Review These
- `Sentiment Agent` → `Objective: Automated portfolio updating/adjustment on market signals`  [AMBIGUOUS]
  papier BlackRock.pdf · relation: conceptually_related_to
- `Role-based Multi-Agent System for Equity Research` → `ESG Integration in Investment Processes`  [AMBIGUOUS]
  Fiche projet Amundi Agentic.pdf · relation: conceptually_related_to
- `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` → `Look-ahead Bias (LLM training data after test period)`  [AMBIGUOUS]
  fiches/fiche_projet_amundi.md · relation: conceptually_related_to

## Knowledge Gaps
- **147 isolated node(s):** `D-001 — Racine du dépôt (2026-10-02)`, `D-002 — Gestionnaire d'environnement et version de Python (2026-10-02)`, `D-003 — Emplacement des prompts de rôle (2026-10-02)`, `D-004 — Fournisseurs LLM et adaptateurs (2026-10-02)`, `D-005 — Outils qualité et CI (2026-10-02)` (+142 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 430 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Sentiment Agent` and `Objective: Automated portfolio updating/adjustment on market signals`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Role-based Multi-Agent System for Equity Research` and `ESG Integration in Investment Processes`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` and `Look-ahead Bias (LLM training data after test period)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `ParquetStore` connect `ParquetStore` to `test_connectors.py`, `test_rejouabilite_analyses.py`, `prix`, `pipeline.py`, `NewsConnector`, `FredConnector`, `test_revue_rejouabilite.py`, `test_revue_robustesse.py`, `.snapshot`, `test_http_store.py`, `coverage.py`, `FilingsConnector`, `Report`, `pit.py`, `PricesConnector`, `settings.py`, `ts`, `manifest.py`, `DataSettings`, `PointInTimeStore`, `EsgConnector`, `_TextExtractor`, `redact`, `EcbConnector`, `SessionJson`, `test_points_de_reprise_jamais_dans_les_donnees_servies`, `test_ecriture_atomique_un_echec_laisse_l_ancien_fichier`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Why does `Journal des décisions` connect `Journal des décisions` to `test_dependances_entre_modules`, `D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)`, `.snapshot`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `test_dependances_entre_modules()` connect `test_dependances_entre_modules` to `pytest`, `test_specifications.py`, `13. Choix du cadre d'orchestration : LangGraph ou AutoGen`, `3. Architecture`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 54 inferred relationships involving `ParquetStore` (e.g. with `EsgConnector` and `FilingsConnector`) actually correct?**
  _`ParquetStore` has 54 INFERRED edges - model-reasoned connections that need verification._