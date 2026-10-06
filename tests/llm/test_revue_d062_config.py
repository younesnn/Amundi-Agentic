"""Revue indépendante (2e passe) : configuration D-062 (sections absentes, clés dupliquées)."""

from __future__ import annotations

import pytest
import yaml

from amundi_agentic.llm import ConfigurationError, load_config
from amundi_agentic.llm.config import CONFIG_PATH


def _ecrire(tmp_path, brut, nom="llm.yaml", texte=None):
    f = tmp_path / nom
    f.write_text(texte if texte is not None else yaml.safe_dump(brut, allow_unicode=True))
    return f


@pytest.fixture
def brut():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_sans_ollama_num_ctx_avec_un_modele_ollama_erreur_claire(tmp_path, brut):
    del brut["ollama"]
    with pytest.raises(ConfigurationError, match="num_ctx"):
        load_config(_ecrire(tmp_path, brut))
    brut["ollama"] = {}
    with pytest.raises(ConfigurationError, match="num_ctx"):
        load_config(_ecrire(tmp_path, brut, "b.yaml"))


def test_sans_truncation_check_les_defauts_sont_surs(tmp_path, brut):
    del brut["truncation_check"]
    c = load_config(_ecrire(tmp_path, brut))
    t = c.truncation_check
    assert t.providers == ["ollama"] and t.saturation_ratio == 0.98
    assert t.exiger_usage_en_evaluation is True and t.min_ratio == 0.5
    assert c.provider_params("ollama") == {"num_ctx": 16384}


def test_sans_aucun_modele_ollama_ni_num_ctx_la_config_est_acceptee(tmp_path, brut):
    del brut["ollama"]
    brut["models"]["dev"] = brut["models"]["main"]
    c = load_config(_ecrire(tmp_path, brut))
    assert c.provider_params("ollama") == {}


@pytest.mark.parametrize(
    "texte",
    [
        "a: 1\na: 2\n",
        "ollama:\n  num_ctx: 8192\nollama:\n  num_ctx: 16384\n",
        "truncation_check: {min_ratio: 0.5}\ntruncation_check: {min_ratio: 0.9}\n",
        "ollama:\n  num_ctx: 8192\n  num_ctx: 16384\n",  # doublon imbriqué
    ],
)
def test_cle_yaml_dupliquee_refusee_avec_son_nom(tmp_path, brut, texte):
    base = CONFIG_PATH.read_text(encoding="utf-8")
    f = _ecrire(tmp_path, None, texte=base + "\n" + texte)
    with pytest.raises(ConfigurationError, match="dupliqu"):
        load_config(f)


def test_le_vrai_fichier_n_a_aucune_cle_dupliquee_et_se_charge():
    assert load_config().ollama.num_ctx == 16384
    texte = CONFIG_PATH.read_text(encoding="utf-8")
    assert texte.count("\nollama:") == 1 and texte.count("\ntruncation_check:") == 1


def test_les_valeurs_de_truncation_check_du_fichier_sont_celles_de_d062(brut):
    t = load_config().truncation_check
    assert (t.providers, t.chars_per_token, t.min_estimated_tokens, t.min_ratio) == (
        ["ollama"], 4.5, 1000, 0.5,
    )  # fmt: skip
    assert t.saturation_ratio == 0.98 and t.exiger_usage_en_evaluation is True


@pytest.mark.parametrize(
    "champ,valeur",
    [("saturation_ratio", 0), ("saturation_ratio", 1.01), ("saturation_ratio", -1),
     ("exiger_usage_en_evaluation", "peut-être"), ("exiger_usage_en_evaluation", 3)],
)  # fmt: skip
def test_nouveaux_champs_de_detection_valides(brut, champ, valeur):
    bloc = {**load_config().truncation_check.model_dump(), champ: valeur}
    with pytest.raises(ConfigurationError):
        load_config(overrides={"truncation_check": bloc})


def test_yaml_invalide_donne_une_configuration_error_pas_une_trace(tmp_path):
    f = _ecrire(tmp_path, None, texte="a: [1, 2\n")
    with pytest.raises(ConfigurationError, match="YAML"):
        load_config(f)
