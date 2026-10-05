"""Revue indépendante de la source ESG manuelle par ETF (D-048) : tests adverses du reviewer-tester.

Les défauts constatés à la première revue (B1 antidatage, B2 `corrige`, ordre, YAML mal formé, limites du rapport)
ont été corrigés : les tests correspondants ne portent plus de marque xfail. Aucun réseau, aucune clé.
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
import yaml

from amundi_agentic.data import analysis as analysis_now
from amundi_agentic.data.analysis import DETERMINE, INCONNU, SUPPOSE, esg_matrix
from amundi_agentic.data.connectors import esg_etf_sources as mod
from amundi_agentic.data.connectors.esg_etf_sources import (
    CHAMPS,
    EsgSourceError,
    RetroactiveModificationError,
    check_append_only,
    load_for_universe,
    parse_sources,
    verify_and_snapshot,
)
from amundi_agentic.data.pit import cutoff_utc
from amundi_agentic.data.settings import CONFIG_DIR, load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.data.universe import Universe

REPO = Path(__file__).resolve().parents[2]
CRIT = ("tobacco", "thermal_coal", "controversial_weapons")


# --------------------------------------------------------------------------- fabriques
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


def _inc(champ: str, n: int = 1, **kw) -> dict:
    e = {"id": f"T.PA:{champ}:{n:03d}", "champ": champ, "valeur": "inconnu", "raison": "aucun document",
         "date_saisie": "2024-01-12"}  # fmt: skip
    e.update(kw)
    return e


def _data(entries: list[dict]) -> dict:
    presents = {e["champ"] for e in entries}
    tous = list(entries) + [_inc(c) for c in CHAMPS if c not in presents]
    return {"version": 1, "etfs": {"T.PA": {"isin": "LU1681048804", "entries": tous}}}


def _store(tmp_path, jour: str) -> ParquetStore:
    return ParquetStore(
        tmp_path / "store", tmp_path / "snap",
        clock=lambda: datetime.fromisoformat(f"{jour}T10:00:00+00:00"),
    )  # fmt: skip


@pytest.fixture(scope="module")
def reel():
    return load_for_universe()


@pytest.fixture(scope="module")
def brut() -> dict:
    return yaml.safe_load((CONFIG_DIR / "esg_etf_sources.yaml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- 1. données saisies
# Empreintes recalculées par le reviewer-tester le 2026-10-03 en retéléchargeant chaque document (TLS actif).
HASH_VERIFIES = {
    "https://www.amundietf.fr/pdfDocuments/download/fc45f551-2b04-47f3-82b9-a157d2518042/91af44c0c20cd1143e107909440027d6.pdf": "12d9dd60aa91f11dc76d451fb09ab8cc7ff9102abdd1c50f694860925303c7b3",
    "https://www.amundietf.fr/pdfDocuments/download/b9c0be33-ce8e-4c9f-8359-c5b9d2f2ca61/483e8262f10dad173d8cbd84533b974b.pdf": "c0d6f48a7b5919fac6b969f244a5e2c484020f540dca0610f9e44b34f9e18f9c",
    "https://www.amundietf.fr/pdfDocuments/download/d1ab4c31-4707-4772-8937-2231a236730e/WebsiteSfdrDisclosure_LU1681040496_FRA_FRA_20230101.pdf": "315a261030411d789c8bf96f0419dae15913fe1e4033e559708001d4f299a5fd",
    "https://www.amundietf.fr/pdfDocuments/download/becef716-3cb9-45b5-bb6d-4ea330c9df43/KIDPRIIPs_1041544_80062_FRA_FRA_20260605.pdf": "a2dbbee32ef7999d6871d5f9a29981a9cff0d3b94303611041e6868c5fdabc00",
    "https://www.amundietf.fr/pdfDocuments/download/9f0702f3-6cd0-4ebd-b188-1bb8161f5d33/KIDPRIIPs_69376_FRA_FRA_20250919.pdf": "760e7cd6a97aa5e403e948123d76d3f0817a3b8a421831e0028c1cd0214f8e36",
    "https://www.amundietf.fr/pdfDocuments/download/8c0bba4f-aa84-4e30-8358-c680a9a72b42/PSC_1_UM49675_fra_FRA_20260901_20260804.pdf": "148c032726b3bca0312ebf227abcfa90a7956214a23cda6d527c3cb3b9c6cdba",
    "https://www.amundietf.fr/pdfDocuments/download/c9c17419-4c53-4123-8535-ab23cb10991a/PSC_1_UM94506_fra_FRA_20260730_20260730.pdf": "6acfa6dc69b0d641d1d016023f14aeb6810efae1b3fd96e23daf9a70956b4763",
}  # fmt: skip


def test_revue_hash_des_documents_recalcules_independamment(brut):
    """Les SHA-256 saisis pour 7 documents (dont ceux de CRP.PA, AHYE.PA et des exclusions) = ceux recalculés."""
    vus = {}
    for bloc in brut["etfs"].values():
        for e in bloc["entries"]:
            for src in [e.get("source") or {}, *(e.get("sources_complementaires") or [])]:
                if src.get("sha256"):
                    vus.setdefault(src["url"], set()).add(src["sha256"])
    for url, attendu in HASH_VERIFIES.items():
        assert vus.get(url) == {attendu}, url


def _luhn_isin(isin: str) -> bool:
    chiffres = "".join(str(int(c, 36)) for c in isin)
    total = 0
    for i, ch in enumerate(reversed(chiffres)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return total % 10 == 0


def test_revue_isin_valides_par_somme_de_controle_et_tickers_de_l_univers(reel):
    for tk, code in reel.isin.items():
        assert _luhn_isin(code), f"ISIN de {tk} invalide : {code}"
    assert set(reel.tickers) <= set(Universe.load().etf_tickers())


def test_revue_ecart_de_nom_entre_fiche_et_univers_est_borne(brut):
    """AHYE.PA (« … ESG UCITS ETF Acc » vs « … ESG UCITS ETF DR ») : seul écart toléré, à signaler."""
    uni = load_yaml("universe.yaml")
    attendus = {}
    for cls in uni["asset_classes"].values():
        if "primary" in cls:
            attendus[cls["primary"]["ticker"]] = cls["primary"].get("expected_name")
    attendus["CW8.PA"] = None

    def norm(s):
        return "".join(ch for ch in (s or "").lower() if ch.isalnum())

    ecarts = {
        tk: (attendus[tk], b["nom_fiche_consultee"])
        for tk, b in brut["etfs"].items()
        if attendus.get(tk) and norm(attendus[tk]) != norm(b["nom_fiche_consultee"])
    }
    assert set(ecarts) == {"AHYE.PA"}, ecarts


def test_revue_aucune_valeur_standard_et_swap_jamais_compte(reel):
    """Le caractère « standard » n'est jamais saisi ; les fonds à swap ne prouvent aucune exclusion de l'exposition."""
    assert all(e.valeur != "standard" for e in reel.all_entries())
    vue = reel.as_of(date(2026, 10, 4))
    for tk in ("500.PA", "AEEM.PA", "COMO.PA"):
        assert vue.exclusions(tk) == {"controversial_weapons": "titres_detenus_hors_swap"}
        assert vue.proven_exclusions(tk) == frozenset()


def test_revue_exclusions_comptees_ont_un_extrait_et_une_portee_documentee(reel):
    for e in reel.all_entries():
        if e.champ == "exclusions" and not e.est_inconnu:
            assert e.extrait and len(e.extrait) > 40
            assert e.source and e.source["url"].startswith("https://")
            assert e.date_document is not None and e.date_effet is not None


# --------------------------------------------------------------------------- 2. point-in-time
def test_revue_boucle_fichier_reel_aucune_valeur_servie_avant_sa_borne(reel):
    """Pour TOUTES les entrées : à t = borne, la veille et le lendemain, rien n'est servi avant sa borne."""
    for mode in ("strict", "non_pit"):
        for e in reel.all_entries():
            if e.est_marqueur:
                continue
            bornes = [d for d in (e.date_effet, e.date_document) if d]
            if mode == "strict":
                bornes.append(e.date_saisie)
            b = max(bornes)
            for t in (b - timedelta(days=1), b, b + timedelta(days=1)):
                r = reel.as_of(t, mode=mode).get(e.ticker, e.champ)
                if r.entry_id is None:
                    continue
                servi = next(x for x in reel.entries[e.ticker] if x.id == r.entry_id)
                refs = [d for d in (servi.date_effet, servi.date_document) if d]
                if mode == "strict":
                    refs.append(servi.date_saisie)
                assert max(refs) < t, (mode, t, servi.id)
            # à la coupure exacte et avant : jamais cette entrée
            for t in (b - timedelta(days=30), b):
                assert reel.as_of(t, mode=mode).get(e.ticker, e.champ).entry_id != e.id


