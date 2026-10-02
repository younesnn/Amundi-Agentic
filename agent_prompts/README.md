# agent_prompts/

Prompts de rôle versionnés des agents (un fichier par agent et par version, ex. `valuation_v1.md`).
Le code les charge depuis ce dossier ; chaque exécution enregistre le nom et le hash du prompt utilisé.

Ce dossier remplace le `prompts/` de la section 5.2 du prompt maître, car `prompts/` contient
le prompt maître et ne doit pas être modifié (voir `DECISIONS.md`, D-003).
