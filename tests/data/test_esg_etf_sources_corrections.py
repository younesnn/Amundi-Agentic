"""Corrections de la revue (D-048) : registre d'empreintes versionné, antidatage, `corrige`, ordre, archives,
rapport. Aucun réseau, aucune clé, aucun accès à `.cache/` (compatible CI)."""

from __future__ import annotations

import copy
import json
import shutil
from datetime import date, datetime

import pandas as pd
import pytest

from amundi_agentic.data.analysis import DETERMINE, INCONNU, esg_matrix
from amundi_agentic.data.connectors import esg_etf_sources as mod
from amundi_agentic.data.connectors.esg_etf_sources import (
    LOCK_FILE,
    EsgSourceError,
    RetroactiveModificationError,
    check_lock,
    load_etf_sources,
    load_for_universe,
    parse_sources,
    read_lock,
    verify_and_snapshot,
    write_lock,
)
from amundi_agentic.data.settings import CONFIG_DIR, load_yaml
from amundi_agentic.data.store import ParquetStore


def _src() -> dict:
    return {
        "type_document": "prospectus",
        "titre": "Prospectus de test",
        "url": "https://exemple.test/d.pdf",
    }


def _v(champ: str, valeur, n: int, **kw) -> dict:
    e = {
        "id": f"T.PA:{champ}:{n:03d}", "champ": champ, "valeur": valeur, "emetteur": "gestionnaire_fonds",
        "source": _src(), "date_document": "2024-01-10", "date_effet": "2024-01-10", "effet_documente": False,
        "date_consultation": "2024-01-12", "date_saisie": "2024-01-12",
    }  # fmt: skip
    e.update(kw)
    return e


def _data(entries: list[dict]) -> dict:
    presents = {e["champ"] for e in entries}
    tous = list(entries) + [
        {"id": f"T.PA:{c}:001", "champ": c, "valeur": "inconnu", "raison": "aucun document", "date_saisie": "2024-01-12"}
        for c in mod.CHAMPS
        if c not in presents
    ]  # fmt: skip
    return {"version": 1, "etfs": {"T.PA": {"isin": "LU1681048804", "entries": tous}}}


def _store(tmp_path, jour: str) -> ParquetStore:
    return ParquetStore(
        tmp_path / "store", tmp_path / "snap",
        clock=lambda: datetime.fromisoformat(f"{jour}T10:00:00+00:00"),
    )  # fmt: skip


# --------------------------------------------------------------------------- registre versionné (sans .cache)


def test_registre_versionne_couvre_chaque_entree_avec_la_bonne_empreinte():
    src = load_for_universe()
    verrou = read_lock(CONFIG_DIR / LOCK_FILE)
    assert verrou, "config/esg_etf_sources.lock.json absent ou vide"
    actuel = {e.id: e for e in src.all_entries()}
    assert set(actuel) == set(verrou), "entrée non verrouillée ou disparue du fichier de saisie"
    for ident, e in actuel.items():
        assert verrou[ident]["sha256"] == e.sha256, ident
        assert verrou[ident]["date_saisie"] == e.date_saisie.isoformat(), ident
        assert verrou[ident]["corrige"] == e.corrige, ident
    assert check_lock(src, CONFIG_DIR / LOCK_FILE) == []


def test_registre_refuse_modification_redatage_deplacement_et_suppression(tmp_path):
    base = _data([_v("sfdr", "article_6", 1), _v("indice", "A", 1), _v("indice", "B", 2)])
    s = parse_sources(base)
    lock = tmp_path / "x.lock.json"
    write_lock(s, lock, today=date(2026, 10, 3))  # amorçage
    assert check_lock(s, lock) == []

    modif = copy.deepcopy(base)
    modif["etfs"]["T.PA"]["entries"][0]["valeur"] = "article_9"
    with pytest.raises(RetroactiveModificationError, match="T.PA:sfdr:001"):
        write_lock(parse_sources(modif), lock, today=date(2026, 10, 4))
    redate = copy.deepcopy(base)
    redate["etfs"]["T.PA"]["entries"][0]["date_effet"] = "2024-01-11"
    with pytest.raises(RetroactiveModificationError):
        write_lock(parse_sources(redate), lock, today=date(2026, 10, 4))
    supp = copy.deepcopy(base)
    supp["etfs"]["T.PA"]["entries"] = [
        e for e in supp["etfs"]["T.PA"]["entries"] if e["id"] != "T.PA:indice:002"
    ]
    with pytest.raises(RetroactiveModificationError, match="supprimée"):
        write_lock(parse_sources(supp), lock, today=date(2026, 10, 4))
    inverse = copy.deepcopy(base)
    es = inverse["etfs"]["T.PA"]["entries"]
    i1, i2 = [i for i, e in enumerate(es) if e["champ"] == "indice"]
    es[i1], es[i2] = es[i2], es[i1]
    with pytest.raises(RetroactiveModificationError, match="déplacée"):
        write_lock(parse_sources(inverse), lock, today=date(2026, 10, 4))
    # le registre n'a pas changé après les refus
    assert set(read_lock(lock)) == {e["id"] for e in base["etfs"]["T.PA"]["entries"]}


