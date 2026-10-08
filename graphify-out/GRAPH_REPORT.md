# Graph Report - Amundi Agentic  (2026-10-07)

## Corpus Check
- 282 files · ~290,344 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 4, .example 1)

## Summary
- 1478 nodes · 3167 edges · 106 communities (79 shown, 27 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 418 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ccd57746`
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
- Universe
- Report
- Journal des décisions
- test_pit.py
- Academic prototype disclaimer (not investment advice)
- pipeline.py
- test_revue_pit_adverse.py
- test_specifications.py
- news.py
- FredConnector
- Couverture des données (phase 2)
- test_revue_rejouabilite.py
- HttpError
- test_revue_corrections.py
- test_revue_verrou_quotas.py
- test_http_store.py
- test_corrections_n1_a_n7.py
- DataView
- DataSettings
- analysis.py
- normalize
- coverage.py
- pytest
- ParquetStore
- test_revue_config_reelle.py
- test_rejouabilite_analyses.py
- FilingsConnector
- prix
- test_revue_robustesse.py
- test_socle_revue.py
- test_config.py
- test_revue_quotas_relais.py
- esg.py
- test_universe_coverage.py
- _Tables
- edgar_acceptance_to_utc
- 7. Construction Black-Litterman
- test_quotas_et_cout.py
- 9. Univers
- 5. Schémas de données (Pydantic, `schemas.py`)
- cli.py
- Prompt maître — Système agentique Amundi
- L1 — Spécifications fonctionnelles et techniques
- 6. Flux du débat
- Contraintes transverses du prompt maître
- 11. Exigences non fonctionnelles
- require_secret
- Projet Amundi Agentic — instructions pour Claude Code
- ny_local_to_utc
- .snapshot
- Avancement
- Amundi Agentic
- add_us_business_days
- FauxPrix
- test_network.py
- run_fetch
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
- .get
- D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)
- amundi-agentic
- parametrize
- esg_matrix
- quality.py
- Horloge
- test_revue_hygiene_texte.py
- test_config_revue.py
- _serie_regime
- 10. Règles de rééquilibrage
- 3. Architecture
- _alternee
- 8. Profils clients
- parametrize
- test_n2_cout_du_repli_par_rejeu_de_52_semaines_raisonnable
- test_dependances_entre_modules
- test_relais_groq_de_bout_en_bout_declenche_l_alerte_de_la_config_reelle
- test_limite_booleenne_refusee
- test_n5_source_id_np_float64_et_float_donnent_le_meme_identifiant
- test_n1_de_bout_en_bout_creux_de_10_pourcent_isole_dans_risk_report

## God Nodes (most connected - your core abstractions)
1. `ParquetStore` - 99 edges
2. `Journal des décisions` - 71 edges
3. `Fiche de revision - AlphaAgents (papier BlackRock)` - 66 edges
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

## Communities (106 total, 27 thin omitted)

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
Cohesion: 0.10
Nodes (22): _client(), _frame_yf(), Connecteurs : analyse des réponses (fixtures minuscules et synthétiques),…, Session factice : renvoie une charge utile selon la fin de l'URL., Resp, SessionAvecErreurs, SessionJson, test_edgar_fetch_filings_et_textes_reprise() (+14 more)

### Community 9 - "Universe"
Cohesion: 0.19
Nodes (14): composition(), Timestamp, Composition de chaque série de classe par date : proxy converti (synthétique)…, AssetClassSpec, Candidate, Universe, test_composition_ne_cite_pas_une_serie_publique_qui_n_existe_pas_avant_l_etf(), test_composition_par_date() (+6 more)

### Community 10 - "Report"
Cohesion: 0.21
Nodes (4): _fmt(), md_table(), Date de début du backtest permise par classe (260 semaines d'historique avant…, Report

### Community 11 - "Journal des décisions"
Cohesion: 0.03
Nodes (67): D-001 — Racine du dépôt (2026-10-02), D-002 — Gestionnaire d'environnement et version de Python (2026-10-02), D-003 — Emplacement des prompts de rôle (2026-10-02), D-004 — Fournisseurs LLM et adaptateurs (2026-10-02), D-005 — Outils qualité et CI (2026-10-02), D-006 — Dépendances ajoutées phase par phase (2026-10-02), D-007 — Hypothèses de cadrage en attendant Amundi (2026-10-02), D-008 — Modèles LLM retenus (2026-10-02) (+59 more)

### Community 12 - "test_pit.py"
Cohesion: 0.07
Nodes (35): _esg(), _fred(), _index(), _news(), Accès point-in-time as_of(t) : aucune donnée publiée à la coupure de t ou après…, Accepté 17:30 à New York le 31/01 = 22:30 UTC : avant la coupure du 01/02…, Sans le recalage, le rendement du 03/01 au 04/01 passerait de +9 % à -45 %…, _store_prix() (+27 more)

### Community 14 - "pipeline.py"
Cohesion: 0.11
Nodes (24): dataclasses, html_parser, io, logging, pandas, pandas_tseries_holiday, random, re (+16 more)

### Community 15 - "test_revue_pit_adverse.py"
Cohesion: 0.07
Nodes (42): Timestamp, ts(), test_coupure_hiver_et_ete(), _esg(), _items(), _monde_brut(), parametrize, Revue indépendante de la phase 2 : tests adverses sur les fuites de futur… (+34 more)

### Community 16 - "test_specifications.py"
Cohesion: 0.09
Nodes (33): fnmatch, Pattern, _cellules(), _colonne(), _composant_prevu(), _config_prevue(), _developper_accolades(), _developper_plages() (+25 more)

### Community 17 - "news.py"
Cohesion: 0.17
Nodes (17): calendar, feedparser, _gdelt_json(), _is_json(), _item_id(), NewsConnector, parse_gdelt(), parse_rss() (+9 more)

### Community 18 - "FredConnector"
Cohesion: 0.18
Nodes (12): FredConnector, merge_vintage_chunks(), parse_fred_observations(), DataFrame, date, Observations actuelles (sans millésimes), paginées., Observations FRED -> DataFrame. Un marqueur « . » (valeur absente) devient NaN…, Fusionne les lignes (date, valeur) contiguës dans le temps réel, coupées par le… (+4 more)

### Community 19 - "Couverture des données (phase 2)"
Cohesion: 0.08
Nodes (25): 0. Statut des téléchargements (dernier événement par élément), 1. Prix des ETF candidats et de leurs proxys (yfinance), 2. Prix de la poche titres (liste de démonstration), 3. Macro (FRED/ALFRED et BCE), 4. Dépôts SEC EDGAR et XBRL (liste de démonstration), 5. News (RSS, GDELT), 6. ESG, 7. Contrôle qualité (signalements, aucune correction appliquée) (+17 more)

### Community 20 - "test_revue_rejouabilite.py"
Cohesion: 0.09
Nodes (33): hashlib, platform, pyarrow_parquet, shutil, data_manifest(), _describe(), _entries(), _event_key() (+25 more)

### Community 21 - "HttpError"
Cohesion: 0.21
Nodes (16): HttpError, RuntimeError, Échec définitif d'une requête (message expurgé de tout secret)., cl(), parametrize, R, test_404_non_rejoue_et_timeout_epuise_les_essais(), test_article_gdelt_commun_a_deux_actifs_garde_les_deux_etiquettes() (+8 more)

### Community 22 - "test_revue_corrections.py"
Cohesion: 0.14
Nodes (11): sys, _feries_federaux(), _jour_ouvre_suivant(), date, Contre-vérification indépendante des corrections de la revue phase 2 (B1, N1,…, Premier jour ouvré américain STRICTEMENT après d (week-end et fériés exclus)., Tout .py de tests/data visible en premier niveau doit avoir un nom spécifique…, Fériés fédéraux américains calculés par règles (indépendant de pandas), avec… (+3 more)

### Community 23 - "test_revue_verrou_quotas.py"
Cohesion: 0.08
Nodes (49): amundi_agentic_llm, amundi_agentic_llm_quotas, contextlib, multiprocessing, os, signal, slow, f() (+41 more)

### Community 24 - "test_http_store.py"
Cohesion: 0.16
Nodes (20): requests, client(), FausseSession, FauxResp, Cache disque, débit, backoff, secrets (jamais dans le cache) ; stockage Parquet…, test_404_non_rejoue(), test_backoff_exponentiel_sur_429_puis_succes(), test_cache_persiste_entre_clients() (+12 more)

### Community 25 - "test_corrections_n1_a_n7.py"
Cohesion: 0.09
Nodes (14): amundi_agentic_tools, amundi_agentic_tools_base, amundi_agentic_tools_macro_regime, math, _panel_vix(), Contre-vérification indépendante des corrections N1 à N7 des outils de calcul…, `RiskReport.indisponibles` peut contenir `__regime__` et `__vix__` (pas des…, test_n3_valuation_summary_marque_les_ratios_refuses_pas_de_nombre() (+6 more)

### Community 26 - "DataView"
Cohesion: 0.14
Nodes (16): LookAheadError, RuntimeError, Une donnée publiée à la coupure de t ou après a été demandée ou servie., cutoff_utc(), DataView, pit_prices(), DataFrame, date (+8 more)

### Community 27 - "DataSettings"
Cohesion: 0.21
Nodes (12): DataSettings, Path, _faux(), fixture, Orchestration : reprise après interruption, erreurs isolées, secrets expurgés…, test_erreur_isolee_et_secret_expurge(), test_reprise_apres_interruption_ne_refait_que_l_echec(), test_sans_reprise_tout_est_rejoue() (+4 more)

### Community 28 - "analysis.py"
Cohesion: 0.21
Nodes (10): numpy, cross_check(), drawdown_episodes(), drawdown_table(), Series, Calculs du rapport de couverture : liquidité, contrôle croisé, matrice ESG,…, Creux (pic -> creux -> récupération) d'amplitude >= `threshold`, sur une série…, Creux par fenêtre (début -> fin de la série), avec la variation du taux sur… (+2 more)

### Community 29 - "normalize"
Cohesion: 0.14
Nodes (13): Fetcher, NoDataError, normalize(), DataFrame, date, Path, RuntimeError, Télécharge ou met à jour un ticker. Retourne un résumé (jamais de secret). (+5 more)

### Community 30 - "coverage.py"
Cohesion: 0.15
Nodes (17): collections, collections_abc, datetime, gzip, json, pathlib, Prix ETF et actions via yfinance (sans clé). Limites : yfinance n'est pas une…, Rapport de couverture des données, généré par script (aucun chiffre écrit à la… (+9 more)

### Community 31 - "pytest"
Cohesion: 0.15
Nodes (10): fixture, importlib, pytest, subprocess, _delai_par_defaut_des_sous_processus(), Réglages communs de la suite : tests lents ignorés par défaut, délai sur les…, parametrize, Tests du socle (phase 0) : structure du dépôt et hygiène des secrets. (+2 more)

### Community 32 - "ParquetStore"
Cohesion: 0.11
Nodes (10): Recalcule `accepted_utc` de tous les index depuis `acceptance_raw` (sans…, reindex_acceptance(), ParquetStore, DataFrame, datetime, Path, Fusionne `df` dans le jeu ; la dernière ligne l'emporte sur une clé identique.…, Ajoute un événement (ok, error, unavailable). `detail` doit déjà être expurgé… (+2 more)

### Community 33 - "test_revue_config_reelle.py"
Cohesion: 0.12
Nodes (4): amundi_agentic_llm_config, _brut(), Revue indépendante : limites de quota et dates de fin d'entraînement de…, test_training_cutoff_ne_contient_que_des_dates_aaaa_mm_jj_valides()

### Community 34 - "test_rejouabilite_analyses.py"
Cohesion: 0.13
Nodes (27): 1. Besoins par objectif, O1 — Agents qui recommandent à partir d'analyses quantitatives et qualitatives (L2), O3 — Mise à jour et ajustement automatiques (L3), O4 — Transparence et explicabilité (L2, L5), O5 — Évaluation face à des benchmarks traditionnels (L4), Exigences détaillées O1 à O5, test_parse_gdelt_seendate(), Pour de nombreuses dates t, aucune source ne sert une donnée datée à la coupure… (+19 more)

### Community 35 - "FilingsConnector"
Cohesion: 0.13
Nodes (11): FilingsConnector, html_to_text(), parse_company_facts(), parse_company_tickers(), DataFrame, HTMLParser, Télécharge le texte des 10-K et 10-Q (reprise : les textes déjà stockés sont…, _rows_from_columns() (+3 more)

### Community 36 - "prix"
Cohesion: 0.28
Nodes (19): check_prices(), prix(), DataFrame, Fabriques de données synthétiques partagées par les tests de `data/`., kinds(), Contrôle qualité : trous, splits, doublons, aberrations, historique court,…, serie(), test_devise_incoherente_signalee() (+11 more)

### Community 37 - "test_revue_robustesse.py"
Cohesion: 0.12
Nodes (12): Revue indépendante de la phase 2 : robustesse réseau, secrets, atomicité,…, Les fichiers de reprise/journal ne sont pas des jeux de données (ni .parquet)., Les motifs de clé (api_key=<valeur>) n'apparaissent dans aucun fichier suivi du…, Sess, test_aucun_secret_ecrit_dans_les_fichiers_du_depot_de_donnees(), test_ecriture_atomique_un_echec_laisse_l_ancien_fichier(), test_points_de_reprise_jamais_dans_les_donnees_servies(), test_points_de_reprise_survivent_a_un_nouveau_processus() (+4 more)

### Community 38 - "test_socle_revue.py"
Cohesion: 0.13
Nodes (12): _fichiers_commitables(), parametrize, Path, Tests complémentaires du socle (revue phase 0) : CI, version de Python, secrets., Fichiers suivis ou non ignorés : ce qui partirait dans un `git add -A`., Aucune valeur pré-remplie, y compris hors suffixe KEY (ex. User-Agent avec…, ANTHROPIC_API_KEY ne doit apparaître que pour être interdite, jamais être lue., test_aucune_cle_anthropic_hors_interdictions() (+4 more)

### Community 39 - "test_config.py"
Cohesion: 0.20
Nodes (5): 4. Agents et prompts de rôle, Grandes lignes des prompts de rôle (fichiers `agent_prompts/<agent>_v1.md` en phase 3), Configuration LLM : modèles déclarés dans config/, jamais codés en dur (C1,…, test_aucun_nom_de_modele_dans_le_code(), yaml

### Community 40 - "test_revue_quotas_relais.py"
Cohesion: 0.06
Nodes (27): BaseModel, pydantic, cfg_limites(), Horloge, msg(), parametrize, Revue indépendante : quotas (journal, minuit UTC, alerte, concurrence), relais…, Rep (+19 more)

### Community 41 - "esg.py"
Cohesion: 0.18
Nodes (10): enforced(), EsgConnector, datetime, ESG : exclusions par secteur (code SIC EDGAR) et scores gratuits disponibles.…, Score et indicateurs d'implication de yfinance ; None si le fournisseur n'a…, Catégories d'exclusion dont un intervalle SIC contient `sic` (règles `enforce:…, sic_exclusions(), yfinance_sustainability() (+2 more)

### Community 42 - "test_universe_coverage.py"
Cohesion: 0.16
Nodes (17): O2 — Portefeuilles optimisés sous contraintes (L3), convert_to_eur(), money_market_index(), Series, Prix en devise -> EUR au fixing BCE du jour, sinon au dernier fixing de moins…, Chaîne les rendements du proxy avant la première date de `primary`, ceux de…, Indice monétaire capitalisé ACT/360 : EONIA jusqu'à la veille de `splice_date`,…, Splice (+9 more)

### Community 43 - "_Tables"
Cohesion: 0.22
Nodes (5): parse_constituents_html(), HTMLParser, Symboles du premier tableau ayant les colonnes Symbol et GICS Sector, filtrés…, _Tables, test_analyse_du_tableau_de_constituants()

### Community 44 - "edgar_acceptance_to_utc"
Cohesion: 0.16
Nodes (14): edgar_acceptance_to_utc(), parse_filings(), Horodatage `acceptanceDateTime` de l'API submissions lu comme UTC (règle…, test_acceptation_mode_brut_toujours_posterieur_ou_egal(), test_parse_filings_ecarte_un_depot_sans_acceptation(), parametrize, test_b1_config_par_defaut_et_mode_corrected_supprime(), test_b1_defaut_jamais_avant_acceptation_reelle() (+6 more)

### Community 45 - "7. Construction Black-Litterman"
Cohesion: 0.22
Nodes (9): 7.1 Univers de l'optimisation, 7.2 Covariance Σ, 7.3 A priori, 7.4 Vues : P, Q et calibration de κ, 7.5 Ω (Idzorek) et τ, 7.6 Optimisation (cvxpy), 7.7 Attribution par vue (pour `explain/attribution.py`), 7.8 Méthodes de comparaison (+1 more)

### Community 46 - "test_quotas_et_cout.py"
Cohesion: 0.21
Nodes (13): amundi_agentic_llm_types, jour(), Journal des quotas, alerte avant la limite, suivi des jetons et du coût (EX-…, Jamais de valeur inventée : seule la limite relevée du modèle de relais Groq…, test_429_comptes_dans_le_journal(), test_alerte_a_80_pourcent_du_quota(), test_alerte_journalisee_dans_le_log(), test_cout_nul_au_niveau_gratuit_mais_calcul_present() (+5 more)

### Community 47 - "9. Univers"
Cohesion: 0.40
Nodes (5): 9.1 Classes d'actifs et ETF candidats, 9.2 Poche actions individuelles, 9.3 Les 15 titres de la réplication AlphaAgents, 9.4 ESG des ETF, 9. Univers

### Community 48 - "5. Schémas de données (Pydantic, `schemas.py`)"
Cohesion: 0.25
Nodes (8): 5.1 Décision à 5 niveaux, 5.2 `Source` et `View` (section 3.4 du prompt), 5.3 Autres sorties d'agents, 5.4 Journal de débat, 5.5 Proposition de rééquilibrage, 5.6 Fiche d'explication, 5.7 Enregistrement d'exécution, 5. Schémas de données (Pydantic, `schemas.py`)

### Community 49 - "cli.py"
Cohesion: 0.25
Nodes (10): argparse, main(), Interface en ligne de commande (D-010). Phase 2 : sous-commande `data`. amundi-…, main(), Path, write_report(), write_manifest(), Initialise des instantanés depuis le stockage dérivé, SANS réseau. Étiquetés «… (+2 more)

### Community 50 - "Prompt maître — Système agentique Amundi"
Cohesion: 0.29
Nodes (6): 1. Rôle, mission et contexte, 2. Règles de travail et garde-fous, 3. Architecture cible, 4. Les phases, 5. Évaluation, dépôt et compte rendu, Prompt maître — Système agentique Amundi

### Community 51 - "L1 — Spécifications fonctionnelles et techniques"
Cohesion: 0.33
Nodes (5): 14. Écarts avec AlphaAgents, 16. Entrées proposées pour `DECISIONS.md` et `QUESTIONS_AMUNDI.md`, 2. Cas d'usage du gérant, L1 — Spécifications fonctionnelles et techniques, Sommaire

### Community 52 - "6. Flux du débat"
Cohesion: 0.29
Nodes (7): 6.1 Déroulé, 6.2 Règle de consensus, 6.3 Avocat du diable tournant, 6.4 Du consensus à la confiance d'Idzorek, 6.5 Journalisation, 6. Flux du débat, h()

### Community 53 - "Contraintes transverses du prompt maître"
Cohesion: 0.18
Nodes (10): 11.1 Tableau, Contraintes transverses du prompt maître, Exigences non fonctionnelles sans contrainte C dédiée, Livrables, Matrice de traçabilité : exigences → composants → tests, Objectifs du cahier des charges, test_fournisseurs_gratuits_uniquement(), test_env_example_sans_secret_ni_cle_anthropic() (+2 more)

### Community 54 - "11. Exigences non fonctionnelles"
Cohesion: 0.22
Nodes (9): 11.2 Budget d'appels, 11.3 bis Instantanés et manifeste des données (D-043), 11.3 Point-in-time : règles par source, 11.4 Objet de l'évaluation (L4) et limites de preuve, 11.5 Protocole d'anonymisation (EX-O5-06), 11.6 Pré-enregistrement (EX-O5-12), 11. Exigences non fonctionnelles, 12. Risques et parades (+1 more)

### Community 55 - "require_secret"
Cohesion: 0.29
Nodes (8): MissingSecretError, Variable d'environnement absente (seul le NOM de la variable est indiqué,…, load_dotenv(), Charge `.env` sans écraser l'environnement. Ne retourne ni n'affiche aucune…, require_secret(), test_secret_manquant_ne_donne_que_le_nom(), env(), fixture

### Community 56 - "Projet Amundi Agentic — instructions pour Claude Code"
Cohesion: 0.33
Nodes (5): graphify, Projet Amundi Agentic — instructions pour Claude Code, Rappels non négociables, Règles d'orchestration, Ton équipe (sous-agents dans `.claude/agents/`)

### Community 57 - "ny_local_to_utc"
Cohesion: 0.18
Nodes (11): ny_local_to_utc(), datetime, Timestamp, Heure de New York (sans fuseau) -> UTC. Règle de D-023 pour un horodatage en…, parametrize, Règle prudente (raw_as_utc) : l'instant servi n'est jamais antérieur à…, test_acceptation_par_defaut_jamais_anterieure_a_l_instant_reel(), test_heure_new_york_vers_utc_hiver_et_ete() (+3 more)

### Community 58 - ".snapshot"
Cohesion: 0.50
Nodes (3): D-046 — Points de la couche de données reportés (2026-10-02), D-054 — Nettoyage de la couche de données : date de Paris, plafonds par classe, C3M.PA (2026-10-06), Écrit les données brutes reçues dans `snapshots/<source>/<AAAA-MM-…

### Community 59 - "Avancement"
Cohesion: 0.29
Nodes (6): Avancement, Phase 0 — 2026-10-02, Phase 1 — 2026-10-02, Phase 2 — 2026-10-02, Phase 3 — 2026-10-06 (en cours), Phase 3 : état au 2026-10-07 (matin)

### Community 60 - "Amundi Agentic"
Cohesion: 0.40
Nodes (4): Amundi Agentic, Installation, Organisation, État

### Community 61 - "add_us_business_days"
Cohesion: 0.25
Nodes (8): CustomBusinessDay, add_us_business_days(), Series, Jours ouvrés américains (fériés fédéraux exclus), sans dépendance nouvelle., `dates` + n jours ouvrés américains, vectorisé (équivalent à `dates +…, us_business_days(), test_lag_rule_saute_les_jours_feries_americains(), test_jours_ouvres_vectorises_identiques_a_pandas()

### Community 63 - "test_network.py"
Cohesion: 0.22
Nodes (8): PointInTimeStore, Tests réseau (lancés à la main : `uv run pytest -m network`). Exclus de la CI.…, test_fred_alfred_gdpc1_millesimes(), test_fx_bce_usd(), test_gdelt_une_requete(), test_prix_yfinance_spy(), Chemin réel : `fetch_series` (réponse simulée) puis `as_of`, attendu issu du…, test_n1_jours_feries_via_fetch_series_puis_as_of()

### Community 64 - "run_fetch"
Cohesion: 0.11
Nodes (20): PricesConnector, company_query(), _guard(), Nom de société -> requête GDELT entre guillemets (suffixes juridiques retirés)., run_fetch(), faire(), _pool(), load_yaml() (+12 more)

### Community 78 - ".get"
Cohesion: 0.13
Nodes (10): Session, HttpResponse, Any, Path, GET avec cache. `ttl_s=None` : le cache n'expire jamais (reproductibilité)., Retire des secrets d'un texte : motifs `api_key=...` et valeurs connues de…, redact(), test_redact_motifs_et_valeur_d_environnement() (+2 more)

### Community 79 - "D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)"
Cohesion: 0.50
Nodes (4): Conditions d'utilisation des niveaux gratuits, D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03), Date de fin d'entraînement (borne de contamination de D-025), Limites du niveau gratuit

### Community 88 - "parametrize"
Cohesion: 0.20
Nodes (10): _pib_et_cpi(), parametrize, test_n1_creux_10_et_20_pourcent_oracle(), test_n1_rang_de_volatilite_080_et_095(), test_n1_vix_25_et_35(), test_n2_chaine_hebdomadaire_avec_previous_egale_le_rejeu_complet(), test_n3_calmar_min_abs_drawdown(), test_n5_meta_macro_regime_serialisable_et_sourcee() (+2 more)

### Community 89 - "esg_matrix"
Cohesion: 0.25
Nodes (9): esg_matrix(), liquidity_stats(), DataFrame, Valeur échangée (volume x clôture, devise de cotation) : médiane, 10e centile,…, Matrice actif x critère à trois états : déterminé par donnée, supposé par…, Sans indicateur fournisseur, « armes controversées » n'est jamais déterminé…, _records(), test_aucune_regle_sic_pour_les_armes_controversees() (+1 more)

### Community 90 - "quality.py"
Cohesion: 0.33
Nodes (8): QualityIssue, check_dated_series(), check_duplicates(), _d(), DataFrame, date, Contrôle qualité : trous, splits, doublons, valeurs aberrantes, séries trop…, Doublons de date et trous (en jours calendaires) d'une série macro ou de change.

### Community 91 - "Horloge"
Cohesion: 0.22
Nodes (6): Horloge, test_alerte_a_80_pourcent_de_1000_requetes_avec_la_limite_reelle(), test_attente_proactive_a_30_requetes_par_minute(), test_attente_proactive_a_8000_jetons_par_minute(), test_l_alerte_compte_les_requetes_du_modele_pas_celles_du_fournisseur(), test_les_autres_modeles_groq_sans_limite_ne_declenchent_aucune_alerte()

### Community 92 - "test_revue_hygiene_texte.py"
Cohesion: 0.09
Nodes (26): amundi_agentic_tools_text_config, ast, parametrize, Path, _code_sans_docstrings(), _existants(), _fichiers_ajoutes(), _gere() (+18 more)

### Community 93 - "test_config_revue.py"
Cohesion: 0.25
Nodes (3): Tests complémentaires de config/llm.yaml (revue de D-008)., La config ne nomme que des variables d'environnement, jamais une valeur de clé., test_variables_d_environnement_et_non_valeurs()

### Community 94 - "_serie_regime"
Cohesion: 0.25
Nodes (8): Porter `previous` JOUR après JOUR n'est pas identique par construction au rejeu…, _serie_regime(), test_n2_chaine_quotidienne_signalee_si_elle_differe_du_rejeu_hebdomadaire(), test_n2_etat_fourni_ne_depend_ni_de_la_profondeur_ni_du_passe_lointain(), test_n2_la_sortie_depend_du_rejeu_seulement_sans_etat_et_l_origine_le_dit(), test_n2_meme_t_meme_previous_meme_resultat_toujours(), test_n2_previous_fourni_aucune_donnee_posterieure_a_t(), test_n2_rejeu_incomplet_signale_le_nombre_de_pas_reellement_calcules()

### Community 95 - "10. Règles de rééquilibrage"
Cohesion: 0.40
Nodes (5): 10.1 Calendrier et déclencheurs, 10.2 Volume de vues, 10.3 Coûts de transaction (aller simple, en points de base, H), 10.4 Limite de rotation et file de validation, 10. Règles de rééquilibrage

### Community 96 - "3. Architecture"
Cohesion: 0.40
Nodes (5): 3.1 Vue d'ensemble, 3.2 Modules (conformes à la section 5.2, D-003, D-004), 3.3 Interfaces principales (signatures, pseudo-code), 3.4 Axes d'exécution et fichiers de configuration (phase 3), 3. Architecture

### Community 97 - "_alternee"
Cohesion: 0.40
Nodes (5): Series, _alternee(), Rendements +a, -a alternés dont l'écart-type d'échantillon (ddof=1) annualisé…, test_n3_sharpe_sortino_bords_de_volatilite(), test_n3_valeur_du_sharpe_au_dessus_du_seuil_oracle()

### Community 98 - "8. Profils clients"
Cohesion: 0.50
Nodes (4): 8.1 Benchmark par profil, 8.2 δ, volatilité plafond, tracking error, rotation, 8.3 Bornes par classe (H, en % du portefeuille), 8. Profils clients

### Community 99 - "parametrize"
Cohesion: 0.67
Nodes (3): parametrize, test_valeur_de_limite_non_numerique_ou_negative_refusee(), test_valeurs_de_limite_valides_acceptees()

### Community 100 - "test_n2_cout_du_repli_par_rejeu_de_52_semaines_raisonnable"
Cohesion: 0.67
Nodes (3): _mediane(), Garde contre une dérive d'ordre de grandeur, en mesure RELATIVE : les durées…, test_n2_cout_du_repli_par_rejeu_de_52_semaines_raisonnable()

### Community 101 - "test_dependances_entre_modules"
Cohesion: 0.17
Nodes (12): D-010 — Modèles de données partagés (2026-10-02), 13.1 Relevé (2026-10-02, en ligne de commande), 13.2 Comparaison sur les trois critères, 13.3 Choix proposé, 13. Choix du cadre d'orchestration : LangGraph ou AutoGen, 15. Plan de tests, _imports(), Path (+4 more)

## Ambiguous Edges - Review These
- `Sentiment Agent` → `Objective: Automated portfolio updating/adjustment on market signals`  [AMBIGUOUS]
  papier BlackRock.pdf · relation: conceptually_related_to
- `Role-based Multi-Agent System for Equity Research` → `ESG Integration in Investment Processes`  [AMBIGUOUS]
  Fiche projet Amundi Agentic.pdf · relation: conceptually_related_to
- `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` → `Look-ahead Bias (LLM training data after test period)`  [AMBIGUOUS]
  fiches/fiche_projet_amundi.md · relation: conceptually_related_to

## Knowledge Gaps
- **166 isolated node(s):** `D-001 — Racine du dépôt (2026-10-02)`, `D-002 — Gestionnaire d'environnement et version de Python (2026-10-02)`, `D-003 — Emplacement des prompts de rôle (2026-10-02)`, `D-004 — Fournisseurs LLM et adaptateurs (2026-10-02)`, `D-005 — Outils qualité et CI (2026-10-02)` (+161 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 559 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **27 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Sentiment Agent` and `Objective: Automated portfolio updating/adjustment on market signals`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Role-based Multi-Agent System for Equity Research` and `ESG Integration in Investment Processes`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` and `Look-ahead Bias (LLM training data after test period)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `ParquetStore` connect `ParquetStore` to `test_connectors.py`, `Report`, `pipeline.py`, `news.py`, `FredConnector`, `test_revue_rejouabilite.py`, `HttpError`, `test_http_store.py`, `DataView`, `DataSettings`, `normalize`, `coverage.py`, `test_rejouabilite_analyses.py`, `FilingsConnector`, `test_revue_robustesse.py`, `esg.py`, `test_universe_coverage.py`, `cli.py`, `require_secret`, `.snapshot`, `test_network.py`, `run_fetch`, `.get`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `Journal des décisions` connect `Journal des décisions` to `.snapshot`, `test_dependances_entre_modules`, `D-052 — Quotas, dates de fin d'entraînement et conditions des niveaux gratuits (2026-10-03)`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Why does `test_dependances_entre_modules()` connect `test_dependances_entre_modules` to `3. Architecture`, `test_specifications.py`, `Contraintes transverses du prompt maître`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 54 inferred relationships involving `ParquetStore` (e.g. with `EsgConnector` and `FilingsConnector`) actually correct?**
  _`ParquetStore` has 54 INFERRED edges - model-reasoned connections that need verification._