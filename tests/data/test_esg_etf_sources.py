"""Source ESG manuelle et historisée par ETF (D-048, EX-O1-18) : validation, point-in-time, append-only,
matrice ESG. Aucun réseau, aucune clé : le fichier réel `config/esg_etf_sources.yaml` et des cas synthétiques."""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime

import pandas as pd
import pytest
import yaml

from amundi_agentic.data.analysis import DETERMINE, INCONNU, SUPPOSE, esg_matrix
from amundi_agentic.data.connectors.esg_etf_sources import (
    CHAMPS,
    EsgSourceError,
    RetroactiveModificationError,
    check_append_only,
    load_for_universe,
    parse_sources,
    verify_and_snapshot,
)
from amundi_agentic.data.settings import CONFIG_DIR, load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Universe

# --------------------------------------------------------------------------- fabriques


def _src(url: str = "https://exemple.test/doc.pdf") -> dict:
    return {"type_document": "prospectus", "titre": "Prospectus de test", "url": url}


def _valued(champ: str, valeur, n: int, **kw) -> dict:
    e = {
        "id": f"T.PA:{champ}:{n:03d}",
        "champ": champ,
        "valeur": valeur,
        "emetteur": "gestionnaire_fonds",
        "source": _src(),
        "date_document": "2024-01-10",
        "date_effet": "2024-01-10",
        "effet_documente": False,
        "date_consultation": "2024-01-12",
        "date_saisie": "2024-01-12",
    }
    e.update(kw)
    return e


def _inconnu(champ: str, n: int = 1) -> dict:
    return {
        "id": f"T.PA:{champ}:{n:03d}",
        "champ": champ,
        "valeur": "inconnu",
        "raison": "aucun document",
        "date_saisie": "2024-01-12",
    }


def _data(entries: list[dict]) -> dict:
    """Fichier minimal valide : les champs non fournis sont `inconnu`."""
    presents = {e["champ"] for e in entries}
    tous = list(entries) + [_inconnu(c) for c in CHAMPS if c not in presents]
    return {"version": 1, "etfs": {"T.PA": {"isin": "LU1681048804", "entries": tous}}}


def _excl(**kw) -> dict:
    return {"controversial_weapons": "indice", **kw}


@pytest.fixture(scope="module")
def reel():
    return load_for_universe()


