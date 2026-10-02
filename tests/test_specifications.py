"""Cohérence de la spécification L1 et de la matrice de traçabilité (phase 1).

Critères d'acceptation de la phase 1 :
(a) chaque exigence O1-O5 est reliée à au moins un composant et à au moins un test prévu ;
(b) chaque écart avec AlphaAgents est justifié.

Conventions des documents dont dépendent ces tests (à préserver lors des révisions) :
- C-1 Les exigences sont dans des tableaux Markdown dont la première colonne s'appelle « ID »
  et vaut `EX-Ox-nn` (O1 à O5) ou `EX-NF-nn`.
- C-2 Dans ces tableaux, la colonne « Composants » cite chaque composant entre accents graves ;
  la colonne dont l'en-tête commence par « Tests prévus » cite chaque test entre accents graves,
  sous la forme `test_...` (un joker `*` est admis, ex. `test_contrainte_*`).
- C-3 Les chemins de composants sont relatifs à `src/amundi_agentic/`, sauf ceux qui commencent
  par un dossier racine (`config/`, `app/`, `agent_prompts/`, ...). Un mot entre accents graves
  sans « / » ni « . » (ex. `View`) est un nom de classe, pas un composant.
- C-4 La structure prévue est le tableau de la section « ### 3.2 Modules » de L1 (colonnes
  « Module » et « Fichiers prévus », accolades `{a,b}` développées) ; les fichiers de `config/`
  prévus sont ceux du tableau de `config/README.md`.
- C-5 Les écarts avec AlphaAgents sont le tableau de la section « ## 14. Écarts avec
  AlphaAgents » (colonnes « # », « AlphaAgents », « Ce projet », « Justification »).
- C-6 La matrice regroupe les exigences par plages « EX-O1-01 à EX-O1-16 ».
"""

from __future__ import annotations

import ast
import re
from fnmatch import fnmatch
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
L1 = (ROOT / "docs" / "L1_specifications.md").read_text(encoding="utf-8")
TRACA = (ROOT / "docs" / "tracabilite.md").read_text(encoding="utf-8")
CONFIG_README = (ROOT / "config" / "README.md").read_text(encoding="utf-8")

ID_EX_O = re.compile(r"^EX-O[1-5]-\d{2}$")
ID_EX_NF = re.compile(r"^EX-NF-\d{2}$")
BACKTICKS = re.compile(r"`([^`]+)`")
NOM_TEST = re.compile(r"^test_[a-z0-9_*]+$")

# Sous-paquets de la section 5.2 du prompt, plus les ajouts proposés par L1 (3.2).
SOUS_PAQUETS_5_2 = {
    "llm",
    "data",
    "tools",
    "agents",
    "debate",
    "portfolio",
    "rebalancing",
    "explain",
    "evaluation",
}
AJOUTS_L1 = {"schemas.py", "cli.py"}
# Dossiers racine du dépôt (section 5.2, D-003 pour agent_prompts/).
DOSSIERS_RACINE = {"config", "app", "agent_prompts", "tests", "docs", "runs"}


# --------------------------------------------------------------------------- analyse Markdown


def _section(texte: str, titre: str) -> str:
    """Texte d'une section dont le titre commence par `titre`, jusqu'au titre de même niveau."""
    niveau = len(titre) - len(titre.lstrip("#"))
    lignes = texte.splitlines()
    debut = next((i for i, ligne in enumerate(lignes) if ligne.startswith(titre)), None)
    assert debut is not None, f"section introuvable : {titre!r}"
    fin = len(lignes)
    for j in range(debut + 1, len(lignes)):
        m = re.match(r"^(#+) ", lignes[j])
        if m and len(m.group(1)) <= niveau:
            fin = j
            break
    return "\n".join(lignes[debut:fin])


def _cellules(ligne: str) -> list[str]:
    # Les « \| » échappés à l'intérieur d'une cellule ne séparent pas les colonnes.
    brut = ligne.strip().strip("|").replace(r"\|", "\x00")
    return [c.replace("\x00", "|").strip() for c in brut.split("|")]


def _tableaux(texte: str) -> list[list[dict[str, str]]]:
    """Tous les tableaux Markdown du texte, chaque ligne étant un dict en-tête -> cellule."""
    tableaux, courant, entete = [], [], None
    for ligne in texte.splitlines() + [""]:
        if ligne.lstrip().startswith("|"):
            cellules = _cellules(ligne)
            if entete is None:
                entete = cellules
            elif all(re.fullmatch(r":?-{3,}:?", c) for c in cellules):
                continue
            else:
                courant.append(dict(zip(entete, cellules, strict=False)))
        else:
            if entete is not None:
                tableaux.append(courant)
            courant, entete = [], None
    return tableaux


