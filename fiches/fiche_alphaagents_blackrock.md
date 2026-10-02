# Fiche de révision — AlphaAgents (papier BlackRock)

Oct 2, 2026 · @Younes

## L'essentiel en 30 secondes

AlphaAgents est un système de **3 agents IA (LLM GPT-4o) spécialisés** qui analysent des actions, **débattent jusqu'au consensus**, puis disent BUY ou SELL pour chaque titre. Le portefeuille construit par le groupe bat les agents seuls en profil « risk-neutral » sur un test de 4 mois.

| Élément | Ce qu'il faut retenir |
| --- | --- |
| Auteurs | Équipe BlackRock (Zhao, Lyu, Jones, Garber, Pasquali, Mehta), arXiv 2508.11152, août 2025 |
| Question | Une équipe d'agents LLM peut-elle faire du *stock picking* mieux qu'un agent seul ou qu'un benchmark ? |
| Agents | Fundamental (10-K/10-Q), Sentiment (news), Valuation (prix et volumes) |
| Mécanisme clé | Collaboration (rapport commun) + débat en *round robin* jusqu'au consensus |
| Outil technique | Microsoft AutoGen (group chat), AutoGen Studio comme interface |
| Test | 15 actions tech, sélection le 1er février 2024, suivi sur 4 mois, équipondéré |
| Résultat | Risk-neutral : multi-agent > agents seuls et benchmark. Risk-averse : tous sous le benchmark (marché haussier), mais multi-agent avec moins de drawdown |
| Apport | Explicabilité (logs du débat), réduction des biais humains et des hallucinations |
| Ce que ce n'est PAS | Un moteur d'optimisation de portefeuille : il fait seulement de la **sélection** de titres |

## 1. Le problème : pourquoi des agents ?

L'analyste equity humain est débordé par le volume d'information et biaisé par sa psychologie ; les agents LLM visent à traiter les deux.

**Problème n°1 — le volume.** Un analyste doit lire 10-K et 10-Q (rapports annuels et trimestriels SEC), earnings calls, price targets, ratios, news, notes de visite… Trop pour un humain, donc des opportunités d'*alpha* (surperformance) sont ratées.

**Problème n°2 — les biais cognitifs** (finance comportementale, Kahneman & Tversky, *Prospect Theory*) :

- **Aversion aux pertes** : on souffre plus d'une perte qu'on ne jouit d'un gain équivalent.
- **Excès de confiance** : on surestime ses propres jugements.
- Les remèdes classiques (check-lists, ancrage sur la frontière efficiente) marchent mal car ces biais sont **inconscients**.

**La thèse du papier.** Des agents LLM « non biaisés », chacun sur une tâche déléguée, complètent l'humain. Le débat entre agents réduit aussi un problème propre à l'IA : les **hallucinations** (réponses inventées).