@pytest.fixture(scope="module")
def reel_brut() -> dict:
    return yaml.safe_load((CONFIG_DIR / "esg_etf_sources.yaml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- fichier réel


def test_esg_etf_valeur_sans_document_reste_inconnue(reel, reel_brut):
    """Chaque entrée a une source https, une date de document et une date d'effet, ou vaut `inconnu` motivé."""
    n_valeurs = n_inconnus = 0
    for bloc in reel_brut["etfs"].values():
        for e in bloc["entries"]:
            if e["valeur"] == "inconnu":
                n_inconnus += 1
                assert e.get("raison", "").strip(), e["id"]
                assert "source" not in e, f"{e['id']} : un inconnu n'a pas de source"
                continue
            n_valeurs += 1
            assert e["source"]["url"].startswith("https://"), e["id"]
            assert e["source"]["type_document"] and e["source"]["titre"], e["id"]
            assert e["date_document"] and e["date_effet"] and e["date_saisie"], e["id"]
            assert e["emetteur"] in {"gestionnaire_fonds", "administrateur_indice"}, e["id"]
    assert (
        n_valeurs > 20 and n_inconnus > 10
    )  # le fichier contient des valeurs ET des inconnus explicites


def test_fichier_reel_couvre_les_etf_primaires_et_chaque_champ(reel):
    uni = Universe.load()
    for spec in uni.classes.values():
        assert spec.primary.ticker in reel.entries, spec.primary.ticker
    for tk in reel.tickers:
        champs = {e.champ for e in reel.entries[tk]}
        assert champs == set(CHAMPS), tk
    assert set(reel.tickers) <= set(uni.etf_tickers())


def test_fichier_reel_sha256_des_documents_et_ids_uniques(reel):
    ids = [e.id for e in reel.all_entries()]
    assert len(ids) == len(set(ids))
    for e in reel.all_entries():
        sha = (e.source or {}).get("sha256")
        if sha is not None:
            assert len(sha) == 64 and set(sha) <= set("0123456789abcdef"), e.id


def test_valeurs_du_fichier_reel_attendues(reel):
    """Valeurs relevées dans les documents d'Amundi (consultation du 2026-10-03)."""
    v = reel.as_of(date(2026, 10, 4))
    assert v.sfdr("CRP.PA") == "article_8" and v.sfdr("AHYE.PA") == "article_8"
    assert v.sfdr("500.PA") == "article_6" and v.sfdr("GOLD.PA") == "non_applicable"
    assert v.get("CRP.PA", "caractere_indice").valeur == "pab"
    assert v.get("AHYE.PA", "caractere_indice").valeur == "esg"
    assert v.get("MEU.PA", "caractere_indice").valeur == INCONNU  # rien déduit du nom
    assert v.proven_exclusions("CRP.PA") == {"controversial_weapons", "tobacco", "thermal_coal"}
    assert v.proven_exclusions("AHYE.PA") == {"controversial_weapons", "tobacco", "thermal_coal"}
    # fonds à swap : l'exclusion porte sur les titres détenus, pas sur l'exposition
    assert v.exclusions("500.PA") == {"controversial_weapons": "titres_detenus_hors_swap"}
    assert v.proven_exclusions("500.PA") == frozenset()
    for tk in ("MEU.PA", "JPN.PA", "MTD.PA", "C3M.PA", "GOLD.PA"):
        assert v.proven_exclusions(tk) == frozenset(), tk


def test_fichier_reel_historise_le_changement_d_indice_de_crp(reel):
    """H-21 : l'indice de CRP.PA a changé le 2023-01-11 (avis aux actionnaires) ; mode non_pit pour remonter le temps."""
    avant = reel.as_of(date(2023, 1, 10), mode="non_pit").get("CRP.PA", "indice")
    jour = reel.as_of(date(2023, 1, 11), mode="non_pit").get("CRP.PA", "indice")
    apres = reel.as_of(date(2023, 1, 12), mode="non_pit").get("CRP.PA", "indice")
    assert "Liquid SRI Sustainable" in avant.valeur
    assert jour.valeur == avant.valeur  # donnée « disponible exactement à t » : exclue (D-031)
    assert "Paris Aligned Green Tilted" in apres.valeur
    assert apres.non_point_in_time and apres.source["type_document"] == "avis_actionnaires"
    # le caractère PAB n'est pas servi avant la date d'effet du changement
    assert (
        reel.as_of(date(2023, 1, 11), mode="non_pit").get("CRP.PA", "caractere_indice").valeur
        == INCONNU
    )
    assert (
        reel.as_of(date(2023, 1, 12), mode="non_pit").get("CRP.PA", "caractere_indice").valeur
        == "pab"
    )


def test_fichier_reel_strict_ne_sert_rien_avant_la_saisie(reel):
    """Strict : rien avant la date de saisie (2026-10-03) ; le jour même est exclu (coupure t 00:00)."""
    for t in (date(2023, 6, 1), date(2025, 1, 1), date(2026, 10, 3)):
        v = reel.as_of(t)
        for tk in reel.tickers:
            assert all(r.valeur == INCONNU for r in v.state(tk).values()), (tk, t)
    assert reel.as_of(date(2026, 10, 4)).sfdr("CRP.PA") == "article_8"
    # en non_pit, la valeur documentée en 2023 est servie en 2023 mais marquée non point-in-time
    r = reel.as_of(date(2023, 6, 1), mode="non_pit").get("CRP.PA", "sfdr")
    assert r.valeur == "article_8" and r.non_point_in_time


def test_fichier_reel_ne_sert_jamais_avant_la_date_du_document(reel):
    """Même en non_pit : aucune valeur avant max(date d'effet, date du document)."""
    for e in reel.all_entries():
        if e.est_marqueur:
            continue
        borne = max(d for d in (e.date_effet, e.date_document) if d)
        veille = date.fromordinal(borne.toordinal() - 1)
        for mode in ("strict", "non_pit"):
            r = reel.as_of(borne, mode=mode).get(e.ticker, e.champ)
            assert r.entry_id != e.id, (e.id, mode)  # à t == borne : exclue
            r2 = reel.as_of(veille, mode=mode).get(e.ticker, e.champ)
            assert r2.entry_id != e.id, (e.id, mode)


# --------------------------------------------------------------------------- validation stricte


def test_validation_refuse_une_valeur_sans_source():
    e = _valued("sfdr", "article_8", 1)
    del e["source"]
    with pytest.raises(EsgSourceError, match="source absente"):
        parse_sources(_data([e]))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            {
                "source": {
                    "type_document": "prospectus",
                    "titre": "x",
                    "url": "http://non-tls.test/a",
                }
            },
            "https",
        ),
        (
            {"source": {"type_document": "blog", "titre": "x", "url": "https://a.test/x"}},
            "type_document",
        ),
        ({"emetteur": "courtier"}, "emetteur"),
        ({"date_document": None}, "date_document"),
        ({"date_effet": None}, "date_effet"),
        ({"date_saisie": None}, "date_saisie"),
        ({"date_effet": "10/01/2024"}, "date ISO"),
        (
            {"date_effet": "2023-12-01"},
            "effet_documente",
        ),  # effet antérieur au document sans preuve
        ({"date_consultation": "2024-01-05"}, "date_consultation"),
        ({"date_saisie": "2024-01-11"}, "date_saisie"),  # saisie avant la consultation
        ({"valeur": "article_7"}, "sfdr"),
        ({"effet_documente": "oui"}, "booléen"),
        ({"id": "autre:sfdr:001"}, "id doit commencer"),
    ],
)
def test_validation_refuse_les_entrees_incoherentes(mutation, message):
    e = _valued("sfdr", "article_8", 1)
    e.update(mutation)
    with pytest.raises(EsgSourceError, match=message):
        parse_sources(_data([e]))


