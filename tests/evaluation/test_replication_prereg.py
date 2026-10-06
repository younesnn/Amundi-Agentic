# ruff: noqa: E501
"""Pré-enregistrement en ajout seul et tirage vérifiable (D-027, D-065)."""

from __future__ import annotations

import json
import shutil

import pytest

from amundi_agentic.data.settings import CONFIG_DIR
from amundi_agentic.evaluation import preregistration as pr
from amundi_agentic.evaluation.repl_config import charger_config
from amundi_agentic.evaluation.tirage import (
    GraineNonConforme,
    graine_sha256,
    permutation,
    tirage_primaire,
    tirages_secondaires,
    verifier_graine,
)

POOL = [f"T{i:02d}" for i in range(40)]


@pytest.fixture
def cfg_dir(tmp_path):
    """Copie des configurations : on peut les modifier sans toucher au dépôt."""
    d = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, d, ignore=shutil.ignore_patterns("esg_etf_sources_archive"))
    return d


def _enr(cfg, cfg_dir, tmp_path, **kw):
    return pr.enregistrer(cfg, racine=tmp_path / "pr", config_dir=cfg_dir, **kw)


def test_hash_de_graine_stable_et_verifie():
    h = graine_sha256(20240201)
    assert h == graine_sha256(20240201) != graine_sha256(20240202)
    verifier_graine(20240201, h)
    with pytest.raises(GraineNonConforme):
        verifier_graine(20240202, h)


def test_tirage_deterministe_et_independant_de_lordre_dentree():
    a = tirage_primaire(POOL, hors_pool="ZS", n=14, graine=7)
    b = tirage_primaire(list(reversed(POOL)), hors_pool="ZS", n=14, graine=7)
    assert a == b
    assert a.titres[0] == "ZS" and len(a.titres) == 15 and len(set(a.titres)) == 15
    assert a.retenus == tuple(permutation(POOL, 7)[:14])
    assert tirage_primaire(POOL, hors_pool="ZS", n=14, graine=8).retenus != a.retenus


def test_remplacement_par_le_titre_suivant_de_la_permutation():
    base = tirage_primaire(POOL, hors_pool="ZS", n=5, graine=1)
    perm = base.permutation
    tombe = base.retenus[2]
    t = tirage_primaire(POOL, hors_pool="ZS", n=5, graine=1, echecs={tombe: "x"})
    assert tombe not in t.retenus
    assert t.remplaces == {tombe: perm[5]}
    assert set(t.retenus) == (set(base.retenus) - {tombe}) | {perm[5]}


def test_tirages_secondaires_reproductibles_sans_hors_pool():
    s1 = tirages_secondaires(POOL + ["ZS"], hors_pool="ZS", n=14, graine=3, nombre=20)
    s2 = tirages_secondaires(POOL + ["ZS"], hors_pool="ZS", n=14, graine=3, nombre=20)
    assert s1 == s2 and len(set(s1)) > 1
    assert all("ZS" not in x and len(x) == 14 for x in s1)


def test_enregistrement_ecrit_hash_de_graine_avant_tirage(cfg_dir, tmp_path):
    cfg = charger_config(cfg_dir / "replication.yaml")
    e = _enr(cfg, cfg_dir, tmp_path)
    rec = json.loads(e.chemin.read_text(encoding="utf-8"))
    assert rec["empreintes"]["graine_sha256"] == graine_sha256(cfg.tirage.graine)
    assert rec["tirage_effectue"] is False and rec["version"] == 1
    assert rec["empreintes"]["configs"]["replication.yaml"]
    assert rec["empreintes"]["prompts"]["roles"] and rec["empreintes"]["uv_lock_sha256"]
    assert set(rec["empreintes"]["prompts"]["paraphrases"]) == {"paraphrase_1", "paraphrase_2"}
    assert e.chemin.name.endswith(".json") and e.sha256 == pr.sha256_fichier(e.chemin)


def test_check_conforme_puis_detecte_chaque_deviation(cfg_dir, tmp_path):
    cfg = charger_config(cfg_dir / "replication.yaml")
    _enr(cfg, cfg_dir, tmp_path)
    ok = pr.verifier(cfg, racine=tmp_path / "pr", config_dir=cfg_dir)
    assert ok.ok and not ok.ecarts
    # déviation 1 : un paramètre du protocole
    y = cfg_dir / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    rv = pr.verifier(charger_config(y), racine=tmp_path / "pr", config_dir=cfg_dir)
    chemins = {e.chemin for e in rv.ecarts}
    assert not rv.ok and "protocole.tirage.n_titres" in chemins
    assert "configs.replication.yaml" in chemins
    # déviation 2 : la graine
    y.write_text(
        y.read_text(encoding="utf-8").replace("graine: 20240201", "graine: 5"), encoding="utf-8"
    )
    rv = pr.verifier(charger_config(y), racine=tmp_path / "pr", config_dir=cfg_dir)
    assert "graine_sha256" in {e.chemin for e in rv.ecarts}


