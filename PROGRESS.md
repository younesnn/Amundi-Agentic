# Avancement

Mis à jour par le chef de projet à chaque étape.

| Phase | Intitulé | Statut |
| --- | --- | --- |
| 0 | Cadrage et socle du dépôt | Validée par Younes le 2026-10-02 |
| 1 | Spécifications (L1) | En cours |
| 2 | Couche de données | À faire |
| 3 | Agents et débat (L2) | À faire |
| 4 | Construction du portefeuille (L3) | À faire |
| 5 | Rééquilibrage automatique (O3) | À faire |
| 6 | Explicabilité et interface (O4) | À faire |
| 7 | Évaluation (L4) | À faire |
| 8 | Documentation et guide gérant (L5) | À faire |
| 9 | Plan de déploiement (L6) | À faire |

## Phase 0 — 2026-10-02

- Sources lues : cahier des charges (PDF), papier AlphaAgents (PDF, survol), trois fiches, rapport du graphe de connaissances.
- Créés : `PROMPT.md`, `PROGRESS.md`, `DECISIONS.md` (D-001 à D-007), `QUESTIONS_AMUNDI.md` (Q-1 à Q-8), `docs/tracabilite.md`.
- Socle : structure de la section 5.2, environnement uv + Python 3.12, ruff, pytest, CI GitHub Actions, `.env.example`.
- Relecture `reviewer-tester` : validé, aucune objection bloquante ; 10 tests ajoutés (`tests/test_socle_revue.py`) ; 6 remarques non bloquantes appliquées (CI : uv figé, permissions, matrice 3.11/3.12, couverture ; `--strict-markers` ; commande de test du README ; horizon dans Q-5).
- Tests de connexion : Gemini (Flash), Groq, Ollama, FRED et SEC EDGAR répondent ; modèles retenus dans `config/llm.yaml` (D-008).
- Commit de la phase 0 fait en local. Pas encore fait : push et premier passage de la CI sur GitHub.
