"""Revue indépendante de D-062 (contexte Ollama, détection de troncature, cache versionné, journal).

Tout est simulé (transport espion, mock) : aucun réseau, aucune clé. Les `xfail(strict=True)`
documentent des défauts confirmés ; ils passeront en XPASS quand le défaut sera corrigé."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from types import SimpleNamespace

import pytest
import yaml

from amundi_agentic.llm import (
    PromptTronque,
    ProviderError,
    load_config,
)
from amundi_agentic.llm.cache import CACHE_KEY_VERSION, cache_key
from amundi_agentic.llm.config import CONFIG_PATH, ConfigurationError
from amundi_agentic.llm.transport import LiteLLMTransport
from amundi_agentic.llm.types import RawCompletion
from amundi_agentic.schemas import ExecutionRecord

T = date(2024, 2, 1)
SERVI = "llama3.1:8b"


def _msgs(chars, n=1, role="user"):
    par = chars // n
    return [{"role": role if i else "system", "content": "x" * par} for i in range(n)]


def _appel(client, chars, evalues, n=1, schema=None):
    client.mock.push(RawCompletion("{}" if schema else "ok", SERVI, evalues, 5))
    msgs = _msgs(chars, n)
    if schema:
        return client.complete_structured(schema, msgs, date_donnees=T)
    return client.complete(msgs, date_donnees=T)


def _tronque(client, chars, evalues, n=1):
    try:
        _appel(client, chars, evalues, n)
    except PromptTronque as exc:
        return exc
    return None


def _estimes(chars, cfg):
    return int(chars / cfg.truncation_check.chars_per_token)


# --------------------------------------------------------------------------- 1. détection
@pytest.mark.parametrize("chars", [1_000, 4_400, 4_499])
def test_sous_le_seuil_d_estimation_jamais_de_controle_meme_avec_zero_jeton(fabrique, cfg, chars):
    assert _estimes(chars, cfg) < cfg.truncation_check.min_estimated_tokens
    assert _tronque(fabrique(profile="dev"), chars, 0) is None


@pytest.mark.parametrize("chars", [4_500, 10_000, 20_000, 40_000])
def test_limite_exacte_du_ratio_a_toutes_les_tailles(fabrique, cfg, chars):
    est = _estimes(chars, cfg)
    seuil = cfg.truncation_check.min_ratio * est
    c = fabrique(profile="dev")
    # 25 %, 49 % : tronqué ; 50 % exactement et 51 % : accepté
    assert _tronque(c, chars, int(est * 0.25)) is not None
    assert _tronque(c, chars, int(est * 0.49)) is not None
    assert _tronque(c, chars, int(seuil) - 1) is not None  # un jeton sous la limite
    assert _tronque(c, chars, -(-int(seuil * 2) // 2)) is None  # ceil(seuil) : limite acceptée
    assert _tronque(c, chars, int(est * 0.51) + 1) is None


def test_la_somme_des_caracteres_de_tous_les_messages_est_comptee(fabrique, cfg):
    chars = 10_000
    est = _estimes(chars, cfg)
    for n in (1, 2, 5):  # même total, répartition différente : même décision
        assert _tronque(fabrique(profile="dev"), chars, est // 4, n=n) is not None
        assert _tronque(fabrique(profile="dev"), chars, est, n=n) is None
    # système court + utilisateur long : seul le total compte
    c = fabrique(profile="dev")
    c.mock.push(RawCompletion("ok", SERVI, 100, 5))
    with pytest.raises(PromptTronque):
        c.complete(
            [{"role": "system", "content": "s" * 2_500}, {"role": "user", "content": "u" * 2_500}],
            date_donnees=T,
        )


def test_l_estimation_du_schema_de_sortie_structuree_est_incluse(fabrique, cfg):
    """La consigne de schéma ajoutée au message système fait partie du prompt estimé."""
    from pydantic import BaseModel

    class S(BaseModel):
        x: int

    c = fabrique(profile="dev")
    c.mock.push(RawCompletion('{"x": 1}', SERVI, 10, 5))
    with pytest.raises(PromptTronque) as e:
        c.complete_structured(S, _msgs(4_300), date_donnees=T)
    assert e.value.estimes > _estimes(4_300, cfg)  # 4 300 caractères seuls : 955 < seuil


# rapports évalués/estimés réalistes selon le type de texte (caractères par jeton typiques) :
# un texte ne déclenche une alerte que s'il a plus de chars_per_token / min_ratio = 9 car./jeton
@pytest.mark.parametrize(
    "nature,car_par_jeton,chars",
    [
        ("français avec nombres", 3.1, 20_000),
        ("anglais", 4.2, 20_000),
        ("JSON dense", 2.5, 20_000),
        ("nombres", 2.0, 20_000),
        ("code", 3.0, 20_000),
        ("non ASCII (CJK)", 1.2, 12_000),  # 10 000 jetons : sous la fenêtre
        ("emojis", 0.6, 6_000),  # 10 000 jetons
        ("base64", 1.4, 14_000),
    ],
)
def test_pas_de_faux_positif_sur_les_types_de_texte_usuels(
    fabrique, cfg, nature, car_par_jeton, chars
):
    evalues = int(chars / car_par_jeton)
    ctx = cfg.ollama.num_ctx
    # rapports réalistes : le serveur ne peut pas évaluer plus que sa fenêtre
    assert evalues <= 0.95 * ctx, nature
    assert evalues >= cfg.truncation_check.min_ratio * _estimes(chars, cfg)
    assert _tronque(fabrique(profile="dev"), chars, evalues) is None, nature


def test_faux_positif_theorique_sur_du_texte_a_plus_de_9_caracteres_par_jeton(fabrique, cfg):
    """Constat (mineur) : de longues suites d'espaces ou de retours à la ligne se tokenisent à plus
    de 9 caractères par jeton : la détection les prendrait pour une troncature."""
    chars = 20_000
    assert _tronque(fabrique(profile="dev"), chars, chars // 12) is not None


@pytest.mark.parametrize("valeur", [0])
def test_usage_inconnu_pas_de_troncature_mais_detection_aveugle_signalee_une_fois(
    fabrique, tmp_path, caplog, valeur
):
    import logging

    c = fabrique(profile="dev", run_dir=tmp_path / "run")
    with caplog.at_level(logging.WARNING):
        for i in range(3):
            c.mock.push(RawCompletion("ok", SERVI, valeur, 5))
            r = c.complete(_msgs(10_000 + i), date_donnees=T)
            assert r.text == "ok" and r.record.detection_aveugle is True
    avertissements = [m for m in caplog.messages if "aveugle" in m]
    assert len(avertissements) == 1  # avertissement unique par exécution
    lignes = [json.loads(x) for x in (tmp_path / "run" / "calls.jsonl").read_text().splitlines()]
    assert [x["detection_aveugle"] for x in lignes] == [True, True, True]


def test_usage_inconnu_sur_prompt_court_pas_de_detection_aveugle(fabrique):
    c = fabrique(profile="dev")
    c.mock.push(RawCompletion("ok", SERVI, 0, 5))
    r = c.complete(_msgs(500), date_donnees=T)
    assert not r.record.detection_aveugle


def test_usage_connu_ne_marque_pas_la_detection_aveugle(fabrique):
    c = fabrique(profile="dev")
    c.mock.push(RawCompletion("ok", SERVI, 4_500, 5))
    assert not c.complete(_msgs(20_000), date_donnees=T).record.detection_aveugle


@pytest.mark.parametrize("valeur", [0])
def test_usage_inconnu_en_evaluation_leve_usage_inconnu_et_est_journalise(
    fabrique, cfg, tmp_path, valeur
):
    from amundi_agentic.llm.types import UsageInconnu

    ev_cfg = load_config(
        overrides={
            "evaluation": {
                "fallback_enabled": False,
                "models": {"main": "ollama/modele-fige-1", "light": cfg.evaluation.models["light"]},
            }
        }
    )
    assert ev_cfg.truncation_check.exiger_usage_en_evaluation is True
    c = fabrique(config=ev_cfg, mode="evaluation", profile="prod", run_dir=tmp_path / "run")
    c.mock.push(RawCompletion("ok", "v1", valeur, 5))
    with pytest.raises(UsageInconnu):
        c.complete(_msgs(20_000), date_donnees=T)
    assert _fichiers_cache(c) == [] and c.sleeps == []
    ligne = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[-1])
    assert ligne["erreur"].startswith("usage_inconnu") and ligne["detection_aveugle"] is True
    # prompt court : aucune exigence
    c.mock.push(RawCompletion("ok", "v1", 0, 5))
    assert c.complete(_msgs(500), date_donnees=T).text == "ok"
    # exigence désactivée par la configuration : avertissement seulement
    souple = load_config(
        overrides={
            "evaluation": {
                "fallback_enabled": False,
                "models": {"main": "ollama/modele-fige-1", "light": cfg.evaluation.models["light"]},
            },
            "truncation_check": {
                **cfg.truncation_check.model_dump(),
                "exiger_usage_en_evaluation": False,
            },
        }
    )
    c2 = fabrique(config=souple, mode="evaluation", profile="prod")
    c2.mock.push(RawCompletion("ok", "v1", valeur, 5))
    assert c2.complete(_msgs(20_000), date_donnees=T).record.detection_aveugle is True


def test_usage_inconnu_en_evaluation_ne_concerne_pas_un_fournisseur_non_controle(fabrique):
    c = fabrique(mode="evaluation", profile="prod")  # modèles figés Gemini : non contrôlés
    c.mock.push(RawCompletion("ok", "v1", 0, 5))
    assert c.complete(_msgs(20_000), date_donnees=T).text == "ok"


@pytest.mark.parametrize(
    "valeur,attendu",
    [(None, 0), ("abc", 0), (-5, 0), (True, 0), (float("nan"), 0), (float("inf"), 0), (0, 0),
     (2.5, 2), (4500, 4500), ("4500", 0)],
)  # fmt: skip
def test_prompt_tokens_aberrant_dans_le_transport_donne_un_usage_inconnu_jamais_une_exception(
    monkeypatch, valeur, attendu
):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    t = LiteLLMTransport(load_config())

    class Lib:
        def completion(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                model="m",
                usage=SimpleNamespace(prompt_tokens=valeur, completion_tokens=valeur),
            )

    t._litellm = Lib()
    r = t.completion(
        model="ollama/x", messages=[{"role": "user", "content": "a"}], temperature=0,
        seed=0, max_tokens=None, timeout=5, json_mode=False,
    )  # fmt: skip
    assert r.tokens_in == attendu and r.tokens_out == attendu


def test_usage_absent_de_la_reponse_donne_zero(monkeypatch):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    t = LiteLLMTransport(load_config())

    class Lib:
        def completion(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], model="m"
            )

    t._litellm = Lib()
    r = t.completion(
        model="ollama/x", messages=[{"role": "user", "content": "a"}], temperature=0,
        seed=0, max_tokens=None, timeout=5, json_mode=False,
    )  # fmt: skip
    assert (r.tokens_in, r.tokens_out) == (0, 0)


# --- faux négatifs : troncature partielle au-delà de la moitié
@pytest.mark.parametrize(
    "ratio,refuse",
    [(0.6, False), (0.95, False), (0.97, False), (0.98, True), (0.99, True), (1.0, True)],
)
def test_prompt_depassant_num_ctx_est_detecte_par_la_saturation(
    fabrique, cfg, tmp_path, ratio, refuse
):
    import math

    chars = 80_000
    assert _estimes(chars, cfg) > cfg.ollama.num_ctx  # prompt plus grand que la fenêtre
    seuil = cfg.truncation_check.saturation_ratio
    assert seuil == 0.98
    evalues = (
        math.ceil(ratio * cfg.ollama.num_ctx) if ratio >= seuil else int(ratio * cfg.ollama.num_ctx)
    )
    c = fabrique(profile="dev", run_dir=tmp_path / "run")
    exc = _tronque(c, chars, evalues)
    assert (exc is not None) is refuse
    if refuse:
        assert exc.motif == "saturation" and "saturation" in str(exc)
        assert _fichiers_cache(c) == [] and len(c.mock.chat_calls) == 1  # ni cache ni retry
        ligne = json.loads((tmp_path / "run" / "calls.jsonl").read_text().splitlines()[-1])
        assert ligne["erreur"].startswith("prompt_tronque_saturation")
        assert ligne["prompt_tokens_evalues"] == evalues and ligne["num_ctx"] == cfg.ollama.num_ctx


def test_exactement_a_la_limite_de_saturation(fabrique, cfg):
    import math

    limite = cfg.truncation_check.saturation_ratio * cfg.ollama.num_ctx
    assert _tronque(fabrique(profile="dev"), 80_000, math.ceil(limite) - 1) is None
    # autre taille de prompt : le cache partagé ne doit pas servir la réponse précédente
    assert _tronque(fabrique(profile="dev"), 80_001, math.ceil(limite)) is not None


def test_saturation_sans_relais_ni_retry_en_chaine_interactive(fabrique, cfg_ollama_principal):
    c = fabrique(config=cfg_ollama_principal, profile="prod")
    modele = cfg_ollama_principal.models["main"]
    c.mock.push(RawCompletion("x", SERVI, 16384, 5), model=modele)
    with pytest.raises(PromptTronque):
        c.complete(_msgs(80_000), date_donnees=T)
    assert [a["model"] for a in c.mock.chat_calls] == [modele] and c.sleeps == []


def test_la_troncature_n_est_detectee_que_si_le_prompt_depasse_deux_fois_num_ctx(fabrique, cfg):
    chars = int(2.1 * cfg.ollama.num_ctx * cfg.truncation_check.chars_per_token)
    assert _tronque(fabrique(profile="dev"), chars, cfg.ollama.num_ctx) is not None


def test_regle_proposee_contexte_sature_devrait_etre_refuse(fabrique, cfg):
    chars = 80_000
    assert _tronque(fabrique(profile="dev"), chars, int(0.99 * cfg.ollama.num_ctx)) is not None


# --------------------------------------------------------------------------- 2. comportement
@pytest.fixture
def cfg_ollama_principal(cfg):
    """`main` = Ollama puis relais Groq : permet de prouver l'absence de relais."""
    return load_config(overrides={"models": {**cfg.models, "main": cfg.models["dev"]}})


