# Graph Report - Amundi Agentic  (2026-10-03)

## Corpus Check
- 73 files · ~89,243 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 4, .example 1)

## Summary
- 1210 nodes · 2690 edges · 83 communities (60 shown, 23 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 348 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e3ef0411`
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
- test_revue_corrections.py
- Journal des décisions
- test_pit.py
- Academic prototype disclaimer (not investment advice)
- pipeline.py
- test_revue_pit_adverse.py
- test_specifications.py
- settings.py
- FredConnector
- Couverture des données (phase 2)
- test_revue_rejouabilite.py
- test_revue_robustesse.py
- run_fetch
- ParquetStore
- test_http_store.py
- HttpClient
- FilingsConnector
- Report
- DataView
- normalize
- load_yaml
- Universe
- universe.py
- test_socle_revue.py
- test_socle.py
- edgar_acceptance_to_utc
- .path
- coverage.py
- pit.py
- test_prix_invariants_au_contenu_futur_hors_splits
- analysis.py
- EsgConnector
- Contraintes transverses du prompt maître
- 11. Exigences non fonctionnelles
- test_config.py
- 7. Construction Black-Litterman
- _Tables
- test_config_revue.py
- 5. Schémas de données (Pydantic, `schemas.py`)
- test_dependances_entre_modules
- Prompt maître — Système agentique Amundi
- L1 — Spécifications fonctionnelles et techniques
- 6. Flux du débat
- pytest
- ts
- .snapshot
- Projet Amundi Agentic — instructions pour Claude Code
- 10. Règles de rééquilibrage
- 9. Univers
- Avancement
- Amundi Agentic
- 3. Architecture
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
- amundi-agentic

## God Nodes (most connected - your core abstractions)
1. `ParquetStore` - 99 edges
2. `Fiche de revision - AlphaAgents (papier BlackRock)` - 66 edges
3. `Journal des décisions` - 51 edges
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

## Communities (83 total, 23 thin omitted)

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
Nodes (14): _client(), Connecteurs : analyse des réponses (fixtures minuscules et synthétiques),…, Session factice : renvoie une charge utile selon la fin de l'URL., Resp, SessionAvecErreurs, SessionJson, test_edgar_fetch_filings_et_textes_reprise(), test_edgar_user_agent_exige_et_envoye() (+6 more)

### Community 9 - "test_rejouabilite_analyses.py"
Cohesion: 0.18
Nodes (20): O3 — Mise à jour et ajustement automatiques (L3), O5 — Évaluation face à des benchmarks traditionnels (L4), Exigences détaillées O1 à O5, _frame_yf(), _horloge(), Rejouabilité (instantanés, manifeste), matrice ESG, liquidité, contrôle croisé,…, Après un split rétroactif de Yahoo, la valeur d'origine reste retrouvable dans…, _serie() (+12 more)

### Community 10 - "test_revue_corrections.py"
Cohesion: 0.05
Nodes (44): ast, CustomBusinessDay, main(), Interface en ligne de commande (D-010). Phase 2 : sous-commande `data`. amundi-…, add_us_business_days(), Series, Jours ouvrés américains (fériés fédéraux exclus), sans dépendance nouvelle., `dates` + n jours ouvrés américains, vectorisé (équivalent à `dates +… (+36 more)

### Community 11 - "Journal des décisions"
Cohesion: 0.04
Nodes (49): D-001 — Racine du dépôt (2026-10-02), D-002 — Gestionnaire d'environnement et version de Python (2026-10-02), D-003 — Emplacement des prompts de rôle (2026-10-02), D-004 — Fournisseurs LLM et adaptateurs (2026-10-02), D-005 — Outils qualité et CI (2026-10-02), D-006 — Dépendances ajoutées phase par phase (2026-10-02), D-007 — Hypothèses de cadrage en attendant Amundi (2026-10-02), D-008 — Modèles LLM retenus (2026-10-02) (+41 more)

### Community 12 - "test_pit.py"
Cohesion: 0.06
Nodes (61): check_prices(), prix(), DataFrame, Fabriques de données synthétiques partagées par les tests de `data/`., _esg(), _fred(), _index(), _news() (+53 more)

### Community 14 - "pipeline.py"
Cohesion: 0.11
Nodes (30): collections_abc, datetime, gzip, hashlib, io, json, logging, os (+22 more)

### Community 15 - "test_revue_pit_adverse.py"
Cohesion: 0.11
Nodes (23): _esg(), _items(), Revue indépendante de la phase 2 : tests adverses sur les fuites de futur…, Split daté t-1 : connu (prix post-split). Split daté t : inconnu, prix pré-…, Série mensuelle : la disponibilité part de la FIN de période (pas du début) +…, Observation du vendredi en règle `date + 1 jour` : servie dès t = samedi + 1…, Retraitement déposé par 10-K/A (absent de l'index) : valeur d'origine jusqu'à…, Deux dépôts le même jour sur la même clé : le résultat ne doit pas dépendre de… (+15 more)

### Community 16 - "test_specifications.py"
Cohesion: 0.08
Nodes (36): fnmatch, Pattern, _cellules(), _colonne(), _composant_prevu(), _config_prevue(), _developper_accolades(), _developper_plages() (+28 more)

### Community 17 - "settings.py"
Cohesion: 0.19
Nodes (12): dataclasses, make_http_client(), MissingSecretError, Variable d'environnement absente (seul le NOM de la variable est indiqué,…, load_dotenv(), Chemins, configuration et secrets. Les secrets ne sont jamais affichés ni…, Charge `.env` sans écraser l'environnement. Ne retourne ni n'affiche aucune…, require_secret() (+4 more)

### Community 18 - "FredConnector"
Cohesion: 0.18
Nodes (13): FredConnector, merge_vintage_chunks(), parse_fred_observations(), DataFrame, date, Observations actuelles (sans millésimes), paginées., Observations FRED -> DataFrame. Un marqueur « . » (valeur absente) devient NaN…, Fusionne les lignes (date, valeur) contiguës dans le temps réel, coupées par le… (+5 more)

### Community 19 - "Couverture des données (phase 2)"
Cohesion: 0.08
Nodes (25): 0. Statut des téléchargements (dernier événement par élément), 1. Prix des ETF candidats et de leurs proxys (yfinance), 2. Prix de la poche titres (liste de démonstration), 3. Macro (FRED/ALFRED et BCE), 4. Dépôts SEC EDGAR et XBRL (liste de démonstration), 5. News (RSS, GDELT), 6. ESG, 7. Contrôle qualité (signalements, aucune correction appliquée) (+17 more)

### Community 20 - "test_revue_rejouabilite.py"
Cohesion: 0.09
Nodes (34): 11.3 bis Instantanés et manifeste des données (D-043), 12. Risques et parades, shutil, data_manifest(), _describe(), _entries(), _event_key(), Path (+26 more)

### Community 21 - "test_revue_robustesse.py"
Cohesion: 0.06
Nodes (49): calendar, feedparser, Session, _gdelt_json(), _is_json(), _item_id(), NewsConnector, parse_gdelt() (+41 more)

### Community 22 - "run_fetch"
Cohesion: 0.11
Nodes (19): PricesConnector, company_query(), _guard(), Nom de société -> requête GDELT entre guillemets (suffixes juridiques retirés)., run_fetch(), faire(), _pool(), fetch_stock_pool() (+11 more)

### Community 23 - "ParquetStore"
Cohesion: 0.11
Nodes (11): Recalcule `accepted_utc` de tous les index depuis `acceptance_raw` (sans…, reindex_acceptance(), FxConnector, EcbConnector, parse_ecb_csv(), CSV SDMX de la BCE -> colonnes date (début de période), period_end, value., ParquetStore, Ajoute un événement (ok, error, unavailable). `detail` doit déjà être expurgé… (+3 more)

### Community 24 - "test_http_store.py"
Cohesion: 0.16
Nodes (20): requests, client(), FausseSession, FauxResp, Cache disque, débit, backoff, secrets (jamais dans le cache) ; stockage Parquet…, test_404_non_rejoue(), test_backoff_exponentiel_sur_429_puis_succes(), test_cache_persiste_entre_clients() (+12 more)

### Community 25 - "HttpClient"
Cohesion: 0.18
Nodes (8): HttpClient, HttpResponse, Any, GET avec cache. `ttl_s=None` : le cache n'expire jamais (reproductibilité)., Retire des secrets d'un texte : motifs `api_key=...` et valeurs connues de…, redact(), test_cle_hors_url_dans_les_journaux_d_evenements(), test_redact_motifs_courants()

### Community 26 - "FilingsConnector"
Cohesion: 0.13
Nodes (11): FilingsConnector, html_to_text(), parse_company_facts(), parse_company_tickers(), DataFrame, HTMLParser, Télécharge le texte des 10-K et 10-Q (reprise : les textes déjà stockés sont…, _rows_from_columns() (+3 more)

### Community 27 - "Report"
Cohesion: 0.23
Nodes (3): md_table(), Date de début du backtest permise par classe (260 semaines d'historique avant…, Report

### Community 28 - "DataView"
Cohesion: 0.22
Nodes (9): DataView, pit_prices(), DataFrame, date, Series, Dernière version connue de chaque observation : date, value, available_from., Unités de `currency` pour 1 EUR (convention BCE), fixings connus à t., Barres connues à t, recalées des seuls splits et dividendes connus à t. (+1 more)

### Community 29 - "normalize"
Cohesion: 0.14
Nodes (13): Fetcher, NoDataError, normalize(), DataFrame, date, Path, RuntimeError, Télécharge ou met à jour un ticker. Retourne un résumé (jamais de secret). (+5 more)

### Community 30 - "load_yaml"
Cohesion: 0.16
Nodes (14): 1. Besoins par objectif, O1 — Agents qui recommandent à partir d'analyses quantitatives et qualitatives (L2), O2 — Portefeuilles optimisés sous contraintes (L3), O4 — Transparence et explicabilité (L2, L5), esg_matrix(), Matrice actif x critère à trois états : déterminé par donnée, supposé par…, load_yaml(), Any (+6 more)

### Community 31 - "Universe"
Cohesion: 0.21
Nodes (13): composition(), Timestamp, Composition de chaque série de classe par date : proxy converti (synthétique)…, Candidate, Universe, test_composition_ne_cite_pas_une_serie_publique_qui_n_existe_pas_avant_l_etf(), test_composition_par_date(), test_config_distribution_renseignee_pour_chaque_candidat() (+5 more)

### Community 32 - "universe.py"
Cohesion: 0.12
Nodes (22): html_parser, AssetClassSpec, convert_to_eur(), money_market_index(), parse_constituents_html(), Series, Univers (config/universe.yaml), conversion en EUR, jonctions, monétaire…, Prix en devise -> EUR au fixing BCE du jour, sinon au dernier fixing de moins… (+14 more)

### Community 33 - "test_socle_revue.py"
Cohesion: 0.13
Nodes (12): _fichiers_commitables(), parametrize, Path, Tests complémentaires du socle (revue phase 0) : CI, version de Python, secrets., Fichiers suivis ou non ignorés : ce qui partirait dans un `git add -A`., Aucune valeur pré-remplie, y compris hors suffixe KEY (ex. User-Agent avec…, ANTHROPIC_API_KEY ne doit apparaître que pour être interdite, jamais être lue., test_aucune_cle_anthropic_hors_interdictions() (+4 more)

### Community 34 - "test_socle.py"
Cohesion: 0.29
Nodes (6): importlib, subprocess, parametrize, Tests du socle (phase 0) : structure du dépôt et hygiène des secrets., test_fichiers_de_pilotage_presents(), test_sous_paquets_de_la_section_5_2()

### Community 35 - "edgar_acceptance_to_utc"
Cohesion: 0.13
Nodes (16): edgar_acceptance_to_utc(), ny_local_to_utc(), datetime, Timestamp, Heure de New York (sans fuseau) -> UTC. Règle de D-023 pour un horodatage en…, Horodatage `acceptanceDateTime` de l'API submissions lu comme UTC (règle…, parametrize, Règle prudente (raw_as_utc) : l'instant servi n'est jamais antérieur à… (+8 more)

### Community 36 - ".path"
Cohesion: 0.31
Nodes (3): DataFrame, Fusionne `df` dans le jeu ; la dernière ligne l'emporte sur une clé identique.…, Tous les instantanés d'un jeu, avec colonnes snapshot_date et origin (ordre…

### Community 37 - "coverage.py"
Cohesion: 0.17
Nodes (14): argparse, collections, numpy, _fmt(), main(), Rapport de couverture des données, généré par script (aucun chiffre écrit à la…, QualityIssue, check_dated_series() (+6 more)

### Community 38 - "pit.py"
Cohesion: 0.20
Nodes (11): Couche de données (phase 2). Connecteurs de données gratuites, stockage Parquet…, EsgRecord, Filing, LookAheadError, NewsItem, NewsQuery, RuntimeError, Modèles de données de la couche `data/` (sans dépendance vers un autre module… (+3 more)

### Community 39 - "test_prix_invariants_au_contenu_futur_hors_splits"
Cohesion: 0.21
Nodes (12): _monde_brut(), parametrize, Invariant prudent : l'instant servi n'est jamais antérieur à l'instant brut lu…, Prix BRUTS (non ajustés) tels que cotés à chaque séance, avec splits et…, Ce que Yahoo sert : clôtures ajustées des splits connus à la date de…, Sans split futur, tronquer les lignes >= t ne change RIEN au résultat servi à t., Un cours aberrant daté >= t (donnée future) ne doit influencer aucune ligne…, test_edgar_corrige_jamais_avant_l_instant_utc_brut() (+4 more)

### Community 40 - "analysis.py"
Cohesion: 0.18
Nodes (12): cross_check(), drawdown_episodes(), drawdown_table(), liquidity_stats(), DataFrame, Series, Calculs du rapport de couverture : liquidité, contrôle croisé, matrice ESG,…, Creux (pic -> creux -> récupération) d'amplitude >= `threshold`, sur une série… (+4 more)

### Community 41 - "EsgConnector"
Cohesion: 0.18
Nodes (8): enforced(), EsgConnector, datetime, Catégories d'exclusion dont un intervalle SIC contient `sic` (règles `enforce:…, sic_exclusions(), test_esg_connecteur_titres_et_etf(), test_regles_sic(), VendorFetcher

### Community 42 - "Contraintes transverses du prompt maître"
Cohesion: 0.18
Nodes (11): 11.1 Tableau, Contraintes transverses du prompt maître, Exigences non fonctionnelles sans contrainte C dédiée, Livrables, Matrice de traçabilité : exigences → composants → tests, Objectifs du cahier des charges, test_requete_identique_servie_par_le_cache(), test_fournisseurs_gratuits_uniquement() (+3 more)

### Community 43 - "11. Exigences non fonctionnelles"
Cohesion: 0.33
Nodes (6): 11.2 Budget d'appels, 11.3 Point-in-time : règles par source, 11.4 Objet de l'évaluation (L4) et limites de preuve, 11.5 Protocole d'anonymisation (EX-O5-06), 11.6 Pré-enregistrement (EX-O5-12), 11. Exigences non fonctionnelles

### Community 44 - "test_config.py"
Cohesion: 0.20
Nodes (5): 4. Agents et prompts de rôle, Grandes lignes des prompts de rôle (fichiers `agent_prompts/<agent>_v1.md` en phase 3), Configuration LLM : modèles déclarés dans config/, jamais codés en dur (C1,…, test_aucun_nom_de_modele_dans_le_code(), yaml

### Community 45 - "7. Construction Black-Litterman"
Cohesion: 0.22
Nodes (9): 7.1 Univers de l'optimisation, 7.2 Covariance Σ, 7.3 A priori, 7.4 Vues : P, Q et calibration de κ, 7.5 Ω (Idzorek) et τ, 7.6 Optimisation (cvxpy), 7.7 Attribution par vue (pour `explain/attribution.py`), 7.8 Méthodes de comparaison (+1 more)

### Community 47 - "test_config_revue.py"
Cohesion: 0.25
Nodes (3): Tests complémentaires de config/llm.yaml (revue de D-008)., La config ne nomme que des variables d'environnement, jamais une valeur de clé., test_variables_d_environnement_et_non_valeurs()

### Community 48 - "5. Schémas de données (Pydantic, `schemas.py`)"
Cohesion: 0.25
Nodes (8): 5.1 Décision à 5 niveaux, 5.2 `Source` et `View` (section 3.4 du prompt), 5.3 Autres sorties d'agents, 5.4 Journal de débat, 5.5 Proposition de rééquilibrage, 5.6 Fiche d'explication, 5.7 Enregistrement d'exécution, 5. Schémas de données (Pydantic, `schemas.py`)

### Community 49 - "test_dependances_entre_modules"
Cohesion: 0.22
Nodes (9): D-010 — Modèles de données partagés (2026-10-02), 13.1 Relevé (2026-10-02, en ligne de commande), 13.2 Comparaison sur les trois critères, 13.3 Choix proposé, 13. Choix du cadre d'orchestration : LangGraph ou AutoGen, 15. Plan de tests, L1 3.2 : aucun SDK de fournisseur hors de llm/ ; portfolio/ n'importe ni llm ni…, _sdk_interdit() (+1 more)

### Community 50 - "Prompt maître — Système agentique Amundi"
Cohesion: 0.29
Nodes (6): 1. Rôle, mission et contexte, 2. Règles de travail et garde-fous, 3. Architecture cible, 4. Les phases, 5. Évaluation, dépôt et compte rendu, Prompt maître — Système agentique Amundi

### Community 51 - "L1 — Spécifications fonctionnelles et techniques"
Cohesion: 0.20
Nodes (9): 14. Écarts avec AlphaAgents, 16. Entrées proposées pour `DECISIONS.md` et `QUESTIONS_AMUNDI.md`, 2. Cas d'usage du gérant, 8.1 Benchmark par profil, 8.2 δ, volatilité plafond, tracking error, rotation, 8.3 Bornes par classe (H, en % du portefeuille), 8. Profils clients, L1 — Spécifications fonctionnelles et techniques (+1 more)

### Community 52 - "6. Flux du débat"
Cohesion: 0.33
Nodes (6): 6.1 Déroulé, 6.2 Règle de consensus, 6.3 Avocat du diable tournant, 6.4 Du consensus à la confiance d'Idzorek, 6.5 Journalisation, 6. Flux du débat

### Community 53 - "pytest"
Cohesion: 0.38
Nodes (6): pytest, cfg(), pit(), fixture, Fabriques de données synthétiques pour les tests de la couche `data/` (aucun…, store()

### Community 54 - "ts"
Cohesion: 0.18
Nodes (12): parse_filings(), cutoff_utc(), Timestamp, Instant de coupure : t 00:00 heure de Paris, en UTC., Timestamp, ts(), test_parse_filings_ecarte_un_depot_sans_acceptation(), test_coupure_hiver_et_ete() (+4 more)

### Community 55 - ".snapshot"
Cohesion: 0.33
Nodes (4): D-046 — Points de la couche de données reportés (2026-10-02), datetime, Path, Écrit les données brutes reçues dans `snapshots/<source>/<AAAA-MM-…

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

### Community 62 - "3. Architecture"
Cohesion: 0.50
Nodes (4): 3.1 Vue d'ensemble, 3.2 Modules (conformes à la section 5.2, D-003, D-004), 3.3 Interfaces principales (signatures, pseudo-code), 3. Architecture

## Ambiguous Edges - Review These
- `Sentiment Agent` → `Objective: Automated portfolio updating/adjustment on market signals`  [AMBIGUOUS]
  papier BlackRock.pdf · relation: conceptually_related_to
- `Role-based Multi-Agent System for Equity Research` → `ESG Integration in Investment Processes`  [AMBIGUOUS]
  Fiche projet Amundi Agentic.pdf · relation: conceptually_related_to
- `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` → `Look-ahead Bias (LLM training data after test period)`  [AMBIGUOUS]
  fiches/fiche_projet_amundi.md · relation: conceptually_related_to

## Knowledge Gaps
- **143 isolated node(s):** `amundi-agentic`, `Ton équipe (sous-agents dans `.claude/agents/`)`, `Règles d'orchestration`, `Rappels non négociables`, `graphify` (+138 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 426 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Sentiment Agent` and `Objective: Automated portfolio updating/adjustment on market signals`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Role-based Multi-Agent System for Equity Research` and `ESG Integration in Investment Processes`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` and `Look-ahead Bias (LLM training data after test period)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `ParquetStore` connect `ParquetStore` to `test_connectors.py`, `test_rejouabilite_analyses.py`, `test_revue_corrections.py`, `pipeline.py`, `settings.py`, `FredConnector`, `test_revue_rejouabilite.py`, `test_revue_robustesse.py`, `run_fetch`, `test_http_store.py`, `HttpClient`, `FilingsConnector`, `Report`, `DataView`, `normalize`, `load_yaml`, `universe.py`, `.path`, `coverage.py`, `pit.py`, `EsgConnector`, `pytest`, `.snapshot`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Why does `L1 — Spécifications fonctionnelles et techniques` connect `L1 — Spécifications fonctionnelles et techniques` to `11. Exigences non fonctionnelles`, `test_config.py`, `7. Construction Black-Litterman`, `5. Schémas de données (Pydantic, `schemas.py`)`, `test_dependances_entre_modules`, `test_revue_rejouabilite.py`, `6. Flux du débat`, `3. Architecture`, `10. Règles de rééquilibrage`, `9. Univers`, `load_yaml`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `Journal des décisions` connect `Journal des décisions` to `test_dependances_entre_modules`, `.snapshot`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 54 inferred relationships involving `ParquetStore` (e.g. with `EsgConnector` and `FilingsConnector`) actually correct?**
  _`ParquetStore` has 54 INFERRED edges - model-reasoned connections that need verification._