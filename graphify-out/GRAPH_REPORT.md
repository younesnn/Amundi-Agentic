# Graph Report - corpus  (2026-10-02)

## Corpus Check
- 6 files · ~14,426 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 195 nodes · 595 edges · 14 communities (13 shown, 1 thin omitted)
- Extraction: 77% EXTRACTED · 22% INFERRED · 1% AMBIGUOUS · INFERRED: 132 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Agents, LLM gratuits et RAG
- AlphaAgents et état de l art
- Construction Black-Litterman
- Débat et ses limites
- Déploiement ALTO et choix du LLM
- Profils de risque client
- Projet Amundi et ESG
- Backtest, biais et live test
- Explicabilité et validation humaine
- Rééquilibrage automatique
- Phases du prompt maître
- Benchmark et ablations
- Frameworks d orchestration
- Avertissement prototype

## God Nodes (most connected - your core abstractions)
1. `Fiche de revision - AlphaAgents (papier BlackRock)` - 66 edges
2. `Fiche de revision - Projet Amundi Agentic AI` - 45 edges
3. `Prompt maître — Système agentique Amundi` - 30 edges
4. `Fiche de revision - Markowitz et Black-Litterman` - 29 edges
5. `Multi-agent Debate (Round Robin to consensus)` - 20 edges
6. `Deliverable: Performance analysis report (backtesting & live testing)` - 20 edges
7. `LLMClient abstraction (provider-agnostic, temperature 0, Pydantic outputs)` - 19 edges
8. `AlphaAgents: LLM-based Multi-Agents for Equity Portfolio Construction` - 17 edges
9. `Fiche projet Amundi Agentic (3rd-year project 2025-2026)` - 17 edges
10. `Objective: Transparency and explainability of agent recommendations` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Baseline: equal weight (AlphaAgents)` --semantically_similar_to--> `Equal-weight Portfolio from Agent Picks`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `Sentiment Agent (allocation level, macro news RSS/GDELT)` --semantically_similar_to--> `Sentiment Agent`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `Macro Agent (allocation: FRED/ECB regime indicators)` --semantically_similar_to--> `Macro Economist Agent (future)`  [INFERRED] [semantically similar]
  prompts/prompt_maitre_amundi.md → papier BlackRock.pdf
- `CrewAI` --semantically_similar_to--> `Microsoft AutoGen`  [INFERRED] [semantically similar]
  fiches/fiche_projet_amundi.md → papier BlackRock.pdf
- `LangGraph` --semantically_similar_to--> `Microsoft AutoGen`  [INFERRED] [semantically similar]
  fiches/fiche_projet_amundi.md → papier BlackRock.pdf

## Hyperedges (group relationships)
- **Limits undermining AlphaAgents backtest validity** — fiches_fiche_alphaagents_blackrock_look_ahead_bias, fiches_fiche_alphaagents_blackrock_small_sample_limitation, fiches_fiche_alphaagents_blackrock_no_transaction_costs, fiches_fiche_alphaagents_blackrock_llm_non_determinism, fiches_fiche_alphaagents_blackrock_groupthink_risk, papier_blackrock_tech_stock_experiment [EXTRACTED 1.00]
- **AlphaAgents specialist agents debate to consensus via group chat** — papier_blackrock_fundamental_agent, papier_blackrock_sentiment_agent, papier_blackrock_valuation_agent, papier_blackrock_group_chat_assistant, papier_blackrock_multi_agent_debate, papier_blackrock_stock_analysis_report [EXTRACTED 1.00]
- **Black-Litterman pipeline: agent views to portfolio weights** — papier_blackrock_multi_agent_debate, fiches_fiche_markowitz_black_litterman_agent_views_mapping, fiches_fiche_markowitz_black_litterman_views_p_q, fiches_fiche_markowitz_black_litterman_view_uncertainty_omega, fiches_fiche_markowitz_black_litterman_equilibrium_returns_pi, fiches_fiche_markowitz_black_litterman_posterior_returns_mu_bl, papier_blackrock_mean_variance_optimization, fiches_fiche_markowitz_black_litterman_real_constraints, fiche_projet_amundi_agentic_deliv_portfolio_construction_module [EXTRACTED 1.00]
- **Extending stock selection to optimized portfolio construction** — fiche_projet_amundi_agentic_obj_optimized_portfolio_construction, fiche_projet_amundi_agentic_deliv_portfolio_construction_module, papier_blackrock_mean_variance_optimization, papier_blackrock_black_litterman, papier_blackrock_confidence_weighted_allocation, papier_blackrock_risk_tolerance_profiles [INFERRED 0.75]
- **Brief objectives mapped to AlphaAgents mechanisms (recommend, explain, evaluate)** — fiche_projet_amundi_agentic_obj_investment_recommendations, fiche_projet_amundi_agentic_obj_transparency_explainability, fiche_projet_amundi_agentic_obj_benchmark_evaluation, papier_blackrock_role_based_multi_agent_system, papier_blackrock_discussion_logs, papier_blackrock_backtesting [INFERRED 0.85]
- **Open design questions to clarify with Amundi** — fiches_fiche_projet_amundi_oq_investment_universe, fiches_fiche_projet_amundi_oq_data_sources, fiches_fiche_projet_amundi_oq_client_profile, fiches_fiche_projet_amundi_oq_llm_hosting, fiches_fiche_projet_amundi_oq_rebalancing_frequency, fiches_fiche_projet_amundi_oq_benchmark, fiche_projet_amundi_agentic_deliv_specifications [INFERRED 0.85]
- **Phase 0-9 delivery sequence** — prompts_prompt_maitre_amundi_phase_0, prompts_prompt_maitre_amundi_phase_1, prompts_prompt_maitre_amundi_phase_2, prompts_prompt_maitre_amundi_phase_3, prompts_prompt_maitre_amundi_phase_4, prompts_prompt_maitre_amundi_phase_5, prompts_prompt_maitre_amundi_phase_6, prompts_prompt_maitre_amundi_phase_7, prompts_prompt_maitre_amundi_phase_8, prompts_prompt_maitre_amundi_phase_9 [EXTRACTED 1.00]
- **L4 evaluation protocol** — prompts_prompt_maitre_amundi_walk_forward_backtest, prompts_prompt_maitre_amundi_evaluation_metrics, prompts_prompt_maitre_amundi_ablations, prompts_prompt_maitre_amundi_bootstrap_robustness, prompts_prompt_maitre_amundi_training_cutoff_split, prompts_prompt_maitre_amundi_anonymization_test, prompts_prompt_maitre_amundi_weekly_paper_trading, prompts_prompt_maitre_amundi_reasoning_quality_review [EXTRACTED 1.00]
- **Zero-cost LLM stack** — prompts_prompt_maitre_amundi_litellm, prompts_prompt_maitre_amundi_ollama_local_model, prompts_prompt_maitre_amundi_groq_free_tier, prompts_prompt_maitre_amundi_gemini_free_tier, prompts_prompt_maitre_amundi_quota_fallback_429, prompts_prompt_maitre_amundi_disk_response_cache, prompts_prompt_maitre_amundi_quota_log [EXTRACTED 1.00]

## Communities (14 total, 1 thin omitted)

### Community 0 - "Agents, LLM gratuits et RAG"
Cohesion: 0.12
Nodes (29): Open question: Accessible data sources (Bloomberg, Amundi internal), Arize Phoenix, Bloomberg Financial News, RAG Evaluation (faithfulness & relevance), Valuation Agent, Yahoo Finance Price & Volume Data, Sentiment Agent (allocation level, macro news RSS/GDELT), ECB Data Portal (macro, rates) (+21 more)

### Community 1 - "AlphaAgents et état de l art"
Cohesion: 0.14
Nodes (25): Fiche de revision - AlphaAgents (papier BlackRock), Annualized Return & Volatility formulas (252 days), Summarization vs RAG choice for news, AlphaAgents: LLM-based Multi-Agents for Equity Portfolio Construction, BlackRock, Inc., FinAgent, Financial Report RAG Tool, FinMem (+17 more)

### Community 2 - "Construction Black-Litterman"
Cohesion: 0.21
Nodes (24): Deliverable: Portfolio construction module, Fiche de revision - Markowitz et Black-Litterman, Mapping agent BUY/SELL recommendations to views Q, Black & Litterman (Goldman Sachs, 1990-1992), Covariance Matrix Sigma, Efficient Frontier, Equilibrium (implied) Returns Pi = delta Sigma w_mkt, Error Maximization (sensitivity of weights to mu) (+16 more)

### Community 3 - "Débat et ses limites"
Cohesion: 0.14
Nodes (16): Binary BUY/SELL decision (no HOLD), Groupthink Risk (forced consensus), Reproducibility / LLM Non-determinism, Zscaler ('Company Z') debate example (BUY -> SELL consensus), Improving Factuality via Multiagent Debate (Du et al. 2023), Baseline: equal weight (AlphaAgents), Baseline: Markowitz on same views, Baseline: risk parity (+8 more)

### Community 4 - "Déploiement ALTO et choix du LLM"
Cohesion: 0.19
Nodes (15): ALTO (Amundi Leading Technology & Operations), Deliverable: Deployment plan & integration into Amundi processes, Claude (LLM), End-to-end target system (recommendation -> construction -> rebalancing -> evaluation -> integration), Open question: Allowed LLMs (external vs internally hosted for confidentiality), GPT-4o, ALTO integration as API service with human validation before orders, End-of-phase report format (done, criteria, decisions, limits, questions, next) (+7 more)

### Community 5 - "Profils de risque client"
Cohesion: 0.23
Nodes (11): Drawdown, Qualitative risk profile injected in prompt (vs quantitative constraints), Risk-averse underperformance in bull market (risk/return trade-off), Combining short-term and long-term signals, Small Sample / No Statistical Significance (15 stocks, 4 months), Risk Aversion Coefficient lambda / delta, Open question: Client type, risk profiles and constraints (ESG, exclusions), 15 Tech-stock Experiment (Feb-May 2024) (+3 more)

### Community 6 - "Projet Amundi et ESG"
Cohesion: 0.30
Nodes (10): Fiche projet Amundi Agentic (3rd-year project 2025-2026), Agentic AI System for Portfolio Construction, Amundi Asset Management, Amundi Technology, Fiche de revision - Projet Amundi Agentic AI, Agentic AI (LLM with role, tools, multi-step autonomy), Diversification, Open question: Investment universe (equities vs multi-asset, region) (+2 more)

### Community 7 - "Backtest, biais et live test"
Cohesion: 0.35
Nodes (10): Deliverable: Performance analysis report (backtesting & live testing), Look-ahead Bias (LLM training data after test period), Live Testing (real-period run), Rolling Sharpe Ratio, Sharpe Ratio, Anonymization test (names and dates masked) for memorization, Metrics (Sharpe, Sortino, max drawdown, Calmar, TE, IR, turnover, ESG, LLM cost), Point-in-time data access as_of(date) + leakage test (+2 more)

### Community 8 - "Explicabilité et validation humaine"
Cohesion: 0.33
Nodes (7): Deliverable: Technical documentation & user guide for asset managers, AutoGen Studio, Full debate log (prompts, answers, sources, duration, cost), Phase 6 — Explicabilité et interface (O4), Phase 8 — Documentation et guide gérant (L5), Streamlit dashboard (portfolio, views, debates, performance, validations), 'Why this weight' explanation sheet + benchmark-deviation attribution

### Community 9 - "Rééquilibrage automatique"
Cohesion: 0.43
Nodes (7): No Transaction Costs nor Rebalancing, Open question: Horizon and rebalancing frequency, Rebalancing (trigger rules on new signals), Manager validation queue (validate / modify / reject), Phase 5 — Rééquilibrage automatique (O3), Rebalancing triggers (monthly review, view change, weight drift, vol regime), Transaction costs in bps per asset class

### Community 10 - "Phases du prompt maître"
Cohesion: 0.48
Nodes (7): Deliverable: Functional & technical specifications, Prompt maître — Système agentique Amundi, Phase 0 — Cadrage et socle du dépôt, Phase 1 — Spécifications (L1), Phase 2 — Couche de données, Repository structure amundi-agentic/, Requirements-to-components traceability matrix (docs/tracabilite.md)

### Community 11 - "Benchmark et ablations"
Cohesion: 0.48
Nodes (6): Market (Reference) Portfolio w_mkt, Open question: Reference benchmark for evaluation, Ablation studies (single agent, no debate, no Macro, no BL, no ESG, LLM provider), 60/40 benchmark (world equities / bonds), per client profile, Phase 7 — Évaluation (L4), Provider ablation (compare free LLMs, report as-is)

### Community 12 - "Frameworks d orchestration"
Cohesion: 0.70
Nodes (5): Deliverable: Functional prototype of recommendation agents, CrewAI, LangGraph, Microsoft AutoGen, LangGraph vs AutoGen comparison (loops, traceability, multi-provider)

## Ambiguous Edges - Review These
- `ESG Integration in Investment Processes` → `Role-based Multi-Agent System for Equity Research`  [AMBIGUOUS]
  Fiche projet Amundi Agentic.pdf · relation: conceptually_related_to
- `Objective: Automated portfolio updating/adjustment on market signals` → `Sentiment Agent`  [AMBIGUOUS]
  papier BlackRock.pdf · relation: conceptually_related_to
- `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` → `Look-ahead Bias (LLM training data after test period)`  [AMBIGUOUS]
  fiches/fiche_projet_amundi.md · relation: conceptually_related_to

## Knowledge Gaps
- **9 isolated node(s):** `Goldman Sachs`, `Tool-grounded agents (numbers computed in Python, cited sources)`, `Baseline: risk parity`, `Requirements-to-components traceability matrix (docs/tracabilite.md)`, `Unit tests + integration tests with mock LLM` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 9 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `ESG Integration in Investment Processes` and `Role-based Multi-Agent System for Equity Research`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Objective: Automated portfolio updating/adjustment on market signals` and `Sentiment Agent`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Open question: Allowed LLMs (external vs internally hosted for confidentiality)` and `Look-ahead Bias (LLM training data after test period)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Fiche de revision - AlphaAgents (papier BlackRock)` connect `AlphaAgents et état de l art` to `Agents, LLM gratuits et RAG`, `Construction Black-Litterman`, `Débat et ses limites`, `Déploiement ALTO et choix du LLM`, `Profils de risque client`, `Projet Amundi et ESG`, `Backtest, biais et live test`, `Explicabilité et validation humaine`, `Rééquilibrage automatique`, `Phases du prompt maître`, `Benchmark et ablations`, `Frameworks d orchestration`?**
  _High betweenness centrality (0.343) - this node is a cross-community bridge._
- **Why does `Prompt maître — Système agentique Amundi` connect `Phases du prompt maître` to `Agents, LLM gratuits et RAG`, `AlphaAgents et état de l art`, `Construction Black-Litterman`, `Déploiement ALTO et choix du LLM`, `Projet Amundi et ESG`, `Backtest, biais et live test`, `Explicabilité et validation humaine`, `Rééquilibrage automatique`, `Benchmark et ablations`, `Frameworks d orchestration`?**
  _High betweenness centrality (0.170) - this node is a cross-community bridge._
- **Why does `Fiche de revision - Projet Amundi Agentic AI` connect `Projet Amundi et ESG` to `Agents, LLM gratuits et RAG`, `AlphaAgents et état de l art`, `Construction Black-Litterman`, `Déploiement ALTO et choix du LLM`, `Profils de risque client`, `Backtest, biais et live test`, `Explicabilité et validation humaine`, `Rééquilibrage automatique`, `Phases du prompt maître`, `Benchmark et ablations`, `Frameworks d orchestration`?**
  _High betweenness centrality (0.161) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Multi-agent Debate (Round Robin to consensus)` (e.g. with `Objective: Transparency and explainability of agent recommendations` and `Groq free tier - fallback when Gemini quota is reached`) actually correct?**
  _`Multi-agent Debate (Round Robin to consensus)` has 2 INFERRED edges - model-reasoned connections that need verification._