def _fichiers_cache(c):
    return list(c.cache.directory.glob("??/*.json"))


def test_prompt_tronque_ni_relais_ni_retry_ni_cache_ni_attente(fabrique, cfg_ollama_principal):
    c = fabrique(config=cfg_ollama_principal, profile="prod")
    modele_principal = cfg_ollama_principal.models["main"]
    assert cfg_ollama_principal.chain("main", mode="interactif", profile="prod")[1][0] == "fallback"
    c.mock.push(RawCompletion("tronqué", SERVI, 300, 5), model=modele_principal)
    with pytest.raises(PromptTronque):
        c.complete(_msgs(20_000), date_donnees=T)
    assert [a["model"] for a in c.mock.chat_calls] == [modele_principal]  # pas de relais
    assert c.sleeps == [] and _fichiers_cache(c) == []
    # le même appel, bien évalué cette fois, repart au fournisseur (rien n'est servi du cache)
    c.mock.push(RawCompletion("bon", SERVI, 4_500, 5), model=modele_principal)
    assert c.complete(_msgs(20_000), date_donnees=T).text == "bon"
    assert len(c.mock.chat_calls) == 2


def test_aucune_ecriture_en_cache_en_sortie_structuree_meme_au_second_essai(fabrique):
    from pydantic import BaseModel

    class S(BaseModel):
        x: int

    c = fabrique(profile="dev")
    # 1er essai : JSON invalide mais bien évalué ; 2e essai (prompt allongé) : tronqué
    c.mock.push(
        RawCompletion("pas du json", SERVI, 4_500, 5), RawCompletion('{"x": 1}', SERVI, 100, 5)
    )
    with pytest.raises(PromptTronque):
        c.complete_structured(S, _msgs(20_000), date_donnees=T)
    assert len(c.mock.chat_calls) == 2 and _fichiers_cache(c) == []


