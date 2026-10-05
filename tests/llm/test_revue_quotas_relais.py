"""Revue indépendante : quotas (journal, minuit UTC, alerte, concurrence), relais et sorties
structurées. Verrou, alerte par modèle, concurrence inter-processus."""

import json
import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import BaseModel

from amundi_agentic.llm import (
    MockLLMClient,
    ProviderError,
    QuotaEpuise,
    StructuredOutputError,
    load_config,
)
from amundi_agentic.llm.quotas import QuotaJournal
from amundi_agentic.llm.types import RawCompletion

T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "Bonjour"}]


def msg(i):
    return [{"role": "user", "content": f"q{i}"}]


def cfg_limites(cfg, **limits):
    return load_config(overrides={"quotas": {**cfg.quotas.model_dump(), "limits": limits}})


class Horloge:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


# --------------------------------------------------------------------------- quotas


def test_remise_a_zero_a_minuit_utc(cfg, tmp_path):
    h = Horloge(datetime(2024, 2, 1, 23, 59, 59, tzinfo=UTC))
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=h)
    j.record("gemini", "gemini/x")
    h.t = datetime(2024, 2, 2, 0, 0, 0, tzinfo=UTC)
    j.record("gemini", "gemini/x")
    assert j.usage("gemini", date(2024, 2, 1))["requests"] == 1
    assert j.usage("gemini", date(2024, 2, 2))["requests"] == 1
    assert j.usage("gemini")["requests"] == 1  # « aujourd'hui » = le 2


def test_jour_calcule_en_utc_meme_avec_horloge_dans_un_autre_fuseau(cfg, tmp_path):
    from zoneinfo import ZoneInfo

    h = Horloge(datetime(2024, 2, 2, 0, 30, tzinfo=ZoneInfo("Europe/Paris")))  # 23:30 UTC le 1er
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=h)
    j.record("gemini", "gemini/x")
    assert j.usage("gemini", date(2024, 2, 1))["requests"] == 1


