"""Revue indépendante : limites de quota et dates de fin d'entraînement de `config/llm.yaml`
(D-052), testées avec la configuration RÉELLE, de bout en bout."""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from amundi_agentic.llm import ConfigurationError, MockLLMClient, load_config
from amundi_agentic.llm.config import CONFIG_PATH
from amundi_agentic.llm.quotas import QuotaJournal

GROQ = "groq/openai/gpt-oss-120b"
T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "Bonjour"}]


class Horloge:
    def __init__(self):
        self.t = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

    def __call__(self):
        return self.t


# --------------------------------------------------------------------------- limites réelles


def test_les_limites_du_relais_prennent_le_pas_sur_celles_du_fournisseur(cfg):
    lim = cfg.limits_for("groq", GROQ)
    assert (lim.requests_per_minute, lim.requests_per_day, lim.tokens_per_minute) == (
        30,
        1000,
        8000,
    )
    # un autre modèle du même fournisseur retombe sur la limite du fournisseur (null)
    autre = cfg.limits_for("groq", "groq/un-autre-modele")
    assert (autre.requests_per_day, autre.requests_per_minute, autre.tokens_per_minute) == (
        None,
    ) * 3
    # Gemini et Ollama : aucune limite inventée
    for modele in (cfg.models["main"], cfg.models["light"], cfg.models["dev"]):
        fournisseur = modele.split("/", 1)[0]
        lim = cfg.limits_for(fournisseur, modele)
        assert (lim.requests_per_day, lim.requests_per_minute, lim.tokens_per_minute) == (None,) * 3


def test_alerte_a_80_pourcent_de_1000_requetes_avec_la_limite_reelle(cfg, tmp_path):
    h = Horloge()
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=h)
    alertes = []
    for i in range(1, 1001):
        a = j.record("groq", GROQ)
        if a:
            alertes.append((i, a))
    assert [i for i, _ in alertes] == [800]  # 80 % de 1 000, une seule fois dans la journée
    assert GROQ in alertes[0][1] and "800/1000" in alertes[0][1]
    assert j.usage("groq")["requests"] == 1000


def test_les_autres_modeles_groq_sans_limite_ne_declenchent_aucune_alerte(cfg, tmp_path):
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge())
    for _ in range(900):
        assert j.record("groq", "groq/un-autre-modele") is None
    assert j.alertes == []


def test_l_alerte_compte_les_requetes_du_modele_pas_celles_du_fournisseur(cfg, tmp_path):
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge())
    for _ in range(
        790
    ):  # requêtes d'un autre modèle Groq : ne comptent pas pour la limite du relais
        j.record("groq", "groq/un-autre-modele")
    assert all(j.record("groq", GROQ) is None for _ in range(799))
    assert j.record("groq", GROQ) is not None  # 800e requête du modèle limité


def test_attente_proactive_a_30_requetes_par_minute(cfg, tmp_path):
    t = {"now": 1000.0}
    attentes = []

    def dormir(s):
        attentes.append(s)
        t["now"] += s

    j = QuotaJournal(
        cfg, tmp_path / "q.json", clock=Horloge(), sleep=dormir, monotonic=lambda: t["now"]
    )
    for _ in range(30):
        j.before_call("groq", GROQ)
        j.record("groq", GROQ)
        t["now"] += 1
    assert attentes == []  # 30 requêtes en 30 s : la 30e est la dernière admise
    j.before_call("groq", GROQ)  # 31e dans la minute
    assert len(attentes) == 1 and 29 <= attentes[0] <= 31  # attend la fin de la minute de la 1re
    # un autre modèle du même fournisseur n'est pas ralenti (limite null)
    j.before_call("groq", "groq/un-autre-modele")
    assert len(attentes) == 1


