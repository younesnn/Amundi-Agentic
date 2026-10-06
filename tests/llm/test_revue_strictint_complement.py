"""Revue indépendante : complément sur `StrictInt` des limites de quota (valeurs absentes des tests
de l'agent : 1.0, « 5 », très grand entier, None, YAML réel inchangé)."""

import pytest

from amundi_agentic.llm import ConfigurationError, load_config

GROQ = "groq/openai/gpt-oss-120b"
CHAMPS = ["requests_per_day", "requests_per_minute", "tokens_per_minute"]


@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("valeur", [True, False, 1.0, 5.0, "5", " 5", "five", [5], {"v": 5}])
def test_refuses_booleens_flottants_chaines(champ, valeur):
    with pytest.raises(ConfigurationError):
        load_config(overrides={"quotas": {"limits": {GROQ: {champ: valeur}}}})


@pytest.mark.parametrize("champ", CHAMPS)
@pytest.mark.parametrize("valeur", [None, 1, 5, 2**40])
def test_acceptes_entiers_positifs_et_null(champ, valeur):
    cfg = load_config(overrides={"quotas": {"limits": {GROQ: {champ: valeur}}}})
    assert getattr(cfg.quotas.limits[GROQ], champ) == valeur
    assert type(getattr(cfg.quotas.limits[GROQ], champ)) in (int, type(None))


def test_configuration_reelle_toujours_chargeable_et_limites_entieres():
    cfg = load_config()
    for lim in cfg.quotas.limits.values():
        for champ in CHAMPS:
            v = getattr(lim, champ)
            assert v is None or (type(v) is int and v > 0)