def test_validation_inconnu_exige_une_raison_et_les_champs_sont_obligatoires():
    sans_raison = _inconnu("sfdr")
    del sans_raison["raison"]
    with pytest.raises(EsgSourceError, match="raison"):
        parse_sources(_data([sans_raison]))
    d = _data([])
    d["etfs"]["T.PA"]["entries"] = [
        e for e in d["etfs"]["T.PA"]["entries"] if e["champ"] != "indice"
    ]
    with pytest.raises(EsgSourceError, match="aucune entrée pour le champ `indice`"):
        parse_sources(d)


def test_validation_extrait_obligatoire_pour_pab_et_exclusions():
    with pytest.raises(EsgSourceError, match="extrait"):
        parse_sources(_data([_valued("caractere_indice", "pab", 1)]))
    with pytest.raises(EsgSourceError, match="extrait"):
        parse_sources(_data([_valued("exclusions", _excl(), 1)]))
    parse_sources(
        _data([_valued("caractere_indice", "pab", 1, extrait="vise à respecter les EU PAB")])
    )


def test_validation_exclusions_portee_et_critere(reel):
    esg = set(load_yaml("esg.yaml")["normative_exclusions"])
    with pytest.raises(EsgSourceError, match="portée"):
        parse_sources(_data([_valued("exclusions", {"tobacco": "peut-etre"}, 1, extrait="x")]))
    with pytest.raises(EsgSourceError, match="critère"):
        parse_sources(
            _data([_valued("exclusions", {"alcool": "indice"}, 1, extrait="x")]), criteres=esg
        )


def test_validation_ticker_hors_univers_et_id_duplique_et_futur():
    with pytest.raises(EsgSourceError, match="absent de config/universe.yaml"):
        parse_sources(_data([]), universe_tickers={"AUTRE.PA"})
    dup = [
        _valued("sfdr", "article_8", 1),
        _valued("sfdr", "article_6", 1, date_saisie="2024-02-01"),
    ]
    with pytest.raises(EsgSourceError, match="dupliqué"):
        parse_sources(_data(dup))
    with pytest.raises(EsgSourceError, match="futur"):
        parse_sources(_data([_valued("sfdr", "article_8", 1)]), today=date(2024, 1, 11))


