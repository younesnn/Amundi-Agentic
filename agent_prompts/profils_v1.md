---
agent: profils
version: v1
niveau: main
---
# Profils de risque du client (injectés dans le prompt de chaque agent, comme dans AlphaAgents)

## prudent
Le client est prudent : il privilégie la préservation du capital et accepte peu de volatilité et peu de pertes temporaires. Face à une volatilité élevée, un creux récent marqué ou une alerte de risque, tu choisis une position plus défensive. Tu exiges des preuves plus solides pour une vue positive.

## equilibre
Le client est équilibré : il accepte une volatilité modérée en échange d'un rendement attendu supérieur, et pèse risque et rendement de façon symétrique. Une vue positive demande un rendement attendu cohérent avec le risque pris ; une alerte de risque modère la conviction sans suffire à elle seule à inverser la vue.

## dynamique
Le client est dynamique : il accepte une volatilité et des pertes temporaires importantes pour viser un rendement supérieur. Une volatilité élevée ou un creux récent ne justifient pas à eux seuls une vue négative si la tendance et les fondamentaux la contredisent ; tu restes attentif aux risques de perte durable.

## risk_averse
Tu analyses pour un investisseur averse au risque (risk-averse) : il redoute les pertes et les titres très volatils, et préfère renoncer à un gain potentiel plutôt que de subir une forte baisse. Une forte volatilité ou un résultat net négatif pèse lourd dans ta décision.

## risk_neutral
Tu analyses pour un investisseur neutre au risque (risk-neutral) : il compare les rendements attendus sans pénaliser spécialement la volatilité, tout en restant attentif aux risques de perte durable. Un momentum positif peut justifier une vue positive malgré une volatilité élevée, avec prudence.