def test_revue_strict_rien_avant_le_4_octobre_2026(reel):
    """Conséquence assumée : aucun backtest ne voit l'ESG des ETF (toutes les saisies datent du 2026-10-03)."""
    for t in (
        date(2018, 8, 28),
        date(2024, 2, 1),
        date(2025, 12, 31),
        date(2026, 10, 2),
        date(2026, 10, 3),
    ):
        v = reel.as_of(t)
        for tk in reel.tickers:
            assert all(r.est_inconnu for r in v.state(tk).values()), (t, tk)
    v = reel.as_of(date(2026, 10, 4))
    assert v.sfdr("CRP.PA") == "article_8" and v.sfdr("AHYE.PA") == "article_8"
    assert max(e.date_saisie for e in reel.all_entries()) == date(2026, 10, 3)


def test_revue_non_pit_ne_sert_jamais_avant_l_effet_ni_le_document(reel):
    """CRP.PA : avant 2022-12-12 rien ; l'indice change à la date d'effet documentée (2023-01-11)."""
    assert reel.as_of(date(2022, 12, 12), mode="non_pit").get("CRP.PA", "indice").est_inconnu
    anc = reel.as_of(date(2023, 1, 11), mode="non_pit").get("CRP.PA", "indice")
    assert "Liquid SRI" in anc.valeur and anc.non_point_in_time is True
    nouv = reel.as_of(date(2023, 1, 12), mode="non_pit").get("CRP.PA", "indice")
    assert "Green Tilted" in nouv.valeur
    # caractère PAB : saisi avec effet 2023-01-11 (document de 2022-12-12) : pas servi la veille
    assert (
        reel.as_of(date(2023, 1, 11), mode="non_pit").get("CRP.PA", "caractere_indice").est_inconnu
    )
    assert (
        reel.as_of(date(2023, 1, 12), mode="non_pit").get("CRP.PA", "caractere_indice").valeur
        == "pab"
    )


@pytest.mark.parametrize(
    ("veille", "jour"),
    [(date(2026, 10, 24), date(2026, 10, 25)), (date(2026, 3, 28), date(2026, 3, 29))],
)
def test_revue_changement_d_heure_paris(veille, jour):
    """La coupure est minuit Paris : 22:00Z (été, UTC+2) ou 23:00Z (hiver) ; jamais 24 h fixes."""
    assert cutoff_utc(jour).hour in (22, 23) and cutoff_utc(jour + timedelta(days=1)).hour in (
        22,
        23,
    )
    s = parse_sources(_data([_v("sfdr", "article_8", 1, date_saisie=veille.isoformat(),
                                date_consultation=veille.isoformat())]))  # fmt: skip
    # effet 2024 ; saisie la veille du changement d'heure : servie le jour du changement, pas la veille
    assert s.as_of(veille).sfdr("T.PA") == "inconnu"
    assert s.as_of(jour).sfdr("T.PA") == "article_8"
    # saisie le jour même du changement d'heure : exclue ce jour-là, servie le lendemain
    s2 = parse_sources(_data([_v("sfdr", "article_8", 1, date_saisie=jour.isoformat(),
                                 date_consultation=jour.isoformat())]))  # fmt: skip
    assert s2.as_of(jour).sfdr("T.PA") == "inconnu"
    assert s2.as_of(jour + timedelta(days=1)).sfdr("T.PA") == "article_8"


def test_revue_effet_documente_faux_avec_date_prudente():
    """Document du 2024-05-01, classification peut-être antérieure : avant le document, `inconnu` (jamais l'effet réel)."""
    e = _v("sfdr", "article_8", 1, date_document="2024-05-01", date_effet="2024-05-01",
           date_consultation="2024-05-02", date_saisie="2024-05-02")  # fmt: skip
    s = parse_sources(_data([e]))
    for mode in ("strict", "non_pit"):
        assert s.as_of(date(2024, 5, 1), mode=mode).sfdr("T.PA") == "inconnu"
    assert s.as_of(date(2024, 5, 2), mode="non_pit").sfdr("T.PA") == "article_8"
    assert s.as_of(date(2024, 5, 2)).sfdr("T.PA") == "inconnu"  # strict : saisie le 05-02, exclue
    assert s.as_of(date(2024, 5, 3)).sfdr("T.PA") == "article_8"
    # effet antérieur au document sans `effet_documente: true` : refusé
    mauvais = _v("sfdr", "article_8", 1, date_document="2024-05-01", date_effet="2024-01-01",
                 date_consultation="2024-05-02", date_saisie="2024-05-02")  # fmt: skip
    with pytest.raises(EsgSourceError, match="effet_documente"):
        parse_sources(_data([mauvais]))