def _colonne(ligne: dict[str, str], prefixe: str) -> str:
    cles = [k for k in ligne if k.startswith(prefixe)]
    assert len(cles) == 1, f"colonne {prefixe!r} absente ou ambiguë : {list(ligne)}"
    return ligne[cles[0]]


def _exigences(texte: str, motif_id: re.Pattern[str]) -> dict[str, dict[str, list[str]]]:
    """ID -> composants et tests prévus (convention C-1, C-2)."""
    resultat: dict[str, dict[str, list[str]]] = {}
    for tableau in _tableaux(texte):
        for ligne in tableau:
            ident = ligne.get("ID", "")
            if not motif_id.match(ident):
                continue
            assert ident not in resultat, f"{ident} défini deux fois"
            resultat[ident] = {
                "composants": [
                    c
                    for c in BACKTICKS.findall(_colonne(ligne, "Composants"))
                    if "/" in c or "." in c
                ],
                "tests": [
                    t
                    for t in BACKTICKS.findall(_colonne(ligne, "Tests prévus"))
                    if NOM_TEST.match(t)
                ],
            }
    return resultat


def _developper_accolades(nom: str) -> list[str]:
    m = re.search(r"\{([^}]+)\}", nom)
    if not m:
        return [nom]
    return [
        variante
        for choix in m.group(1).split(",")
        for variante in _developper_accolades(nom[: m.start()] + choix.strip() + nom[m.end() :])
    ]


def _structure_prevue() -> tuple[set[str], set[str]]:
    """(modules, fichiers) prévus par la section 3.2 de L1 (convention C-4)."""
    modules, fichiers = set(), set()
    (tableau,) = [t for t in _tableaux(_section(L1, "### 3.2")) if t and "Module" in t[0]]
    for ligne in tableau:
        module = BACKTICKS.findall(ligne["Module"])[0]
        modules.add(module)
        for nom in BACKTICKS.findall(ligne["Fichiers prévus"]):
            for chemin in _developper_accolades(nom):
                fichiers.add(module + chemin)
    return modules, fichiers


def _config_prevue() -> set[str]:
    noms = set()
    for tableau in _tableaux(CONFIG_README):
        for ligne in tableau:
            noms.update(BACKTICKS.findall(ligne.get("Fichier prévu", "")))
    return {f"config/{n}" for n in noms}


def _composant_prevu(composant: str, modules: set[str], fichiers: set[str]) -> bool:
    racine = composant.split("/", 1)[0]
    if racine == "config" and composant != "config/":
        return composant in _config_prevue() or (ROOT / composant).exists()
    if racine in DOSSIERS_RACINE:
        return (ROOT / racine).is_dir()
    if composant.endswith("/"):
        return composant in modules
    return composant in fichiers or composant in modules


def _developper_plages(texte: str, prefixe: str) -> set[str]:
    """IDs cités dans un texte, plages « EX-O1-01 à EX-O1-16 » développées (convention C-6)."""
    ids = set(re.findall(rf"{prefixe}-\d{{2}}", texte))
    for debut, fin in re.findall(rf"({prefixe}-\d{{2}}) à ({prefixe}-\d{{2}})", texte):
        assert debut[:-2] == fin[:-2], f"plage incohérente {debut} à {fin}"
        racine = debut[:-2]
        ids.update(f"{racine}{n:02d}" for n in range(int(debut[-2:]), int(fin[-2:]) + 1))
    return ids


# Les deux documents analysés une fois pour toutes.
EX_L1 = _exigences(_section(L1, "## 1. "), ID_EX_O)
EX_TRACA = _exigences(_section(TRACA, "## Exigences détaillées"), ID_EX_O)


# --------------------------------------------------------------------------- critère (a)