def test_troncature_au_premier_essai_pas_de_nouvelle_demande_structuree(fabrique):
    from pydantic import BaseModel

    class S(BaseModel):
        x: int

    c = fabrique(profile="dev")
    c.mock.push(RawCompletion('{"x": 1}', SERVI, 50, 5))
    with pytest.raises(PromptTronque):
        c.complete_structured(S, _msgs(20_000), date_donnees=T)
    assert len(c.mock.chat_calls) == 1  # une troncature n'est pas une sortie invalide


def test_journal_calls_jsonl_porte_les_trois_champs_et_l_erreur(fabrique, tmp_path):
    c = fabrique(profile="dev", run_dir=tmp_path / "run")
    with pytest.raises(PromptTronque):
        _appel(c, 20_000, 300)
    _appel(c, 20_000, 4_500)  # un appel normal ensuite
    lignes = [json.loads(x) for x in (tmp_path / "run" / "calls.jsonl").read_text().splitlines()]
    err, ok = lignes[0], lignes[1]
    assert err["erreur"].startswith("prompt_tronque")
    assert (err["prompt_tokens_evalues"], err["prompt_tokens_estimes"], err["num_ctx"]) == (
        300,
        4444,
        16384,
    )
    assert err["tokens_entree"] == 300 and err["modele_servi"] == SERVI
    assert (ok["prompt_tokens_evalues"], ok["prompt_tokens_estimes"], ok["num_ctx"]) == (
        4_500,
        4444,
        16384,
    )
    assert ok["erreur"] is None and ok["cache_hit"] is False