def test_revue_retrait_inconnu_retire_une_valeur_et_n_agit_qu_apres_saisie():
    a = _v("sfdr", "article_8", 1)
    r = _inc("sfdr", 2, corrige="T.PA:sfdr:001", date_effet="2024-06-01", date_saisie="2025-01-10")
    s = parse_sources(_data([a, r]))
    assert (
        s.as_of(date(2025, 1, 10)).sfdr("T.PA") == "article_8"
    )  # retrait saisi ce jour : pas encore connu
    assert s.as_of(date(2025, 1, 11)).sfdr("T.PA") == "inconnu"
    # non_pit : le retrait s'applique dès sa date d'effet, marqué
    rr = s.as_of(date(2024, 7, 1), mode="non_pit").get("T.PA", "sfdr")
    assert rr.valeur == "inconnu" and rr.non_point_in_time is True
    # un marqueur `inconnu` sans corrige n'efface jamais une valeur
    m = _inc("sfdr", 3, date_saisie="2025-02-01")
    s2 = parse_sources(_data([a, m]))
    assert s2.as_of(date(2025, 3, 1)).sfdr("T.PA") == "article_8"
    assert s2.as_of(date(2025, 3, 1), mode="non_pit").sfdr("T.PA") == "article_8"


def test_revue_deux_entrees_le_meme_jour_tranchees_par_l_ordre_du_fichier():
    """Deux entrées concurrentes (même effet, même saisie) : la dernière du fichier l'emporte (documenté)."""
    a = _v("indice", "A", 1)
    b = _v("indice", "B", 2)
    assert parse_sources(_data([a, b])).as_of(date(2024, 2, 1)).get("T.PA", "indice").valeur == "B"
    assert parse_sources(_data([b, a])).as_of(date(2024, 2, 1)).get("T.PA", "indice").valeur == "A"


def test_revue_la_vue_ne_lit_jamais_les_instantanes():
    """Les instantanés ne servent qu'au contrôle append-only, jamais d'`as_of`."""
    src = inspect.getsource(mod.EtfEsgView) + inspect.getsource(mod.EtfSources)
    assert "read_snapshots" not in src and "snapshot" not in src.lower()


# --------------------------------------------------------------------------- défauts constatés puis corrigés
def test_revue_une_entree_corrigee_n_est_plus_servie_apres_sa_correction():
    a = _v("sfdr", "article_6", 1, date_document="2024-06-01", date_effet="2024-06-01",
           date_consultation="2024-06-02", date_saisie="2024-06-02")  # fmt: skip
    c = _v("sfdr", "article_8", 2, corrige="T.PA:sfdr:001", date_document="2024-01-10",
           date_effet="2024-01-10", effet_documente=True, date_consultation="2025-01-01",
           date_saisie="2025-01-01")  # fmt: skip
    s = parse_sources(_data([a, c]))
    assert s.as_of(date(2024, 7, 1)).sfdr("T.PA") == "article_6"  # ce qu'on savait alors
    assert (
        s.as_of(date(2025, 2, 1)).sfdr("T.PA") == "article_8"
    )  # la correction est connue : elle prévaut


def test_revue_entree_nouvelle_antidatee_refusee(tmp_path):
    base = parse_sources(_data([_v("sfdr", "article_6", 1)]))
    verify_and_snapshot(base, _store(tmp_path, "2026-10-03"))
    ajout = copy.deepcopy(_data([_v("sfdr", "article_6", 1)]))
    ajout["etfs"]["T.PA"]["entries"].append(
        _v("indice", "Indice antidaté", 2, date_document="2026-01-01", date_effet="2026-01-01",
           date_consultation="2026-01-01", date_saisie="2026-01-01")  # saisie réelle le 2026-10-10
    )  # fmt: skip
    s2 = parse_sources(ajout)
    assert (
        s2.as_of(date(2026, 2, 1)).get("T.PA", "indice").valeur == "Indice antidaté"
    )  # fuite du futur
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(s2, _store(tmp_path, "2026-10-10"))


def test_revue_reordonner_le_fichier_ne_change_pas_la_valeur_servie_sans_alerte(tmp_path):
    a, b = _v("indice", "A", 1), _v("indice", "B", 2)
    s1 = parse_sources(_data([a, b]))
    verify_and_snapshot(s1, _store(tmp_path, "2026-10-03"))
    s2 = parse_sources(_data([b, a]))
    v1 = s1.as_of(date(2024, 2, 1)).get("T.PA", "indice").valeur
    v2 = s2.as_of(date(2024, 2, 1)).get("T.PA", "indice").valeur
    try:
        verify_and_snapshot(s2, _store(tmp_path, "2026-10-04"))
        alerte = False
    except RetroactiveModificationError:
        alerte = True
    assert v1 == v2 or alerte


# --------------------------------------------------------------------------- 3. append-only
def _snap_count(tmp_path) -> int:
    return len(list((tmp_path / "snap" / "esg_etf_sources").glob("*/entries*.parquet")))


def test_revue_append_only_contournements(tmp_path):
    base = _data([_v("indice", "Indice Alpha", 1, extrait="Indice Alpha")])
    s1 = parse_sources(base)
    verify_and_snapshot(s1, _store(tmp_path, "2026-10-03"))
    assert _snap_count(tmp_path) == 1

    # casse d'un champ libre : c'est une modification
    maj = copy.deepcopy(base)
    maj["etfs"]["T.PA"]["entries"][0]["valeur"] = "INDICE ALPHA"
    with pytest.raises(RetroactiveModificationError, match="T.PA:indice:001"):
        verify_and_snapshot(parse_sources(maj), _store(tmp_path, "2026-10-04"))
    # extrait modifié
    ex = copy.deepcopy(base)
    ex["etfs"]["T.PA"]["entries"][0]["extrait"] = "Indice Alpha (reformulé)"
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(parse_sources(ex), _store(tmp_path, "2026-10-04"))
    # source modifiée (URL)
    u = copy.deepcopy(base)
    u["etfs"]["T.PA"]["entries"][0]["source"]["url"] = "https://exemple.test/autre.pdf"
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(parse_sources(u), _store(tmp_path, "2026-10-04"))
    # date de saisie redatée
    d = copy.deepcopy(base)
    d["etfs"]["T.PA"]["entries"][0]["date_saisie"] = "2024-01-11"
    d["etfs"]["T.PA"]["entries"][0]["date_consultation"] = "2024-01-11"
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(parse_sources(d), _store(tmp_path, "2026-10-04"))
    # même jour : modification refusée aussi
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(parse_sources(maj), _store(tmp_path, "2026-10-03"))
    assert _snap_count(tmp_path) == 1

    # réordonnancement de champs dans l'entrée ou de dates en chaîne ISO au lieu de date : pas de faux positif
    ok = copy.deepcopy(base)
    e0 = ok["etfs"]["T.PA"]["entries"][0]
    ok["etfs"]["T.PA"]["entries"][0] = dict(reversed(list(e0.items())))
    e0["date_saisie"] = date(2024, 1, 12)  # objet date au lieu de chaîne ISO (YAML non quoté)
    assert check_append_only(parse_sources(ok), _store(tmp_path, "2026-10-04")) == []

    # ajout le même jour : autorisé, écrit sous ~2 (jamais d'écrasement)
    plus = copy.deepcopy(base)
    plus["etfs"]["T.PA"]["entries"].append(_inc("indice", 2))
    p = verify_and_snapshot(parse_sources(plus), _store(tmp_path, "2026-10-03"))
    assert p is not None and "~2" in p.name and _snap_count(tmp_path) == 2
    # nouvelle exécution identique : idempotente
    assert verify_and_snapshot(parse_sources(plus), _store(tmp_path, "2026-10-03")) == p
    assert _snap_count(tmp_path) == 2