def test_registre_ajoute_une_entree_nouvelle_saisie_le_jour_meme(tmp_path):
    base = _data([_v("sfdr", "article_6", 1)])
    lock = tmp_path / "x.lock.json"
    write_lock(parse_sources(base), lock, today=date(2026, 10, 3))
    avant = lock.read_text(encoding="utf-8")
    plus = copy.deepcopy(base)
    plus["etfs"]["T.PA"]["entries"].append(
        _v(
            "sfdr",
            "article_8",
            2,
            corrige="T.PA:sfdr:001",
            date_saisie="2026-10-10",
            date_consultation="2026-10-10",
        )
    )
    write_lock(parse_sources(plus), lock, today=date(2026, 10, 10))
    apres = json.loads(lock.read_text(encoding="utf-8"))
    assert {r["id"] for r in apres["entries"]} >= {"T.PA:sfdr:001", "T.PA:sfdr:002"}
    # les lignes déjà verrouillées sont inchangées
    assert all(r in apres["entries"] for r in json.loads(avant)["entries"])


# --------------------------------------------------------------------------- B1 : antidatage


def test_b1_entree_nouvelle_antidatee_ou_future_refusee_par_le_registre_et_le_cache(tmp_path):
    base = _data([_v("sfdr", "article_6", 1)])
    s1 = parse_sources(base)
    lock = tmp_path / "x.lock.json"
    write_lock(s1, lock, today=date(2024, 1, 12))
    verify_and_snapshot(s1, _store(tmp_path, "2024-01-12"), lock_path=lock)

    def avec(date_saisie: str) -> dict:
        d = copy.deepcopy(base)
        d["etfs"]["T.PA"]["entries"].append(
            _v("indice", "X", 2, date_document="2026-01-01", date_effet="2026-01-01",
               date_consultation="2026-01-01", date_saisie=date_saisie)
        )  # fmt: skip
        return d

    # antidatée : ajoutée le 2026-10-10 avec saisie 2026-01-01
    s2 = parse_sources(avec("2026-01-01"))
    with pytest.raises(RetroactiveModificationError, match="antidatage"):
        verify_and_snapshot(s2, _store(tmp_path, "2026-10-10"), lock_path=lock)
    with pytest.raises(RetroactiveModificationError, match="antidatage"):
        write_lock(s2, lock, today=date(2026, 10, 10))
    # future : saisie datée du lendemain
    s3 = parse_sources(avec("2026-10-11"))
    with pytest.raises(RetroactiveModificationError, match="future"):
        verify_and_snapshot(s3, _store(tmp_path, "2026-10-10"), lock_path=lock)
    # le jour même : acceptée
    s4 = parse_sources(avec("2026-10-10"))
    assert verify_and_snapshot(s4, _store(tmp_path, "2026-10-10"), lock_path=lock) is not None
    # sans instantané local (clone neuf), le registre seul suffit à refuser l'antidatage
    with pytest.raises(RetroactiveModificationError, match="antidatage"):
        verify_and_snapshot(s2, _store(tmp_path / "neuf", "2026-10-10"), lock_path=lock)


def test_b1_un_marqueur_inconnu_jamais_servi_n_est_pas_concerne(tmp_path):
    base = _data([_v("sfdr", "article_6", 1)])
    lock = tmp_path / "x.lock.json"
    write_lock(parse_sources(base), lock, today=date(2024, 1, 12))
    plus = copy.deepcopy(base)
    plus["etfs"]["T.PA"]["entries"].append(
        {
            "id": "T.PA:indice:002",
            "champ": "indice",
            "valeur": "inconnu",
            "raison": "note",
            "date_saisie": "2024-01-12",
        }
    )
    verify_and_snapshot(parse_sources(plus), _store(tmp_path, "2026-10-10"), lock_path=lock)


# --------------------------------------------------------------------------- B2 : `corrige`


