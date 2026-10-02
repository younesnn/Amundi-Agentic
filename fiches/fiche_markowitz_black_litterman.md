# Fiche de révision — Markowitz et Black-Litterman

Oct 2, 2026 · @Younes

## Pourquoi cette fiche

Dans le graphe de connaissances des deux documents, **Markowitz et Black-Litterman sont le pont** entre ce que fait AlphaAgents (choisir des actions) et ce que demande Amundi (objectif 2 : des portefeuilles optimisés).

Ce que montre le graphe :

- La communauté **« Construction de portefeuille »** regroupe l'objectif 2, le livrable « module de construction », Mean-Variance, l'allocation pondérée par la confiance et le portefeuille équipondéré d'AlphaAgents.
- Black-Litterman est relié à l'objectif 2 par un lien *implements* (inféré) : c'est la suite naturelle proposée par le papier (§5).
- Un groupe (hyperedge) « Passer de la sélection de titres à un portefeuille optimisé » relie objectif 2, module de construction, Mean-Variance, Black-Litterman, allocation par confiance et profils de risque.

En clair : **AlphaAgents dit QUOI acheter ; ces modèles disent COMBIEN.**

## 1. Mean-Variance (Markowitz, 1952)

Markowitz choisit les poids qui donnent **le meilleur rendement attendu pour un niveau de risque donné**, en tenant compte des corrélations entre actifs.

**Les ingrédients**

| Symbole | Signification |
| --- | --- |
| w | Vecteur des poids (combien on met sur chaque actif) |
| μ | Rendements attendus de chaque actif |
| Σ | Matrice de covariance (risques et corrélations) |
| λ (ou δ) | Aversion au risque de l'investisseur |

Rendement et risque du portefeuille :

```latex
E[R_p] = w^\top \mu \qquad \sigma_p^2 = w^\top \Sigma w
```

Le problème d'optimisation (on maximise le rendement, pénalisé par le risque) :

```latex
\max_w \; w^\top \mu - \frac{\lambda}{2} \, w^\top \Sigma w \quad \text{s.c.} \; \sum_i w_i = 1
```

Sans autre contrainte, la solution est :

```latex
w^* = \frac{1}{\lambda} \, \Sigma^{-1} \mu \quad (\text{puis normalisée})
```

**Frontière efficiente :** l'ensemble des portefeuilles qu'on ne peut pas améliorer (plus de rendement sans plus de risque). Le client choisit son point sur la frontière selon λ.

**Le gros problème :** les poids sont **très sensibles à μ**, qu'on estime mal. Une petite erreur sur un rendement attendu donne des portefeuilles extrêmes et concentrés (« error maximization »). C'est exactement ce que Black-Litterman corrige.

**Contraintes réelles** à ajouter pour Amundi : pas de vente à découvert (w ≥ 0), poids max par titre ou par secteur, exclusions ESG, volatilité cible selon le profil client.

## 2. Black-Litterman (1990-1992, Goldman Sachs)

