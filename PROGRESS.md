# Avancement

Mis à jour par le chef de projet à chaque étape.

| Phase | Intitulé | Statut |
| --- | --- | --- |
| 0 | Cadrage et socle du dépôt | Validée par Younes le 2026-10-02 |
| 1 | Spécifications (L1) | Validée par Younes le 2026-10-02 |
| 2 | Couche de données | Validée par Younes le 2026-10-03 |
| 3 | Agents et débat (L2) | En cours |
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

## Phase 2 — 2026-10-02

- Couche de données (data-engineer) : connecteurs (yfinance, FRED/ALFRED, BCE, EDGAR, RSS, GDELT, ESG par exclusions, change), stockage Parquet, cache HTTP, contrôle qualité, accès `as_of(date)`, instantanés bruts append-only et manifeste SHA-256, rapport de couverture (`docs/couverture_donnees.md`, généré par script).
- Revues :
  - `reviewer-tester` : 1 objection bloquante (horodatage EDGAR : la « correction » servait des dépôts avant leur acceptation), corrigée (`raw_as_utc`, mode `corrected` supprimé). Il a ajouté 4 fichiers de tests adverses. Validation finale : 304 tests verts, aucun `xfail`, CI Python 3.11 simulée verte, 7 tests réseau verts.
  - `financial-critic` : « acceptable avec réserves ». Rejouabilité (instantanés, manifeste) faite ; matrice ESG, liquidité, contrôle croisé de l'or, creux du benchmark ajoutés ; points restants reportés aux phases 3, 4 et 7 (D-046).
- Décisions D-030 à D-047 ; questions Q-19 à Q-26 ; L1 v1.3 (66 exigences).
- Constats qui contredisaient L1 : indices ICE Euro absents de FRED (début du backtest 2018-08-28 avec le haut rendement, 2014-03-27 sans) ; aucun score ESG gratuit exploitable ; champ `acceptanceDateTime` d'EDGAR non fiable comme UTC.
- Mon erreur corrigée : D-029 laissait croire que limiter la poche à 15 titres réduisait le budget d'appels ; le chiffre était déjà calculé avec 15 titres.
- Décisions de Younes du 2026-10-03 : D-039 corrigée (allocation mensuelle sur tout l'historique, poche titres trimestrielle sur l'historique long) ; D-045 validée avec haut rendement conservé et étiquette « non investissable » sur les périodes de séries synthétiques ; source ESG manuelle par ETF à construire en phase 3 (D-048) ; règle sur les tests (D-049) ; graphify installé en mode code seulement (D-050).
- L1 v1.4 : 69 exigences (O1 18, O2 14, O3 11, O4 9, O5 17). Budget d'appels recalculé (calcul de L1 §11.2) : 852 appels par profil et par an d'historique long (φ = 1), environ 9 060 par profil sur 8,1 ans avant ablations ; la faisabilité dépend des quotas à relever en phase 3.
- Point à confirmer par Younes : l'étiquette « non investissable » s'applique dès qu'une classe détenue ou du benchmark repose sur un segment synthétique ; les titres de la poche (instruments réels cotés en dollars) ne sont pas des proxys.