**Ce qui existait avant (état de l'art) :**

| Approche | Limite selon les auteurs |
| --- | --- |
| Reinforcement Learning pour portefeuilles | Spécifique à une tâche, données structurées seulement, pas de langage |
| FinRobot | Analyse d'états financiers par agents spécialisés |
| FinMem | Mémoire en couches, dépend de la couverture news |
| MarketSenseAI | 5 agents sur différentes modalités financières |
| FinAgent | Données financières multimodales |
| FinVerse | 600+ API financières pour répondre aux questions d'investisseurs |

**Le trou que comble AlphaAgents :** peu de travaux sur la sélection systématique d'actions par multi-agents, sur l'**interaction structurée** (coopération + débat) et sur le rôle de la **tolérance au risque** des agents.

## 2. Architecture : trois agents, chacun avec ses données et ses outils

Chaque agent imite un analyste d'une équipe de gestion, ne voit **que les données de son rôle**, et dispose d'outils dédiés.

[Schéma : Architecture AlphaAgents · 3 agents, 1 coordinateur, 2 phases]

Les trois agents nourrissent le coordinateur, qui produit d'abord un rapport puis organise le débat ; le gérant garde le dernier mot.

| Agent | Imite | Données | Outil | Horizon |
| --- | --- | --- | --- | --- |
| **Fundamental** | Analyste fondamental | 10-K / 10-Q (états financiers, perspectives) | *Report Pull Tool* (appels API yfinance vérifiés) + *RAG Tool* sur les rapports | Long terme |
| **Sentiment** | Analyste news | Bloomberg News : actualités, changements de notes d'analystes, ventes d'initiés | Outil de **résumé** LLM avec réflexion (résumer, critiquer, affiner) | Court terme (1–3 mois) |
| **Valuation** | Analyste valorisation | Prix Open/High/Low/Close + volumes (Yahoo Finance) | Outil de **calcul** : rendement annualisé et volatilité | Court terme (1–3 mois) |

**Trois techniques à bien comprendre :**

1. **Role prompting** — on donne à chaque LLM un rôle explicite (« As a valuation equity analyst, your primary responsibility is… »). Le modèle répond alors de façon plus pertinente pour sa tâche.
2. **RAG (Retrieval-Augmented Generation)** — l'agent ne lit pas tout le 10-K : il pose des questions, l'outil retrouve les passages pertinents et le LLM répond à partir d'eux. Ici le découpage (*chunking*) suit les **sections du rapport**, et l'outil contient un guide d'expert sur comment lire chaque section. L'agent l'interroge sur : cash-flow et résultat, opérations et marge brute, points d'inquiétude, progrès vers les objectifs.
3. **Résumé vs RAG** — pour les news, les auteurs choisissent le résumé plutôt que le RAG : le résumé « lit tout » et permet à l'agent de se faire une **opinion globale**, alors que le RAG ne ramène que des extraits.

**Pourquoi un outil de calcul pour le Valuation Agent ?** Les LLM calculent mal. On lui fournit donc une calculatrice dédiée pour éviter les chiffres hallucinés (formules en section 5).

**Extensible :** on pourrait ajouter un agent *Technical Analysis* (tendances court terme) ou un agent *Macro Economist* (politique économique).

## 3. Le workflow : collaboration puis débat

Le système fonctionne en deux temps : les agents **coopèrent** pour écrire un rapport d'analyse, puis **débattent** jusqu'à un consensus BUY ou SELL. Un *group chat agent* (coordinateur) orchestre le tout.

**Infrastructure :** Microsoft **AutoGen** (framework multi-agents : *group chat* + *assistant agents*), interface **AutoGen Studio**, modèle **GPT-4o** (choisi après test de plusieurs GPT).

|  | Collaboration | Débat |
| --- | --- | --- |
| But | Produire un **rapport d'analyse** consolidé par action | Trancher **BUY ou SELL** (pas de HOLD) |
| Fonctionnement | Le coordinateur fait parler chaque agent au moins 2 fois, puis consolide | ***Round robin*** : chaque agent reçoit la question + les analyses des autres, met à jour la sienne, et on recommence |
| Fin | Le coordinateur écrit « TERMINATE » | Quand tous sont d'accord (consensus) |
| Règle clé | Tous les inputs sont intégrés | Aucun agent ne peut décider pour le groupe ; tous doivent être invoqués avant de terminer |

**Pourquoi débattre ?** Deux agents peuvent conclure différemment, soit par raisonnement divergent, soit par hallucination. Confronter les analyses corrige les erreurs ; des travaux antérieurs (Du et al., 2023) montrent que le débat multi-agents améliore la factualité.

**Exemple du papier : Zscaler (« Company Z »), investisseur risk-neutral.**

1. Au départ, le Valuation Agent dit **BUY** : hausse d'environ 50 % sur 3 mois, tendance haussière, malgré une forte volatilité.
2. Le Fundamental Agent pointe le résultat net négatif, une marge opérationnelle de −14,5 % et des **ventes d'initiés** (directeurs, trusts familiaux).
3. Le Sentiment Agent relève aussi ces ventes d'initiés.
4. Après débat, **consensus unanime : SELL**. Le Valuation Agent change d'avis.

Le rapport final suit 3 blocs : **indicateurs positifs** (perf. +13,56 % vs +3,85 % pour le S&P 500 en janvier, leader Forrester Wave), **préoccupations** (volatilité, liquidité, initiés, marge), **conclusion** adaptée au profil de risque.

**Transparence :** tout l'historique du débat est enregistré. Le gérant peut le relire et **passer outre** la décision des agents (*human-in-the-loop*).

## 4. La tolérance au risque, injectée par le prompt

Le profil de risque de l'investisseur est écrit **directement dans les instructions** des agents, comme un client exprimerait ses préférences, et non sous forme de seuils chiffrés.

- **Exemple :** pour une même société A, le Valuation Agent dit **SELL** en profil *risk-averse* (trop volatile) et **BUY** en profil *risk-neutral* (momentum positif, avec prudence).
- **Profils testés :** risk-averse, risk-neutral, risk-seeking.
- **Limite découverte :** le profil *risk-seeking* donnait des réponses quasi identiques au *risk-neutral*, il a donc été retiré. Le prompt seul ne suffit pas à différencier des profils proches.

À retenir pour un oral : c'est une approche **qualitative** du risque (le LLM « interprète » le profil), à l'opposé d'une contrainte quantitative classique (volatilité cible, VaR max).

## 5. Évaluation : contrôler les agents, puis backtester

L'évaluation se fait à deux niveaux : la **qualité du raisonnement** des agents, puis la **performance financière** des portefeuilles (backtest).

**Niveau 1 — contrôler les agents**

- **Arize Phoenix** (outil open source d'observabilité LLM) mesure la *faithfulness* (la réponse est-elle fidèle aux documents ?) et la *relevance* (les passages récupérés sont-ils pertinents ?) pour les agents Fundamental et Sentiment.
- Le Valuation Agent n'a pas de « bonne réponse » de référence : on vérifie avec Phoenix qu'il **utilise bien l'outil de calcul** au lieu d'inventer.
- Les débats sont relus par des **humains** pour vérifier leur cohérence logique.

**Niveau 2 — le backtest (protocole)**

| Paramètre | Valeur |
| --- | --- |
| Univers = benchmark | 15 actions tech tirées au hasard |
| Données des agents | Données et news de janvier 2024 |
| Date de construction | 1er février 2024 |
| Période de test | 4 mois |
| Pondération | Équipondérée (pas d'optimisation) |
| Portefeuilles comparés | Valuation seul, Fundamental seul, Multi-agent, Benchmark |
| Exclu | Sentiment seul (pas assez de news sur certaines actions) ; risk-seeking |
| Taux sans risque | Treasury 1 mois |

**Les formules à connaître**

Rendement annualisé (252 jours de bourse par an, n = nombre de jours) :

```latex
R_{annualisé} = (1 + R_{cumulé})^{252/n} - 1
```

Volatilité annualisée :

```latex
\sigma_{annualisée} = \sigma_{quotidienne} \times \sqrt{252}
```

Ratio de Sharpe (rendement excédentaire par unité de risque) :

```latex
S = \frac{R_p - R_f}{\sigma_p}
```

Sharpe glissant (*rolling*) sur une fenêtre de w jours, pour suivre la performance dans le temps :

```latex
S_{rolling}(t) = \frac{\bar{R}_{p,\,t-w+1:t} - R_f}{\sigma_{p,\,t-w+1:t}}
```

Lecture simple : un Sharpe de 1 signifie qu'on gagne 1 point de rendement au-dessus du sans-risque pour chaque point de volatilité. Plus il est haut, mieux c'est ; négatif = on fait moins bien que le placement sans risque.

## 6. Résultats

En risk-neutral, le portefeuille multi-agent fait le mieux ; en risk-averse, tout le monde fait moins bien que le benchmark, mais le multi-agent limite le mieux les pertes.

**Composition des portefeuilles**

| Profil | Valuation seul | Fundamental seul | Multi-agent |
| --- | --- | --- | --- |
| Risk-neutral | Garde tout le benchmark (pas de sélection) | Élargit la sélection (diversification) | Reprend la plupart des choix Fundamental, en plus resserré |
| Risk-averse | Réduit la liste (exclut les plus volatils) | Petit sous-ensemble défensif (bilans solides) | Quelques titres seulement : le consensus prudent |

**Performance (figures 6 à 8 du papier)**

- **Risk-neutral :** le multi-agent bat les deux agents seuls et le benchmark, en rendement cumulé et en Sharpe glissant. Explication des auteurs : il combine le **court terme** (Valuation, Sentiment : 1–3 mois d'historique) et le **long terme** (Fundamental : 10-K).
- **Risk-averse :** tous les portefeuilles sous-performent le benchmark. Raison : la tech montait fortement et les titres volatils (donc tech) ont été exclus. C'est le compromis classique risque / rendement en marché haussier.
- Mais le multi-agent risk-averse a **moins de volatilité et des drawdowns plus faibles** que les agents seuls, surtout en début de période.
- **Risk-neutral vs risk-averse :** le risk-neutral obtient toujours un rendement cumulé plus élevé, quel que soit l'agent.

**Conclusion des auteurs.** AlphaAgents améliore la rigueur d'analyse, surtout quand les signaux se contredisent, et produit des traces de raisonnement transparentes. Il reproduit la logique d'un **comité d'investissement**. Prochaine étape : servir d'entrée à un modèle d'optimisation (**Mean-Variance** ou **Black-Litterman**) et pondérer selon la confiance des agents (un « strong BUY » pèse plus).

## 7. Limites : ce qu'un jury peut vous objecter

Le papier est une **preuve de concept** : l'idée est solide, mais les résultats chiffrés sont trop fragiles pour conclure statistiquement.

| Limite | Pourquoi c'est un problème |
| --- | --- |
| 15 actions, un seul secteur | Échantillon minuscule, aucune diversification sectorielle |
| 4 mois de test, une seule date de départ | Aucun test de significativité ; le résultat peut être de la chance |
| Sharpe glissant négatif sur la figure 6 (environ −0,1 à −0,4) | « Surperformer » veut ici dire « perdre un peu moins » sur la fenêtre affichée |
| GPT-4o entraîné sur des données possiblement postérieures à 2024 | Risque de **look-ahead bias** (le modèle « connaît » peut-être déjà l'avenir) |
| Équipondération, pas d'optimisation | Ce n'est pas encore de la construction de portefeuille |
| BUY/SELL binaire, pas de HOLD | Perd la nuance et la conviction |
| Risk-seeking ≈ risk-neutral | Le prompt ne différencie pas bien des profils proches |
| Sentiment exclu du backtest individuel | Couverture news insuffisante pour certaines actions |
| Pas de coûts de transaction, pas de rééquilibrage | Performance réelle surestimée |
| Consensus forcé | Risque de **pensée de groupe** : un agent s'aligne sans vraie raison |
| Reproductibilité | Un LLM n'est pas déterministe : rejouer le débat peut donner une autre décision |

Ces limites sont des **pistes d'amélioration directes** pour votre projet Amundi.

## 8. Lien avec le projet Amundi

AlphaAgents couvre la partie « agents qui recommandent » du projet ; tout le reste (optimisation, mise à jour automatique, évaluation robuste) est à construire.

| Objectif Amundi | Couvert par AlphaAgents ? |
| --- | --- |
| Agents qui génèrent des recommandations (quanti + quali) | Oui, c'est le cœur du papier |
| Portefeuilles optimisés (risque, diversification, objectifs client) | Non : équipondération ; piste Black-Litterman |
| Mise à jour automatique selon le marché | Non : une seule sélection, pas de rééquilibrage |
| Transparence et explicabilité | Oui : logs du débat, rapports structurés |
| Comparaison à des benchmarks | Partiellement : backtest court et petit |

## Glossaire

| Terme | Définition |
| --- | --- |
| LLM | Grand modèle de langage (ici GPT-4o) |
| Agent | LLM avec un rôle, des outils et une boucle de décision |
| Multi-agents | Plusieurs agents qui communiquent pour résoudre une tâche |
| RAG | Le LLM répond à partir de passages récupérés dans des documents |
| Hallucination | Réponse inventée mais présentée comme vraie |
| Role prompting | Donner un rôle explicite au LLM dans son prompt |
| Round robin | Chacun parle à tour de rôle, en boucle |
| 10-K / 10-Q | Rapports annuel / trimestriel déposés à la SEC (États-Unis) |
| Alpha | Rendement au-delà du benchmark |
| Drawdown | Baisse depuis un pic de valeur |
| Backtest | Tester une stratégie sur des données passées |
| Black-Litterman | Modèle qui combine l'équilibre de marché et les vues de l'investisseur |

## Questions d'auto-test

- [ ] Citez les 3 agents, leurs données et leurs outils.
- [ ] Pourquoi le Sentiment Agent utilise-t-il un résumé plutôt qu'un RAG ?
- [ ] Quelle différence entre collaboration et débat ?
- [ ] Comment le profil de risque est-il intégré, et quelle limite cela révèle-t-il ?
- [ ] Pourquoi les portefeuilles risk-averse sous-performent-ils ?
- [ ] Expliquez pourquoi le multi-agent fait mieux en risk-neutral.
- [ ] Donnez 3 critiques méthodologiques du backtest.
- [ ] Comment brancheriez-vous AlphaAgents sur un modèle Black-Litterman ?