def test_tracabilite_complete():
    """Critère (a) : mêmes EX-O* dans L1 et la matrice, chacune avec composant et test prévu."""
    assert EX_L1, "aucune exigence EX-O* trouvée dans la section 1 de L1"
    assert set(EX_L1) == set(EX_TRACA), (
        f"absentes de la matrice : {sorted(set(EX_L1) - set(EX_TRACA))} ; "
        f"absentes de L1 : {sorted(set(EX_TRACA) - set(EX_L1))}"
    )
    for objectif in ("O1", "O2", "O3", "O4", "O5"):
        assert any(i.startswith(f"EX-{objectif}-") for i in EX_L1), f"{objectif} sans exigence"

    manques = [
        f"{doc} {ident} : {champ} vide"
        for doc, exigences in (("L1", EX_L1), ("tracabilite", EX_TRACA))
        for ident, contenu in exigences.items()
        for champ in ("composants", "tests")
        if not contenu[champ]
    ]
    assert not manques, "\n".join(manques)


@pytest.mark.parametrize("doc", ["L1", "tracabilite"])
def test_composants_cites_existent_dans_la_structure_prevue(doc):
    modules, fichiers = _structure_prevue()
    exigences = EX_L1 if doc == "L1" else EX_TRACA
    inconnus = sorted(
        {
            f"{ident} -> {c}"
            for ident, contenu in exigences.items()
            for c in contenu["composants"]
            if not _composant_prevu(c, modules, fichiers)
        }
    )
    assert not inconnus, "composants hors de la structure prévue (L1 3.2, config/README.md) :\n" + (
        "\n".join(inconnus)
    )


def test_matrice_et_l1_citent_les_memes_tests():
    """Les tests prévus d'une exigence ne divergent pas entre L1 et la matrice (jokers admis)."""
    ecarts = []
    for ident in sorted(set(EX_L1) & set(EX_TRACA)):
        l1, matrice = EX_L1[ident]["tests"], EX_TRACA[ident]["tests"]
        orphelins_l1 = [t for t in l1 if not any(fnmatch(t, m) for m in matrice)]
        orphelins_matrice = [m for m in matrice if not any(fnmatch(t, m) for t in l1)]
        if orphelins_l1 or orphelins_matrice:
            ecarts.append(f"{ident} : L1 seul {orphelins_l1} ; matrice seule {orphelins_matrice}")
    assert not ecarts, "\n".join(ecarts)


def test_composants_de_la_matrice_inclus_dans_ceux_de_l1():
    ecarts = [
        f"{ident} : {sorted(set(EX_TRACA[ident]['composants']) - set(EX_L1[ident]['composants']))}"
        for ident in sorted(set(EX_L1) & set(EX_TRACA))
        if not set(EX_TRACA[ident]["composants"]) <= set(EX_L1[ident]["composants"])
    ]
    assert not ecarts, "\n".join(ecarts)


def test_bilan_annonce_egal_au_decompte():
    """Le « Bilan » de la section 1 de L1 correspond aux exigences réellement listées."""
    bilan = re.search(r"\*\*Bilan :\*\* (\d+) exigences fonctionnelles \(([^)]*)\)", L1)
    assert bilan, "phrase « Bilan » introuvable dans L1"
    assert int(bilan.group(1)) == len(EX_L1)
    for objectif, nombre in re.findall(r"(O[1-5]) : (\d+)", bilan.group(2)):
        assert sum(i.startswith(f"EX-{objectif}-") for i in EX_L1) == int(nombre), objectif


def test_plages_du_tableau_des_objectifs_couvrent_toutes_les_exigences():
    tableau = _section(TRACA, "## Objectifs du cahier des charges")
    assert _developper_plages(tableau, r"EX-O[1-5]") == set(EX_TRACA)


def test_identifiants_numerotes_sans_trou():
    for objectif in ("O1", "O2", "O3", "O4", "O5"):
        numeros = sorted(int(i[-2:]) for i in EX_L1 if i.startswith(f"EX-{objectif}-"))
        assert numeros == list(range(1, len(numeros) + 1)), f"{objectif} : {numeros}"


def test_exigences_non_fonctionnelles_toutes_tracees():
    nf_l1 = _exigences(_section(L1, "## 11. "), ID_EX_NF)
    assert nf_l1, "aucune exigence EX-NF trouvée dans la section 11 de L1"
    for ident, contenu in nf_l1.items():
        assert contenu["composants"], f"{ident} sans composant"
    assert set(nf_l1) <= _developper_plages(TRACA, "EX-NF"), sorted(
        set(nf_l1) - _developper_plages(TRACA, "EX-NF")
    )


# --------------------------------------------------------------------------- structure