def test_champs_none_sur_cache_hit_et_hors_ollama(fabrique, tmp_path):
    c = fabrique(profile="dev")
    _appel(c, 6_000, 1_400)
    r = c.complete(_msgs(6_000), date_donnees=T)  # cache hit
    assert r.record.cache_hit
    assert (r.record.prompt_tokens_evalues, r.record.prompt_tokens_estimes, r.record.num_ctx) == (
        None,
        None,
        None,
    )
    p = fabrique(profile="prod")
    rec = p.complete(_msgs(6_000), date_donnees=T).record
    assert (
        rec.num_ctx is None and rec.prompt_tokens_evalues is not None
    )  # estimation faite pour tout fournisseur


def test_modele_servi_change_prime_sur_la_detection_de_troncature(fabrique, cfg):
    """En évaluation sur un modèle Ollama figé : le contrôle du modèle servi (dans `_tenter`) passe
    AVANT la détection de troncature ; les deux erreurs restent distinctes."""
    from amundi_agentic.llm.types import ModeleServiChange

    ev_cfg = load_config(
        overrides={
            "evaluation": {
                "fallback_enabled": False,
                "models": {"main": "ollama/modele-fige-1", "light": cfg.evaluation.models["light"]},
            }
        }
    )
    c = fabrique(config=ev_cfg, mode="evaluation", profile="prod")
    c.mock.push(RawCompletion("ok", "v1", 4_500, 5))
    c.complete(_msgs(20_000), date_donnees=T)  # gèle v1
    c.mock.push(RawCompletion("ok", "v2", 100, 5))  # servi par v2 ET tronqué
    with pytest.raises(ModeleServiChange):
        c.complete(_msgs(20_001), date_donnees=T)
    c.mock.push(RawCompletion("ok", "v1", 100, 5))  # même modèle, tronqué
    with pytest.raises(PromptTronque):
        c.complete(_msgs(20_002), date_donnees=T)


