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
| `debate.yaml` | Paramètres du débat : tours maximum, règle de consensus, confiance (L1 §6) | 3 |
| `text_tools.yaml` | Outils de texte : RAG sur les 10-K et 10-Q (formulaires, nombre de dépôts, taille des passages, préfixes d'embedding par profil), résumé de news, juge de l'évaluation RAG ; aucun nom de modèle | 3 |
| `data.yaml` | Couche de données : limites d'usage par source, seuils qualité, séries FRED et BCE, flux RSS, concepts XBRL | 2 |
| `replication.yaml` | Protocole de réplication AlphaAgents : tirage des titres, graine, dates, profils (L1 §9) | 3 |

Les valeurs chiffrées sont fixées en phase 1 comme hypothèses documentées dans `DECISIONS.md`.
