"""Revue indépendante de la date de Paris (D-031) pour `verify_and_snapshot` et `write_lock` (D-048).

Horloge injectée, aucun réseau. Une entrée nouvelle doit avoir `date_saisie` == jour de Paris de l'horloge."""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from amundi_agentic.data.connectors import esg_etf_sources as mod
from amundi_agentic.data.connectors.esg_etf_sources import (
    CHAMPS,
    RetroactiveModificationError,
    jour_paris,
    parse_sources,
    read_lock,
    verify_and_snapshot,
    write_lock,
)
from amundi_agentic.data.store import ParquetStore


def _entree(champ, valeur, n, saisie, **kw):
    e = {
        "id": f"T.PA:{champ}:{n:03d}", "champ": champ, "valeur": valeur, "emetteur": "gestionnaire_fonds",
        "source": {"type_document": "prospectus", "titre": "t", "url": "https://exemple.test/d.pdf"},
        "date_document": "2024-01-10", "date_effet": "2024-01-10", "effet_documente": False,
        "date_consultation": "2024-01-12", "date_saisie": saisie,
    }  # fmt: skip
    e.update(kw)
    return e


def _donnees(extra=()):
    base = [_entree("sfdr", "article_6", 1, "2024-01-12")]
    inc = [
        {
            "id": f"T.PA:{c}:001",
            "champ": c,
            "valeur": "inconnu",
            "raison": "aucun",
            "date_saisie": "2024-01-12",
        }
        for c in CHAMPS
        if c != "sfdr"
    ]
    return {
        "version": 1,
        "etfs": {"T.PA": {"isin": "LU1681048804", "entries": base + inc + list(extra)}},
    }


def _horloge(iso_utc):
    return lambda: datetime.fromisoformat(iso_utc).replace(tzinfo=UTC)


def _etat_verrouille(tmp_path):
    """Registre et instantané d'un état antérieur (amorçage), puis l'appelant ajoute une entrée nouvelle."""
    s0 = parse_sources(_donnees())
    lock = tmp_path / "t.lock.json"
    store = ParquetStore(
        tmp_path / "store", tmp_path / "snap", clock=_horloge("2024-01-12T10:00:00")
    )
    verify_and_snapshot(s0, store, lock_path=lock)
    write_lock(s0, lock, clock=_horloge("2024-01-12T10:00:00"))
    return lock


def _avec_nouvelle(saisie):
    e = _entree("indice", "Indice N", 2, saisie, date_consultation=saisie)
    return parse_sources(_donnees([e]))


def _essaie(tmp_path, fonction, saisie, instant_utc):
    """Rejoue `fonction` ('verify' ou 'lock') dans un état neuf ; True si acceptée, False si refusée."""
    sous = tmp_path / f"cas{len(list(tmp_path.iterdir()))}"
    sous.mkdir()
    lock = _etat_verrouille(sous)
    s = _avec_nouvelle(saisie)
    h = _horloge(instant_utc)
    try:
        if fonction == "verify":
            store = ParquetStore(sous / "store", sous / "snap", clock=h)
            verify_and_snapshot(s, store, lock_path=lock, clock=h)
        else:
            write_lock(s, lock, clock=h)
    except RetroactiveModificationError as exc:
        assert "entrée nouvelle" in str(exc)
        return False
    return True


# (instant UTC, jour de Paris attendu) : bords de minuit en hiver (UTC+1), en été (UTC+2),
# et les deux dimanches de changement d'heure 2026 (29 mars : début de l'heure d'été ; 25 octobre : fin).
CAS = [
    ("2026-01-14T22:59:59", "2026-01-14"), ("2026-01-14T23:00:00", "2026-01-15"),
    ("2026-07-14T21:59:59", "2026-07-14"), ("2026-07-14T22:00:00", "2026-07-15"),
    ("2026-03-28T22:59:59", "2026-03-28"), ("2026-03-28T23:00:00", "2026-03-29"),
    ("2026-03-29T00:59:59", "2026-03-29"), ("2026-03-29T01:00:00", "2026-03-29"),  # 02:00 -> 03:00 CEST
    ("2026-03-29T21:59:59", "2026-03-29"), ("2026-03-29T22:00:00", "2026-03-30"),
    ("2026-10-24T21:59:59", "2026-10-24"), ("2026-10-24T22:00:00", "2026-10-25"),
    ("2026-10-25T00:59:59", "2026-10-25"), ("2026-10-25T01:00:00", "2026-10-25"),  # 03:00 -> 02:00 CET
    ("2026-10-25T22:59:59", "2026-10-25"), ("2026-10-25T23:00:00", "2026-10-26"),
]  # fmt: skip


@pytest.mark.parametrize(("instant", "paris"), CAS)
def test_jour_paris_bords_de_minuit_et_changements_d_heure(instant, paris):
    assert jour_paris(_horloge(instant)) == date.fromisoformat(paris)
    # indépendant : calcul direct avec zoneinfo
    assert (
        jour_paris(_horloge(instant))
        == _horloge(instant)().astimezone(ZoneInfo("Europe/Paris")).date()
    )