def test_evaluation_prompt_tronque_n_est_ni_une_pause_ni_une_panne_geree(fabrique, cfg):
    from amundi_agentic.llm.types import ExecutionPausee

    ev_cfg = load_config(
        overrides={
            "evaluation": {
                "fallback_enabled": False,
                "models": {"main": "ollama/modele-fige-1", "light": cfg.evaluation.models["light"]},
            }
        }
    )
    c = fabrique(config=ev_cfg, mode="evaluation", profile="prod")
    c.mock.push(RawCompletion("ok", "v1", 100, 5))
    with pytest.raises(PromptTronque) as e:
        c.complete(_msgs(20_000), date_donnees=T)
    assert not isinstance(e.value, (ExecutionPausee, ProviderError)) and c.sleeps == []


# ------------------------------------------------------------------- 3. num_ctx et configuration
def test_num_ctx_transmis_seulement_a_ollama_pour_les_trois_fournisseurs(fabrique, cfg):
    c = fabrique(profile="prod")
    c.mock.fail("quota", 1, model=cfg.models["main"])  # gemini -> relais groq
    c.complete(_msgs(500), date_donnees=T)
    par_modele = {a["model"]: a["extra_params"] for a in c.mock.chat_calls}
    assert par_modele[cfg.models["main"]] == {} and par_modele[cfg.models["fallback"]] == {}
    d = fabrique(profile="dev")
    d.complete(_msgs(500), date_donnees=T)
    assert d.mock.chat_calls[0]["extra_params"] == {"num_ctx": 16384}
    assert all(set(a["extra_params"]) <= {"num_ctx"} for a in c.mock.chat_calls + d.mock.chat_calls)