def test_validation_correction_doit_suivre_et_viser_le_meme_champ():
    base = _valued("sfdr", "article_6", 1)
    bonne = _valued(
        "sfdr",
        "article_8",
        2,
        corrige="T.PA:sfdr:001",
        date_saisie="2024-03-01",
        date_consultation="2024-03-01",
    )
    parse_sources(_data([base, bonne]))
    meme_jour = {**bonne, "date_saisie": "2024-01-12", "date_consultation": "2024-01-12"}
    with pytest.raises(EsgSourceError, match="postérieure"):
        parse_sources(_data([base, meme_jour]))
    with pytest.raises(EsgSourceError, match="inexistant"):
        parse_sources(_data([base, {**bonne, "corrige": "T.PA:sfdr:099"}]))
    with pytest.raises(EsgSourceError, match="APRÈS"):
        parse_sources(_data([bonne, base]))
    autre_champ = _valued(
        "indice",
        "X",
        1,
        corrige="T.PA:sfdr:001",
        date_saisie="2024-03-01",
        date_consultation="2024-03-01",
    )
    with pytest.raises(EsgSourceError, match="même ETF et le même champ"):
        parse_sources(_data([base, autre_champ]))


# --------------------------------------------------------------------------- point-in-time


def test_esg_etf_servie_a_partir_de_la_date_d_effet():
    """Jamais avant la date d'effet, ni avant celle du document, ni avant la saisie (strict)."""
    e = _valued(
        "sfdr", "article_8", 1,
        date_document="2024-01-10", date_effet="2024-03-01", date_consultation="2024-02-01", date_saisie="2024-02-01",
    )  # fmt: skip
    s = parse_sources(_data([e]))
    assert s.as_of(date(2024, 2, 20)).sfdr("T.PA") == INCONNU  # saisie connue, effet pas encore
    assert s.as_of(date(2024, 3, 1)).sfdr("T.PA") == INCONNU  # exactement à la coupure : exclue
    assert s.as_of(date(2024, 3, 2)).sfdr("T.PA") == "article_8"
    # le mode non_pit n'avance jamais la date d'effet
    assert s.as_of(date(2024, 2, 20), mode="non_pit").sfdr("T.PA") == INCONNU
    assert s.as_of(date(2024, 3, 2), mode="non_pit").get("T.PA", "sfdr").non_point_in_time is False


def test_esg_etf_non_servie_avant_la_saisie_en_strict_mais_marquee_en_non_pit():
    e = _valued(
        "sfdr",
        "article_8",
        1,
        date_effet="2024-01-10",
        date_saisie="2025-06-01",
        date_consultation="2025-06-01",
    )
    s = parse_sources(_data([e]))
    assert (
        s.as_of(date(2024, 6, 1)).sfdr("T.PA") == INCONNU
    )  # strict : on ne savait pas encore (saisie)
    r = s.as_of(date(2024, 6, 1), mode="non_pit").get("T.PA", "sfdr")
    assert r.valeur == "article_8" and r.non_point_in_time is True
    assert s.as_of(date(2025, 6, 1)).sfdr("T.PA") == INCONNU  # le jour de la saisie : exclu
    r2 = s.as_of(date(2025, 6, 2)).get("T.PA", "sfdr")
    assert r2.valeur == "article_8" and r2.non_point_in_time is False