def test_revue_instantane_corrompu_echoue_bruyamment(tmp_path):
    s = parse_sources(_data([_v("sfdr", "article_6", 1)]))
    p = verify_and_snapshot(s, _store(tmp_path, "2026-10-03"))
    Path(p).write_bytes(b"pas du parquet")
    with pytest.raises(Exception):  # noqa: B017 - toute erreur est acceptable, jamais un « conforme » silencieux
        check_append_only(s, _store(tmp_path, "2026-10-04"))


def test_revue_limite_connue_instantane_supprime_rend_le_controle_vacuous(tmp_path):
    """LIMITE (non bloquante en soi, mais à dire) : `.cache/` n'est pas versionné ; sans instantané, rien n'est vérifié."""
    base = _data([_v("sfdr", "article_6", 1)])
    s = parse_sources(base)
    verify_and_snapshot(s, _store(tmp_path, "2026-10-03"))
    modif = copy.deepcopy(base)
    modif["etfs"]["T.PA"]["entries"][0]["valeur"] = "article_9"
    shutil.rmtree(tmp_path / "snap")
    assert check_append_only(parse_sources(modif), _store(tmp_path, "2026-10-04")) == []
    assert ".cache/" in (REPO / ".gitignore").read_text()


def _git(*args: str) -> str | None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        return None
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


# Migration autorisée une seule fois, avant verrouillage (D-048, corrections) : 23 sources de type `fiche_produit`
# deviennent `fiche_produit_archivee` (réponse brute de l'API archivée). Seuls ces champs de la source changent.
MIGRATION_FICHE_ARCHIVEE = frozenset(
    {
        "500.PA:indice:001", "500.PA:sfdr:001", "AEEM.PA:indice:001", "AEEM.PA:sfdr:001",
        "C3M.PA:indice:001", "C3M.PA:sfdr:001", "COMO.PA:indice:001", "COMO.PA:sfdr:001",
        "CRP.PA:indice:003", "CSH2.PA:indice:001", "CSH2.PA:sfdr:001", "CW8.PA:indice:001",
        "CW8.PA:sfdr:001", "EGOV.PA:indice:001", "EGOV.PA:sfdr:001", "GOLD.PA:indice:001",
        "GOLD.PA:sfdr:001", "JPN.PA:indice:001", "JPN.PA:sfdr:001", "MEU.PA:indice:001",
        "MEU.PA:sfdr:001", "MTD.PA:indice:001", "MTD.PA:sfdr:001",
    }
)  # fmt: skip
CHAMPS_SOURCE_MIGRES = {"type_document", "reference", "titre", "archive"}


def _source_migree_autorisee(ancienne: dict, nouvelle: dict) -> bool:
    if ancienne == nouvelle:
        return True
    if ancienne.get("type_document") != "fiche_produit":
        return False
    if nouvelle.get("type_document") != "fiche_produit_archivee" or not nouvelle.get("archive"):
        return False
    diff = {k for k in set(ancienne) | set(nouvelle) if ancienne.get(k) != nouvelle.get(k)}
    return diff <= CHAMPS_SOURCE_MIGRES and ancienne.get("url") == nouvelle.get("url")


def _sans_sources(e: dict) -> dict:
    return {k: v for k, v in e.items() if k not in ("source", "sources_complementaires")}


def test_revue_historique_git_aucune_entree_modifiee_ni_supprimee():
    """Garde-fou versionné : aucune entrée d'un commit passé n'est supprimée ni modifiée (valeur, dates, id,
    `extrait`, note...). Seule exception : la migration documentée `fiche_produit` -> `fiche_produit_archivee`
    des 23 sources de MIGRATION_FICHE_ARCHIVEE (même URL, mêmes dates). Ensuite, la référence est le registre."""
    commits = (_git("log", "--format=%H", "--", "config/esg_etf_sources.yaml") or "").split()
    if len(commits) < 1:
        pytest.skip("historique git indisponible")
    actuel = yaml.safe_load((CONFIG_DIR / "esg_etf_sources.yaml").read_text(encoding="utf-8"))
    now = {e["id"]: e for b in actuel["etfs"].values() for e in b["entries"]}
    for c in commits:
        txt = _git("show", f"{c}:config/esg_etf_sources.yaml")
        if txt is None:
            continue
        for b in yaml.safe_load(txt)["etfs"].values():
            for ancien in b["entries"]:
                ident = ancien["id"]
                assert ident in now, f"entrée supprimée depuis {c[:8]} : {ident}"
                nouveau = now[ident]
                assert mod._canon(_sans_sources(ancien)) == mod._canon(_sans_sources(nouveau)), (
                    f"entrée modifiée depuis {c[:8]} : {ident}"
                )
                olds = [ancien.get("source") or {}, *(ancien.get("sources_complementaires") or [])]
                news = [
                    nouveau.get("source") or {},
                    *(nouveau.get("sources_complementaires") or []),
                ]
                assert len(olds) == len(news), f"sources ajoutées ou retirées : {ident}"
                for o, n in zip(olds, news, strict=True):
                    if o == n:
                        continue
                    assert ident in MIGRATION_FICHE_ARCHIVEE, (
                        f"source modifiée hors migration : {ident}"
                    )
                    assert _source_migree_autorisee(o, n), f"migration non conforme : {ident}"


