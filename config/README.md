# config/

Configuration versionnée, lue par le code (aucune valeur codée en dur) :

| Fichier prévu | Contenu | Phase |
| --- | --- | --- |
| `universe.yaml` | ETF par classe d'actifs, poche actions individuelles, benchmark | 1–2 |
| `profiles.yaml` | Profils prudent, équilibré, dynamique : δ, volatilité cible, bornes, benchmark | 1, 4 |
| `esg.yaml` | Exclusions normatives, score ESG minimal | 1–2, 4 |
| `esg_etf_sources.yaml` | Source ESG manuelle et historisée par ETF (D-048) : SFDR, indice suivi, caractère ESG/PAB/CTB, exclusions documentées ; chaque valeur avec source, dates de document, d'effet et de saisie ; append-only, `inconnu` sans document ; chargé par `data/connectors/esg_etf_sources.py` | 3 |
| `llm.yaml` | Fournisseurs (Gemini, Ollama, Groq), modèles retenus (D-008), ordre de relais ; quotas en phase 3 | 0, 3 |
| `costs.yaml` | Coûts de transaction en points de base par classe d'actifs | 5 |
| `debate.yaml` | Paramètres du débat : tours maximum, règle de consensus, confiance (L1 §6) | 3 |
| `data.yaml` | Couche de données : limites d'usage par source, seuils qualité, séries FRED et BCE, flux RSS, concepts XBRL | 2 |
| `replication.yaml` | Protocole de réplication AlphaAgents : tirage des titres, graine, dates, profils (L1 §9) | 3 |

Les valeurs chiffrées sont fixées en phase 1 comme hypothèses documentées dans `DECISIONS.md`.