def test_b2_entree_corrigee_exclue_meme_si_son_effet_est_plus_recent():
    a = _v("sfdr", "article_6", 1, date_document="2024-06-01", date_effet="2024-06-01",
           date_consultation="2024-06-02", date_saisie="2024-06-02")  # fmt: skip
    c = _v("sfdr", "article_8", 2, corrige="T.PA:sfdr:001", date_document="2024-01-10", date_effet="2024-01-10",
           effet_documente=True, date_consultation="2025-01-01", date_saisie="2025-01-01")  # fmt: skip
    s = parse_sources(_data([a, c]))
    for mode in ("strict", "non_pit"):
        assert (
            s.as_of(date(2024, 7, 1), mode=mode).sfdr("T.PA") == "article_6"
            if mode == "strict"
            else True
        )
        assert s.as_of(date(2025, 2, 1), mode=mode).sfdr("T.PA") == "article_8", mode
    # non_pit avant la saisie de la correction : la correction est connue (document daté) et prévaut
    r = s.as_of(date(2024, 7, 1), mode="non_pit").get("T.PA", "sfdr")
    assert r.valeur == "article_8" and r.non_point_in_time is True
    # strict : ce qu'on savait en 2024
    assert s.as_of(date(2024, 7, 1)).sfdr("T.PA") == "article_6"
    # avant la date du document de A : rien, même en non_pit sans A (C a un effet 2024-01-10)
    assert s.as_of(date(2024, 3, 1), mode="non_pit").sfdr("T.PA") == "article_8"
    assert s.as_of(date(2024, 3, 1)).sfdr("T.PA") == INCONNU


def test_b2_retrait_non_pit_exclut_aussi_l_entree_retiree():
    a = _v(
        "indice",
        "A",
        1,
        date_effet="2024-06-01",
        date_document="2024-06-01",
        date_consultation="2024-06-02",
        date_saisie="2024-06-02",
    )
    r = {"id": "T.PA:indice:002", "champ": "indice", "valeur": "inconnu", "raison": "document retiré",
         "corrige": "T.PA:indice:001", "date_effet": "2024-01-15", "date_saisie": "2025-01-01"}  # fmt: skip
    s = parse_sources(_data([a, r]))
    assert s.as_of(date(2024, 9, 1), mode="non_pit").get("T.PA", "indice").valeur == INCONNU
    assert s.as_of(date(2024, 9, 1)).get("T.PA", "indice").valeur == "A"
    assert s.as_of(date(2025, 1, 2)).get("T.PA", "indice").valeur == INCONNU


# --------------------------------------------------------------------------- ordre des entrées concurrentes


def test_ordre_fait_partie_de_l_empreinte():
    a = _v("indice", "A", 1)
    b = _v("indice", "B", 2)
    s1 = parse_sources(_data([a, b]))
    s2 = parse_sources(_data([b, a]))
    assert {e.id: e.sha256 for e in s1.all_entries()} != {e.id: e.sha256 for e in s2.all_entries()}


def test_reordonner_est_refuse_par_le_registre(tmp_path):
    a, b = _v("indice", "A", 1), _v("indice", "B", 2)
    lock = tmp_path / "x.lock.json"
    write_lock(parse_sources(_data([a, b])), lock, today=date(2026, 10, 3))
    with pytest.raises(RetroactiveModificationError, match="déplacée"):
        verify_and_snapshot(
            parse_sources(_data([b, a])), _store(tmp_path, "2026-10-04"), lock_path=lock
        )


# --------------------------------------------------------------------------- archives et fiches produit


def test_fiche_produit_sans_preuve_refusee_et_archive_exigee():
    e = _v(
        "sfdr",
        "article_6",
        1,
        source={"type_document": "fiche_produit", "titre": "fiche", "url": "https://a.test/x"},
    )
    with pytest.raises(EsgSourceError, match="fiche produit non archivée"):
        parse_sources(_data([e]))
    e2 = _v(
        "sfdr",
        "article_6",
        1,
        source={
            "type_document": "fiche_produit_archivee",
            "titre": "fiche",
            "url": "https://a.test/x",
        },
    )
    with pytest.raises(EsgSourceError, match="archive"):
        parse_sources(_data([e2]))
    ok = _v("sfdr", "article_6", 1, source={"type_document": "fiche_produit", "titre": "PDF daté",
                                             "url": "https://a.test/x.pdf", "sha256": "a" * 64})  # fmt: skip
    parse_sources(_data([ok]))


