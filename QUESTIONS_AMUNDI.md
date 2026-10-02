# Questions pour Amundi

Points que le cahier des charges ne précise pas. Pour chacun : la question, l'hypothèse retenue en attendant la réponse (voir `DECISIONS.md`), et l'impact si la réponse diffère.

| # | Sujet | Question | Hypothèse de travail | Impact si la réponse diffère |
| --- | --- | --- | --- | --- |
| Q-1 | Univers exact | Quel univers d'investissement viser : actions seules ou multi-actifs ? Quelles zones ? Une liste d'ETF Amundi de référence ? | Multi-actifs par ETF, ETF Amundi quand l'historique gratuit le permet, plus 15 à 50 actions (D-007) | Connecteurs, agents de niveau allocation, benchmark |
| Q-2 | Sources de données | Des données internes Amundi (prix, ESG, recherche) ou Bloomberg sont-elles accessibles aux étudiants ? | Données gratuites uniquement (D-007) | Couverture ESG, qualité des news, profondeur historique |
| Q-3 | Profils clients et ESG | Quels profils de risque et quelles contraintes utiliser ? Quelle politique d'exclusion Amundi appliquer ? | Prudent, équilibré, dynamique ; armes controversées, tabac, charbon thermique (D-007) | Contraintes de l'optimiseur, agent ESG |
| Q-4 | LLM autorisés | Un LLM externe est-il acceptable pour le prototype ? Quel hébergement viser en production ? | Niveaux gratuits externes (Gemini, Groq) et Ollama local ; hébergement interne en production (D-004) | Adaptateurs LLM, plan de déploiement L6 |
| Q-5 | Horizon et fréquence | Quel horizon d'investissement et quelle fréquence de rééquilibrage ? | Horizon de 3 à 5 ans ; revue mensuelle plus déclencheurs (D-007) | Moteur de rééquilibrage, budget d'appels LLM |
| Q-6 | Benchmark | Quel benchmark de référence pour l'évaluation ? | 60 % actions monde / 40 % obligations, décliné par profil (D-007) | Rapport L4, prior Black-Litterman |
| Q-7 | Intégration ALTO | Existe-t-il une documentation des API ALTO ou un format d'échange attendu (vues, poids, fiches) ? | Service d'API générique décrit dans L6 | Plan de déploiement L6 |
| Q-8 | Validation humaine | Qui valide un rééquilibrage chez Amundi (gérant seul, comité, risque) et avec quelle traçabilité ? | Le gérant valide, modifie ou rejette chaque proposition | File de validation (phase 5), interface (phase 6) |