def test_transport_litellm_ne_passe_num_ctx_qu_a_ollama(monkeypatch):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "Sy" + "q" * 33)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "q" * 40)
    cfg = load_config()
    t = LiteLLMTransport(cfg)
    vus = []

    class Lib:
        def completion(self, **kw):
            vus.append(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                model="m",
                usage=SimpleNamespace(prompt_tokens=7, completion_tokens=1),
            )

    t._litellm = Lib()
    for modele in (cfg.models["dev"], cfg.models["main"], cfg.models["fallback"]):
        extra = cfg.provider_params(modele.split("/", 1)[0])
        t.completion(
            model=modele,
            messages=[{"role": "user", "content": "a"}],
            temperature=0,
            seed=0,
            max_tokens=None,
            timeout=5,
            json_mode=False,
            extra_params=extra,
        )
    assert vus[0].get("num_ctx") == 16384
    assert "num_ctx" not in vus[1] and "num_ctx" not in vus[2]
    # extra_params ne peut pas écraser un paramètre commun
    t.completion(
        model=cfg.models["dev"],
        messages=[{"role": "user", "content": "a"}],
        temperature=0,
        seed=0,
        max_tokens=None,
        timeout=5,
        json_mode=False,
        extra_params={"temperature": 9},
    )
    assert vus[-1]["temperature"] == 0


@pytest.mark.parametrize("valeur", [0, -1, -16384, 1.5, 16384.0, True, False, "16384", [], {}])
def test_num_ctx_invalide_refuse_a_la_lecture(cfg, valeur):
    with pytest.raises(ConfigurationError):
        load_config(overrides={"ollama": {"num_ctx": valeur}})


@pytest.mark.parametrize("valeur", [2048, 16384, 131072])
def test_num_ctx_valide_accepte(cfg, valeur):
    assert load_config(overrides={"ollama": {"num_ctx": valeur}}).ollama.num_ctx == valeur


def test_num_ctx_none_avec_un_modele_ollama_configure_est_une_erreur_de_configuration(cfg):
    with pytest.raises(ConfigurationError, match="num_ctx"):
        load_config(overrides={"ollama": {"num_ctx": None}})
    # modèle d'évaluation Ollama sans num_ctx : refusé aussi
    sans_dev = {**cfg.models, "dev": cfg.models["main"]}
    ev = {"fallback_enabled": False, "models": {**cfg.evaluation.models, "main": "ollama/fige-1"}}
    with pytest.raises(ConfigurationError, match="num_ctx"):
        load_config(overrides={"models": sans_dev, "ollama": {"num_ctx": None}, "evaluation": ev})