def test_esg_etf_correction_retroactive_ne_reecrit_pas_ce_qu_on_savait():
    """Adverse : une correction saisie en 2025 avec effet 2024 n'altère pas les dates antérieures à sa saisie."""
    a = _valued("sfdr", "article_6", 1, date_effet="2024-01-10")
    c = _valued(
        "sfdr", "article_8", 2, corrige="T.PA:sfdr:001", date_effet="2024-01-10",
        date_saisie="2025-06-01", date_consultation="2025-06-01", date_document="2025-05-30",
        effet_documente=True,
    )  # fmt: skip
    s = parse_sources(_data([a, c]))
    assert s.as_of(date(2024, 6, 1)).sfdr("T.PA") == "article_6"  # ce qu'on savait en 2024
    assert s.as_of(date(2025, 5, 31)).sfdr("T.PA") == "article_6"
    assert s.as_of(date(2025, 6, 1)).sfdr("T.PA") == "article_6"  # le jour de la saisie : exclue
    r = s.as_of(date(2025, 6, 2)).get("T.PA", "sfdr")
    assert r.valeur == "article_8" and r.entry_id == "T.PA:sfdr:002"
    # non_pit : la correction est servie rétroactivement, mais jamais avant la date de son document
    assert s.as_of(date(2024, 6, 1), mode="non_pit").sfdr("T.PA") == "article_6"
    r3 = s.as_of(date(2025, 5, 31), mode="non_pit").get("T.PA", "sfdr")
    assert r3.valeur == "article_8" and r3.non_point_in_time is True


def test_esg_etf_entree_la_plus_recente_gagne_et_retrait_possible():
    a = _valued("indice", "Indice A", 1, date_effet="2024-01-10")
    b = _valued(
        "indice",
        "Indice B",
        2,
        date_document="2024-05-01",
        date_effet="2024-06-01",
        date_saisie="2024-05-02",
        date_consultation="2024-05-02",
    )
    retrait = {
        "id": "T.PA:indice:003", "champ": "indice", "valeur": "inconnu", "raison": "document retiré par la gestionnaire",
        "corrige": "T.PA:indice:002", "date_effet": "2024-09-01", "date_saisie": "2024-09-05",
    }  # fmt: skip
    s = parse_sources(_data([a, b, retrait]))
    assert s.as_of(date(2024, 4, 1)).get("T.PA", "indice").valeur == "Indice A"
    assert s.as_of(date(2024, 7, 1)).get("T.PA", "indice").valeur == "Indice B"
    assert (
        s.as_of(date(2024, 9, 2)).get("T.PA", "indice").valeur == "Indice B"
    )  # retrait pas encore saisi
    assert s.as_of(date(2024, 9, 6)).get("T.PA", "indice").valeur == INCONNU


def test_as_of_refuse_un_datetime_et_un_mode_inconnu():
    s = parse_sources(_data([]))
    with pytest.raises(TypeError):
        s.as_of(datetime(2024, 1, 1, tzinfo=UTC))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mode"):
        s.as_of(date(2024, 1, 1), mode="laxiste")


# --------------------------------------------------------------------------- append-only


def _store(tmp_path, jour="2026-10-03") -> ParquetStore:
    return ParquetStore(
        tmp_path / "store",
        tmp_path / "snap",
        clock=lambda: datetime.fromisoformat(f"{jour}T10:00:00+00:00"),
    )


def test_esg_etf_historisation_append_only(tmp_path):
    base = _data([_valued("sfdr", "article_6", 1)])
    s1 = parse_sources(base)
    st = _store(tmp_path)
    assert check_append_only(s1, st) == []  # aucun instantané : rien à comparer
    p1 = verify_and_snapshot(s1, st)
    assert p1 is not None and p1.exists()
    assert verify_and_snapshot(s1, st) == p1  # idempotent le même jour

    # ajout d'une correction : autorisé, nouvel instantané daté
    ajout = copy.deepcopy(base)
    ajout["etfs"]["T.PA"]["entries"].append(
        _valued(
            "sfdr",
            "article_8",
            2,
            corrige="T.PA:sfdr:001",
            date_saisie="2026-10-05",
            date_consultation="2026-10-05",
        )
    )
    s2 = parse_sources(ajout)
    p2 = verify_and_snapshot(s2, _store(tmp_path, "2026-10-05"))
    assert p2 != p1
    # le dossier contient maintenant deux instantanés datés
    assert len(list((tmp_path / "snap" / "esg_etf_sources").glob("*/entries*.parquet"))) == 2

    # modification rétroactive d'une entrée existante : refusée
    modif = copy.deepcopy(ajout)
    modif["etfs"]["T.PA"]["entries"][0]["valeur"] = "article_9"
    with pytest.raises(RetroactiveModificationError, match="entrée modifiée : T.PA:sfdr:001"):
        verify_and_snapshot(parse_sources(modif), _store(tmp_path, "2026-10-06"))

    # modification d'une date : refusée aussi (la date d'effet fait partie de l'entrée)
    redate = copy.deepcopy(ajout)
    redate["etfs"]["T.PA"]["entries"][0]["date_effet"] = "2024-01-11"
    with pytest.raises(RetroactiveModificationError, match="T.PA:sfdr:001"):
        verify_and_snapshot(parse_sources(redate), _store(tmp_path, "2026-10-06"))

    # suppression : refusée
    supp = copy.deepcopy(ajout)
    supp["etfs"]["T.PA"]["entries"] = [
        {k: v for k, v in e.items() if k != "corrige"}
        for e in supp["etfs"]["T.PA"]["entries"]
        if e["id"] != "T.PA:sfdr:001"
    ]
    with pytest.raises(RetroactiveModificationError, match="entrée supprimée : T.PA:sfdr:001"):
        verify_and_snapshot(parse_sources(supp), _store(tmp_path, "2026-10-07"))

    # rien n'a été écrit par les tentatives refusées
    assert len(list((tmp_path / "snap" / "esg_etf_sources").glob("*/entries*.parquet"))) == 2


