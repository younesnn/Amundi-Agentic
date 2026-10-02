# Fiche de révision — Projet Amundi Agentic AI

Oct 2, 2026 · @Younes

## L'essentiel en 30 secondes

Projet de 3ᵉ année (2025-2026) pour **Amundi** : concevoir un **système d'agents IA autonomes** qui analysent le marché, évaluent les risques et recommandent des investissements, puis en tirer des **portefeuilles optimisés**, mis à jour automatiquement, explicables, et comparés à des benchmarks.

En une phrase : il faut aller **plus loin qu'AlphaAgents** (BlackRock), qui ne fait que choisir des actions. Ici on demande la chaîne complète : recommandation → construction de portefeuille → rééquilibrage → évaluation → intégration chez Amundi.

## 1. L'entreprise : Amundi et sa division tech

Amundi est un des plus grands gérants d'actifs au monde ; le projet s'inscrit dans sa division **Amundi Technology**, qui vend des outils de gestion à d'autres acteurs.

| Entité | Ce que dit la fiche | À retenir pour le projet |
| --- | --- | --- |
| **Amundi Asset Management** | Leader européen, siège à Paris, 30+ pays ; actions, taux, multi-actifs, alternatifs ; clients institutionnels et particuliers | Forte culture **ESG** (environnement, social, gouvernance) intégrée à tous les processus d'investissement |
| **Amundi Technology** | Division qui fournit des solutions technologiques sur toute la chaîne de gestion : portefeuille, risque, conformité, reporting client | Mise sur big data, IA et machine learning ; insiste sur la **flexibilité** et la **personnalisation** |
| **ALTO** (Amundi Leading Technology & Operations) | Plateforme cloud phare : gestion de portefeuille, exécution d'ordres, analyse risque et performance, contrôle conformité, reporting | C'est là que votre système devrait s'**intégrer** à terme (livrable « plan de déploiement ») |

**Pourquoi c'est important :** vos agents ne vivent pas seuls. Ils devront respecter les contraintes ESG, de conformité et de reporting déjà gérées dans ALTO, et être configurables par client.

## 2. Contexte et les 5 objectifs

Amundi veut utiliser l'**IA agentique** pour optimiser la construction de portefeuilles : des agents autonomes qui analysent les données de marché, évaluent les risques et proposent des recommandations **personnalisées**, pour une gestion **dynamique** des portefeuilles clients.

| # | Objectif (fiche) | Ce que ça veut dire concrètement | Ce qu'apporte le papier BlackRock |
| --- | --- | --- | --- |
| 1 | Agents qui génèrent des recommandations à partir d'analyses **quantitatives et qualitatives** | Des agents spécialisés : chiffres (prix, ratios, volatilité) + texte (rapports, news) | Modèle direct : 3 agents + débat |
| 2 | Construire des portefeuilles **optimisés** sous contraintes de risque, diversification et objectifs client | Transformer les avis en **poids** : optimisation Markowitz, Black-Litterman, limites par titre/secteur | Absent : équipondération seulement |
| 3 | **Automatiser** la mise à jour selon le marché et les signaux des agents | Boucle de suivi : nouveaux signaux → rééquilibrage, avec règles de déclenchement | Absent : une seule sélection au 1er février 2024 |
| 4 | Améliorer **transparence et explicabilité** pour gérants et clients | Chaque recommandation justifiée, traçable, contestable par un humain | Logs de débat, rapports structurés |
| 5 | **Évaluer** la performance face à des benchmarks traditionnels | Backtest + test en conditions réelles, indicateurs de risque/rendement | Sharpe et Sharpe glissant, mais test court (4 mois, 15 titres) |

**Le mot-clé à comprendre : « agentique ».** Un agent n'est pas un simple modèle qui prédit : c'est un LLM qui a un **rôle**, des **outils** (API, calculs, recherche documentaire), et qui **agit en plusieurs étapes** de façon autonome, souvent en interaction avec d'autres agents.

