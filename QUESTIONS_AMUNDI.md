# Questions pour Amundi

Points que le cahier des charges ne précise pas. Pour chacun : la question, l'hypothèse retenue en attendant la réponse (voir `DECISIONS.md`), et l'impact si la réponse diffère.

| # | Sujet | Question | Hypothèse de travail | Impact si la réponse diffère |
| --- | --- | --- | --- | --- |
| Q-1 | Univers exact | Quel univers d'investissement viser : actions seules ou multi-actifs ? Quelles zones ? Une liste d'ETF Amundi de référence ? Une poche d'actions européennes est-elle attendue ? | Multi-actifs par ETF, ETF Amundi quand l'historique gratuit le permet, plus 15 à 50 actions (D-007) | Connecteurs, agents de niveau allocation, benchmark |
| Q-2 | Sources de données | Des données internes Amundi (prix, ESG, recherche) ou Bloomberg sont-elles accessibles aux étudiants ? | Données gratuites uniquement (D-007) | Couverture ESG, qualité des news, profondeur historique |
| Q-3 | Profils clients et ESG | Quels profils de risque et quelles contraintes utiliser ? Quelle politique d'exclusion Amundi appliquer ? | Prudent, équilibré, dynamique ; armes controversées, tabac, charbon thermique (D-007) | Contraintes de l'optimiseur, agent ESG |
| Q-4 | LLM autorisés | Un LLM externe est-il acceptable pour le prototype ? Quel hébergement viser en production ? | Niveaux gratuits externes (Gemini, Groq) et Ollama local ; hébergement interne en production (D-004) | Adaptateurs LLM, plan de déploiement L6 |
| Q-5 | Horizon et fréquence | Quel horizon d'investissement et quelle fréquence de rééquilibrage ? | Horizon de 3 à 5 ans ; revue mensuelle plus déclencheurs (D-007) | Moteur de rééquilibrage, budget d'appels LLM |
| Q-6 | Benchmark | Quel benchmark de référence pour l'évaluation ? | 60 % actions monde / 40 % obligations, décliné par profil (D-007) | Rapport L4, prior Black-Litterman |
| Q-7 | Intégration ALTO | Existe-t-il une documentation des API ALTO ou un format d'échange attendu (vues, poids, fiches) ? | Service d'API générique décrit dans L6 | Plan de déploiement L6 |
| Q-8 | Validation humaine | Qui valide un rééquilibrage chez Amundi (gérant seul, comité, risque) et avec quelle traçabilité ? | Le gérant valide, modifie ou rejette chaque proposition | File de validation (phase 5), interface (phase 6) |
| Q-9 | Devise et change | Quelle devise de référence, et faut-il couvrir le risque de change ? | EUR, sans couverture (D-011) | Σ, choix des ETF, benchmark |
| Q-10 | Coûts de transaction | Quels coûts réalistes par classe d'actifs, y compris le change, la retenue à la source (ETF physiques et synthétiques) et la convention d'exécution (clôture de t ou ouverture de t+1) ? | L1 §10.3, exécution à la clôture de t (D-020) | Performance nette, rotation |
| Q-11 | Risque par profil | Quelles volatilités, tracking errors, rotations et bornes accepter par profil ? La volatilité est-elle une cible ou un plafond strict ? | Valeurs de D-019, plafond strict | Contraintes, calibration de κ |
| Q-12 | Score ESG | Quelle source et quelle méthode de score ESG Amundi retient-elle ? | Scores gratuits partiels et exclusions par secteur (D-022) | Contrainte ESG du portefeuille, couverture |
| Q-13 | Critère de succès de L4 | Qu'attend Amundi : démontrer la mécanique ou prouver un alpha ? Quelle durée de live test est acceptable ? | Démonstration de la mécanique (D-025) | Objet et conclusions de L4 |
| Q-14 | ESG des ETF | Comment Amundi applique-t-elle ses exclusions aux ETF (transparence sur le contenu, labels SFDR, indices PAB) ? | Méthodologie de l'indice de l'ETF (D-022) | Contraintes ESG au niveau allocation |
| Q-15 | Séries obligataires et monétaires | Amundi peut-elle fournir des historiques d'indices ou de valeurs liquidatives en EUR ? | BCE et ICE sur FRED, sinon début retardé (D-011) | Date de début du backtest |
| Q-16 | Poche titres | Quel rôle et quel univers pour la poche d'actions individuelles (satellite, États-Unis ou Europe, plafond par titre) ? Elle consomme environ 94 % du budget d'appels LLM | Actions américaines, 5 à 15 % du portefeuille, trimestrielle sur l'historique long | Agent Fundamental, budget d'appels |
| Q-17 | Modèle figé | Amundi peut-elle fournir, ou autoriser, un modèle à version figée et à date de fin d'entraînement documentée pour l'évaluation ? | Niveau gratuit avec alias (D-008, D-024) | Contamination, reproductibilité |
| Q-18 | Gouvernance | Qui valide les paramètres gelés et les révisions de prompts (risque de modèle) ? | L'équipe, avec trace dans `DECISIONS.md` (D-027) | L6, crédibilité de L4 |
