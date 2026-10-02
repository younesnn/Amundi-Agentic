# config/

Configuration versionnée, lue par le code (aucune valeur codée en dur) :

| Fichier prévu | Contenu | Phase |
| --- | --- | --- |
| `universe.yaml` | ETF par classe d'actifs, poche actions individuelles, benchmark | 1–2 |
| `profiles.yaml` | Profils prudent, équilibré, dynamique : δ, volatilité cible, bornes, benchmark | 1, 4 |
| `esg.yaml` | Exclusions normatives, score ESG minimal | 1–2, 4 |
| `llm.yaml` | Fournisseurs (Gemini, Ollama, Groq), modèles retenus (D-008), ordre de relais ; quotas en phase 3 | 0, 3 |
| `costs.yaml` | Coûts de transaction en points de base par classe d'actifs | 5 |
| `debate.yaml` | Paramètres du débat : tours maximum, règle de consensus, confiance (L1 §6) | 3 |
| `replication.yaml` | Protocole de réplication AlphaAgents : tirage des titres, graine, dates, profils (L1 §9) | 3 |

Les valeurs chiffrées sont fixées en phase 1 comme hypothèses documentées dans `DECISIONS.md`.
