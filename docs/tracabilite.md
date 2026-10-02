# Matrice de traçabilité : exigences → composants → tests

Chaque exigence du cahier des charges (objectifs O, livrables L) et chaque contrainte du prompt maître (C) est reliée aux composants qui la réalisent et aux tests qui la vérifieront. La colonne **Statut** est mise à jour à chaque fin de phase. Les noms de tests sont prévisionnels ; la phase 1 les précise.

## Objectifs du cahier des charges

| ID | Exigence | Composants | Tests prévus | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| O1 | Agents qui recommandent à partir d'analyses quantitatives et qualitatives | `agents/` (macro, valuation, sentiment, risque, fundamental, ESG, coordinateur), `tools/`, `debate/`, `agent_prompts/` | Schéma de vue valide pour chaque agent ; chaque vue cite ses sources ; l'agent Valuation appelle ses outils ; débat qui termine (consensus ou vue « contestée ») ; réplication AlphaAgents | 3 | Prévu |
| O2 | Portefeuilles optimisés sous contraintes de risque, de diversification et d'objectifs client | `portfolio/` (Black-Litterman, optimiseur, contraintes, méthodes de comparaison), `config/profiles.yaml`, `config/esg.yaml` | Sans vue, retour au benchmark ; vue plus confiante, déplacement plus grand ; chaque contrainte vérifiée sur chaque solution (long-only, bornes, ESG, volatilité cible, rotation) | 4 | Prévu |
| O3 | Mise à jour et ajustement automatiques | `rebalancing/` (planificateur, déclencheurs, coûts, file de validation) | Simulation sur 3 ans ou plus avec la cause de chaque rééquilibrage ; coûts toujours déduits ; chaque déclencheur testé isolément | 5 | Prévu |
| O4 | Transparence et explicabilité | `explain/` (fiches, attribution), `debate/` (journaux), `app/` | Attribution qui somme à l'écart au benchmark ; chaque poids remonte jusqu'aux vues et aux sources ; journal de débat complet ; test d'usage avec 2 personnes | 3, 6 | Prévu |
| O5 | Évaluation face à des benchmarks traditionnels | `evaluation/` (backtest, métriques, ablations, live test) | Métriques contre des valeurs calculées à la main ; walk-forward sans fuite ; rapport L4 généré par script | 7 | Prévu |

## Livrables

| ID | Livrable | Objectifs | Emplacement | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| L1 | Spécifications fonctionnelles et techniques | Tous | `docs/L1_specifications.md` | 1 | À faire |
| L2 | Prototype d'agents | O1, O4 | `src/amundi_agentic/{llm,tools,agents,debate}`, `agent_prompts/` | 3 | À faire |
| L3 | Module de construction de portefeuille | O2, O3 | `src/amundi_agentic/{portfolio,rebalancing}` | 4, 5 | À faire |
| L4 | Rapport de performance (backtest et live test) | O5 | `docs/L4_rapport_performance.md`, `runs/` | 7 | À faire |
| L5 | Documentation technique et guide gérant | O4 | `README.md`, `docs/` | 8 | À faire |
| L6 | Plan de déploiement (ALTO) | Tous | `docs/L6_plan_deploiement.md` | 9 | À faire |

## Contraintes transverses du prompt maître

| ID | Contrainte | Composants | Tests prévus | Phase | Statut |
| --- | --- | --- | --- | --- | --- |
| C1 | LLM agnostique : interface unique, fournisseur changé par configuration | `llm/`, `config/llm.yaml` | Aucun import de SDK fournisseur hors `llm/` ; changement de fournisseur par config seule ; sorties validées par Pydantic | 3 | Prévu |
| C2 | Budget 0 € : Gemini, Ollama, Groq, relais sur 429, cache, journal des quotas | `llm/` | Relais automatique sur 429 simulée ; requête identique servie par le cache ; alerte avant la limite de quota | 3 | Prévu |
| C3 | Données gratuites, licences documentées | `data/` | Rapport de couverture par source | 2 | Prévu |
| C4 | Données point-in-time | `data/` (`as_of(date)`) | Aucune donnée postérieure à t servie (prix, news, rapports) | 2 | Prévu |
| C5 | ESG : exclusions avant recommandation, scores, contraintes | `agents/` (ESG), `portfolio/` | Titre exclu jamais recommandé ni détenu ; score ESG minimal respecté ; couverture des scores mesurée | 2, 3, 4 | Prévu |
| C6 | Chiffres calculés par des outils, jamais par le LLM | `tools/` | Tests unitaires de chaque outil ; vérification des appels d'outils | 3 | Prévu |
| C7 | Reproductibilité : graines, versions de modèles et de prompts enregistrées | `llm/`, `debate/`, `runs/` | Chaque exécution enregistre modèle, prompt (hash) et graine | 3 | Prévu |
| C8 | La suite de tests passe sans clé d'API | `tests/`, CI | LLM simulé (mock) ; tests `llm` et `network` exclus de la CI | 0, 3 | En place (CI) |
| C9 | Avertissement « prototype académique » | `README.md`, `app/`, rapports | `test_readme_porte_l_avertissement` ; équivalents pour l'interface et les rapports | 0, 6, 7 | Partiel (README) |
| C10 | Secrets uniquement dans `.env`, jamais commités | `.gitignore`, `.env.example` | `test_env_ignore_par_git`, `test_env_example_sans_secret_ni_cle_anthropic` | 0 | En place |
| C11 | Contrôle du look-ahead bias du LLM | `evaluation/` | Résultats séparés avant et après la date de fin d'entraînement ; test d'anonymisation | 7 | Prévu |