def test_revue_la_migration_n_autorise_pas_de_changer_une_url_ni_un_hash():
    """Le test précédent n'est pas affaibli : ce qui n'est pas la migration documentée est refusé."""
    ancien = {
        "type_document": "fiche_produit",
        "url": "https://x/y",
        "titre": "a",
        "reference": "r",
    }
    ok = {"type_document": "fiche_produit_archivee", "url": "https://x/y", "titre": "b", "reference": "r2",
          "archive": {"chemin": "a.json", "sha256": "0" * 64}}  # fmt: skip
    assert _source_migree_autorisee(ancien, ok)
    assert not _source_migree_autorisee(ancien, {**ok, "url": "https://x/z"})
    assert not _source_migree_autorisee(ancien, {**ok, "sha256": "1" * 64})
    assert not _source_migree_autorisee({**ancien, "type_document": "dic_kid"}, ok)
    assert not _source_migree_autorisee(ancien, {**ok, "date_document": "2020-01-01"})
    assert not _source_migree_autorisee(ancien, {k: v for k, v in ok.items() if k != "archive"})


def test_revue_historique_git_du_registre_est_append_only():
    """Le registre versionné ne perd ni ne modifie aucune ligne d'un commit à l'autre."""
    commits = (_git("log", "--format=%H", "--", "config/esg_etf_sources.lock.json") or "").split()
    if not commits:
        pytest.skip("registre pas encore versionné ou historique indisponible")
    import json

    now = {
        r["id"]: r
        for r in json.loads((CONFIG_DIR / "esg_etf_sources.lock.json").read_text())["entries"]
    }
    for c in commits:
        txt = _git("show", f"{c}:config/esg_etf_sources.lock.json")
        if txt is None:
            continue
        for r in json.loads(txt)["entries"]:
            assert now.get(r["id"]) == r, (
                f"ligne du registre modifiée ou supprimée depuis {c[:8]} : {r['id']}"
            )


# --------------------------------------------------------------------------- 4. matrice ESG
def _records_reels(reel) -> pd.DataFrame:
    notes = {
        "CRP.PA": "basis:paris_aligned_index|not_verified", "AHYE.PA": "basis:esg_index|not_verified",
    }  # fmt: skip
    rows = [{"asset_id": tk, "kind": "etf", "sic": None, "notes": notes.get(tk, "basis:none_known|not_verified")}
            for tk in reel.tickers]  # fmt: skip
    rows += [{"asset_id": "ZS", "kind": "stock", "sic": "7372", "notes": ""},
             {"asset_id": "AAPL", "kind": "stock", "sic": "3571", "notes": ""}]  # fmt: skip
    return pd.DataFrame(rows).assign(observed_at=pd.Timestamp("2026-10-02", tz="UTC"))


def _attendu_independant(brut, t: date) -> dict[str, set[str]]:
    """Critères prouvés par un document connu à t, recalculés depuis le YAML brut (sans le code du module)."""
    sortie = {}
    for tk, bloc in brut["etfs"].items():
        cand = []
        for ordre, e in enumerate(bloc["entries"]):
            if e["champ"] != "exclusions" or (e["valeur"] == "inconnu" and not e.get("corrige")):
                continue
            bornes = [
                date.fromisoformat(str(e[k]))
                for k in ("date_effet", "date_document", "date_saisie")
                if e.get(k)
            ]
            if max(bornes) < t:
                cand.append(
                    (
                        date.fromisoformat(str(e["date_effet"])),
                        date.fromisoformat(str(e["date_saisie"])),
                        ordre,
                        e,
                    )
                )
        if not cand:
            sortie[tk] = set()
            continue
        e = max(cand, key=lambda x: x[:3])[3]
        v = {} if e["valeur"] == "inconnu" else e["valeur"]
        sortie[tk] = {
            c for c, p in v.items() if p in ("indice", "portefeuille_replication_directe")
        }
    return sortie


def test_revue_matrice_recalculee_independamment(reel, brut):
    cfg = load_yaml("esg.yaml")
    rec = _records_reels(reel)
    t = date(2026, 10, 4)
    avant, _ = esg_matrix(rec, cfg["normative_exclusions"], cfg["basis_definitions"])
    apres, totaux = esg_matrix(
        rec, cfg["normative_exclusions"], cfg["basis_definitions"], etf_view=reel.as_of(t)
    )
    attendu = _attendu_independant(brut, t)
    assert {k for k, v in attendu.items() if v} == {"CRP.PA", "AHYE.PA"}
    pa, pb = {r["actif"]: r for r in avant}, {r["actif"]: r for r in apres}
    for actif, ligne in pb.items():
        for c in CRIT:
            if actif in attendu and c in attendu[actif]:
                assert ligne[c] == DETERMINE, (actif, c)
            else:
                assert ligne[c] == pa[actif][c], (actif, c)  # inchangé : supposé ou inconnu
    n = len(apres)
    assert n == 15
    for c in CRIT:
        assert totaux[c][DETERMINE] == 2
        assert totaux[c][DETERMINE] + totaux[c][SUPPOSE] + totaux[c][INCONNU] == n
    assert pb["ZS"]["sfdr"] == "sans objet" and pb["CRP.PA"]["sfdr"] == "article_8"


def _ancien_analysis():
    """Version de `analysis.py` du commit de la phase 2 (avant D-048) : référence de non-régression."""
    src = _git("show", "7cbbf22:src/amundi_agentic/data/analysis.py")
    if src is None:
        return None
    spec = importlib.util.spec_from_loader("analysis_avant_d048", loader=None)
    m = importlib.util.module_from_spec(spec)
    exec(compile(src, "analysis_avant_d048.py", "exec"), m.__dict__)  # noqa: S102 - code du dépôt, test seulement
    return m


def test_revue_sans_etf_view_resultat_identique_a_l_ancien():
    ancien = _ancien_analysis()
    if ancien is None:
        pytest.skip("commit de référence 7cbbf22 indisponible (clone superficiel)")
    cfg = load_yaml("esg.yaml")
    rows = []
    for i, basis in enumerate(
        ["paris_aligned_index", "esg_index", "none_known", "ctb_index", "inconnue"]
    ):
        rows.append(
            {
                "asset_id": f"E{i}",
                "kind": "etf",
                "sic": None,
                "notes": f"basis:{basis}|not_verified",
            }
        )
    for i, (sic, notes) in enumerate(
        [("3571", ""), ("2111", ""), (None, "vendor_flag:tobacco"), ("1220", "")]
    ):
        rows.append({"asset_id": f"S{i}", "kind": "stock", "sic": sic, "notes": notes})
    rec = pd.DataFrame(rows).assign(observed_at=pd.Timestamp("2026-10-02", tz="UTC"))
    args = (rec, cfg["normative_exclusions"], cfg["basis_definitions"])
    assert analysis_now.esg_matrix(*args) == ancien.esg_matrix(*args)
    assert analysis_now.esg_matrix(*args, etf_view=None) == ancien.esg_matrix(*args)


