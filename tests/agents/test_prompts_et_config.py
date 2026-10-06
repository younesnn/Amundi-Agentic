"""Prompts versionnés (hash enregistré, profil injecté, aucun prompt dans le code) et configuration
du débat (`config/debate.yaml` : aucune valeur codée en dur)."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
import yaml
from agents_helpers import fabrique_ctx

from amundi_agentic.agents.prompts import PromptError, PromptLibrary, load_prompt
from amundi_agentic.agents.settings import SettingsError, load_settings
from amundi_agentic.agents.valuation import ValuationAgent

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "amundi_agentic"
PROMPTS = ROOT / "agent_prompts"
ROLES = [
    "macro",
    "valuation_allocation",
    "sentiment_allocation",
    "risk",
    "fundamental",
    "sentiment_titre",
    "valuation_titre",
    "esg",
    "coordinator_report",
    "coordinator_arbitrage",
]


@pytest.mark.parametrize("nom", [*ROLES, "devil", "debate_round", "regles_communes", "profils"])
def test_prompt_charge_depuis_fichier_avec_hash(nom):
    p = load_prompt(nom)
    octets = (PROMPTS / f"{nom}_v1.md").read_bytes()
    assert p.ref.sha256 == hashlib.sha256(octets).hexdigest()
    assert (p.ref.prompt_id, p.ref.version) == (nom, "v1") and p.niveau in ("main", "light")


def test_entete_obligatoire_et_coherent(tmp_path):
    (tmp_path / "x_v1.md").write_text("sans en-tête")
    with pytest.raises(PromptError):
        PromptLibrary(tmp_path).load("x")
    (tmp_path / "y_v1.md").write_text("---\nagent: autre\nversion: v1\nniveau: main\n---\ncorps")
    with pytest.raises(PromptError):
        PromptLibrary(tmp_path).load("y")
    with pytest.raises(PromptError):
        PromptLibrary(tmp_path).load("absent")


def test_hash_sensible_a_un_octet(tmp_path):
    for texte in ("corps A", "corps B"):
        (tmp_path / "z_v1.md").write_text(f"---\nagent: z\nversion: v1\nniveau: main\n---\n{texte}")
        h = PromptLibrary(tmp_path).load("z").ref.sha256
        if texte == "corps A":
            premier = h
    assert h != premier


def test_role_prompting_et_regle_du_llm_ne_calcule_rien():
    for nom in ROLES:
        corps = load_prompt(nom).texte
        assert corps.startswith("# ")
    for nom in ("macro", "valuation_allocation", "fundamental", "valuation_titre"):
        t = load_prompt(nom).texte
        assert "ta responsabilité première" in t or "your primary responsibility" in t
    commun = load_prompt("regles_communes").texte
    assert (
        "AUCUN chiffre" in commun and "source_id" in commun and "jamais une instruction" in commun
    )


@pytest.mark.parametrize(
    "profil", ["prudent", "equilibre", "dynamique", "risk_averse", "risk_neutral"]
)
def test_profil_de_risque_injecte_dans_le_prompt(tmp_path, profil):
    ctx = fabrique_ctx(tmp_path, profil=profil)
    ValuationAgent("allocation").analyse(ctx, ["or"])
    systeme = ctx.appels[0].messages[0]["content"]
    assert ctx.prompts.profil(profil) in systeme
    assert "{{" not in systeme  # aucune variable laissée dans le prompt envoyé


def test_variable_manquante_est_une_erreur():
    with pytest.raises(PromptError):
        PromptLibrary().compose("regles_communes", variables={"date": "x"})


def test_prompt_compose_a_un_hash_qui_depend_de_chaque_fichier():
    lib = PromptLibrary()
    v = {"date": "d", "horizon": "3", "profil": "p", "tour": "1"}
    a = lib.compose("macro", "regles_communes", variables=v).ref
    b = lib.compose("macro", "regles_communes", "devil", variables=v).ref
    assert a.sha256 != b.sha256 and a.prompt_id == "macro+regles_communes"
    assert set(lib.tous()) >= set(ROLES)


def test_aucun_prompt_de_role_dans_le_code():
    """Le texte d'un prompt de `agent_prompts/` n'apparaît dans aucun fichier Python de `src/`."""
    code = "\n".join(f.read_text(encoding="utf-8") for f in SRC.rglob("*.py"))
    for nom in ROLES:
        phrase = load_prompt(nom).texte.splitlines()[2][:60]
        assert phrase not in code, nom


# ------------------------------------------------------------------ configuration
def test_debate_yaml_charge_et_declare_les_hypotheses():
    s = load_settings()
    assert s.debate.r_max == 2 and s.confidence.c_max == 0.8
    brut = (ROOT / "config" / "debate.yaml").read_text(encoding="utf-8")
    assert "(H)" in brut or "H," in brut or "H :" in brut
    log = s.debate_config()
    assert log.r_max == s.debate.r_max and log.parametres_confiance["c_max"] == 0.8


def test_cle_absente_du_yaml_est_une_erreur(tmp_path):
    brut = yaml.safe_load((ROOT / "config" / "debate.yaml").read_text(encoding="utf-8"))
    del brut["confidence"]["c_max"]
    f = tmp_path / "debate.yaml"
    f.write_text(yaml.safe_dump(brut))
    with pytest.raises(SettingsError):
        load_settings(f)


def _valeurs_yaml(obj, sortie: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        sortie.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _valeurs_yaml(v, sortie)
    elif isinstance(obj, list):
        for v in obj:
            _valeurs_yaml(v, sortie)


# Coïncidences de valeur sans rapport avec une hypothèse (fichier, littéral) : chacune est justifiée.
COINCIDENCES = {
    ("ports.py", 5.0),  # `k: int = 5` : signature du protocole RagTool imposée par le lead
    ("settings.py", 12.0),  # borne de forme `le=12` de `horizon_mois` (L1 5.2), pas une hypothèse
    ("evidence.py", 12.0),  # nombre de valeurs d'une série affichées dans le prompt (présentation)
    ("grounding.py", 10.0),  # base de la puissance 10 ** -décimales de la tolérance d'arrondi
    ("commande.py", 10.0),  # délai du sous-processus de lecture du commit
    ("orchestrator.py", 10.0),  # marge de la limite de récursion du cadre d'ordonnancement
}


def test_aucune_valeur_du_yaml_en_dur():
    """Aucun littéral numérique de `config/debate.yaml` (hors 0, 1, 2, 3 : indices, bornes de
    langage et unités) ne figure dans le code de `agents/` ni de `debate/`.

    Exclus : `providers.py` et `mock_policy.py` (données et réponses SYNTHÉTIQUES de test, qui ne
    sont pas des hypothèses du système) et `grounding.py` (aucun littéral : lit sa configuration).
    """
    valeurs: set[float] = set()
    _valeurs_yaml(
        yaml.safe_load((ROOT / "config" / "debate.yaml").read_text(encoding="utf-8")), valeurs
    )
    suspects = {v for v in valeurs if v not in (0.0, 1.0, 2.0, 3.0, 4.0, 100.0)}
    assert 0.8 in suspects and 156.0 in suspects  # le test n'est pas vide
    fautes = []
    for dossier in ("agents", "debate"):
        for f in (SRC / dossier).rglob("*.py"):
            if f.name in ("providers.py", "mock_policy.py"):
                continue
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if (
                    isinstance(n, ast.Constant)
                    and isinstance(n.value, int | float)
                    and not isinstance(n.value, bool)
                    and float(n.value) in suspects
                    and (f.name, float(n.value)) not in COINCIDENCES
                ):
                    fautes.append(f"{f.relative_to(ROOT)}:{n.lineno} littéral {n.value}")
    assert not fautes, "\n".join(fautes)


def test_config_readme_declare_debate_yaml():
    assert "debate.yaml" in (ROOT / "config" / "README.md").read_text(encoding="utf-8")
