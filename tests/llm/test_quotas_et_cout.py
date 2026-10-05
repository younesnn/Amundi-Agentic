"""Journal des quotas, alerte avant la limite, suivi des jetons et du coût (EX-NF-03)."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from amundi_agentic.llm import load_config
from amundi_agentic.llm.quotas import QuotaJournal
from amundi_agentic.llm.types import RawCompletion

MSG = [{"role": "user", "content": "Bonjour"}]


def jour(n):
    return date(2024, 2, 1) + timedelta(days=n)


def test_limites_non_relevees_valent_null_dans_la_config(cfg):
    """Les limites sont relevées par un autre agent : jamais inventées ici."""
    for limites in cfg.quotas.limits.values():
        assert limites.requests_per_day is None
        assert limites.requests_per_minute is None
        assert limites.tokens_per_minute is None
    assert cfg.quotas.alert_threshold == 0.8


def test_alerte_a_80_pourcent_du_quota(fabrique, cfg):
    fournisseur = cfg.models["main"].split("/")[0]
    config = load_config(overrides={"quotas": {"limits": {fournisseur: {"requests_per_day": 10}}}})
    c = fabrique(config=config)
    for n in range(7):
        c.complete(MSG, date_donnees=jour(n))
    assert c.quotas.alertes == []
    c.complete(MSG, date_donnees=jour(7))  # 8e requête = 80 % de 10
    assert len(c.quotas.alertes) == 1 and "8/10" in c.quotas.alertes[0]
    c.complete(MSG, date_donnees=jour(8))
    assert len(c.quotas.alertes) == 1  # une seule alerte par jour et par fournisseur


def test_alerte_journalisee_dans_le_log(fabrique, cfg, caplog):
    fournisseur = cfg.models["main"].split("/")[0]
    config = load_config(overrides={"quotas": {"limits": {fournisseur: {"requests_per_day": 2}}}})
    c = fabrique(config=config)
    with caplog.at_level("WARNING"):
        c.complete(MSG, date_donnees=jour(0))
        c.complete(MSG, date_donnees=jour(1))
    assert any("quota journalier" in m for m in caplog.messages)


def test_sans_limite_relevee_le_journal_compte_sans_alerter(fabrique, cfg):
    c = fabrique()
    for n in range(3):
        c.complete(MSG, date_donnees=jour(n))
    assert c.quotas.alertes == []
    assert c.quotas.usage(cfg.models["main"].split("/")[0])["requests"] == 3


def test_requetes_servies_par_le_cache_ne_comptent_pas(fabrique, cfg):
    c = fabrique()
    c.complete(MSG, date_donnees=jour(0))
    c.complete(MSG, date_donnees=jour(0))
    assert c.quotas.usage(cfg.models["main"].split("/")[0])["requests"] == 1


def test_journal_par_fournisseur_et_par_jour_persistant(fabrique, cfg, tmp_path):
    fournisseur = cfg.models["main"].split("/")[0]
    clock = lambda: datetime(2024, 2, 1, 10, 0, tzinfo=UTC)  # noqa: E731
    c = fabrique(clock=clock)
    c.complete(MSG, date_donnees=jour(0))
    data = json.loads((tmp_path / "quotas.json").read_text())
    assert data["2024-02-01"][fournisseur]["requests"] == 1
    assert data["2024-02-01"][fournisseur]["tokens_in"] > 0
    # Nouveau processus, même journal : le compteur continue.
    c2 = fabrique(clock=clock)
    c2.complete(MSG, date_donnees=jour(1))
    assert c2.quotas.usage(fournisseur, date(2024, 2, 1))["requests"] == 2
    # Le jour suivant repart de zéro.
    c3 = fabrique(clock=lambda: datetime(2024, 2, 2, 10, 0, tzinfo=UTC))
    c3.complete(MSG, date_donnees=jour(2))
    assert c3.quotas.usage(fournisseur, date(2024, 2, 2))["requests"] == 1


def test_429_comptes_dans_le_journal(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", model=cfg.models["main"])
    c.complete(MSG, date_donnees=jour(0))
    assert c.quotas.usage(cfg.models["main"].split("/")[0])["errors_429"] == 1


def test_limite_par_minute_fait_attendre(cfg, tmp_path):
    config = load_config(
        overrides={
            "quotas": {"limits": {cfg.models["main"].split("/")[0]: {"requests_per_minute": 2}}}
        }
    )
    t = [0.0]
    attentes = []
    q = QuotaJournal(
        config,
        tmp_path / "q.json",
        sleep=lambda s: (attentes.append(s), t.__setitem__(0, t[0] + s)),
        monotonic=lambda: t[0],
    )
    modele = cfg.models["main"]
    fournisseur = modele.split("/")[0]
    for _ in range(2):
        q.before_call(fournisseur, modele)
        q.record(fournisseur, modele)
    assert attentes == []
    q.before_call(fournisseur, modele)  # troisième dans la minute
    assert attentes == [60]


def test_cout_nul_au_niveau_gratuit_mais_calcul_present(fabrique, cfg):
    c = fabrique()
    r = c.complete(MSG, date_donnees=jour(0))
    assert r.record.cout_eur == 0
    fournisseur = cfg.models["main"].split("/")[0]
    payant = load_config(
        overrides={
            "pricing": {fournisseur: {"input_eur_per_mtok": 1.0, "output_eur_per_mtok": 2.0}}
        }
    )
    c2 = fabrique(config=payant)
    c2.mock.push(RawCompletion("ok", "m", 1_000_000, 500_000))
    r2 = c2.complete(MSG, date_donnees=jour(1))
    assert r2.record.cout_eur == pytest.approx(1.0 + 1.0)


def test_suivi_des_jetons_par_execution(fabrique):
    c = fabrique()
    c.complete(MSG, date_donnees=jour(0))
    c.complete(MSG, date_donnees=jour(1))
    u = c.usage()
    assert u["appels"] == 2 and u["tokens_entree"] > 0 and u["tokens_sortie"] > 0
    assert u["cout_eur"] == 0
