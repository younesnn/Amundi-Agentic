"""HYPOTHESES.md remplace QUESTIONS_AMUNDI.md : complétude, correspondance Q->H, références."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYP = (ROOT / "HYPOTHESES.md").read_text(encoding="utf-8")
Q_RE = re.compile(r"\bQ-\d+\b")


def _blocs() -> dict[str, str]:
    return {b[:4]: b for b in re.split(r"^## (?=H-\d{2} — )", HYP, flags=re.M)[1:]}


def _corps_sans_table() -> str:
    return "\n".join(ligne for ligne in HYP.splitlines() if not re.match(r"\|\s*Q-\d+\s*\|", ligne))


def test_31_hypotheses_h01_a_h31_presentes_une_fois_dans_l_ordre():
    titres = re.findall(r"^## (H-\d{2}) — ", HYP, flags=re.M)
    assert titres == [f"H-{i:02d}" for i in range(1, 32)]


def test_chaque_hypothese_a_valeur_justification_source_alternative_et_statut():
    blocs = _blocs()
    assert len(blocs) == 31
    for ident, b in blocs.items():
        for champ in ("Valeur retenue", "Justification", "Source", "Alternative plausible"):
            assert f"**{champ} :**" in b, f"{ident} sans {champ}"
        assert re.search(r"\*\*Statut :\*\* à valider avec Amundi", b), ident


def test_table_q_vers_h_exacte_meme_numero_31_lignes():
    lignes = re.findall(r"^\|\s*Q-(\d+)\s*\|\s*H-(\d+)\s*\|", HYP, flags=re.M)
    assert [(int(q), int(h)) for q, h in lignes] == [(i, i) for i in range(1, 32)]


def test_hypotheses_a_sensibilite_ont_un_plan_et_une_ligne_de_recapitulatif():
    oui = []
    for ligne in HYP.splitlines():
        m = re.match(r"\|\s*Q-\d+\s*\|\s*(H-\d+)\s*\|.*\|\s*\*\*oui\*\*", ligne)
        if m:
            oui.append(m.group(1))
    assert len(oui) >= 10
    recap = HYP.split("## Hypothèses à sensibilité")[1]
    blocs = _blocs()
    for h in oui:
        assert re.search(rf"\b{h}\b", recap), f"{h} absent du récapitulatif des grilles"
        assert "sensibilité" in blocs[h] or "voir H-" in blocs[h], h


def test_toute_source_citee_est_definie():
    definies = set(re.findall(r"^\| (S-[A-Z]) \|", HYP, flags=re.M))
    citees = set(re.findall(r"\bS-[A-Z]\b", HYP.split("## H-01")[1]))
    assert len(definies) == 14
    assert citees <= definies, citees - definies


def test_sources_sans_date_verifiee_sont_marquees_a_verifier():
    lignes = [ligne for ligne in HYP.splitlines() if re.match(r"\| S-[A-Z] \|", ligne)]
    for ligne in lignes:
        assert (
            "à vérifier" in ligne
            or "existence" in ligne
            or "D-052" in ligne
            or ligne.rstrip().endswith("— |")
            or "documentée" in ligne
            or "documenter" in ligne
        ), ligne


def test_valeurs_cles_alignees_sur_decisions():
    dec = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")
    for motif in ("SR* = 0,35", "IR_min ≈ 2,8/√T", "liste fermée de 9 tests principaux"):
        assert motif in dec, motif
    h11 = _blocs()["H-11"]
    for motif in ("7 / 11 / 16 %", "2 / 3 / 4 %", "5 / 7,5 / 10 %", "SR* = 0,35"):
        assert motif in h11, motif
    assert "| Prudent | 30/70 | 7 % | 2 % | 5 % |" in dec
    assert "| Dynamique | 80/20 | 16 % | 4 % | 10 % |" in dec


def test_aucun_identifiant_q_pendant_dans_hypotheses_docs_et_claude_md():
    assert not Q_RE.findall(_corps_sans_table()), Q_RE.findall(_corps_sans_table())
    for chemin in [ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        trouves = Q_RE.findall(chemin.read_text(encoding="utf-8"))
        assert not trouves, (chemin.name, trouves)


def test_questions_amundi_md_supprime_et_plus_reference_dans_les_fichiers_vivants():
    assert not (ROOT / "QUESTIONS_AMUNDI.md").exists()
    for rel in ("CLAUDE.md", "docs/L1_specifications.md", "docs/tracabilite.md"):
        assert "QUESTIONS_AMUNDI" not in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_q21_residuel_dans_le_yaml_esg_est_la_seule_exception():
    """Registre SHA-256 append-only : la note d'une entrée verrouillée n'est pas réécrivable.
    Seule exception tolérée : 'Q-21' dans config/esg_etf_sources.yaml
    (correspond à H-21 par la table de HYPOTHESES.md)."""
    texte = (ROOT / "config" / "esg_etf_sources.yaml").read_text(encoding="utf-8")
    assert Q_RE.findall(texte) in ([], ["Q-21"])
    assert re.search(r"\| Q-21 \| H-21 \|", HYP)


def test_ex_nf_16_trace_dans_l1_et_la_tracabilite():
    l1 = (ROOT / "docs" / "L1_specifications.md").read_text(encoding="utf-8")
    tr = (ROOT / "docs" / "tracabilite.md").read_text(encoding="utf-8")
    assert re.search(r"^\| EX-NF-16 \|", l1, flags=re.M)
    assert re.search(r"^\| EX-NF-16 \|.*HYPOTHESES\.md", tr, flags=re.M)
    assert "HYPOTHESES.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