def test_modules_de_l1_conformes_a_la_section_5_2():
    modules, _ = _structure_prevue()
    paquets = {m.rstrip("/") for m in modules if m.endswith("/") and m != "app/"}
    assert paquets == SOUS_PAQUETS_5_2, paquets ^ SOUS_PAQUETS_5_2
    fichiers_uniques = {m for m in modules if not m.endswith("/")}
    assert fichiers_uniques == AJOUTS_L1, fichiers_uniques


# --------------------------------------------------------------------------- critère (b)


def _ecarts_alphaagents() -> list[dict[str, str]]:
    tableaux = [t for t in _tableaux(_section(L1, "## 14. ")) if t and "Justification" in t[0]]
    assert len(tableaux) == 1, "un seul tableau d'écarts attendu en section 14"
    return tableaux[0]


def test_chaque_ecart_avec_alphaagents_est_justifie():
    """Critère (b) : chaque ligne du tableau des écarts a une justification non vide."""
    ecarts = _ecarts_alphaagents()
    assert ecarts
    assert [int(e["#"]) for e in ecarts] == list(range(1, len(ecarts) + 1))
    for e in ecarts:
        for champ in ("AlphaAgents", "Ce projet", "Justification"):
            assert e[champ].strip() not in {"", "—", "-"}, f"écart {e['#']} : {champ} vide"


# Manques d'AlphaAgents listés par le prompt maître (section 1) : mot-clé attendu dans
# la colonne « Ce projet » du tableau des écarts.
MANQUES_DU_PROMPT = {
    "univers multi-actifs et agent Macro": "Macro",
    "vues chiffrées puis Black-Litterman": "Black-Litterman",
    "rééquilibrage": "déclencheurs",
    "profils en contraintes quantitatives": "contraintes",
    "ESG avec veto": "veto",
    "backtest walk-forward et coûts": "Walk-forward",
    "protocole anti-fuite": "Point-in-time",
}


@pytest.mark.parametrize("manque", sorted(MANQUES_DU_PROMPT))
def test_manques_d_alphaagents_du_prompt_couverts_par_un_ecart(manque):
    ce_projet = " ".join(e["Ce projet"] for e in _ecarts_alphaagents()).lower()
    assert MANQUES_DU_PROMPT[manque].lower() in ce_projet


# --------------------------------------------------------------------------- dépendances


SDK_INTERDITS_HORS_LLM = (
    "litellm",
    "openai",
    "anthropic",
    "google.genai",
    "google.generativeai",
    "groq",
    "ollama",
)


def _imports(fichier: Path, paquet: str) -> set[str]:
    """Modules importés, imports relatifs résolus par rapport à `paquet` (ex. amundi_agentic.x)."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    noms = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms.update(a.name for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.level == 0:
                base = noeud.module or ""
            else:
                parties = paquet.split(".")
                parties = parties[: len(parties) - noeud.level + 1]
                base = ".".join(parties + ([noeud.module] if noeud.module else []))
            noms.add(base)
            noms.update(f"{base}.{a.name}" for a in noeud.names)
    return noms


def _sdk_interdit(module: str) -> bool:
    if module.startswith("langchain_") and not module.startswith("langchain_core"):
        return True
    return any(module == s or module.startswith(s + ".") for s in SDK_INTERDITS_HORS_LLM)


def test_dependances_entre_modules():
    """L1 3.2 : aucun SDK de fournisseur hors de llm/ ; portfolio/ n'importe ni llm ni agents."""
    paquet = ROOT / "src" / "amundi_agentic"
    fichiers = list(paquet.rglob("*.py")) + list((ROOT / "app").rglob("*.py"))
    violations = []
    for fichier in fichiers:
        rel = fichier.relative_to(ROOT).as_posix()
        if rel.startswith("src/"):
            parties = fichier.relative_to(ROOT / "src").with_suffix("").parts
            paquet_courant = ".".join(parties if parties[-1] == "__init__" else parties[:-1])
            paquet_courant = paquet_courant.removesuffix(".__init__")
        else:
            paquet_courant = "app"
        imports = _imports(fichier, paquet_courant)
        if not rel.startswith("src/amundi_agentic/llm/"):
            violations += [f"{rel} importe {i}" for i in imports if _sdk_interdit(i)]
        if rel.startswith("src/amundi_agentic/portfolio/"):
            violations += [
                f"{rel} importe {i}"
                for i in imports
                if i.startswith(("amundi_agentic.llm", "amundi_agentic.agents"))
            ]
    assert not violations, "\n".join(violations)