@pytest.mark.parametrize("fonction", ["verify", "lock"])
@pytest.mark.parametrize(("instant", "paris"), CAS)
def test_saisie_du_jour_de_paris_acceptee_veille_lendemain_et_jour_utc_refuses(
    tmp_path, fonction, instant, paris
):
    p = date.fromisoformat(paris)
    utc_jour = _horloge(instant)().date()
    assert _essaie(tmp_path, fonction, p.isoformat(), instant) is True
    assert _essaie(tmp_path, fonction, (p - timedelta(days=1)).isoformat(), instant) is False
    assert _essaie(tmp_path, fonction, (p + timedelta(days=1)).isoformat(), instant) is False
    if utc_jour != p:  # il est déjà demain (ou encore hier) à Paris : la date UTC est refusée
        assert _essaie(tmp_path, fonction, utc_jour.isoformat(), instant) is False


def test_verify_et_write_lock_donnent_le_meme_verdict_partout():
    """Les deux fonctions partagent `jour_paris` : jamais de verdict divergent entre `snapshot` et `lock`."""
    import inspect

    assert "jour_paris" in inspect.getsource(verify_and_snapshot)
    assert "jour_paris" in inspect.getsource(write_lock)


def test_horloge_naive_refusee_par_les_deux_fonctions(tmp_path):
    lock = _etat_verrouille(tmp_path)
    s = _avec_nouvelle("2026-07-15")
    naive = lambda: datetime(2026, 7, 15, 0, 30)  # noqa: E731
    with pytest.raises(ValueError, match="fuseau"):
        write_lock(s, lock, clock=naive)
    store = ParquetStore(
        tmp_path / "store", tmp_path / "snap", clock=_horloge("2026-07-15T10:00:00")
    )
    with pytest.raises(ValueError, match="fuseau"):
        verify_and_snapshot(s, store, lock_path=lock, clock=naive)
    # une horloge de stockage naïve n'est pas devinée non plus quand `clock` n'est pas fourni
    store2 = ParquetStore(tmp_path / "s2", tmp_path / "n2", clock=naive)
    with pytest.raises(ValueError, match="fuseau"):
        verify_and_snapshot(s, store2, lock_path=lock)
    assert set(read_lock(lock)) == {
        e.id for e in parse_sources(_donnees()).all_entries()
    }  # registre intact


def test_horloge_par_defaut_de_write_lock_est_le_jour_de_paris_systeme(tmp_path, monkeypatch):
    """Sans `today` ni `clock` (cas de la commande de production) : jour de Paris de l'instant système."""
    lock = _etat_verrouille(tmp_path)

    class Faux(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                datetime(2026, 7, 14, 22, 30, tzinfo=UTC).astimezone(tz)
                if tz
                else datetime(2026, 7, 14, 22, 30)
            )

    monkeypatch.setattr(mod, "datetime", Faux)
    # 22:30 UTC le 14/07 = 00:30 à Paris le 15/07
    with pytest.raises(RetroactiveModificationError):
        write_lock(_avec_nouvelle("2026-07-14"), lock)  # date UTC : refusée
    write_lock(_avec_nouvelle("2026-07-15"), lock)
    assert "T.PA:indice:002" in read_lock(lock)


def test_instantane_nomme_en_utc_pas_de_defaut_fonctionnel_entre_minuit_et_2h(tmp_path):
    """`ParquetStore.snapshot` date le dossier en UTC : à 00:30 Paris (22:30Z) il porte la date de la veille.
    Conséquence vérifiée : aucune entrée légitime refusée, aucune antidatée acceptée, deux exécutions de la même
    journée de Paris (de part et d'autre de minuit UTC) ne se contredisent pas."""
    lock = _etat_verrouille(tmp_path)
    s = _avec_nouvelle("2026-07-15")
    h1, h2 = (
        _horloge("2026-07-14T22:30:00"),
        _horloge("2026-07-15T00:30:00"),
    )  # 00:30 et 02:30 Paris, le 15/07
    store1 = ParquetStore(tmp_path / "store", tmp_path / "snap", clock=h1)
    p1 = verify_and_snapshot(s, store1, lock_path=lock, clock=h1)
    store2 = ParquetStore(tmp_path / "store", tmp_path / "snap", clock=h2)
    p2 = verify_and_snapshot(
        s, store2, lock_path=lock, clock=h2
    )  # même journée de Paris : pas de refus
    assert (
        p1.parent.name == "2026-07-14" and p2.parent.name == "2026-07-15"
    )  # deux dossiers pour une journée
    # le contrôle compare tous les instantanés quel que soit le dossier : modification toujours refusée
    modif = copy.deepcopy(
        _donnees([_entree("indice", "Indice N", 2, "2026-07-15", date_consultation="2026-07-15")])
    )
    modif["etfs"]["T.PA"]["entries"][-1]["valeur"] = "Autre"
    with pytest.raises(RetroactiveModificationError):
        verify_and_snapshot(parse_sources(modif), store2, lock_path=lock, clock=h2)
    # une entrée antidatée au jour UTC du dossier n'est pas acceptée pour autant
    antidate = parse_sources(
        _donnees(
            [
                _entree("indice", "Indice N", 2, "2026-07-15", date_consultation="2026-07-15"),
                _entree("exclusions", {"tobacco": "indice"}, 3, "2026-07-14", date_consultation="2026-07-14",
                        extrait="texte"),
            ]
        )
    )  # fmt: skip
    with pytest.raises(RetroactiveModificationError, match="entrée nouvelle"):
        verify_and_snapshot(antidate, store2, lock_path=lock, clock=h2)
