"""Revue indépendante : schémas Pydantic, point-in-time aux bords, cohérence avec l'univers."""

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from pydantic import ValidationError

from amundi_agentic.schemas import ACTIFS_SANS_VUE, PARIS, Source, View, coupure

ROOT = Path(__file__).resolve().parents[1]


def source(dt, sid="s1"):
    return Source(
        source_id=sid, type="news", titre="t", reference="r", date_publication=dt, extrait="e"
    )


def vue(t, *sources, **kw):
    base = dict(
        view_id="v", actif="actions_monde", niveau_decision="allocation", date_analyse=t,
        direction="POSITIF", confiance=0.5, arguments_pour=["a"], arguments_contre=["b"],
        sources=list(sources) or [source(datetime(2000, 1, 1, tzinfo=UTC))],
        profil_risque="equilibre", auteur="macro", statut="individuelle", run_id="r",
    )  # fmt: skip
    return View(**{**base, **kw})


def test_actifs_sans_vue_correspond_a_l_identifiant_reel_de_l_univers():
    univers = yaml.safe_load((ROOT / "config" / "universe.yaml").read_text(encoding="utf-8"))
    ids = set(univers["asset_classes"])
    assert ids >= ACTIFS_SANS_VUE, "identifiant codé en dur absent de config/universe.yaml"
    residuels = {
        k for k, v in univers["asset_classes"].items() if "ecb:ESTR" in (v.get("eur_series") or [])
    }
    assert residuels == set(ACTIFS_SANS_VUE)
    for actif in ACTIFS_SANS_VUE:
        with pytest.raises(ValidationError, match="résiduel"):
            vue(date(2024, 2, 1), actif=actif)
    for actif in ids - set(ACTIFS_SANS_VUE):
        vue(date(2024, 2, 1), actif=actif)  # tous les autres actifs de l'univers acceptent une vue


@pytest.mark.parametrize(
    "t,coupure_utc",
    [
        (date(2026, 3, 28), datetime(2026, 3, 27, 23, 0, tzinfo=UTC)),  # CET (UTC+1)
        (date(2026, 3, 29), datetime(2026, 3, 28, 23, 0, tzinfo=UTC)),  # jour du passage, 00:00 CET
        (date(2026, 3, 30), datetime(2026, 3, 29, 22, 0, tzinfo=UTC)),  # CEST (UTC+2)
        (date(2026, 10, 24), datetime(2026, 10, 23, 22, 0, tzinfo=UTC)),  # CEST
        (date(2026, 10, 25), datetime(2026, 10, 24, 22, 0, tzinfo=UTC)),  # jour du passage, CEST
        (date(2026, 10, 26), datetime(2026, 10, 25, 23, 0, tzinfo=UTC)),  # CET
    ],
)
def test_coupure_aux_changements_d_heure(t, coupure_utc):
    assert coupure(t) == coupure_utc
    pile = coupure_utc
    with pytest.raises(ValidationError, match="coupure"):
        vue(t, source(pile))
    vue(t, source(pile - timedelta(microseconds=1)))


def test_source_avec_fuseau_non_utc_comparee_a_l_instant_absolu():
    t = date(2024, 2, 1)  # coupure : 2024-01-31 23:00 UTC
    tokyo = timezone(timedelta(hours=9))
    ny = ZoneInfo("America/New_York")
    # 2024-02-01 07:59 à Tokyo = 2024-01-31 22:59 UTC : avant la coupure
    vue(t, source(datetime(2024, 2, 1, 7, 59, tzinfo=tokyo)))
    # 2024-02-01 08:00 à Tokyo = 23:00 UTC : à la coupure, rejetée
    with pytest.raises(ValidationError):
        vue(t, source(datetime(2024, 2, 1, 8, 0, tzinfo=tokyo)))
    # 31 janvier 18:00 à New York = 23:00 UTC : rejetée
    with pytest.raises(ValidationError):
        vue(t, source(datetime(2024, 1, 31, 18, 0, tzinfo=ny)))
    # 17:59:59.999 à New York : acceptée
    vue(t, source(datetime(2024, 1, 31, 17, 59, 59, 999000, tzinfo=ny)))