## 3. Les 6 livrables attendus

La fiche demande six livrables qui vont de la conception à l'intégration ; dans l'ordre logique de réalisation :

| # | Livrable | Contenu probable | Objectif servi |
| --- | --- | --- | --- |
| 1 | **Spécifications fonctionnelles et techniques** | Rôles des agents, données, outils, workflow, architecture, choix du LLM et du framework | Tous |
| 2 | **Prototype d'agents** qui génèrent des recommandations | Code des agents (ex. AutoGen, LangGraph, CrewAI), prompts, outils | 1, 4 |
| 3 | **Module de construction de portefeuille** | Passer des recommandations à des poids sous contraintes (risque, diversification, client) | 2, 3 |
| 4 | **Rapport de performance** : backtesting **et** live testing | Comparaison au benchmark : rendement, volatilité, Sharpe, drawdown | 5 |
| 5 | **Documentation technique et guide utilisateur** pour les gérants | Comment lancer, lire et contester une recommandation | 4 |
| 6 | **Plan de déploiement** et recommandations d'intégration | Intégration aux processus Amundi (ALTO), gouvernance, risques, étapes | Tous |

À noter : le livrable 4 exige un **live testing**, pas seulement un backtest. Il faut donc prévoir de faire tourner le système sur une période réelle pendant le projet.

## 4. Le système cible, de bout en bout

[Schéma : Système cible · 6 étapes, 5 objectifs, 1 boucle de mise à jour]

Les 5 objectifs forment une boucle : les agents recommandent, le module construit et ajuste le portefeuille, l'évaluation mesure, et le gérant garde la main grâce aux justifications.

## 5. Concepts clés à maîtriser

| Concept | En clair |
| --- | --- |
| IA agentique | LLM avec rôle + outils + autonomie en plusieurs étapes |
| Système multi-agents | Plusieurs agents spécialisés qui coopèrent ou débattent |
| Analyse quantitative | Chiffres : prix, volumes, ratios, volatilité |
| Analyse qualitative | Texte : rapports annuels, news, appels de résultats |
| Optimisation moyenne-variance (Markowitz) | Choisir les poids qui maximisent le rendement pour un risque donné |
| Black-Litterman | Partir de l'équilibre de marché et y injecter des « vues » (ici : celles des agents), pondérées par la confiance |
| Diversification | Répartir pour réduire le risque spécifique |
| Rééquilibrage | Ajuster les poids quand le marché ou les signaux changent |
| Backtest / live test | Tester sur le passé / en temps réel |
| Benchmark | Portefeuille de référence à battre (ex. un indice) |
| Explicabilité | Pouvoir dire **pourquoi** l'agent recommande X |
| ESG | Critères environnementaux, sociaux, de gouvernance |

## 6. Questions ouvertes à clarifier avec Amundi

La fiche ne précise pas ces points ; ils conditionnent la conception :

- **Univers d'investissement :** actions seules ou multi-actifs ? Quelle zone (Europe, US) ?
- **Données :** quelles sources sont accessibles (Bloomberg, données internes Amundi) ?
- **Client type :** quels profils de risque et contraintes (ESG, exclusions) ?
- **LLM autorisés :** modèle externe (GPT, Claude) ou hébergé en interne pour la confidentialité ?
- **Horizon et fréquence** de rééquilibrage ?
- **Benchmark** de référence pour l'évaluation ?

## Questions d'auto-test

- [ ] Que sont Amundi Technology et ALTO, et pourquoi comptent-ils pour le projet ?
- [ ] Citez les 5 objectifs de la fiche.
- [ ] Lesquels sont déjà traités par AlphaAgents, lesquels non ?
- [ ] Citez les 6 livrables dans l'ordre logique.
- [ ] Quelle différence entre backtesting et live testing ?
- [ ] Comment passer d'une recommandation BUY/SELL à un poids dans le portefeuille ?