def test_alerte_unique_a_80_pourcent_puis_silence(cfg, tmp_path):
    c2 = cfg_limites(cfg, gemini={"requests_per_day": 10})
    j = QuotaJournal(c2, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    alertes = [j.record("gemini", "gemini/x") for _ in range(12)]
    assert [i for i, a in enumerate(alertes) if a] == [7]  # 8e requête = 80 %
    assert len(j.alertes) == 1


def test_alerte_se_reinitialise_le_lendemain(cfg, tmp_path):
    c2 = cfg_limites(cfg, gemini={"requests_per_day": 5})
    h = Horloge(datetime(2024, 2, 1, tzinfo=UTC))
    j = QuotaJournal(c2, tmp_path / "q.json", clock=h)
    for _ in range(5):
        j.record("gemini", "gemini/x")
    h.t += timedelta(days=1)
    assert [bool(j.record("gemini", "gemini/x")) for _ in range(5)].count(True) == 1


def test_limites_null_aucune_alerte_aucune_attente(cfg, tmp_path):
    attentes = []
    j = QuotaJournal(cfg, tmp_path / "q.json", sleep=attentes.append)
    for _ in range(50):
        j.before_call("gemini", "gemini/x")
        assert j.record("gemini", "gemini/x", tokens_in=10**6) is None
    assert attentes == [] and j.alertes == []


def test_journal_par_fournisseur_et_par_modele(cfg, tmp_path):
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    j.record("gemini", "gemini/a", tokens_in=3, tokens_out=4)
    j.record("gemini", "gemini/b", tokens_in=1, error_429=True)
    data = json.loads((tmp_path / "q.json").read_text())["2024-02-01"]
    assert data["gemini"]["requests"] == 2 and data["gemini"]["errors_429"] == 1
    assert data["gemini/a"]["tokens_in"] == 3 and data["gemini/b"]["requests"] == 1


def test_journal_corrompu_repart_de_zero_sans_planter(cfg, tmp_path):
    (tmp_path / "q.json").write_text("{pas du json")
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    j.record("gemini", "gemini/a")
    assert j.usage("gemini")["requests"] == 1


def test_limite_par_minute_attente_proactive_puis_reprise(cfg, tmp_path):
    c2 = cfg_limites(cfg, gemini={"requests_per_minute": 2})
    t = {"now": 1000.0}
    attentes = []

    def dormir(s):
        attentes.append(s)
        t["now"] += s

    j = QuotaJournal(c2, tmp_path / "q.json", sleep=dormir, monotonic=lambda: t["now"])
    for _ in range(2):
        j.before_call("gemini", "gemini/x")
        j.record("gemini", "gemini/x")
        t["now"] += 1
    j.before_call("gemini", "gemini/x")
    assert attentes and 57 <= attentes[0] <= 60
    assert len(attentes) == 1


def test_limite_de_jetons_par_minute(cfg, tmp_path):
    c2 = cfg_limites(cfg, gemini={"tokens_per_minute": 100})
    t = {"now": 0.0}
    attentes = []
    j = QuotaJournal(
        c2, tmp_path / "q.json",
        sleep=lambda s: (attentes.append(s), t.__setitem__("now", t["now"] + s)),
        monotonic=lambda: t["now"],
    )  # fmt: skip
    j.record("gemini", "gemini/x", tokens_in=150)
    j.before_call("gemini", "gemini/x")
    assert attentes


def test_une_limite_de_modele_l_emporte_sur_celle_du_fournisseur(cfg):
    c2 = cfg_limites(cfg, gemini={"requests_per_day": 100}, **{"gemini/x": {"requests_per_day": 5}})
    assert c2.limits_for("gemini", "gemini/x").requests_per_day == 5
    assert c2.limits_for("gemini", "gemini/y").requests_per_day == 100


def test_alerte_par_modele_compte_les_requetes_du_modele(cfg, tmp_path):
    c2 = cfg_limites(cfg, **{"gemini/x": {"requests_per_day": 10}})
    j = QuotaJournal(c2, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    for _ in range(5):  # 5 requêtes sur un AUTRE modèle du même fournisseur (sans limite propre)
        j.record("gemini", "gemini/y")
    for _ in range(3):  # 3 requêtes seulement sur le modèle limité à 10 : 30 %
        j.record("gemini", "gemini/x")
    assert j.alertes == []


def test_deux_journaux_sur_le_meme_fichier_ne_perdent_aucun_compte(cfg, tmp_path):
    h = Horloge(datetime(2024, 2, 1, tzinfo=UTC))
    chemin = tmp_path / "q.json"
    a, b = QuotaJournal(cfg, chemin, clock=h), QuotaJournal(cfg, chemin, clock=h)
    lire_a = a._lire
    etat = {"fait": False}

    def lire_puis_laisser_b_passer():
        data = lire_a()
        if not etat["fait"]:
            etat["fait"] = True
            b.record("gemini", "gemini/x")  # b écrit entre la lecture et l'écriture de a
        return data

    a._lire = lire_puis_laisser_b_passer
    a.record("gemini", "gemini/x")
    assert b.usage("gemini")["requests"] == 2


def test_un_seul_client_multithread_ne_perd_aucun_compte(cfg, tmp_path):
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    ths = [
        threading.Thread(target=lambda: [j.record("gemini", "gemini/x") for _ in range(100)])
        for _ in range(4)
    ]
    for t in ths:
        t.daemon = True
    [t.start() for t in ths]
    [t.join(60) for t in ths]
    assert not any(t.is_alive() for t in ths), "thread bloqué sur le journal"
    assert j.usage("gemini")["requests"] == 400


def test_pas_de_fichier_temporaire_residuel(cfg, tmp_path):
    j = QuotaJournal(cfg, tmp_path / "q.json")
    for _ in range(5):
        j.record("gemini", "gemini/x")
    assert [p.name for p in tmp_path.iterdir()] == ["q.json"]


def test_horloge_injectee_date_les_enregistrements(fabrique):
    h = Horloge(datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC))
    c = fabrique(clock=h)
    assert c.complete(MSG, date_donnees=T).record.horodatage == h.t


# --------------------------------------------------------------------------- relais


def test_relais_jamais_en_profil_dev_meme_sur_429(fabrique, cfg):
    c = fabrique(profile="dev")
    c.mock.fail("quota", 1)
    with pytest.raises(QuotaEpuise):
        c.complete(MSG, date_donnees=T)
    assert {a["model"] for a in c.mock.chat_calls} == {cfg.models["dev"]}


def test_chaine_complete_429_partout_pas_de_boucle(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", 10, model=cfg.models["main"])
    c.mock.fail("quota", 10, model=cfg.models["fallback"])
    with pytest.raises(QuotaEpuise):
        c.complete(MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == 2  # un essai par modèle, pas de boucle


def test_chaine_light_main_fallback_ordre_et_pas_de_boucle(fabrique, cfg):
    c = fabrique()
    for m in cfg.fallback_order["light"]:
        c.mock.fail("quota", 5, model=cfg.models[m])
    with pytest.raises(QuotaEpuise):
        c.complete(MSG, date_donnees=T, tier="light")
    assert [a["model"] for a in c.mock.chat_calls] == [
        cfg.models[m] for m in cfg.fallback_order["light"]
    ]


def test_embed_jamais_relaye_et_n_appelle_aucun_modele_de_chat(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", 3)
    with pytest.raises(QuotaEpuise):
        c.embed(["a"], date_donnees=T)
    assert {a["model"] for a in c.mock.calls} == {cfg.embeddings["prod"]}


def test_relais_enregistre_tier_modele_et_drapeau(fabrique, cfg):
    c = fabrique()
    c.mock.fail("quota", 1, model=cfg.models["main"])
    r = c.complete(MSG, date_donnees=T)
    assert r.record.relais_utilise and r.record.tier == "fallback"
    assert r.record.fournisseur == cfg.models["fallback"].split("/", 1)[0]
    erreurs = [x for x in c.records if x.erreur]
    assert len(erreurs) == 1 and erreurs[0].relais_utilise is False


def test_refroidissement_expire_apres_cooldown(cfg, tmp_path):
    t = {"now": 0.0}
    c = MockLLMClient(
        cfg, mode="interactif", profile="prod", cache_dir=tmp_path / "c",
        quota_journal=tmp_path / "q.json", monotonic=lambda: t["now"],
    )  # fmt: skip
    c.mock.fail("quota", 1, model=cfg.models["main"])
    c.complete(msg(1), date_donnees=T)
    c.complete(msg(2), date_donnees=T)  # main évité (refroidissement)
    assert [a["model"] for a in c.mock.chat_calls][1:] == [cfg.models["fallback"]] * 2
    t["now"] = cfg.relay.cooldown_s + 1
    c.complete(msg(3), date_donnees=T)
    assert c.mock.chat_calls[-1]["model"] == cfg.models["main"]


def test_503_epuise_sur_le_dernier_modele_leve_l_erreur_du_fournisseur(fabrique, cfg):
    c = fabrique()
    c.mock.fail("unavailable", 20)
    with pytest.raises(ProviderError) as e:
        c.complete(MSG, date_donnees=T)
    assert e.value.kind == "unavailable"
    assert len(c.mock.chat_calls) == 2 * cfg.retry.max_attempts


def test_relais_desactive_par_config_sur_503(cfg, tmp_path):
    c2 = load_config(overrides={"relay": {"cooldown_s": 60, "on_unavailable_exhausted": False}})
    c = MockLLMClient(c2, profile="prod", cache_dir=tmp_path / "c", quota_journal=tmp_path / "q")
    c.mock.fail("unavailable", 20, model=c2.models["main"])
    with pytest.raises(ProviderError):
        c.complete(MSG, date_donnees=T)
    assert {a["model"] for a in c.mock.chat_calls} == {c2.models["main"]}


# --------------------------------------------------------------------------- sorties structurées


class Rep(BaseModel):
    x: int


def test_json_valide_mais_hors_schema_rejete_jamais_en_cache(fabrique, cfg):
    c = fabrique()
    c.mock.push('{"y": 1}', '{"x": "pas un entier"}', '{"x": 1.5}')
    with pytest.raises(StructuredOutputError) as e:
        c.complete_structured(Rep, MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == cfg.defaults.structured_retries + 1
    assert e.value.last_text == '{"x": 1.5}' and "Rep" in str(e.value)
    assert not list(c.cache.directory.rglob("*.json"))


def test_tentatives_bornees_meme_avec_un_modele_qui_ne_corrige_jamais(fabrique, cfg):
    c = fabrique(handler=lambda m, ms: "n'importe quoi")
    with pytest.raises(StructuredOutputError):
        c.complete_structured(Rep, MSG, date_donnees=T)
    assert len(c.mock.chat_calls) == cfg.defaults.structured_retries + 1


def test_texte_entoure_de_balises_ou_de_prose(fabrique):
    c = fabrique()
    c.mock.push('Voici :\n```json\n{"x": 3}\n```\nVoilà.')
    assert c.complete_structured(Rep, MSG, date_donnees=T).parsed.x == 3
    c.mock.push('<json>{"x": 4}</json>')
    assert c.complete_structured(Rep, msg(2), date_donnees=T).parsed.x == 4
    c.mock.push('{"x": 5} {"x": 6}')  # deux objets : ambigu, doit être rejeté ou lu proprement
    try:
        r = c.complete_structured(Rep, msg(3), date_donnees=T)
        assert r.parsed.x in (5, 6)
    except StructuredOutputError:
        pass


def test_sortie_invalide_puis_valide_met_en_cache_la_valide_seulement(fabrique):
    c = fabrique()
    c.mock.push("pas du json", '{"x": 7}')
    r = c.complete_structured(Rep, MSG, date_donnees=T)
    assert r.parsed.x == 7 and len(r.attempts) == 1
    entrees = [json.loads(p.read_text()) for p in c.cache.directory.rglob("*.json")]
    assert [e["text"] for e in entrees] == ['{"x": 7}']
    again = c.complete_structured(Rep, MSG, date_donnees=T)
    assert again.record.cache_hit and len(c.mock.chat_calls) == 2


def test_entree_de_cache_devenue_invalide_pour_le_schema_est_rappelee(fabrique):
    c = fabrique()
    c.complete(MSG, date_donnees=T)  # met "{}" en cache pour la requête SANS schéma
    c.mock.push('{"x": 1}')
    assert c.complete_structured(Rep, MSG, date_donnees=T).parsed.x == 1


def test_les_nouvelles_tentatives_invalides_ne_comptent_pas_comme_cache(fabrique):
    c = fabrique()
    c.mock.push("zzz", '{"x": 1}')
    c.complete_structured(Rep, MSG, date_donnees=T)
    assert c.usage()["appels"] == 2 and c.usage()["cache_hits"] == 0


def test_sortie_structuree_valide_en_evaluation_gele_le_modele_meme_si_invalide(fabrique, cfg):
    ev = fabrique(mode="evaluation")
    ev.mock.push(RawCompletion("pas du json", "v1"), RawCompletion('{"x": 1}', "v1"))
    ev.complete_structured(Rep, MSG, date_donnees=T)
    assert ev.modeles_servis_figes == {"main": "v1"}


# --------------------------------------------------------------------------- verrou inter-processus


def test_le_verrou_flock_est_pris_a_chaque_ecriture(cfg, tmp_path, monkeypatch):
    from amundi_agentic.llm import quotas

    if quotas.fcntl is None:
        pytest.skip("fcntl indisponible")
    appels = []
    vrai = quotas.fcntl.flock
    monkeypatch.setattr(quotas.fcntl, "flock", lambda fd, op: (appels.append(op), vrai(fd, op))[1])
    j = QuotaJournal(cfg, tmp_path / "q.json")
    for _ in range(3):
        j.record("gemini", "gemini/x")
    assert appels.count(quotas.fcntl.LOCK_EX) >= 3


def test_le_verrou_est_libere_apres_une_erreur_d_ecriture(cfg, tmp_path, monkeypatch):
    j = QuotaJournal(cfg, tmp_path / "q.json")
    j.record("gemini", "gemini/x")
    vrai = j._ecrire
    monkeypatch.setattr(j, "_ecrire", lambda d: (_ for _ in ()).throw(OSError("disque plein")))
    with pytest.raises(OSError):
        j.record("gemini", "gemini/x")
    monkeypatch.setattr(j, "_ecrire", vrai)
    j2 = QuotaJournal(cfg, tmp_path / "q.json")  # un autre client n'est pas bloqué
    j2.record("gemini", "gemini/x")
    assert j2.usage("gemini")["requests"] == 2


def test_repli_sans_fcntl_avertit_une_seule_fois_et_continue_de_compter(
    cfg, tmp_path, monkeypatch, caplog
):
    import logging

    from amundi_agentic.llm import quotas

    monkeypatch.setattr(quotas, "fcntl", None)
    monkeypatch.setattr(QuotaJournal, "_repli_signale", False)
    a = QuotaJournal(cfg, tmp_path / "q.json", clock=lambda: datetime(2024, 2, 1, tzinfo=UTC))
    b = QuotaJournal(cfg, tmp_path / "q.json", clock=lambda: datetime(2024, 2, 1, tzinfo=UTC))
    with caplog.at_level(logging.WARNING):
        for j in (a, b, a, b):
            j.record("gemini", "gemini/x")
    avertissements = [r for r in caplog.records if "fcntl" in r.getMessage()]
    assert len(avertissements) == 1
    assert a.usage("gemini", date(2024, 2, 1))["requests"] == 4


def test_alerte_par_fournisseur_inchangee_sans_limite_de_modele(cfg, tmp_path):
    c2 = cfg_limites(cfg, gemini={"requests_per_day": 10})
    j = QuotaJournal(c2, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    alertes = [j.record("gemini", f"gemini/m{i % 3}") for i in range(10)]
    assert [i for i, a in enumerate(alertes) if a] == [7]
    assert "gemini" in j.alertes[0]


def test_alerte_par_modele_se_declenche_sur_le_modele_limite(cfg, tmp_path):
    c2 = cfg_limites(cfg, **{"gemini/x": {"requests_per_day": 10}})
    j = QuotaJournal(c2, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    for _ in range(7):
        assert j.record("gemini", "gemini/x") is None
    assert j.record("gemini", "gemini/x") is not None  # 8e requête = 80 % de 10
    assert "gemini/x" in j.alertes[0] and len(j.alertes) == 1


def test_journal_de_forme_inattendue_repart_de_zero(cfg, tmp_path):
    for contenu in ("[1, 2]", "3", "null"):
        (tmp_path / "q.json").write_text(contenu)
        j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
        j.record("gemini", "gemini/a")
        assert j.usage("gemini", date(2024, 2, 1))["requests"] == 1
    (tmp_path / "q.json").write_bytes(b"\xff\xfe")
    j.record("gemini", "gemini/a")


def test_usage_tolere_un_journal_de_forme_inattendue(cfg, tmp_path):
    (tmp_path / "q.json").write_text("[1]")
    assert QuotaJournal(cfg, tmp_path / "q.json").usage("gemini") == {}


@pytest.mark.parametrize(
    "contenu",
    [
        {"2024-02-01": {"gemini": 5}},
        {"2024-02-01": "oups"},
        {"2024-02-01": ["a"]},
        {"2024-02-01": {"gemini": None, "gemini/x": 3}},
        {"2024-01-31": {"gemini": {"requests": 2, "tokens_in": 0, "tokens_out": 0,
                                   "errors_429": 0, "alerts": []}}, "2024-02-01": 7},
    ],
)  # fmt: skip
def test_journal_aux_sous_niveaux_de_forme_inattendue_ne_plante_ni_en_usage_ni_en_record(
    cfg, tmp_path, contenu
):
    (tmp_path / "q.json").write_text(json.dumps(contenu))
    j = QuotaJournal(cfg, tmp_path / "q.json", clock=Horloge(datetime(2024, 2, 1, tzinfo=UTC)))
    assert isinstance(j.usage("gemini"), dict)
    j.record("gemini", "gemini/x")
    assert j.usage("gemini")["requests"] == 1
    if "2024-01-31" in contenu:  # les jours valides sont conservés
        assert j.usage("gemini", date(2024, 1, 31))["requests"] == 2