def test_esg_etf_instantane_contient_hash_du_fichier_et_des_entrees(tmp_path, reel):
    st = _store(tmp_path)
    p = verify_and_snapshot(reel, st)
    df = pd.read_parquet(p)
    assert len(df) == len(reel.all_entries()) and set(df["file_sha256"]) == {reel.file_sha256}
    assert df["entry_sha256"].str.len().eq(64).all()


# --------------------------------------------------------------------------- matrice ESG


def _records(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).assign(observed_at=pd.Timestamp("2026-10-02", tz="UTC"))


def _cfg():
    c = load_yaml("esg.yaml")
    return c["normative_exclusions"], c["basis_definitions"]


def test_esg_etf_alimente_la_matrice(reel):
    """CRP.PA passe de « supposé par règle » à « déterminé par donnée » ; le reste ne bouge pas."""
    rules, basis = _cfg()
    rec = _records(
        [
            {
                "asset_id": "CRP.PA",
                "kind": "etf",
                "sic": None,
                "notes": "basis:paris_aligned_index|not_verified",
            },
            {
                "asset_id": "AHYE.PA",
                "kind": "etf",
                "sic": None,
                "notes": "basis:esg_index|not_verified",
            },
            {
                "asset_id": "500.PA",
                "kind": "etf",
                "sic": None,
                "notes": "basis:none_known|not_verified",
            },
            {
                "asset_id": "MEU.PA",
                "kind": "etf",
                "sic": None,
                "notes": "basis:none_known|not_verified",
            },
            {"asset_id": "S1", "kind": "stock", "sic": "3571", "notes": ""},
        ]
    )
    l0, t0 = esg_matrix(rec, rules, basis)  # appel historique, sans la source manuelle
    p0 = {r["actif"]: r for r in l0}
    assert p0["CRP.PA"]["tobacco"] == SUPPOSE and p0["AHYE.PA"]["tobacco"] == INCONNU

    l1, t1 = esg_matrix(rec, rules, basis, etf_view=reel.as_of(date(2026, 10, 4)))
    p1 = {r["actif"]: r for r in l1}
    for c in ("tobacco", "thermal_coal", "controversial_weapons"):
        assert p1["CRP.PA"][c] == DETERMINE and p1["AHYE.PA"][c] == DETERMINE
        assert p1["500.PA"][c] == INCONNU and p1["MEU.PA"][c] == INCONNU  # rien de prouvé : inconnu
    # fonds à swap : exclusion sur titres détenus seulement, pas comptée comme déterminée
    assert p1["500.PA"]["controversial_weapons"] == INCONNU
    # les titres ne changent pas
    assert p1["S1"]["tobacco"] == p0["S1"]["tobacco"] == SUPPOSE
    assert p1["S1"]["controversial_weapons"] == INCONNU
    assert (p1["CRP.PA"]["sfdr"], p1["AHYE.PA"]["sfdr"], p1["500.PA"]["sfdr"]) == (
        "article_8",
        "article_8",
        "article_6",
    )
    assert p1["CRP.PA"]["caractere_indice"] == "pab" and p1["MEU.PA"]["caractere_indice"] == INCONNU
    assert t1["controversial_weapons"][DETERMINE] == 2 and t1["actifs"] == 5
    # mêmes totaux qu'avant pour les titres : seul le nombre de cellules ETF déterminées change
    assert t1["tous_criteres"][DETERMINE] == 6