Black-Litterman part de **ce que le marché pense déjà** (l'équilibre), puis le déplace vers les **vues de l'investisseur**, proportionnellement à la confiance qu'il a en elles. Résultat : des poids stables et intuitifs.

**Étape 1 — le point de départ : les rendements d'équilibre Π.** On inverse Markowitz : si le portefeuille de marché w\_mkt (poids par capitalisation) est optimal, quels rendements implique-t-il ?

```latex
\Pi = \delta \, \Sigma \, w_{mkt}
```

**Étape 2 — les vues.** Chaque vue s'écrit sous forme matricielle :

| Symbole | Signification | Exemple |
| --- | --- | --- |
| P | Quels actifs la vue concerne (une ligne par vue) | Vue 1 porte sur l'action A |
| Q | Le rendement attendu par la vue | A fera +8 % |
| Ω | Incertitude de chaque vue (petite = forte confiance) | Variance de la vue |
| τ | Incertitude sur l'équilibre (souvent 0,025 à 0,05) | Scalaire |

Vue absolue : « A fera +8 % ». Vue relative : « A battra B de 3 % » (ligne de P = +1 sur A, −1 sur B).

**Étape 3 — le mélange (rendements a posteriori) :**

```latex
\mu_{BL} = \left[(\tau\Sigma)^{-1} + P^\top \Omega^{-1} P\right]^{-1} \left[(\tau\Sigma)^{-1}\Pi + P^\top \Omega^{-1} Q\right]
```

Lecture : une **moyenne pondérée** entre l'équilibre Π et les vues Q. Les poids de cette moyenne sont les inverses des incertitudes : plus une vue est sûre (Ω petit), plus elle tire le résultat.

**Étape 4 —** on injecte μ\_BL dans Markowitz pour obtenir les poids. Sans vue, on retombe sur le portefeuille de marché : c'est ce qui rend la méthode robuste.

**Pourquoi c'est parfait pour des agents LLM :**

- Les **vues Q** = les recommandations des agents (BUY fort → rendement excédentaire positif).
- La **confiance Ω** = la force du consensus (unanimité rapide → Ω petit ; débat long ou partagé → Ω grand). C'est exactement la piste « poids selon la confiance » du papier BlackRock.
- Les **profils de risque** passent par δ et les contraintes, au lieu d'être seulement dans le prompt.
- Chaque poids reste **explicable** : « +3 % sur A car la vue des agents (confiance X) l'écarte de l'équilibre ».

## 3. Des avis des agents aux poids du portefeuille

[Schéma : Des avis des agents aux poids · pipeline Black-Litterman]

C'est l'architecture possible du livrable « module de construction de portefeuille » : les agents fournissent Q et Ω, le marché fournit Π, et Markowitz applique les contraintes du client.

## 4. Comparatif des trois façons de pondérer

|  | Équipondération (AlphaAgents) | Markowitz | Black-Litterman |
| --- | --- | --- | --- |
| Entrées | Liste BUY | μ, Σ, λ | Σ, w\_mkt, δ, vues P/Q/Ω |
| Utilise la confiance des agents | Non | Indirectement, via μ | Oui, via Ω |
| Stabilité des poids | Très stable | Instable (sensible à μ) | Stable (ancré sur l'équilibre) |
| Prise en compte du risque | Aucune | Covariances + λ | Covariances + δ + incertitude des vues |
| Explicabilité | Simple | Faible (boîte noire numérique) | Bonne (écart à l'équilibre dû à une vue) |
| Répond à l'objectif 2 d'Amundi | Non | Partiellement | Oui |

**Pièges à connaître**

- Transformer BUY/SELL en un chiffre Q est un **choix de conception** à justifier (ex. BUY = +2 % de surperformance annuelle, strong BUY = +4 %).
- Calibrer Ω et τ est délicat ; une méthode courante (Idzorek) part d'une confiance en % (0–100 %) facile à relier au degré d'accord des agents.
- Σ doit être estimée proprement (historique + *shrinkage*, ex. Ledoit-Wolf), sinon tout le reste est faux.
- Il faut un **portefeuille de marché** de référence (le benchmark du client).

## Questions d'auto-test

- [ ] Pourquoi Markowitz donne-t-il des portefeuilles extrêmes ?
- [ ] Que représente Π et comment l'obtient-on ?
- [ ] Que se passe-t-il dans Black-Litterman si on n'a aucune vue ?
- [ ] À quoi servent P, Q et Ω ?
- [ ] Comment traduiriez-vous un consensus unanime des agents en Ω ?
- [ ] Pourquoi Black-Litterman aide-t-il l'explicabilité (objectif 4) ?

Repères de dates : Markowitz, *Portfolio Selection*, 1952 ; Black et Litterman (Goldman Sachs), 1990-1992. Formules standard des manuels de gestion de portefeuille.