def test_les_archives_du_fichier_reel_existent_avec_le_bon_hash():
    src = load_for_universe()  # lève si une archive manque ou si son SHA-256 diffère
    types = {(e.source or {}).get("type_document") for e in src.all_entries() if not e.est_inconnu}
    assert "fiche_produit" not in types and "fiche_produit_archivee" in types
    sfdr6 = [e for e in src.all_entries() if e.champ == "sfdr" and e.valeur == "article_6"]
    assert len(sfdr6) == 10 and all(
        e.source["type_document"] == "fiche_produit_archivee" for e in sfdr6
    )
    man = json.loads(
        (CONFIG_DIR / "esg_etf_sources_archive" / "MANIFEST.json").read_text(encoding="utf-8")
    )
    assert man["methode"] == "POST" and man["corps_modele"]["filters"][0]["fieldName"] == "ISIN"
    assert len(man["fichiers"]) == 13


def test_archive_alteree_est_detectee(tmp_path):
    cfg = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, cfg)
    f = cfg / "esg_etf_sources_archive" / "LU1681048804.json"
    f.write_bytes(f.read_bytes() + b" ")
    with pytest.raises(EsgSourceError, match="SHA-256 de l'archive"):
        load_etf_sources(cfg / "esg_etf_sources.yaml")
    f.unlink()
    with pytest.raises(EsgSourceError, match="archive introuvable"):
        load_etf_sources(cfg / "esg_etf_sources.yaml")


def test_note_ahye_signale_l_ecart_de_nom_sans_toucher_universe():
    import yaml

    brut = yaml.safe_load((CONFIG_DIR / "esg_etf_sources.yaml").read_text(encoding="utf-8"))
    note = brut["etfs"]["AHYE.PA"]["note"]
    assert "DR" in note and "Acc" in note and "universe.yaml" in note


# --------------------------------------------------------------------------- rapport de couverture


def test_rapport_yaml_mal_forme_indisponible_avec_motif(monkeypatch, tmp_path):
    from amundi_agentic.data.coverage import Report

    (tmp_path / "x.yaml").write_text("etfs: [unclosed\n  - : :\n", encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(mod, "DEFAULT_FILE", "x.yaml")
    r = Report.__new__(Report)
    r.data = {}
    vue, note = r._etf_sources_view()
    assert vue is None and "indisponible" in note and "Error" in note
    assert (
        r.data["esg_etf_sources"]["statut"] == "indisponible"
        and r.data["esg_etf_sources"]["erreur"]
    )


@pytest.mark.parametrize("exc", [KeyError("etfs"), ValueError("v"), TypeError("t")])
def test_rapport_autres_erreurs_de_lecture_ne_plantent_pas(monkeypatch, exc):
    from amundi_agentic.data.coverage import Report

    def casse(*a, **k):
        raise exc

    monkeypatch.setattr(mod, "load_for_universe", casse)
    r = Report.__new__(Report)
    r.data = {}
    vue, note = r._etf_sources_view()
    assert vue is None and "indisponible" in note and type(exc).__name__ in note


def test_rapport_dit_les_limites_backtest_et_seuils():
    from amundi_agentic.data.coverage import Report

    r = Report.__new__(Report)
    r.data = {}
    _, note = r._etf_sources_view()
    for phrase in (
        "aucun backtest ne voit l'ESG des ETF",
        "seuils de revenus",
        "MSCI",
        "2026-10-04",
        "non_pit",
    ):
        assert phrase in note, phrase
    doc = mod.__doc__ or ""
    assert "Aucun backtest ne voit l'ESG des ETF" in doc and "seuils de revenus" in doc


# --------------------------------------------------------------------------- nom attendu par L1


def test_esg_etf_alimente_matrice_et_agent_esg():
    """Nom cité par L1 (EX-O1-18). La matrice est alimentée par la vue point-in-time ; la vue expose aussi, pour
    l'agent ESG (pas encore écrit dans ce worktree), la valeur, la source et l'identifiant de chaque entrée."""
    src = load_for_universe()
    vue = src.as_of(date(2026, 10, 6))
    cfg = load_yaml("esg.yaml")
    rec = pd.DataFrame(
        [
            {
                "asset_id": "CRP.PA",
                "kind": "etf",
                "sic": None,
                "notes": "basis:paris_aligned_index",
            },
            {"asset_id": "MEU.PA", "kind": "etf", "sic": None, "notes": "basis:none_known"},
        ]
    ).assign(observed_at=pd.Timestamp("2026-10-02", tz="UTC"))
    lignes, _ = esg_matrix(rec, cfg["normative_exclusions"], cfg["basis_definitions"], etf_view=vue)
    par = {r["actif"]: r for r in lignes}
    assert par["CRP.PA"]["tobacco"] == DETERMINE and par["MEU.PA"]["tobacco"] == INCONNU
    r = vue.get("CRP.PA", "exclusions")
    assert r.entry_id and r.source["url"].startswith("https://") and r.date_effet is not None