def test_esg_etf_matrice_strict_avant_saisie_ne_change_rien(reel):
    """À une date antérieure à la saisie, la vue stricte ne prouve rien : la matrice est celle de l'existant."""
    rules, basis = _cfg()
    rec = _records(
        [
            {
                "asset_id": "CRP.PA",
                "kind": "etf",
                "sic": None,
                "notes": "basis:paris_aligned_index|not_verified",
            }
        ]
    )
    l0, _ = esg_matrix(rec, rules, basis)
    l1, _ = esg_matrix(rec, rules, basis, etf_view=reel.as_of(date(2025, 1, 1)))
    for c in ("tobacco", "thermal_coal", "controversial_weapons"):
        assert l0[0][c] == l1[0][c] == SUPPOSE
    assert l1[0]["sfdr"] == INCONNU


def test_esg_etf_sans_source_la_matrice_est_inchangee():
    """Régression : sans `etf_view`, ni colonnes ajoutées ni état modifié."""
    rules, basis = _cfg()
    rec = _records(
        [
            {
                "asset_id": "E1",
                "kind": "etf",
                "sic": None,
                "notes": "basis:paris_aligned_index|not_verified",
            },
            {
                "asset_id": "S2",
                "kind": "stock",
                "sic": "2111",
                "notes": "vendor_flag:controversial_weapons",
            },
        ]
    )
    lignes, _ = esg_matrix(rec, rules, basis)
    assert set(lignes[0]) == {"actif", "type", "tobacco", "thermal_coal", "controversial_weapons"}
    assert lignes[1]["controversial_weapons"] == DETERMINE


# --------------------------------------------------------------------------- limites


def test_sfdr_n_est_pas_un_score_et_ct06_reste_suspendue(reel):
    """Un article 8 ne prouve aucune exclusion ; aucun score n'est produit ; CT-06 suspendue."""
    rules, basis = _cfg()
    # article 8 SANS entrée d'exclusion documentée : la matrice reste « inconnu »
    s = parse_sources(
        _data(
            [
                _valued("sfdr", "article_8", 1),
                _valued("caractere_indice", "esg", 1, extrait="indice ESG"),
            ]
        )
    )
    vue = s.as_of(date(2024, 6, 1), mode="non_pit")
    assert vue.sfdr("T.PA") == "article_8" and vue.proven_exclusions("T.PA") == frozenset()
    rec = _records([{"asset_id": "T.PA", "kind": "etf", "sic": None, "notes": "basis:esg_index"}])
    lignes, _ = esg_matrix(rec, rules, basis, etf_view=vue)
    assert all(
        lignes[0][c] == INCONNU for c in ("tobacco", "thermal_coal", "controversial_weapons")
    )
    # aucun score ESG dans la source ; CT-06 : pas de normalisation de score fixée (D-035)
    assert {"score"} & set(CHAMPS) == set()
    esg = load_yaml("esg.yaml")
    assert esg["score"]["normalization"] is None and esg["score"]["s_min"] is None
    # AHYE.PA est article 8 : ses exclusions viennent d'un document, pas de la classification
    assert reel.as_of(date(2026, 10, 4)).sfdr("AHYE.PA") == "article_8"
    exclusions_ahye = [
        e for e in reel.entries["AHYE.PA"] if e.champ == "exclusions" and not e.est_inconnu
    ]
    assert exclusions_ahye and all(e.extrait for e in exclusions_ahye)
    texte = (CONFIG_DIR / "esg_etf_sources.yaml").read_text(encoding="utf-8")
    assert "pas un score ESG" in texte and "CT-06" in texte
