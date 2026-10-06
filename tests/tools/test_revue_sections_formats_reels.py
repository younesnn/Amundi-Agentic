# ruff: noqa: E501
"""Revue indépendante : découpage en sections sur des mises en page observées dans de vrais 10-K
et 10-Q (essai en lecture seule sur 30 dépôts de 15 sociétés, voir le compte rendu de revue).

Les textes ci-dessous sont SYNTHÉTIQUES et courts (société « Zeta ») : seule la mise en page des
en-têtes est reprise (table des matières avec numéros de page, en-têtes « Item N. » seuls sur une
ligne, majuscules, en-têtes courants de page, pied de page, 10-Q à deux parties). Aucun texte de
rapport réel n'est stocké.

Les défauts constatés sur de vrais rapports (table des matières prise pour une section, états
financiers d'un 10-Q étiquetés « Exhibits », renvoi à majuscule pris pour un en-tête) sont corrigés ;
les tests correspondants restent comme régressions.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from amundi_agentic.tools.rag import split_sections


def corps(sujet: str, n: int = 8) -> str:
    return "\n\n".join(
        f"{sujet} : paragraphe {i}. Texte de remplissage synthétique sans valeur informative "
        "pour allonger la section au-delà du seuil minimal."
        for i in range(n)
    )


def par_code(text: str, form: str) -> dict[str, str]:
    return {s.code: s.text for s in split_sections(text, form)}


# ---------------------------------------------------------------- mise en page « Apple » (10-K)
def k_apple() -> str:
    return (
        "zeta-20250927\n\nUNITED STATES\n\nSECURITIES AND EXCHANGE COMMISSION\n\nFORM 10-K\n\n"
        "Zeta Inc.\n\nTABLE OF CONTENTS\n\nPage\n\nPart I\n\n"
        "Item 1.\n\nBusiness\n\n1\n\nItem 1A.\n\nRisk Factors\n\n5\n\nItem 1B.\n\n"
        "Unresolved Staff Comments\n\n17\n\nPart II\n\nItem 7.\n\nManagement’s Discussion and "
        "Analysis of Financial Condition and Results of Operations\n\n21\n\nItem 7A.\n\n"
        "Quantitative and Qualitative Disclosures About Market Risk\n\n27\n\nItem 8.\n\n"
        "Financial Statements and Supplementary Data\n\n28\n\nPart IV\n\nItem 15.\n\n"
        "Exhibit and Financial Statement Schedules\n\n54\n\nItem 16.\n\nForm 10-K Summary\n\n57\n\n"
        "This Annual Report on Form 10-K contains forward-looking statements, within the meaning "
        "of the Private Securities Litigation Reform Act of 1995. "
        * 4
        + "\n\nPART I\n\nItem 1. Business\n\n"
        + corps("Activité de Zeta")
        + "\n\nZeta Inc. | 2025 Form 10-K | 4\n\nItem 1A. Risk Factors\n\n"
        + corps("Facteurs de risque")
        + "\n\nItem 1B. Unresolved Staff Comments\n\nNone.\n\nPART II\n\n"
        + "Item 7. Management’s Discussion and Analysis of Financial Condition and Results of "
        "Operations\n\n"
        + corps("Analyse de la direction")
        + "\n\nItem 7A. Quantitative and Qualitative Disclosures About Market Risk\n\n"
        + corps("Risque de marché", 4)
        + "\n\nItem 8. Financial Statements and Supplementary Data\n\n"
        + corps("États financiers", 10)
        + "\n\nPART IV\n\nItem 15. Exhibit and Financial Statement Schedules\n\n"
        + corps("Annexes", 3)
        + "\n\nItem 16. Form 10-K Summary\n\nNone.\n\nSIGNATURES\n"
    )


def test_apple_les_items_cles_sont_retrouves_avec_leur_vrai_corps():
    s = par_code(k_apple(), "10-K")
    for code in ("Item 1", "Item 1A", "Item 1B", "Item 7", "Item 7A", "Item 8", "Item 15"):
        assert code in s, code
    assert "Facteurs de risque : paragraphe 0" in s["Item 1A"]
    assert "Analyse de la direction : paragraphe 0" in s["Item 7"]
    assert "Risque de marché : paragraphe 0" in s["Item 7A"]
    assert "États financiers : paragraphe 9" in s["Item 8"]
    # la table des matières n'est pas prise pour le corps de la section
    assert "Facteurs de risque" not in s["Item 7"] and "Activité de Zeta" not in s["Item 1A"]


def test_apple_aucune_section_parasite_issue_de_la_table_des_matieres():
    sections = split_sections(k_apple(), "10-K")
    codes = [s.code for s in sections]
    assert codes[1] == "Item 1", codes  # juste après le préambule vient la vraie Item 1
    item16 = [s for s in sections if s.code == "Item 16"]
    assert all("forward-looking" not in s.text for s in item16)


# ---------------------------------------------------------------- mise en page « Microsoft » (10-K)
def k_microsoft() -> str:
    return (
        "FORM 10-K\n\nZeta Corp\n\nTABLE OF CONTENTS\n\nItem 1.\n\nBusiness\n\n3\n\nItem 1A.\n\n"
        "Risk Factors\n\n12\n\nItem 7.\n\nManagement’s Discussion\n\n30\n\nItem 8.\n\n"
        "Financial Statements and Supplementary Data\n\n40\n\nItem 9A.\n\nControls\n\n90\n\n"
        "PART I\n\nItem 1\n\nNote About Forward-Looking Statements\n\n"
        + corps("Avertissement", 3)
        + "\n\nITEM 1. BUSINESS\n\n"
        + corps("Activité", 6)
        + "\n\nItem 1\n\n"  # en-tête courant de page (répété sur chaque page)
        + corps("Suite activité", 3)
        + "\n\nITEM 1A. RISK FACTORS\n\n"
        + corps("Risques", 8)
        + "\n\nItem 1A\n\nITEM 7. MANAGEMENT’S DISCUSSION AND ANALYSIS\n\n"
        + corps("Discussion", 8)
        + "\n\nITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n\n"
        + corps("Comptes", 8)
        + "\n\nITEM 9A. CONTROLS AND PROCEDURES\n\n"
        + corps("Contrôles", 3)
    )


def test_microsoft_en_tetes_majuscules_et_en_tetes_courants_de_page():
    s = par_code(k_microsoft(), "10-K")
    for code in ("Item 1", "Item 1A", "Item 7", "Item 8", "Item 9A"):
        assert code in s
    assert "Risques : paragraphe 7" in s["Item 1A"]
    assert "Discussion : paragraphe 0" in s["Item 7"] and "Risques" not in s["Item 7"]
    assert "Comptes : paragraphe 7" in s["Item 8"]


# ---------------------------------------------------------------- Item 7/8 « par renvoi » (IBM)
def k_incorpore() -> str:
    return (
        "FORM 10-K\n\nZeta Machines\n\nItem 1. Business:\n\n"
        + corps("Activité", 4)
        + "\n\nItem 1A. Risk Factors: \n\n"
        + corps("Risques", 6)
        + "\n\nItem 7. Management’s Discussion and Analysis of Financial Condition and Results of "
        "Operations:\n\nRefer to pages 6 through 38 of the 2025 Annual Report, which are "
        "incorporated herein by reference.\n\nItem 7A. Quantitative and Qualitative Disclosures "
        "About Market Risk:\n\nRefer to the section titled “Market Risk” on page 37.\n\n"
        "Item 8. Financial Statements and Supplementary Data:\n\nRefer to pages 42 through 116.\n\n"
        "Item 9. Changes in and Disagreements with Accountants:\n\n" + corps("Neuf", 3)
    )


def test_items_incorpores_par_renvoi_courts_mais_detectes_sans_voler_le_texte_voisin():
    s = par_code(k_incorpore(), "10-K")
    assert {"Item 1", "Item 1A", "Item 7", "Item 7A", "Item 8", "Item 9"} <= set(s)
    assert "incorporated herein by reference" in s["Item 7"]
    assert "Market Risk" in s["Item 7A"] and "Risques" not in s["Item 7A"]
    assert "pages 42 through 116" in s["Item 8"]


# ---------------------------------------------------------------- 10-Q « Nvidia » (parties I et II)
def q_nvidia() -> str:
    return (
        "zeta-20260726\n\nFORM 10-Q\n\nZeta Corp\n\nTable of Contents\n\nPage\n\n"
        "Part I. Financial Information\n\nItem 1.\nFinancial Statements (Unaudited)\n"
        "a) Condensed Consolidated Statements of Income for the three and six months ended\n"
        "b) Condensed Consolidated Balance Sheets as of\nc) Condensed Consolidated Statements of "
        "Comprehensive Income for the three and six months ended\nd) Condensed Consolidated "
        "Statements of Shareholders’ Equity for the three and six months ended\ne) Condensed "
        "Consolidated Statements of Cash Flows for the six months ended\nf) Notes to Condensed "
        "Consolidated Financial Statements\n3\n\nItem 2.\nManagement’s Discussion "
        "and Analysis of Financial Condition and Results of Operations\n20\n\nItem 3.\n"
        "Quantitative and Qualitative Disclosures About Market Risk\n35\n\nItem 4.\n"
        "Controls and Procedures\n35\n\nPart II. Other Information\n\nItem 1.\nLegal "
        "Proceedings\n36\n\nItem 1A.\nRisk Factors\n36\n\nItem 6.\nExhibits\n42\n\nSignature\n43\n\n"
        "Where You Can Find More Information\n\nInvestors and others should note that we announce "
        "material financial information to our investors using our corporate website and press "
        "releases. "
        * 3
        + "\n\nPart I. Financial Information\n\nItem 1. Financial Statements (Unaudited)\n\n"
        + "Condensed Consolidated Statements of Income\n\n"
        + corps("États trimestriels", 9)
        + "\n\nItem 2. Management’s Discussion and Analysis of Financial Condition and Results of "
        "Operations\n\n"
        + corps("Discussion trimestrielle", 8)
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


def test_nvidia_10q_mda_et_facteurs_de_risque_retrouves():
    s = par_code(q_nvidia(), "10-Q")
    assert "Discussion trimestrielle : paragraphe 7" in s["Part1-Item2"]
    assert "Risques : paragraphe 3" in s["Part2-Item1A"]
    assert "Litiges : paragraphe 0" in s["Part2-Item1"]
    assert "Marché" in s["Part1-Item3"]


def test_nvidia_10q_les_etats_financiers_sont_dans_part1_item1_pas_dans_les_pieces():
    s = par_code(q_nvidia(), "10-Q")
    assert "États trimestriels : paragraphe 8" in s["Part1-Item1"]
    assert "États trimestriels" not in s.get("Part2-Item6", "")


# ---------------------------------------------------------------- renvois et faux en-têtes
def test_renvoi_en_minuscule_en_debut_de_ligne_n_est_pas_un_en_tete():
    t = (
        "Item 1. Business\n\n"
        + corps("A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("B", 6)
        + "\n\nItem 7 of this report discusses liquidity in detail.\n\nItem 7A. is incorporated "
        "by reference as described above.\n\n"
        + corps("B2", 3)
        + "\n\nItem 7. Management’s Discussion\n\n"
        + corps("C", 6)
    )
    s = par_code(t, "10-K")
    assert "Item 7 of this report" in s["Item 1A"] and "B2 : paragraphe 2" in s["Item 1A"]
    assert "Item 7A" not in s


def test_renvoi_a_majuscule_isole_sur_une_ligne_n_est_pas_un_en_tete():
    t = (
        "Item 1. Business\n\n"
        + corps("A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("B", 5)
        + "\n\nFor more information, see\n\nItem 7. Management’s Discussion and Analysis of "
        "Financial Condition\n\nas discussed below.\n\n"
        + corps("B2", 4)
        + "\n\nItem 7. Management’s Discussion and Analysis of Financial Condition\n\n"
        + corps("C", 6)
    )
    s = par_code(t, "10-K")
    assert "B2 : paragraphe 3" in s["Item 1A"]
    assert "B2" not in s["Item 7"]


def test_table_des_matieres_ignoree_quand_le_corps_suit():
    toc = (
        "Table of Contents\n\nItem 1. Business 3\n\nItem 1A. Risk Factors 9\n\nItem 7. MD&A 20\n\n"
    )
    t = (
        toc
        + "Item 1. Business\n\n"
        + corps("Corps A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("Corps B", 6)
        + "\n\nItem 7. MD&A\n\n"
        + corps("Corps C", 6)
    )
    s = par_code(t, "10-K")
    assert "Corps A : paragraphe 0" in s["Item 1"] and "Corps B : paragraphe 5" in s["Item 1A"]
    assert "Item 1A. Risk Factors 9" not in s["Item 1A"]


def test_mise_en_page_atypique_sans_en_tetes_standard_repli_ou_preambule_signale():
    """Intel (INTC) place ses « Item N » dans un index de renvois en fin de document : tout le texte
    tombe dans le « Préambule » (513 000 caractères) au lieu du repli explicite « Document »."""
    t = (
        corps("Rapport sans en-têtes standard", 60)
        + "\n\nItem 1.Business:\n\nItem 1A.Risk Factors\n\n"
        + "\n\n".join(f"Item {n}.Titre" for n in (2, 3, 4))
        + "\n"
    )
    codes = [s.code for s in split_sections(t, "10-K")]
    assert codes[0] in ("Préambule", "Document")  # comportement actuel accepté : ni perte ni erreur
    assert sum(len(s.text) for s in split_sections(t, "10-K")) > 0.9 * len(t.strip())


# ---------------------------------------------------------------- repli « Document » (faux positifs)
def test_petit_emetteur_a_deux_sections_substantielles_tombe_dans_le_repli_limite_documentee():
    """LIMITE (non bloquante) : avec `min_substantial_sections` = 3, un petit 10-K (Item 1 et Item 7
    seuls longs ; 1A « non requis », Item 8 par renvoi) ou un 10-Q à deux grandes sections
    (états financiers + MD&A) est traité comme sans structure. Les seuils (H) sont calibrés sur 15
    sociétés technologiques ; sur des émetteurs de petite taille, la structure est perdue. Si le
    seuil change, mettre ce test à jour."""
    petit_k = (
        "FORM 10-K\n\n"
        + corps("Couverture", 1)
        + "\n\nItem 1. Business\n\n"
        + corps("Activité", 6)
        + "\n\nItem 1A. Risk Factors\n\nNot required for smaller reporting companies.\n\n"
        "Item 7. Management's Discussion and Analysis\n\n"
        + corps("Discussion", 6)
        + "\n\nItem 8. Financial Statements and Supplementary Data\n\nSee the F-pages.\n"
    )
    assert [s.code for s in split_sections(petit_k, "10-K")] == ["Document"]
    petit_q = (
        "FORM 10-Q\n\nPART I\n\nItem 1. Financial Statements\n\n"
        + corps("États", 6)
        + "\n\nItem 2. Management's Discussion\n\n"
        + corps("Discussion", 5)
        + "\n\nPART II\n\nItem 1A. Risk Factors\n\nNo material changes.\n"
    )
    assert [s.code for s in split_sections(petit_q, "10-Q")] == ["Document"]


def test_trois_sections_substantielles_suffisent_pas_de_repli():
    t = (
        "FORM 10-K\n\n"
        + corps("Couverture", 1)
        + "\n\nItem 1. Business\n\n"
        + corps("A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("B", 6)
        + "\n\nItem 7. MD&A\n\n"
        + corps("C", 6)
        + "\n"
    )
    assert "Document" not in [s.code for s in split_sections(t, "10-K")]


def test_preambule_geant_index_en_fin_de_document_repli_explicite():
    """Intel : tout le rapport précède un index de renvois ; ici trois vraies sections suivent un
    préambule de plus de 20 000 caractères, de sorte que SEULE la règle du préambule déclenche."""
    t = (
        corps("Rapport sans structure", 400)
        + "\n\nItem 1. Business\n\n"
        + corps("A", 6)
        + "\n\nItem 1A. Risk Factors\n\n"
        + corps("B", 6)
        + "\n\nItem 7. MD&A\n\n"
        + corps("C", 6)
        + "\n"
    )
    assert [s.code for s in split_sections(t, "10-K", max_preamble_chars=20_000)] == ["Document"]
    codes = [s.code for s in split_sections(t, "10-K", max_preamble_chars=10_000_000)]
    assert codes == ["Préambule", "Item 1", "Item 1A", "Item 7"]


def test_repli_visible_sur_les_passages_et_le_resultat_du_rag(tmp_path):
    from datetime import date

    from text_helpers import client, construire_stockage, depot

    from amundi_agentic.tools.rag import FilingsRAG

    pit, _ = construire_stockage(
        tmp_path,
        [
            depot("0001-24-000001", "10-K", "2023-11-03T21:00:00", k_apple()),
            depot("0001-24-000002", "10-K", "2023-12-03T21:00:00", corps("Sans structure", 12)),
        ],
    )
    rag = FilingsRAG(client(tmp_path), store_dir=tmp_path / "rag", data_view=pit)
    res = rag.query("APEX", "risque", date(2024, 2, 1), k=500)
    par_acc = {}
    for p in res.passages:
        par_acc.setdefault(p.source.source_id.split(":")[2], set()).add(p.section_fallback)
    assert par_acc["0001-24-000001"] == {False} and par_acc["0001-24-000002"] == {True}
    assert res.section_fallback is True and res.fallback_accessions == ["0001-24-000002"]
    assert all(p.section == "Document" for p in res.passages if p.section_fallback)


# ---------------------------------------------------------------- vrais rapports (lecture seule)
_STORE = os.environ.get("AMUNDI_DATA_STORE")


def _lire_depots():
    import gzip

    import pandas as pd

    racine = Path(_STORE)
    for f in sorted((racine / "filings" / "index").glob("*.parquet")):
        idx = pd.read_parquet(f)
        for r in idx[idx["form"].isin(["10-K", "10-Q"])].itertuples():
            fichier = racine / "filings" / "text" / f.stem / f"{r.accession}.txt.gz"
            if fichier.is_file():
                with gzip.open(fichier, "rt", encoding="utf-8") as fh:
                    yield f.stem, r.form, str(r.filing_date)[:10], fh.read()


@pytest.mark.skipif(
    not _STORE, reason="variable AMUNDI_DATA_STORE absente (essai sur vrais rapports)"
)
def test_vrais_rapports_lecture_seule_tous_les_depots_disponibles():
    """Commande : AMUNDI_DATA_STORE=/chemin/.cache/data/store uv run pytest
    tests/tools/test_revue_sections_formats_reels.py -q . Lit le stockage, n'écrit rien.
    Mesuré le 2026-10 sur 286 dépôts (72 10-K, 214 10-Q) de 15 sociétés."""
    n = 0
    replis: set[tuple[str, str]] = set()
    for tk, form, _date, texte in _lire_depots():
        sections = split_sections(texte, form)
        codes = [x.code for x in sections]
        longueurs = {x.code: len(x.text) for x in sections}
        n += 1
        if codes == ["Document"]:
            replis.add((tk, form))
            continue
        # aucune section parasite : juste après le préambule vient la vraie première section
        assert codes[0] == "Préambule" and codes[1] == (
            "Item 1" if form == "10-K" else "Part1-Item1"
        ), (tk, form, codes[:3])
        assert longueurs["Préambule"] < 20_000, (tk, form)
        if form == "10-K":
            assert min(longueurs.get(k, 0) for k in ("Item 1", "Item 1A")) > 2000, (tk, form)
            assert longueurs.get("Item 7", 0) > 150 and longueurs.get("Item 7A", 0) > 150, (
                tk,
                form,
            )
            # états financiers : sous l'Item 8, ou sous l'Item 15 / l'Annexe-F (NVDA, ORCL, QCOM)
            assert sum(longueurs.get(k, 0) for k in ("Item 8", "Item 15", "Annexe-F")) > 1000, (
                tk,
                form,
            )
            assert longueurs.get("Item 16", 0) < 20_000
        else:
            assert (
                longueurs.get("Part1-Item1", 0) > 5000 and longueurs.get("Part1-Item2", 0) > 2000
            ), (tk, form)
            # les états financiers ne sont jamais rangés sous « Exhibits »
            assert longueurs.get("Part2-Item6", 0) < 30_000, (tk, form)
    assert n >= 40
    assert {tk for tk, _ in replis} <= {"INTC"}  # seul Intel (index de renvois en fin de document)


@pytest.mark.skipif(
    not _STORE, reason="variable AMUNDI_DATA_STORE absente (essai sur vrais rapports)"
)
@pytest.mark.parametrize("tk", ["NVDA", "ZS", "ADBE", "CSCO", "CRM"])
def test_vrais_10q_etats_financiers_sous_part1_item1(tk):
    vus = 0
    for t, form, _d, texte in _lire_depots():
        if t != tk or form != "10-Q":
            continue
        sections = {x.code: x.text for x in split_sections(texte, "10-Q")}
        part1 = sections["Part1-Item1"]
        assert len(part1) > 20_000 and "balance sheets" in part1.lower(), (tk, len(part1))
        for code, corps_ in sections.items():
            if code.startswith("Part2-Item6") or code.startswith("Part2-Item5"):
                assert "balance sheets" not in corps_.lower()[3000:], (tk, code)
        vus += 1
    assert vus >= 5


@pytest.mark.skipif(
    not _STORE, reason="variable AMUNDI_DATA_STORE absente (essai sur vrais rapports)"
)
def test_vrais_10k_items_par_renvoi_conserves_msft_ibm_amd_txn():
    for tk, form, _d, texte in _lire_depots():
        if form != "10-K" or tk not in ("MSFT", "IBM", "AMD", "TXN"):
            continue
        s = {x.code: len(x.text) for x in split_sections(texte, form)}
        assert s.get("Item 1A", 0) > 20_000 and s.get("Item 1", 0) > 8000, (tk, s)
        if tk == "IBM":  # Items 7, 7A et 8 par renvoi au rapport annuel : courts mais présents
            assert all(100 < s.get(k, 0) < 600 for k in ("Item 7", "Item 7A", "Item 8")), s
        else:
            assert s.get("Item 7", 0) > 8_000 and s.get("Item 8", 0) > 30_000, (tk, s)
