# Guide d'expert pour lire un 10-K ou un 10-Q (rag_guide_v1)

Comme dans AlphaAgents, l'outil de RAG découpe le rapport par sections et joint à chaque passage
un guide de lecture de sa section. Le guide dit COMMENT LIRE la section, jamais QUOI en conclure.
Il ne contient aucun chiffre d'entreprise. Format : un titre `## <clé>` par section (clé = code de
l'item, `Part1-Item2` pour un 10-Q), puis le texte du guide. Fichier versionné, haché à chaque exécution.

## Général
Un rapport 10-K (annuel) ou 10-Q (trimestriel) est déposé auprès de la SEC. Base-toi uniquement sur
les passages retrouvés ; si la réponse n'y est pas, dis-le au lieu de deviner. Compare toujours une
période à la période comparable (trimestre contre même trimestre de l'an dernier pour un 10-Q ; année
contre année pour un 10-K), jamais à la période précédente d'un autre rythme. Note l'unité (milliers,
millions) et la devise annoncées en tête des tableaux. Les chiffres cités sont repris tels quels du
passage, sans calcul ni arrondi par toi ; les ratios sont calculés par les outils Python.

## Item 1
Description de l'activité (Business). Sert à comprendre comment l'entreprise gagne de l'argent :
produits et services, segments, clients, concurrents, saisonnalité, réglementation, effectifs. À
lire pour situer les chiffres des autres sections (quel segment pèse le plus, quelle dépendance à un
client ou à un fournisseur). Ne contient presque pas de chiffres d'évolution.

## Item 1A
Facteurs de risque. Liste exhaustive et souvent générique : la longueur ne mesure pas la gravité. Repère
les risques propres à l'entreprise (dépendance, litiges, chaîne d'approvisionnement, réglementation,
concentration de clients), les risques nouveaux ou reformulés par rapport au dépôt précédent, et le
vocabulaire d'intensité (« pourrait » contre « a eu » ou « a subi » : un risque déjà réalisé pèse plus
qu'un risque hypothétique). Ne traite pas un risque standard de secteur comme un signal négatif en soi.

## Item 1B
Commentaires du personnel de la SEC non résolus. Souvent vide (« Néant »). Un contenu ici est un signal
rare à signaler.

## Item 1C
Cybersécurité (10-K récents) : gouvernance et gestion du risque, incidents significatifs déclarés.

## Item 2
Propriétés : sites, usines, bureaux, détenus ou loués. Utile pour la structure de coûts fixes ; peu de
signal de valorisation.

## Item 3
Procédures judiciaires. Distingue les litiges avec montant provisionné ou estimé des litiges sans
estimation. Une absence d'estimation n'est pas une absence de risque ; ne devine pas le montant.

## Item 5
Marché des actions ordinaires, rachats d'actions, dividendes. Lis les rachats et dividendes comme
des usages du flux de trésorerie, à rapprocher de l'Item 7 et du tableau de flux.

## Item 7
Analyse de la direction (MD&A, Management's Discussion and Analysis). Section la plus utile pour le
résultat, la marge brute, les moteurs de variation (volumes, prix, change, acquisitions), la liquidité
et les sources de financement, les engagements et les perspectives. La direction y explique les
variations : retiens la cause donnée, mais distingue le fait chiffré (tableau) de l'interprétation
(texte). Vérifie la cohérence entre le discours (« solide ») et les chiffres cités. Les points
d'attention et les « progrès vers les objectifs » s'y trouvent souvent.

## Item 7A
Risques de marché : taux, change, matières premières, avec sensibilités. Lis les sensibilités comme des
ordres de grandeur donnés par la direction, avec leurs hypothèses (variation supposée).

## Item 8
États financiers et notes : compte de résultat, bilan, tableau des flux de trésorerie, variations des
capitaux propres, puis les notes (dette, impôts, segments, événements postérieurs). Source primaire des
chiffres : flux d'exploitation, d'investissement et de financement ; dette à court et long terme
(échéances dans les notes) ; résultat net. Les notes expliquent les méthodes (reconnaissance du chiffre
d'affaires, provisions) et les éléments exceptionnels. Vérifie l'unité et la période de chaque colonne.

## Item 9A
Contrôles et procédures. Cherche une faiblesse significative (material weakness) : signal rare et
important ; son absence est la situation normale.

## Item 10
Administrateurs, dirigeants et gouvernance (souvent incorporé par renvoi à la déclaration de procuration,
donc absent du texte). Les ventes d'initiés ne s'y trouvent pas : elles relèvent des formulaires 4, hors
de ce RAG.

## Item 15
Pièces et annexes (Exhibits and Financial Statement Schedules). Attention : plusieurs sociétés placent ICI
leurs états financiers et leurs notes, et l'Item 8 se réduit alors à un renvoi vers l'Item 15 (ou vers les
pages F-). Si le passage contient bilan, compte de résultat, flux de trésorerie ou notes, lis-le avec les
règles de l'Item 8. Sinon, il s'agit d'une liste de pièces sans signal de valorisation.

## Item 16
Résumé du formulaire 10-K (facultatif), souvent « None », parfois suivi des signatures et, selon la mise en
page, des pages F- (états financiers) : traite un contenu financier comme l'Item 8.

## Annexe-F
Pages F : états financiers et notes que certains 10-K placent APRÈS l'Item 16 et les signatures. Contenu
primaire des chiffres : lis-le avec les règles de l'Item 8 (compte de résultat, bilan, flux de trésorerie,
notes).

## Part1-Item1
(10-Q) États financiers intermédiaires non audités et leurs notes : mêmes règles que l'Item 8 d'un
10-K, sur un trimestre et le cumul de l'exercice. Compare au même trimestre de l'exercice précédent. Si le
titre de la section dit que l'en-tête est inféré, la ligne « Item 1 » manquait dans le texte : le contenu est
quand même celui de la Partie I, Item 1 du formulaire 10-Q.

## Part1-Item2
(10-Q) Analyse de la direction trimestrielle : mêmes règles que l'Item 7 d'un 10-K. Repère ce qui
change par rapport au dernier rapport annuel.

## Part1-Item3
(10-Q) Risques de marché : mises à jour de l'Item 7A du dernier 10-K ; souvent « pas de changement
significatif », ce qui est une information en soi.

## Part1-Item4
(10-Q) Contrôles et procédures : mêmes règles que l'Item 9A.

## Part2-Item1
(10-Q) Procédures judiciaires : mises à jour de l'Item 3 du 10-K.

## Part2-Item1A
(10-Q) Facteurs de risque : seulement les changements importants par rapport au 10-K ; chaque ajout
est un signal plus fort que dans un 10-K, où la liste est entière.

## Part2-Item2
(10-Q) Rachats d'actions non enregistrés et utilisation du produit : lis comme l'Item 5 du 10-K.

## Document
REPLI (`section_fallback` vrai) : le découpage par sections a échoué pour ce dépôt (en-têtes absents, index
de renvois en fin de document, trop peu de sections lisibles). Le rapport est découpé en fenêtres sans
section. Sois plus prudent : tu ne sais pas de quelle partie du rapport vient le passage ; ne le présente
pas comme venant de l'analyse de la direction ou des états financiers, et dis dans ta réponse que la section
d'origine est inconnue.