def test_source_ramenee_en_utc_et_millisecondes_conservees():
    s = source(datetime(2024, 1, 31, 12, 0, 0, 123000, tzinfo=timezone(timedelta(hours=-5))))
    assert s.date_publication.utcoffset() == timedelta(0)
    assert s.date_publication == datetime(2024, 1, 31, 17, 0, 0, 123000, tzinfo=UTC)


def test_source_datee_du_jour_t_ou_apres_rejetee_et_une_seule_suffit():
    t = date(2024, 2, 1)
    bonne, mauvaise = (
        source(datetime(2024, 1, 1, tzinfo=UTC), "ok"),
        source(datetime(2024, 2, 1, 12, tzinfo=UTC), "futur"),
    )
    with pytest.raises(ValidationError, match="futur"):
        vue(t, bonne, mauvaise)
    with pytest.raises(ValidationError, match="futur"):
        vue(t, mauvaise, bonne)


@pytest.mark.parametrize("brut", ["2024-02-01T10:00:00", "2024-02-01 10:00:00", "20240201"])
def test_date_analyse_avec_heure_en_chaine_non_acceptee_ou_normalisee(brut):
    try:
        v = vue(brut)
    except ValidationError:
        return
    assert v.date_analyse == date(2024, 2, 1)  # si acceptée, jamais de décalage de jour


def test_source_sans_fuseau_et_chaine_naive_rejetees():
    with pytest.raises(ValidationError):
        source(datetime(2024, 1, 1))
    with pytest.raises(ValidationError):
        source("2024-01-01T10:00:00")
    with pytest.raises(ValidationError):
        source("2024-01-01")  # date sans heure ni fuseau


def test_source_en_chaine_iso_avec_fuseau_acceptee():
    s = source("2024-01-31T12:00:00+02:00")
    assert s.date_publication == datetime(2024, 1, 31, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize("c", [-1e-12, 1.0000001, float("nan"), float("inf"), "abc", None])
def test_confiance_hors_intervalle_ou_invalide(c):
    with pytest.raises(ValidationError):
        vue(date(2024, 2, 1), confiance=c)


@pytest.mark.parametrize("r", [1.0000001, -1.5, 2, 5.0, float("nan"), float("inf")])
def test_rendement_hors_garde_fou_d_unite(r):
    with pytest.raises(ValidationError):
        vue(date(2024, 2, 1), rendement_excedentaire_attendu=r)


@pytest.mark.parametrize("r", [None, 0.0, 1.0, -1.0, 0.02, -0.5])
def test_rendement_dans_le_garde_fou(r):
    assert vue(date(2024, 2, 1), rendement_excedentaire_attendu=r)


@pytest.mark.parametrize("d", ["FORTEMENT_POSITIF", "FORTEMENT_NEGATIF"])
def test_contestee_limitee_a_un_et_les_autres_statuts_non(d):
    with pytest.raises(ValidationError, match="±1"):
        vue(date(2024, 2, 1), direction=d, statut="contestee")
    for statut in ("individuelle", "unanime", "consensus", "surcharge_gerant"):
        assert vue(date(2024, 2, 1), direction=d, statut=statut)


def test_direction_numerique_ou_hors_enum_rejetee():
    for d in (2, 1, "TRES_POSITIF", "positif", None):
        with pytest.raises(ValidationError):
            vue(date(2024, 2, 1), direction=d)


def test_champ_supplementaire_rendement_calcule_par_le_llm_non_accepte_hors_schema():
    with pytest.raises(ValidationError):
        vue(date(2024, 2, 1), poids_optimal=0.3)


def test_paris_est_bien_europe_paris():
    assert PARIS.key == "Europe/Paris"
