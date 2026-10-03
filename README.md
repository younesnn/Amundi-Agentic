# Amundi Agentic

> **Prototype académique (ESCP, projet de 3ᵉ année 2025-2026), pas un conseil en investissement.**

Système d'IA agentique pour la construction de portefeuilles multi-actifs, en réponse au cahier des
charges d'Amundi Technology (`Fiche projet Amundi Agentic.pdf`). Il reprend la méthode AlphaAgents
(BlackRock, arXiv 2508.11152) : agents spécialisés, coordinateur, débat jusqu'au consensus. Il y
ajoute un univers multi-actifs, une construction Black-Litterman sous contraintes, le rééquilibrage
automatique, l'ESG et une évaluation walk-forward.

## État

Phase 0 (socle du dépôt). Voir `PROGRESS.md` pour l'avancement et `DECISIONS.md` pour les choix.

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/). uv installe lui-même Python 3.12.

```bash
uv sync                 # crée .venv et installe les dépendances
cp .env.example .env    # puis remplir les clés localement (jamais commitées)
uv run pytest -m "not llm and not network"   # tests sans clé ni réseau
uv run ruff check .     # lint
uv run amundi-agentic data fetch      # télécharge les données gratuites (cache et reprise ; clés dans .env)
uv run amundi-agentic data coverage   # génère docs/couverture_donnees.md
```

## Organisation

| Dossier | Contenu |
| --- | --- |
| `config/` | Univers, profils clients, ESG, LLM, coûts |
| `agent_prompts/` | Prompts de rôle versionnés |
| `src/amundi_agentic/` | Code : `llm`, `data`, `tools`, `agents`, `debate`, `portfolio`, `rebalancing`, `explain`, `evaluation` |
| `app/` | Tableau de bord Streamlit |
| `tests/` | Tests unitaires et d'intégration (LLM simulé, sans clé d'API) |
| `docs/` | Livrables L1 à L6, matrice de traçabilité |
| `runs/` | Journaux et résultats d'exécution horodatés |

Sources du projet (non modifiées) : les deux PDF, `fiches/`, `graphify-out/`, `prompts/`.
