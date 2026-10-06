# ruff: noqa: E501
"""Découpage en sections : corrections après la revue sur de vrais 10-K et 10-Q (I1, I2).

Textes SYNTHÉTIQUES reprenant seulement des mises en page observées : table des matières collée au
vrai corps, 10-Q sans ligne « Item 1 », index de renvois en fin de document, renvois coupés.
"""

from __future__ import annotations

from datetime import date

from text_helpers import client, construire_stockage, depot

from amundi_agentic.tools.rag import (
    FALLBACK_SECTION,
    FilingsRAG,
    guide_for,
    load_guide,
    split_sections,
)
from amundi_agentic.tools.text_config import load_text_tools_config

T = date(2024, 2, 1)


def corps(sujet: str, n: int = 8) -> str:
    return "\n\n".join(
        f"{sujet} : paragraphe {i}. Texte de remplissage synthétique sans valeur informative "
        "pour allonger la section au-delà du seuil minimal."
        for i in range(n)
    )


def par_code(text: str, form: str, **kw) -> dict[str, str]:
    return {s.code: s.text for s in split_sections(text, form, **kw)}


# --------------------------------------------------------------------------- table des matières
def test_toc_collee_au_vrai_corps_le_premier_item_n_est_pas_avale():
    """Le vrai « Item 1 » suit de près le dernier élément de la table des matières : la chaîne de
    la table s'arrête au premier code déjà vu."""
    t = (
        "FORM 10-K\n\nTable of Contents\n\nItem 1. Business 3\n\nItem 1A. Risk Factors 9\n\n"
        "Item 7. MD&A 20\n\nItem 8. Financial Statements 30\n\nItem 16. Summary 90\n\n"
        "Item 1. Business\n\n"
        + corps("Corps A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("Corps B", 6)
        + "\n\nItem 7. MD&A\n\n"
        + corps("Corps C", 6)
        + "\n\nItem 8. Financial Statements\n\n"
        + corps("Corps D", 6)
        + "\n\nItem 16. Summary\n\nNone.\n"
    )
    sections = split_sections(t, "10-K")
    codes = [s.code for s in sections]
    assert codes[0] == "Item 1"  # préambule trop court pour être une section
    s = {x.code: x.text for x in sections}
    assert "Corps A : paragraphe 5" in s["Item 1"]
    assert "Corps D : paragraphe 5" in s["Item 8"]
    assert s["Item 16"].endswith("None.")  # le vrai Item 16, pas l'entrée de la table des matières
    assert "Item 16. Summary 90" not in s["Item 8"] and "Item 1. Business 3" not in s["Item 1"]


def test_10q_toc_et_etats_financiers_sous_part1_item1():
    toc = (
        "Part I. Financial Information\n\nItem 1.\nFinancial Statements (Unaudited)\na) Statements of Income\n"
        "b) Balance Sheets\nc) Cash Flows\n3\n\nItem 2.\nManagement’s Discussion and Analysis\n20\n\n"
        "Item 3.\nQuantitative and Qualitative Disclosures About Market Risk\n35\n\nItem 4.\nControls\n35\n\n"
        "Part II. Other Information\n\nItem 1.\nLegal Proceedings\n36\n\nItem 1A.\nRisk Factors\n36\n\n"
        "Item 6.\nExhibits\n42\n\n"
    )
    t = (
        toc
        + "Cautionary note. " * 40
        + "\n\nPart I. Financial Information\n\nItem 1. Financial Statements (Unaudited)\n\n"
        + corps("Comptes trimestriels", 12)
        + "\n\nItem 2. Management’s Discussion and Analysis\n\n"
        + corps("Discussion", 6)
        + "\n\nItem 3. Quantitative and Qualitative Disclosures About Market Risk\n\n"
        + corps("Marché", 3)
        + "\n\nItem 4. Controls and Procedures\n\n"
        + corps("Contrôles", 3)
        + "\n\nPart II. Other Information\n\nItem 1. Legal Proceedings\n\n"
        + corps("Litiges", 3)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("Risques", 4)
        + "\n\nItem 6. Exhibits\n\n"
        + corps("Pièces", 2)
    )
    s = par_code(t, "10-Q")
    assert "Comptes trimestriels : paragraphe 11" in s["Part1-Item1"]
    assert "Comptes trimestriels" not in s["Part2-Item6"]
    assert "Pièces : paragraphe 1" in s["Part2-Item6"]


def test_10q_sans_ligne_item_1_etats_financiers_inferes_et_etiquetes_comme_tels():
    t = (
        "Part I. Financial Information\n\nItem 1.\nFinancial Statements\n3\n\nItem 2.\nMD&A\n20\n\n"
        "Item 3.\nMarket Risk\n35\n\nItem 4.\nControls\n35\n\nPart II. Other Information\n\n"
        "Item 1.\nLegal\n36\n\nItem 1A.\nRisk Factors\n36\n\nItem 6.\nExhibits\n42\n\n"
        + "Avertissement. " * 40
        + "\n\nPART I. FINANCIAL INFORMATION\n\n"  # aucune ligne « Item 1 » dans le corps
        + corps("Bilan et résultat", 12)
        + "\n\nItem 2. Management’s Discussion and Analysis\n\n"
        + corps("Discussion", 6)
        + "\n\nItem 3. Quantitative and Qualitative Disclosures About Market Risk\n\n"
        + corps("Marché", 3)
        + "\n\nPART II. OTHER INFORMATION\n\nItem 1A. Risk Factors\n\n"
        + corps("Risques", 4)
        + "\n\nItem 6. Exhibits\n\n"
        + corps("Pièces", 2)
    )
    sections = split_sections(t, "10-Q")
    s = {x.code: x for x in sections}
    assert "Bilan et résultat : paragraphe 11" in s["Part1-Item1"].text
    assert "inférée" in s["Part1-Item1"].title and "Part1-Item1 - " in s["Part1-Item1"].label
    assert "Bilan et résultat" not in s["Part2-Item6"].text


# --------------------------------------------------------------------------- renvois
def test_renvoi_precede_d_un_mot_de_liaison_ou_suivi_d_une_minuscule_n_est_pas_un_en_tete():
    base = (
        "Item 1. Business\n\n"
        + corps("A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("B", 5)
        + "\n\nFor more information, see\n\nItem 7. Management’s Discussion and Analysis\n\nas discussed below.\n\n"
        + corps("B2", 4)
        + "\n\nItem 7. Management’s Discussion and Analysis\n\n"
        + corps("C", 6)
        + "\n\nItem 8. Financial Statements\n\n"
        + corps("D", 6)
    )
    s = par_code(base, "10-K")
    assert "B2 : paragraphe 3" in s["Item 1A"] and "B2" not in s["Item 7"]
    # un en-tête normal précédé d'un titre de page ou d'un numéro de page reste un en-tête
    ok = base.replace("For more information, see", "Table of Contents")
    ok = ok.replace("as discussed below.", "Overview of the year.")
    assert "B2" in par_code(ok, "10-K")["Item 7"]


def test_items_par_renvoi_adjacents_conserves_sans_table_des_matieres():
    t = (
        "Item 1. Business:\n\n"
        + corps("Activité", 4)
        + "\n\nItem 1A. Risk Factors:\n\n"
        + corps("Risques", 6)
        + "\n\nItem 7. MD&A:\n\nRefer to pages 6 through 38.\n\nItem 7A. Market Risk:\n\nRefer to page 37.\n\n"
        "Item 8. Financial Statements:\n\nRefer to pages 42 through 116.\n\nItem 9. Changes:\n\n"
        + corps("Neuf", 3)
    )
    s = par_code(t, "10-K")
    assert {"Item 7", "Item 7A", "Item 8"} <= set(s) and "pages 42 through 116" in s["Item 8"]


# --------------------------------------------------------------------------- repli (I2)
def test_index_de_renvois_en_fin_de_document_repli_document():
    t = (
        corps("Rapport sans en-têtes standard", 120)
        + "\n\nItem 1.Business:\n\nItem 1A.Risk Factors\n\nItem 1B.Unresolved\n\nItem 2.Properties\n\nItem 3.Legal\n"
    )
    sections = split_sections(t, "10-K", max_preamble_chars=5000)
    assert [s.code for s in sections] == [FALLBACK_SECTION] and len(sections[0].text) > 0.9 * len(
        t.strip()
    )
    # sans le seuil de préambule, c'est le nombre de sections lisibles qui déclenche le repli
    assert [s.code for s in split_sections(t, "10-K")] == [FALLBACK_SECTION]


def test_trop_peu_de_sections_substantielles_repli():
    t = "Item 1. Business\n\n" + corps("A", 6) + "\n\nItem 1A. Risk Factors\n\n" + corps("B", 6)
    assert [s.code for s in split_sections(t, "10-K")] == [FALLBACK_SECTION]
    assert [s.code for s in split_sections(t, "10-K", min_substantial_sections=2)] == [
        "Item 1",
        "Item 1A",
    ]


def test_repli_visible_dans_les_passages_et_le_resultat(tmp_path):
    texte_sans_en_tetes = "\n\n".join(
        f"Rapport atypique, paragraphe {i} sur les litiges, la marge et la dette. " * 6
        for i in range(60)
    )
    pit, _ = construire_stockage(
        tmp_path,
        [
            depot("0001-24-000001", "10-K", "2023-11-03T21:00:00", texte_sans_en_tetes),
            depot("0001-24-000002", "10-Q", "2023-12-03T21:00:00"),
        ],
    )
    cfg = load_text_tools_config().rag.model_copy(update={"max_preamble_chars": 5000})
    rag = FilingsRAG(client(tmp_path), store_dir=tmp_path / "rag", data_view=pit, config=cfg)
    res = rag.query("APEX", "litiges marge dette", T, k=500)
    atypiques = [p for p in res.passages if p.section_fallback]
    normaux = [p for p in res.passages if not p.section_fallback]
    assert atypiques and normaux
    assert all(
        p.section == FALLBACK_SECTION and ":0001-24-000001:" in p.source.source_id
        for p in atypiques
    )
    assert all(p.section != FALLBACK_SECTION for p in normaux)
    assert res.section_fallback is True and res.fallback_accessions == ["0001-24-000001"]
    # jamais d'étiquette de section fausse : aucun passage « Item » issu du dépôt sans en-têtes
    assert not any(
        p.section.startswith(("Item", "Part"))
        for p in res.passages
        if ":0001-24-000001:" in p.source.source_id
    )
    sain = rag.query(
        "APEX", "risque", date(2023, 11, 10), k=500
    )  # seul le dépôt atypique est éligible
    assert sain.section_fallback and sain.fallback_accessions == ["0001-24-000001"]


def test_resultat_sans_repli_drapeaux_faux(tmp_path):
    pit, _ = construire_stockage(tmp_path, [depot("0001-24-000001", "10-K", "2023-11-03T21:00:00")])
    rag = FilingsRAG(client(tmp_path), store_dir=tmp_path / "rag", data_view=pit)
    res = rag.query("APEX", "risque", T, k=3)
    assert res.section_fallback is False and res.fallback_accessions == []
    assert not any(p.section_fallback for p in res.passages)


def test_guide_item_15_et_repli_et_section_inferee():
    g = load_guide()
    assert "états financiers" in g["Item 15"] and "Item 16" in g
    assert "REPLI" in g["Document"] and "inféré" in g["Part1-Item1"]
    assert "[Guide Item 15]" in guide_for(["Item 15 - Exhibits and Financial Statement Schedules"])


def test_etats_financiers_places_apres_item_16_et_signatures_etiquetes_annexe_f():
    t = (
        "Item 1. Business\n\n"
        + corps("A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("B", 6)
        + "\n\nItem 7. MD&A\n\n"
        + corps("C", 6)
        + "\n\nItem 8. Financial Statements\n\nSee Item 15.\n\n"
        + "Item 15. Exhibits\n\n"
        + corps("Pièces", 3)
        + "\n\nItem 16. Form 10-K Summary\n\nNone.\n\nSIGNATURES\n\n"
        + "Signé par le directeur.\n\nCONSOLIDATED BALANCE SHEETS\n\n"
        + corps("Bilan consolidé", 200)
    )
    sections = {x.code: x for x in split_sections(t, "10-K")}
    assert "Bilan consolidé : paragraphe 199" in sections["Annexe-F"].text
    assert "Bilan consolidé" not in sections["Item 16"].text and "None." in sections["Item 16"].text
    assert "états financiers" in load_guide()["Annexe-F"]
