"""Date « du jour » de la saisie ESG : heure de Paris pour `verify_and_snapshot` ET `write_lock` (D-031, D-048).

Hiver (UTC+1) : 23:30 UTC le 14/01 = 00:30 à Paris le 15/01. Été (UTC+2) : 22:30 UTC le 14/07 = 00:30 le 15/07.
Horloge injectée, aucun réseau."""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from amundi_agentic.data.connectors.esg_etf_sources import (
    CHAMPS,
    RetroactiveModificationError,
    jour_paris,
    parse_sources,
    verify_and_snapshot,
    write_lock,
)
from amundi_agentic.data.store import ParquetStore


def _src() -> dict:
    return {
        "type_document": "prospectus",
        "titre": "Prospectus de test",
        "url": "https://exemple.test/d.pdf",
    }


def _v(champ, valeur, n, saisie, **kw) -> dict:
    e = {
        "id": f"T.PA:{champ}:{n:03d}", "champ": champ, "valeur": valeur, "emetteur": "gestionnaire_fonds",
        "source": _src(), "date_document": "2024-01-10", "date_effet": "2024-01-10", "effet_documente": False,
        "date_consultation": "2024-01-12", "date_saisie": saisie,
    }  # fmt: skip
    e.update(kw)
    return e


def _data(entries: list[dict]) -> dict:
    presents = {e["champ"] for e in entries}
    tous = list(entries) + [
        {"id": f"T.PA:{c}:001", "champ": c, "valeur": "inconnu", "raison": "aucun document", "date_saisie": "2024-01-12"}
        for c in CHAMPS
        if c not in presents
    ]  # fmt: skip
    return {"version": 1, "etfs": {"T.PA": {"isin": "LU1681048804", "entries": tous}}}


def _horloge(iso_utc: str):
    return lambda: datetime.fromisoformat(iso_utc).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("instant_utc", "attendu"),
    [
        ("2026-01-14T22:59:59", date(2026, 1, 14)),  # 23:59:59 Paris (hiver)
        ("2026-01-14T23:00:00", date(2026, 1, 15)),  # minuit Paris
        ("2026-01-14T23:30:00", date(2026, 1, 15)),
        ("2026-07-14T21:59:59", date(2026, 7, 14)),  # 23:59:59 Paris (été)
        ("2026-07-14T22:00:00", date(2026, 7, 15)),  # minuit Paris
        ("2026-07-14T22:30:00", date(2026, 7, 15)),  # 00:30 Paris
        ("2026-07-14T23:30:00", date(2026, 7, 15)),  # 01:30 Paris
    ],
)
def test_jour_paris_autour_de_minuit_hiver_et_ete(instant_utc, attendu):
    assert jour_paris(_horloge(instant_utc)) == attendu


def test_jour_paris_accepte_une_horloge_en_heure_de_paris_et_refuse_le_naif():
    assert jour_paris(
        lambda: datetime(2026, 7, 15, 0, 30, tzinfo=ZoneInfo("Europe/Paris"))
    ) == date(2026, 7, 15)
    with pytest.raises(ValueError, match="fuseau"):
        jour_paris(lambda: datetime(2026, 7, 15, 0, 30))


def _amorce(tmp_path):
    base = _data([_v("sfdr", "article_6", 1, "2024-01-12")])
    lock = tmp_path / "x.lock.json"
    write_lock(parse_sources(base), lock, today=date(2024, 1, 12))
    return base, lock


def _avec(base, saisie):
    d = copy.deepcopy(base)
    d["etfs"]["T.PA"]["entries"].append(
        _v("indice", "X", 2, saisie, date_document="2026-01-01", date_effet="2026-01-01", date_consultation="2026-01-01")
    )  # fmt: skip
    return d


@pytest.mark.parametrize(
    ("instant_utc", "saisie_paris"),
    [
        ("2026-01-14T23:30:00", "2026-01-15"),  # hiver, 00:30 Paris
        ("2026-07-14T22:30:00", "2026-07-15"),  # été, 00:30 Paris
        ("2026-07-14T23:30:00", "2026-07-15"),  # été, 01:30 Paris
    ],
)
def test_les_deux_commandes_acceptent_la_meme_saisie_datee_de_paris(
    tmp_path, instant_utc, saisie_paris
):
    base, lock = _amorce(tmp_path)
    s = parse_sources(_avec(base, saisie_paris))
    horloge = _horloge(instant_utc)
    store = ParquetStore(tmp_path / "store", tmp_path / "snap", clock=horloge)
    assert verify_and_snapshot(s, store, lock_path=lock, clock=horloge) is not None
    write_lock(s, lock, clock=horloge)
    # sans `clock` explicite, `verify_and_snapshot` lit l'horloge du stockage : même verdict
    assert verify_and_snapshot(s, store, lock_path=lock) is not None


def test_saisie_datee_de_l_utc_refusee_quand_paris_a_deja_change_de_jour(tmp_path):
    base, lock = _amorce(tmp_path)
    horloge = _horloge("2026-07-14T22:30:00")  # 14/07 en UTC, 15/07 à Paris
    store = ParquetStore(tmp_path / "store", tmp_path / "snap", clock=horloge)
    s = parse_sources(_avec(base, "2026-07-14"))
    with pytest.raises(RetroactiveModificationError, match="antidatage"):
        verify_and_snapshot(s, store, lock_path=lock, clock=horloge)
    with pytest.raises(RetroactiveModificationError, match="antidatage"):
        write_lock(s, lock, clock=horloge)


def test_saisie_du_lendemain_de_paris_refusee_par_les_deux_commandes(tmp_path):
    base, lock = _amorce(tmp_path)
    horloge = _horloge("2026-01-14T22:59:00")  # 23:59 Paris le 14/01
    store = ParquetStore(tmp_path / "store", tmp_path / "snap", clock=horloge)
    s = parse_sources(_avec(base, "2026-01-15"))
    with pytest.raises(RetroactiveModificationError, match="future"):
        verify_and_snapshot(s, store, lock_path=lock, clock=horloge)
    with pytest.raises(RetroactiveModificationError, match="future"):
        write_lock(s, lock, clock=horloge)


def test_today_explicite_reste_prioritaire(tmp_path):
    base, lock = _amorce(tmp_path)
    horloge = _horloge("2026-01-14T23:30:00")
    store = ParquetStore(tmp_path / "store", tmp_path / "snap", clock=horloge)
    s = parse_sources(_avec(base, "2026-03-01"))
    day = date(2026, 3, 1)
    assert verify_and_snapshot(s, store, lock_path=lock, today=day, clock=horloge) is not None
    write_lock(s, lock, today=day, clock=horloge)