def test_check_detecte_modification_de_debate_yaml_et_de_prompt(cfg_dir, tmp_path):
    cfg = charger_config(cfg_dir / "replication.yaml")
    _enr(cfg, cfg_dir, tmp_path)
    d = cfg_dir / "debate.yaml"
    d.write_text(d.read_text(encoding="utf-8") + "\n# modif\n", encoding="utf-8")
    rv = pr.verifier(cfg, racine=tmp_path / "pr", config_dir=cfg_dir)
    assert "configs.debate.yaml" in {e.chemin for e in rv.ecarts}
    # prompt de paraphrase modifié dans un dossier de prompts copié
    pdir = tmp_path / "prompts"
    shutil.copytree(pr.PROMPTS_DIR, pdir)
    pr_dir = tmp_path / "pr2"
    pr.enregistrer(cfg, racine=pr_dir, config_dir=CONFIG_DIR, prompts_dir=pdir)
    f = pdir / "valuation_titre_v1.md"
    f.write_text(f.read_text(encoding="utf-8") + "\nmodif\n", encoding="utf-8")
    rv = pr.verifier(cfg, racine=pr_dir, config_dir=CONFIG_DIR, prompts_dir=pdir)
    assert "prompts.roles.valuation_titre" in {e.chemin for e in rv.ecarts}


def test_ajout_seul_nouvelle_version_chainee_et_motivee(cfg_dir, tmp_path):
    cfg = charger_config(cfg_dir / "replication.yaml")
    e1 = _enr(cfg, cfg_dir, tmp_path)
    with pytest.raises(pr.RienAChanger):
        _enr(cfg, cfg_dir, tmp_path)
    y = cfg_dir / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    cfg2 = charger_config(y)
    with pytest.raises(pr.MotifRequis):
        _enr(cfg2, cfg_dir, tmp_path)
    avant = e1.chemin.read_bytes()
    e2 = _enr(cfg2, cfg_dir, tmp_path, motif="essai")
    assert e2.version == 2 and e2.chemin != e1.chemin
    assert e1.chemin.read_bytes() == avant  # jamais réécrit
    rec = json.loads(e2.chemin.read_text(encoding="utf-8"))
    assert rec["precedente"]["sha256"] == e1.sha256 and rec["motif"] == "essai"
    assert any(c["chemin"] == "protocole.tirage.n_titres" for c in rec["changements"])
    assert pr.verifier_chaine(cfg.protocole.nom, tmp_path / "pr") == []
    # altération de la première version : la chaîne le dit
    e1.chemin.write_text(avant.decode() + " ", encoding="utf-8")
    assert pr.verifier_chaine(cfg.protocole.nom, tmp_path / "pr")


def test_meme_jour_ne_reecrit_jamais(cfg_dir, tmp_path):
    from datetime import date

    cfg = charger_config(cfg_dir / "replication.yaml")
    e1 = _enr(cfg, cfg_dir, tmp_path, aujourd_hui=date(2026, 1, 2))
    y = cfg_dir / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    e2 = _enr(charger_config(y), cfg_dir, tmp_path, motif="m", aujourd_hui=date(2026, 1, 2))
    assert e1.chemin.name == "2026-01-02.json" and e2.chemin.name == "2026-01-02-2.json"


def test_verifier_sha_et_exiger_conforme(cfg_dir, tmp_path, monkeypatch):
    cfg = charger_config(cfg_dir / "replication.yaml")
    e1 = _enr(cfg, cfg_dir, tmp_path)
    racine = tmp_path / "pr"
    assert pr.verifier_sha(e1.sha256, racine)[0] == "courant"
    assert pr.verifier_sha("0" * 64, racine)[0] == "inconnu"
    assert pr.exiger_conforme(e1.sha256, racine=racine, config_dir=cfg_dir) == e1.chemin
    with pytest.raises(pr.PreenregistrementNonConforme):
        pr.exiger_conforme("0" * 64, racine=racine, config_dir=cfg_dir)
    y = cfg_dir / "replication.yaml"
    y.write_text(
        y.read_text(encoding="utf-8").replace("n_titres: 14", "n_titres: 13"), encoding="utf-8"
    )
    with pytest.raises(pr.PreenregistrementNonConforme):
        pr.exiger_conforme(e1.sha256, racine=racine, config_dir=cfg_dir)
    e2 = pr.enregistrer(charger_config(y), racine=racine, config_dir=cfg_dir, motif="m")
    assert pr.verifier_sha(e1.sha256, racine)[0] == "remplace"
    with pytest.raises(pr.PreenregistrementNonConforme):
        pr.exiger_conforme(e1.sha256, racine=racine, config_dir=cfg_dir)
    assert pr.exiger_conforme(e2.sha256, racine=racine, config_dir=cfg_dir) == e2.chemin


def test_paraphrases_ont_les_memes_variables_et_en_tetes():
    import re

    cfg = charger_config()
    for p in ("paraphrase_1", "paraphrase_2"):
        for nom in cfg.paraphrases.prompts_paraphrases:
            orig = (pr.PROMPTS_DIR / f"{nom}_v1.md").read_text(encoding="utf-8")
            par = (CONFIG_DIR / "replication_paraphrases" / p / f"{nom}_v1.md").read_text(
                encoding="utf-8"
            )
            assert par != orig
            assert (
                set(re.findall(r"\{\{\w+\}\}", par)) == set(re.findall(r"\{\{\w+\}\}", orig))
                or nom == "profils"
            )
            assert par.splitlines()[:4] == orig.splitlines()[:4]