# --------------------------------------------------------------------------- 5. validation et rapport
@pytest.mark.parametrize("caractere", ["esg", "pab", "ctb"])
def test_revue_extrait_obligatoire_pour_esg_pab_ctb(caractere):
    with pytest.raises(EsgSourceError, match="extrait"):
        parse_sources(_data([_v("caractere_indice", caractere, 1)]))
    parse_sources(_data([_v("caractere_indice", caractere, 1, extrait="texte du document")]))


@pytest.mark.parametrize(
    ("mutation", "motif"),
    [
        ({"source": None}, "source"),
        ({"emetteur": "moi"}, "emetteur"),
        ({"source": {**_src(), "url": "http://exemple.test/x"}}, "https"),
        ({"source": {**_src(), "type_document": "blog"}}, "type_document"),
        ({"effet_documente": "oui"}, "booléen"),
        ({"date_saisie": "2024-01-01"}, "antérieure"),
        ({"valeur": "article_7"}, "sfdr"),
        ({"date_effet": "10/01/2024"}, "date ISO"),
    ],
)
def test_revue_validation_refuse(mutation, motif):
    with pytest.raises(EsgSourceError, match=motif):
        e = _v("sfdr", "article_8", 1)
        e.update(mutation)
        parse_sources(_data([e]))


def test_revue_fichier_invalide_le_rapport_le_dit_et_garde_la_matrice(monkeypatch):
    from amundi_agentic.data.coverage import Report

    def casse(*a, **k):
        raise EsgSourceError("- T.PA: aucune entrée pour le champ `sfdr`")

    monkeypatch.setattr(mod, "load_for_universe", casse)
    r = Report.__new__(Report)
    r.data = {}
    vue, note = r._etf_sources_view()
    assert vue is None and "indisponible" in note and "EsgSourceError" in note
    assert (
        r.data["esg_etf_sources"]["statut"] == "indisponible"
        and "sfdr" in r.data["esg_etf_sources"]["erreur"]
    )
    cfg = load_yaml("esg.yaml")
    rec = pd.DataFrame([{"asset_id": "CRP.PA", "kind": "etf", "sic": None,
                         "notes": "basis:paris_aligned_index"}]).assign(observed_at=pd.Timestamp("2026-10-02", tz="UTC"))  # fmt: skip
    ligne = esg_matrix(rec, cfg["normative_exclusions"], cfg["basis_definitions"], etf_view=vue)[0][
        0
    ]
    assert ligne["tobacco"] == SUPPOSE and "sfdr" not in ligne  # matrice précédente