def test_attente_proactive_a_8000_jetons_par_minute(cfg, tmp_path):
    t = {"now": 0.0}
    attentes = []
    j = QuotaJournal(
        cfg,
        tmp_path / "q.json",
        clock=Horloge(),
        sleep=lambda s: (attentes.append(s), t.__setitem__("now", t["now"] + s)),
        monotonic=lambda: t["now"],
    )
    j.record("groq", GROQ, tokens_in=7000, tokens_out=999)  # 7 999 < 8 000
    j.before_call("groq", GROQ)
    assert attentes == []
    j.record("groq", GROQ, tokens_in=1)  # 8 000 atteints
    j.before_call("groq", GROQ)
    assert len(attentes) == 1 and attentes[0] > 0


def test_relais_groq_de_bout_en_bout_declenche_l_alerte_de_la_config_reelle(fabrique, cfg):
    """Client complet, relais 429 -> Groq, avec la config réelle : les requêtes relayées sont
    comptées sur le modèle de relais (alerte à 80 %), pas sur Gemini (limite null)."""
    c = fabrique(mode="interactif")
    for i in range(800):
        c.mock.fail("quota", 1, model=cfg.models["main"])
        c.complete([{"role": "user", "content": f"q{i}"}], date_donnees=T)
    assert len(c.quotas.alertes) == 1 and GROQ in c.quotas.alertes[0]
    assert c.quotas.usage("groq")["requests"] == 800


@pytest.mark.parametrize("champ", ["requests_per_day", "requests_per_minute", "tokens_per_minute"])
@pytest.mark.parametrize("valeur", ["abc", "", -1, 0, -1000, [], {}, 1.5, "1e3"])
def test_valeur_de_limite_non_numerique_ou_negative_refusee(cfg, champ, valeur):
    bloc = {"requests_per_day": 10, "requests_per_minute": 1, "tokens_per_minute": 1, champ: valeur}
    with pytest.raises(ConfigurationError):
        load_config(overrides={"quotas": {"limits": {GROQ: bloc}}})


@pytest.mark.parametrize("champ", ["requests_per_day", "requests_per_minute", "tokens_per_minute"])
def test_valeurs_de_limite_valides_acceptees(cfg, champ):
    for valeur in (None, 1, 30, 10**9):
        c = load_config(
            overrides={"quotas": {"limits": {GROQ: {champ: valeur}}}}  # les autres champs : null
        )
        assert getattr(c.limits_for("groq", GROQ), champ) == valeur


def test_champ_de_limite_inconnu_refuse():
    with pytest.raises(ConfigurationError):
        load_config(overrides={"quotas": {"limits": {GROQ: {"requests_per_hour": 5}}}})


@pytest.mark.xfail(
    strict=True,
    reason="DEFAUT MINEUR : `requests_per_day: true` est accepté et vaut 1 (booléen converti en "
    "entier par Pydantic) ; un booléen n'est pas une limite numérique (config.py, LimitCfg)",
)
def test_limite_booleenne_refusee():
    with pytest.raises(ConfigurationError):
        load_config(overrides={"quotas": {"limits": {GROQ: {"requests_per_day": True}}}})


# --------------------------------------------------------------------------- fin d'entraînement


def _brut():
    return yaml.safe_load(Path(CONFIG_PATH).read_text(encoding="utf-8"))["training_cutoff"]


def test_training_cutoff_ne_contient_que_des_dates_aaaa_mm_jj_valides():
    brut = _brut()
    assert brut, "training_cutoff vide : les dates de fin d'entraînement ne sont pas relevées"
    for cle, valeur in brut.items():
        if isinstance(valeur, date) and not isinstance(valeur, datetime):
            continue  # YAML non guillemeté : date ISO déjà valide
        assert isinstance(valeur, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valeur), (cle, valeur)
        datetime.strptime(valeur, "%Y-%m-%d")  # lève ValueError si le jour n'existe pas
    for cle, valeur in load_config().training_cutoff.items():
        assert isinstance(valeur, date) and not isinstance(valeur, datetime), cle


