# Questions fixes de l'agent Fundamental (rag_questions_v1)

Le papier AlphaAgents interroge le RAG sur quatre thèmes : flux de trésorerie et résultat, opérations
et marge brute, points d'inquiétude, progrès vers les objectifs. Elles sont les questions CORE
(q = 4 dans le budget de L1 §11.2). Deux questions facultatives (endettement, ventes d'initiés)
complètent la liste ; elles ne sont posées que si le budget d'appels le permet.

Format d'une ligne : `- <id> | <statut> | <sections privilégiées> | <question>`.
`statut` vaut `core` ou `optionnelle`. Les sections privilégiées sont des indications de lecture
(clés du guide `rag_guide_v1.md`), pas un filtre : la récupération reste libre.

- cashflow_resultat | core | Item 7, Item 8, Part1-Item1, Part1-Item2 | Que disent les passages sur le résultat net, le résultat d'exploitation et les flux de trésorerie d'exploitation de la période, et comment évoluent-ils par rapport à la période comparable ?
- exploitation_marge | core | Item 7, Part1-Item2, Item 1 | Que disent les passages sur l'activité, le chiffre d'affaires par segment et la marge brute, et quelles causes la direction donne-t-elle à leur évolution ?
- inquietudes_risques | core | Item 1A, Item 7, Item 3, Part2-Item1A | Quels points d'inquiétude, risques nouveaux ou litiges importants les passages signalent-ils, et lesquels se sont déjà réalisés ?
- progres_objectifs | core | Item 7, Part1-Item2 | Quels progrès vers ses objectifs stratégiques et financiers l'entreprise décrit-elle (perspectives, investissements, initiatives), et sont-ils étayés par des faits ?
- endettement | optionnelle | Item 7, Item 8, Item 7A | Que disent les passages sur l'endettement (dette totale, échéances, charges d'intérêt, liquidités disponibles) et sur la capacité à le rembourser ?
- operations_inities | optionnelle | Item 5, Item 10 | Les passages mentionnent-ils des ventes ou achats d'actions par des dirigeants ou des administrateurs, ou des rachats d'actions de l'entreprise ? Si le rapport ne contient pas ces informations (les formulaires 4 ne font pas partie du RAG), réponds qu'elles ne sont pas disponibles.