def test_num_ctx_none_accepte_quand_aucun_modele_ollama_n_est_configure(cfg):
    sans_ollama = {**cfg.models, "dev": cfg.models["main"]}
    c = load_config(overrides={"models": sans_ollama, "ollama": {"num_ctx": None}})
    assert c.ollama.num_ctx is None and c.provider_params("ollama") == {}


@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("chars_per_token", 0),
        ("chars_per_token", -1),
        ("min_ratio", 0),
        ("min_ratio", 1.5),
        ("min_ratio", -0.1),
        ("min_estimated_tokens", -1),
        ("providers", "ollama"),
        ("inconnu", 1),
    ],
)
def test_truncation_check_invalide_refuse(cfg, champ, valeur):
    bloc = {**cfg.truncation_check.model_dump(), champ: valeur}
    with pytest.raises(ConfigurationError):
        load_config(overrides={"truncation_check": bloc})


def test_min_ratio_a_un_est_accepte_et_zero_refuse(cfg):
    assert load_config(
        overrides={"truncation_check": {**cfg.truncation_check.model_dump(), "min_ratio": 1}}
    )
    with pytest.raises(ConfigurationError):
        load_config(
            overrides={"truncation_check": {**cfg.truncation_check.model_dump(), "min_ratio": 0}}
        )


def test_surcharge_par_un_autre_fichier_de_config(tmp_path, fabrique):
    brut = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    brut["ollama"]["num_ctx"] = 8192
    f = tmp_path / "llm_8k.yaml"
    f.write_text(yaml.safe_dump(brut, allow_unicode=True), encoding="utf-8")
    cfg2 = load_config(f)
    c = fabrique(config=cfg2, profile="dev")
    c.complete(_msgs(500), date_donnees=T)
    assert c.mock.chat_calls[0]["extra_params"] == {"num_ctx": 8192}


def test_une_config_sans_les_sections_d062_n_est_pas_silencieusement_dangereuse(tmp_path):
    brut = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    brut.pop("ollama")
    brut.pop("truncation_check")
    f = tmp_path / "ancienne.yaml"
    f.write_text(yaml.safe_dump(brut, allow_unicode=True), encoding="utf-8")
    try:
        cfg = load_config(f)
    except ConfigurationError:
        return  # erreur claire : acceptable
    assert (
        cfg.provider_params("ollama").get("num_ctx") and "ollama" in cfg.truncation_check.providers
    )


def test_llm_yaml_sans_cle_dupliquee():
    class Strict(yaml.SafeLoader):
        pass

    def construire(loader, node, deep=False):
        cles = [loader.construct_object(k, deep=deep) for k, _ in node.value]
        doublons = {k for k in cles if cles.count(k) > 1}
        if doublons:
            raise ValueError(f"clés dupliquées : {sorted(doublons)}")
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construire)
    yaml.load(CONFIG_PATH.read_text(encoding="utf-8"), Loader=Strict)


# --------------------------------------------------------------------------- 4. cache
def _cle(**params):
    return cache_key(
        kind="chat",
        model="ollama/x",
        messages=[{"role": "user", "content": "a"}],
        schema=None,
        params={"temperature": 0, "seed": 0, "max_tokens": None, **params},
        date_donnees=T,
        scope="interactif/dev",
    )


def test_num_ctx_differents_ne_partagent_jamais_une_entree(fabrique, tmp_path):
    assert len({_cle(), _cle(num_ctx=2048), _cle(num_ctx=16384), _cle(num_ctx=32768)}) == 4
    cache = tmp_path / "cache"
    ids = set()
    for n in (2048, 8192, 16384):
        c = fabrique(
            config=load_config(overrides={"ollama": {"num_ctx": n}}), profile="dev", cache=cache
        )
        r = c.complete(_msgs(500), date_donnees=T)
        assert r.record.cache_hit is False
        ids.add(r.record.cle_cache)
    assert len(ids) == 3
    c = fabrique(profile="dev", cache=cache)  # 16384 : retrouve SON entrée seulement
    assert c.complete(_msgs(500), date_donnees=T).record.cache_hit is True