def test_training_cutoff_cles_connues_de_models_ou_de_evaluation_models(cfg):
    connus = {
        ident.split("/", 1)[1] for ident in [*cfg.models.values(), *cfg.evaluation.models.values()]
    }
    inconnues = sorted(set(cfg.training_cutoff) - connus)
    assert not inconnues, (
        f"clés sans modèle correspondant (sans préfixe de fournisseur) : {inconnues}"
    )


def test_training_cutoff_couvre_les_modeles_figes_et_de_relais(cfg):
    for ident in [*cfg.evaluation.models.values(), cfg.models["fallback"], cfg.models["dev"]]:
        assert ident.split("/", 1)[1] in cfg.training_cutoff, (
            f"fin d'entraînement absente : {ident}"
        )


def test_aucune_date_de_fin_d_entrainement_posterieure_a_aujourd_hui(cfg):
    aujourdhui = datetime.now(UTC).date()
    futures = {k: d for k, d in cfg.training_cutoff.items() if d > aujourdhui}
    assert not futures, futures
    assert all(d > date(2000, 1, 1) for d in cfg.training_cutoff.values())


def test_training_cutoff_refuse_les_dates_invalides(cfg):
    for mauvaise in ("2026-02-30", "31/03/2026", "mars 2026", "", 20260331, "2026-13-01"):
        with pytest.raises(ConfigurationError):
            load_config(overrides={"training_cutoff": {"gemini-3.8-flash": mauvaise}})


def test_run_fields_renseigne_fin_entrainement_pour_les_niveaux_figes_avec_la_config_reelle(
    fabrique, cfg
):
    ev = fabrique(mode="evaluation")
    for niveau in ("main", "light"):
        ev.complete(MSG, date_donnees=T, tier=niveau)
    champs = ev.run_fields()
    for niveau in ("main", "light"):
        servi = champs["modele_servi_fige"][niveau]
        assert servi in cfg.training_cutoff, "précondition : le modèle figé a une date relevée"
        assert champs["fin_entrainement"][niveau] == cfg.training_cutoff[servi]
        assert champs["fin_entrainement"][niveau] is not None
    # l'enregistrement d'appel porte la même date
    derniers = {r.tier: r for r in ev.records if not r.erreur}
    assert (
        derniers["main"].fin_entrainement_modele
        == cfg.training_cutoff[champs["modele_servi_fige"]["main"]]
    )


def test_run_fields_fin_entrainement_none_pour_un_modele_sans_date(fabrique, cfg):
    ev = fabrique(mode="evaluation")
    ev.embed(["a"], date_donnees=T)
    champs = ev.run_fields()
    assert champs["fin_entrainement"] == {"embed": None}  # clé présente, valeur non inventée


def test_run_fields_interactif_pas_de_fin_entrainement_de_niveau_fige(fabrique):
    c = fabrique(mode="interactif")
    c.complete(MSG, date_donnees=T)
    assert c.run_fields()["fin_entrainement"] == {}


def test_la_date_du_modele_servi_figure_dans_l_enregistrement_du_relais(fabrique, cfg):
    c = fabrique(mode="interactif")
    c.mock.fail("quota", 1, model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T)
    assert r.record.modele_servi == GROQ.split("/", 1)[1]
    assert r.record.fin_entrainement_modele == cfg.training_cutoff["openai/gpt-oss-120b"]
    assert r.record.fin_entrainement_modele == date(2024, 6, 30)


def test_fin_entrainement_dev(fabrique, cfg):
    c = fabrique(profile="dev")
    r = c.complete(MSG, date_donnees=T)
    assert r.record.fin_entrainement_modele == cfg.training_cutoff["llama3.1:8b"]


def test_config_reelle_se_charge_et_garde_le_hash_de_la_source(cfg):
    assert re.fullmatch(r"[0-9a-f]{64}", cfg.source_sha256)
    assert MockLLMClient  # garde l'import utilisé
    assert timedelta(0) == timedelta()
