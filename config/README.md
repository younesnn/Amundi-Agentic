# config/

Configuration versionnée, lue par le code (aucune valeur codée en dur) :

| Fichier prévu | Contenu | Phase |
| --- | --- | --- |
| `universe.yaml` | ETF par classe d'actifs, poche actions individuelles, benchmark | 1–2 |
| `profiles.yaml` | Profils prudent, équilibré, dynamique : δ, volatilité cible, bornes, benchmark | 1, 4 |
| `esg.yaml` | Exclusions normatives, score ESG minimal | 1–2, 4 |
| `esg_etf_sources.yaml` | Source ESG manuelle et historisée par ETF (D-048) : SFDR, indice suivi, caractère ESG/PAB/CTB, exclusions documentées ; chaque valeur avec source, dates de document, d'effet et de saisie ; append-only, `inconnu` sans document ; chargé par `data/connectors/esg_etf_sources.py` | 3 |
| `esg_etf_sources.lock.json` | Registre d'empreintes append-only (SHA-256 de chaque entrée de `esg_etf_sources.yaml`, position, date de saisie) ; versionné avec la saisie, écrit seulement par `python -m amundi_agentic.data.connectors.esg_etf_sources lock`, jamais à la main | 3 |
| `esg_etf_sources_archive/` | Réponses brutes archivées de l'API des fiches produit (un JSON par ISIN, SHA-256 et corps de requête dans `MANIFEST.json`) ; preuves des entrées `fiche_produit_archivee` | 3 |
| `llm.yaml` | Fournisseurs, modèles par niveau (D-008), section `evaluation` (versions figées, sans relais, D-024), ordre de relais, `defaults` (température 0, graine, délai), `cache`, `retry` et `relay` (valeurs H), `quotas` (limites `null` tant qu'elles ne sont pas relevées, D-052), `pricing` (0 €), `embeddings`, `training_cutoff` | 0, 3 |
| `costs.yaml` | Coûts de transaction en points de base par classe d'actifs | 5 |
| `debate.yaml` | Paramètres du débat et des agents, tous marqués (H) avec leur source (L1 ou outil du quant) : `debate` (R_max, graine de rotation de l'avocat du diable, ordre du round robin, Sentiment en live seulement, 15 titres au plus), `consensus` (écarts), `confidence` (c_max, c_min, g, rho, h, alerte par défaut), `risk` (seuils d'alerte de `tools/risk.py`, `default_replay_weeks`, classe de référence du régime), `grounding` (redemandes, tolérance d'arrondi des chiffres), `valuation`, `fundamental` (questions RAG du papier), `sentiment`, `esg` (critères requis des ETF). Aucune valeur par défaut dans le code : une clé absente est une erreur ; lu par `agents/settings.py` | 3 |
| `text_tools.yaml` | Outils de texte : RAG sur les 10-K et 10-Q (formulaires, nombre de dépôts, taille des passages, préfixes d'embedding par profil), résumé de news, juge de l'évaluation RAG ; aucun nom de modèle | 3 |
| `data.yaml` | Couche de données : limites d'usage par source, seuils qualité, séries FRED et BCE, flux RSS, concepts XBRL | 2 |
| `replication.yaml` | Protocole de réplication AlphaAgents (D-065), tous les paramètres marqués (H) : dates (décision 2024-02-01, suivi jusqu'au 2024-05-31, `as_of` 2024-06-01), profils, règle d'utilisabilité du pool, tirage (14 titres plus ZS, graine dont le SHA-256 est pré-enregistré, 1 000 tirages secondaires), exécutions (baseline, 2 paraphrases, 5 à température 0,7), mapping BUY/SELL, abstention et sensibilité « abstention = BUY », titres sans prix en fin de suivi (dernière valeur connue), formulations interdites du rapport (`rapport_interdit`), taux sans risque `DGS1MO`, bootstrap par blocs de 5 séances, Sharpe glissant, règles de rapport « non concluant ». Hashé en entier par `amundi-agentic preregister` ; lu par `evaluation/repl_config.py`. `replication_paraphrases/<nom>/` : paraphrases des prompts de rôle utilisés (mêmes en-têtes et variables), hashées aussi | 3 |

## Variables d'environnement des données

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `AMUNDI_DATA_DIR` | dossier qui **contient** `store/` (Parquet), `snapshots/` et `http/` ; lue par `data/settings.py` | `.cache/data` |
| `AMUNDI_RAG_DIR` | index du RAG sur les dépôts ; lue par `evaluation/sources.py` | `.cache/rag` |
| `AMUNDI_DATA_STORE` | désigne `store/` **lui-même** ; utilisée seulement par les tests de revue en lecture seule, ignorée par le code : ne pas la confondre avec `AMUNDI_DATA_DIR` | aucune |

Les valeurs chiffrées sont fixées en phase 1 comme hypothèses documentées dans `DECISIONS.md`.