def test_une_entree_de_version_1_n_est_pas_servie(fabrique, tmp_path):
    import hashlib

    assert CACHE_KEY_VERSION == 2
    cache = tmp_path / "cache"
    c = fabrique(profile="dev", cache=cache)
    msgs = _msgs(500)
    modele = c.config.models["dev"]
    ancien = {
        "kind": "chat",
        "model": modele,
        "messages": msgs,
        "schema": None,
        "params": {"temperature": 0, "seed": 0, "max_tokens": None},
        "date_donnees": T.isoformat(),
        "scope": "interactif/dev",
    }
    cle1 = hashlib.sha256(
        json.dumps(ancien, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    dossier = cache / cle1[:2]
    dossier.mkdir(parents=True)
    (dossier / f"{cle1}.json").write_text(
        json.dumps(
            {
                "text": "REPONSE-TRONQUEE-ANCIENNE",
                "modele_servi": SERVI,
                "modele_demande": modele,
                "fournisseur": "ollama",
                "tier": "dev",
                "relais_utilise": False,
                "tokens_entree": 2050,
                "tokens_sortie": 5,
                "date_donnees": T.isoformat(),
            }
        )
    )
    r = c.complete(msgs, date_donnees=T)
    assert r.text != "REPONSE-TRONQUEE-ANCIENNE" and r.record.cache_hit is False
    assert r.record.cle_cache != cle1


def test_la_version_de_cle_entre_dans_le_hachage():
    import amundi_agentic.llm.cache as cache_mod

    a = _cle()
    ancienne = cache_mod.CACHE_KEY_VERSION
    try:
        cache_mod.CACHE_KEY_VERSION = ancienne + 1
        assert _cle() != a
    finally:
        cache_mod.CACHE_KEY_VERSION = ancienne


def test_cle_de_cache_stable_entre_processus_avec_num_ctx():
    code = (
        "from datetime import date; from amundi_agentic.llm.cache import cache_key;"
        "print(cache_key(kind='chat', model='ollama/x', messages=[{'role':'user','content':'é'}],"
        "schema=None, params={'seed':0,'num_ctx':16384}, date_donnees=date(2024,2,1), scope='a/b'))"
    )
    sorties = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": str(s)},
        ).stdout
        for s in (1, 2, 3)
    }
    assert len(sorties) == 1


# --------------------------------------------------------------------------- 5. ExecutionRecord
def _rec(**kw):
    base = dict(
        appel_id="a",
        run_id="r",
        horodatage="2024-02-01T00:00:00+00:00",
        agent="x",
        tier="dev",
        mode="interactif",
        modele_demande="m",
        modele_servi="s",
        fournisseur="ollama",
        prompt_id="p",
        prompt_version="v",
        prompt_sha256="0" * 64,
        cle_cache="1" * 64,
        cache_hit=False,
        graine=0,
        temperature=0,
        tokens_entree=1,
        tokens_sortie=1,
        cout_eur=0,
        latence_ms=1,
        date_donnees=T,
    )
    return ExecutionRecord(**{**base, **kw})


def test_nouveaux_champs_facultatifs_et_valides():
    r = _rec()
    assert (r.prompt_tokens_evalues, r.prompt_tokens_estimes, r.num_ctx) == (None, None, None)
    r2 = _rec(prompt_tokens_evalues=0, prompt_tokens_estimes=5, num_ctx=16384)
    assert ExecutionRecord.model_validate_json(r2.model_dump_json()) == r2
    for mauvais in (
        {"prompt_tokens_evalues": -1},
        {"prompt_tokens_estimes": -1},
        {"num_ctx": 0},
        {"num_ctx": -4},
    ):
        with pytest.raises(Exception):  # noqa: B017, PT011
            _rec(**mauvais)
    assert "prompt_tokens_evalues" in json.loads(r2.model_dump_json())