def test_revue_yaml_mal_forme_ne_plante_pas_le_rapport(monkeypatch, tmp_path):
    from amundi_agentic.data.coverage import Report

    mauvais = tmp_path / "x.yaml"
    mauvais.write_text("etfs: [unclosed\n  - : :\n", encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(mod, "DEFAULT_FILE", "x.yaml")
    r = Report.__new__(Report)
    r.data = {}
    vue, note = r._etf_sources_view()
    assert vue is None and "indisponible" in note


def test_revue_note_du_rapport_porte_les_limites():
    from amundi_agentic.data.coverage import Report

    r = Report.__new__(Report)
    r.data = {}
    vue, note = r._etf_sources_view()
    assert vue is not None and r.data["esg_etf_sources"]["statut"] == "ok"
    for phrase in ("score ESG", "n'implique pas", "réplication directe"):
        assert phrase in note
    assert str(r.data["esg_etf_sources"]["as_of"]) > "2026-10-03"


def test_revue_rapport_dit_que_les_exclusions_ont_des_seuils():
    from amundi_agentic.data.coverage import Report

    r = Report.__new__(Report)
    r.data = {}
    _, note = r._etf_sources_view()
    assert "seuil" in note.lower()


def test_revue_documentation_dit_qu_aucun_backtest_ne_voit_l_esg_des_etf():
    from amundi_agentic.data.coverage import Report

    r = Report.__new__(Report)
    r.data = {}
    _, note = r._etf_sources_view()
    assert "backtest" in (mod.__doc__ or "").lower() or "backtest" in note.lower()


# =========================================================================== 2e revue (après corrections B1/B2)
import hashlib  # noqa: E402
import json  # noqa: E402

from amundi_agentic.data.connectors.esg_etf_sources import (  # noqa: E402
    check_lock,
    read_lock,
    write_lock,
)

LOCK = CONFIG_DIR / "esg_etf_sources.lock.json"


def _canon_independant(e: dict) -> str:
    def plat(x):
        if isinstance(x, datetime | date):
            return x.isoformat()
        if isinstance(x, dict):
            return {str(k): plat(v) for k, v in x.items()}
        if isinstance(x, list | tuple):
            return [plat(v) for v in x]
        return x

    return json.dumps(plat(e), sort_keys=True, ensure_ascii=False)


def test_registre_script_independant_chaque_entree_verrouillee_avec_le_bon_sha(brut):
    lock = {r["id"]: r for r in json.loads(LOCK.read_text(encoding="utf-8"))["entries"]}
    attendu = {}
    for bloc in brut["etfs"].values():
        for ordre, e in enumerate(bloc["entries"]):
            attendu[e["id"]] = hashlib.sha256(
                f"{ordre}|{_canon_independant(e)}".encode()
            ).hexdigest()
    assert len(attendu) == 58 and set(lock) == set(attendu)
    for ident, h in attendu.items():
        assert lock[ident]["sha256"] == h, ident


def _mutations_du_fichier_reel(brut):
    """Une modification d'un seul caractère dans un `extrait`, une date, un id ou une valeur."""
    b1 = copy.deepcopy(brut)
    e = next(x for x in b1["etfs"]["CRP.PA"]["entries"] if x["id"] == "CRP.PA:exclusions:002")
    e["extrait"] = e["extrait"].replace("aucun", "aucum", 1)
    b2 = copy.deepcopy(brut)
    next(x for x in b2["etfs"]["AHYE.PA"]["entries"] if x["id"] == "AHYE.PA:sfdr:001")[
        "date_effet"
    ] = "2023-01-17"
    b3 = copy.deepcopy(brut)
    next(x for x in b3["etfs"]["CRP.PA"]["entries"] if x["id"] == "CRP.PA:indice:003")["id"] = (
        "CRP.PA:indice:004"
    )
    b4 = copy.deepcopy(brut)
    next(x for x in b4["etfs"]["500.PA"]["entries"] if x["id"] == "500.PA:sfdr:001")["valeur"] = (
        "article_8"
    )
    return {"extrait": b1, "date": b2, "id": b3, "valeur": b4}


@pytest.mark.parametrize("cle", ["extrait", "date", "id", "valeur"])
def test_registre_refuse_un_caractere_modifie_sans_cache(brut, cle, tmp_path):
    """Sans `.cache` ni instantané : le registre versionné suffit (comme en CI sur un clone neuf)."""
    modif = _mutations_du_fichier_reel(brut)[cle]
    src = parse_sources(modif, base_dir=CONFIG_DIR)
    assert check_lock(src, LOCK), cle
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(
            src, _store(tmp_path, "2026-10-10"), lock_path=LOCK, today=date(2026, 10, 10)
        )
    with pytest.raises(RetroactiveModificationError):
        write_lock(src, LOCK, today=date(2026, 10, 10))


def test_registre_reel_non_reecrit_par_les_refus():
    avant = LOCK.read_bytes()
    brut_ = yaml.safe_load((CONFIG_DIR / "esg_etf_sources.yaml").read_text(encoding="utf-8"))
    brut_["etfs"]["500.PA"]["entries"][0]["valeur"] = "article_9"
    with pytest.raises(RetroactiveModificationError):
        write_lock(parse_sources(brut_, base_dir=CONFIG_DIR), LOCK, today=date(2026, 10, 10))
    assert LOCK.read_bytes() == avant


def test_registre_incoherent_echoue_bruyamment(reel, tmp_path):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    # empreinte fausse
    faux = copy.deepcopy(lock)
    faux["entries"][0]["sha256"] = "0" * 64
    p = tmp_path / "faux.json"
    p.write_text(json.dumps(faux), encoding="utf-8")
    assert len(check_lock(reel, p)) == 1
    # ligne pour une entrée absente du fichier
    fantome = copy.deepcopy(lock)
    fantome["entries"].append({**lock["entries"][0], "id": "500.PA:sfdr:099"})
    p2 = tmp_path / "fantome.json"
    p2.write_text(json.dumps(fantome), encoding="utf-8")
    assert any("supprimée" in v for v in check_lock(reel, p2))
    # JSON corrompu : exception, jamais « conforme »
    p3 = tmp_path / "casse.json"
    p3.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        check_lock(reel, p3)
    # registre au mauvais format
    p4 = tmp_path / "mauvais.json"
    p4.write_text(json.dumps({"entries": [{"id": lock["entries"][0]["id"]}]}), encoding="utf-8")
    with pytest.raises(KeyError):
        check_lock(reel, p4)


def _etat_verrouille(tmp_path, jour="2026-10-03"):
    base = _data([_v("sfdr", "article_6", 1)])
    s = parse_sources(base)
    lock = tmp_path / "t.lock.json"
    verify_and_snapshot(s, _store(tmp_path, jour), lock_path=lock, today=date.fromisoformat(jour))
    write_lock(s, lock, today=date.fromisoformat(jour))
    return base, lock


def test_b1_antidatage_et_date_future_refuses_apres_amorcage(tmp_path):
    base, lock = _etat_verrouille(tmp_path)
    assert len(read_lock(lock)) == 4
    for saisie in ("2026-01-01", "2026-10-09", "2027-03-01"):  # antidatée, veille, future
        ajout = copy.deepcopy(base)
        ajout["etfs"]["T.PA"]["entries"].append(
            _v(
                "indice",
                "X",
                2,
                date_document="2026-01-01",
                date_effet="2026-01-01",
                date_consultation=saisie,
                date_saisie=saisie,
            )  # fmt: skip
        )
        # (date_consultation <= date_saisie requis ; date_document < consultation ok)
        s = parse_sources(ajout)
        with pytest.raises(RetroactiveModificationError, match="entrée nouvelle"):
            verify_and_snapshot(
                s, _store(tmp_path, "2026-10-10"), lock_path=lock, today=date(2026, 10, 10)
            )
        with pytest.raises(RetroactiveModificationError, match="entrée nouvelle"):
            write_lock(s, lock, today=date(2026, 10, 10))
    # la saisie du jour est acceptée
    ok = copy.deepcopy(base)
    ok["etfs"]["T.PA"]["entries"].append(
        _v("indice", "X", 2, date_consultation="2026-10-10", date_saisie="2026-10-10")
    )
    s = parse_sources(ok)
    verify_and_snapshot(s, _store(tmp_path, "2026-10-10"), lock_path=lock, today=date(2026, 10, 10))
    write_lock(s, lock, today=date(2026, 10, 10))
    assert "T.PA:indice:002" in read_lock(lock)


def test_b1_supprimer_les_instantanes_cache_ne_contourne_pas_le_registre(tmp_path):
    base, lock = _etat_verrouille(tmp_path)
    shutil.rmtree(tmp_path / "snap")
    antidate = copy.deepcopy(base)
    antidate["etfs"]["T.PA"]["entries"].append(
        _v("indice", "X", 2, date_consultation="2026-01-02", date_saisie="2026-01-02")
    )
    with pytest.raises(RetroactiveModificationError, match="entrée nouvelle"):
        verify_and_snapshot(
            parse_sources(antidate),
            _store(tmp_path, "2026-10-10"),
            lock_path=lock,
            today=date(2026, 10, 10),
        )
    # et réciproquement : sans registre mais avec instantanés, l'antidatage est refusé aussi
    lock.unlink()
    base2 = _data([_v("sfdr", "article_6", 1)])
    verify_and_snapshot(parse_sources(base2), _store(tmp_path, "2026-10-03"))
    antidate2 = copy.deepcopy(base2)
    antidate2["etfs"]["T.PA"]["entries"].append(
        _v("indice", "X", 2, date_consultation="2026-01-02", date_saisie="2026-01-02")
    )
    with pytest.raises(RetroactiveModificationError, match="entrée nouvelle"):
        verify_and_snapshot(
            parse_sources(antidate2), _store(tmp_path, "2026-10-10"), today=date(2026, 10, 10)
        )


def test_b1_amorcage_accepte_une_fois_puis_plus_jamais(tmp_path):
    """Limite connue et assumée : le tout premier état est accepté tel quel (même antidaté). Ensuite refus."""
    antidate = _data(
        [
            _v(
                "sfdr",
                "article_6",
                1,
                date_document="2020-01-01",
                date_effet="2020-01-01",
                date_consultation="2020-01-02",
                date_saisie="2020-01-02",
            )
        ]
    )
    s = parse_sources(antidate)
    lock = tmp_path / "boot.lock.json"
    verify_and_snapshot(
        s, _store(tmp_path, "2026-10-03"), lock_path=lock, today=date(2026, 10, 3)
    )  # amorçage
    write_lock(s, lock, today=date(2026, 10, 3))
    plus = copy.deepcopy(antidate)
    plus["etfs"]["T.PA"]["entries"].append(
        _v(
            "indice",
            "Y",
            2,
            date_document="2020-01-01",
            date_effet="2020-01-01",
            date_consultation="2020-02-02",
            date_saisie="2020-02-02",
        )
    )
    with pytest.raises(RetroactiveModificationError):
        write_lock(parse_sources(plus), lock, today=date(2026, 10, 4))


def test_b1_horloge_pas_detournable_par_la_commande_de_production():
    """`today=` n'est exposé qu'aux appelants de bibliothèque : la commande `lock`/`snapshot` ne le passe pas
    (horloge système pour le registre ; horloge du stockage, système par défaut, pour les instantanés)."""
    src = inspect.getsource(mod.main)
    assert "today" not in src
    assert "date.today()" in inspect.getsource(mod.write_lock)
    assert "_clock().date()" in inspect.getsource(mod.verify_and_snapshot)


def test_b2_corrige_en_strict_en_non_pit_et_en_chaine():
    a = _v("indice", "A", 1, date_document="2024-06-01", date_effet="2024-06-01",
           date_consultation="2024-06-02", date_saisie="2024-06-02")  # fmt: skip
    b = _v("indice", "B", 2, corrige="T.PA:indice:001", date_document="2024-03-01", date_effet="2024-03-01",
           date_consultation="2025-01-01", date_saisie="2025-01-01")  # fmt: skip
    c = _v("indice", "C", 3, corrige="T.PA:indice:002", date_document="2024-02-01", date_effet="2024-02-01",
           date_consultation="2025-06-01", date_saisie="2025-06-01")  # fmt: skip
    s = parse_sources(_data([a, b, c]))
    val = lambda t, mode="strict": s.as_of(t, mode=mode).get("T.PA", "indice").valeur  # noqa: E731
    assert val(date(2024, 7, 1)) == "A"
    assert val(date(2025, 1, 1)) == "A"  # B saisie ce jour : pas encore connue
    assert val(date(2025, 1, 2)) == "B"  # A corrigée par B, bien que d'effet plus récent
    assert val(date(2025, 6, 1)) == "B"
    assert val(date(2025, 6, 2)) == "C"  # chaîne : B corrigée par C
    # non_pit : la dernière correction connue (documents) prévaut dès sa date de document
    assert val(date(2024, 7, 1), "non_pit") == "C"
    assert val(date(2024, 2, 15), "non_pit") == "C"
    assert val(date(2024, 1, 15), "non_pit") == "inconnu"
    r = s.as_of(date(2024, 7, 1), mode="non_pit").get("T.PA", "indice")
    assert r.non_point_in_time is True


def test_b2_retrait_corrige_et_visant_un_id_inexistant():
    a = _v("sfdr", "article_8", 1)
    fantome = _inc(
        "sfdr", 2, corrige="T.PA:sfdr:042", date_effet="2024-06-01", date_saisie="2025-01-01"
    )
    with pytest.raises(EsgSourceError, match="inexistant"):
        parse_sources(_data([a, fantome]))
    # une entrée ne peut pas se corriger elle-même ni corriger une entrée postérieure
    soi = _v(
        "sfdr",
        "article_9",
        2,
        corrige="T.PA:sfdr:002",
        date_saisie="2025-01-01",
        date_consultation="2025-01-01",
    )
    with pytest.raises(EsgSourceError):
        parse_sources(_data([a, soi]))
    r = _inc("sfdr", 2, corrige="T.PA:sfdr:001", date_effet="2024-01-10", date_saisie="2025-01-01")
    s = parse_sources(_data([a, r]))
    assert s.as_of(date(2025, 1, 2)).sfdr("T.PA") == "inconnu"
    assert s.as_of(date(2025, 1, 1)).sfdr("T.PA") == "article_8"


# --------------------------------------------------------------------------- archives de l'API (hygiène, preuves)
ARCH = CONFIG_DIR / "esg_etf_sources_archive"


def test_archives_json_valides_hash_taille_et_aucun_secret(brut):
    fichiers = sorted(ARCH.glob("*.json"))
    assert len(fichiers) == 14  # 13 ISIN + MANIFEST
    manifest = json.loads((ARCH / "MANIFEST.json").read_text(encoding="utf-8"))
    for f in fichiers:
        txt = f.read_text(encoding="utf-8")
        json.loads(txt)
        assert f.stat().st_size < 20_000, f.name
        bas = txt.lower()
        for mot in (
            "authorization",
            "cookie",
            "set-cookie",
            "token",
            "bearer",
            "api_key",
            "apikey",
            "password",
        ):
            assert mot not in bas, (f.name, mot)
    isins = {b["isin"] for b in brut["etfs"].values()}
    assert {f.stem for f in fichiers} - {"MANIFEST"} == isins
    # chaque archive référencée a le bon SHA-256
    for bloc in brut["etfs"].values():
        for e in bloc["entries"]:
            for s in [e.get("source") or {}, *(e.get("sources_complementaires") or [])]:
                if s.get("archive"):
                    f = CONFIG_DIR / s["archive"]["chemin"]
                    assert hashlib.sha256(f.read_bytes()).hexdigest() == s["archive"]["sha256"]
    assert manifest  # contenu inspecté dans la revue


def test_archives_prouvent_la_classification_sfdr_lisible(brut):
    """Pour chaque entrée sfdr « fiche_produit_archivee », la valeur saisie est lisible dans l'archive brute."""
    lisible = {
        "article_6": "article 6",
        "article_8": "article 8",
        "non_applicable": "not applicable",
    }
    n = 0
    for tk, bloc in brut["etfs"].items():
        for e in bloc["entries"]:
            if (
                e["champ"] != "sfdr"
                or (e.get("source") or {}).get("type_document") != "fiche_produit_archivee"
            ):
                continue
            data = json.loads(
                (CONFIG_DIR / e["source"]["archive"]["chemin"]).read_text(encoding="utf-8")
            )
            txt = json.dumps(data, ensure_ascii=False).lower()
            assert "fund_sfdr_classification" in txt, tk
            assert lisible[e["valeur"]] in txt, (tk, e["valeur"])
            assert bloc["isin"].lower() in txt, tk
            n += 1
    assert n == 11  # 10 article 6 + GOLD.PA non applicable


# --------------------------------------------------------------------------- rapport : limites au-dessus de la matrice
def test_rapport_limites_au_dessus_de_la_matrice(monkeypatch):
    from amundi_agentic.data.coverage import Report

    r = Report.__new__(Report)
    r.data = {}
    _, note = r._etf_sources_view()
    for phrase in ("aucun backtest ne voit l'ESG des ETF", "seuils de revenus", "critères MSCI", "n'implique pas",
                   "score ESG", "titres détenus d'un fonds à swap"):  # fmt: skip
        assert phrase in note, phrase
    src = inspect.getsource(Report.esg)
    assert src.index("s += etf_note") < src.index("s += md_table(lignes)")
