# Avancement

Mis à jour par le chef de projet à chaque étape.

| Phase | Intitulé | Statut |
| --- | --- | --- |
| 0 | Cadrage et socle du dépôt | Validée par Younes le 2026-10-02 |
| 1 | Spécifications (L1) | Validée par Younes le 2026-10-02 |
| 2 | Couche de données | En cours |
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

## Phase 1 — 2026-10-02

- `docs/L1_specifications.md` v1.1 (architect) : 59 exigences O1–O5 et 14 exigences non fonctionnelles, 21 écarts avec AlphaAgents ; `docs/tracabilite.md` mis à jour.
- Relectures :
  - `reviewer-tester` : 4 objections bloquantes, corrigées. Il a ajouté `tests/test_specifications.py` (critères de la phase vérifiés automatiquement) et `tests/test_config_revue.py`.
  - `financial-critic` : 7 objections bloquantes. La contre-vérification de la v1.1 les juge toutes levées : « acceptable avec réserves ».
- Décisions D-009 à D-027 et questions Q-9 à Q-18 consignées.
- `docs/` exclu de ruff ; `config/README.md` complété (`debate.yaml`, `replication.yaml`).
- Réserves non bloquantes à traiter en phase 4 ou 7 :
  - κ calibré en supposant des vues non corrélées : à recalibrer numériquement sur Σ ;
  - IR_min à recalculer après la correction de Holm (environ 3,6/√T) ;
  - CT-09 relâchée en crise : exempter la rotation de retour vers le benchmark, et publier la fréquence de relâchement ;
  - unités de l'objectif (μ annuel contre coût ponctuel) ;
  - parité de risque calculée hors monétaire ;
  - confiance non comparable entre backtest (K = 2) et live (K = 3) ;
  - anonymisation limitée à l'agent Valuation.
- Décisions de Younes : D-024 validée (versions figées en évaluation, `config/llm.yaml`), D-028 validée (`--import-mode=importlib`), D-029 (plan réduit : environ 15 titres, décisions trimestrielles sur l'historique long).
- À répercuter dans L1 avant le pré-enregistrement : D-029 (poche titres de 15 titres au plus, plafonds par titre).
