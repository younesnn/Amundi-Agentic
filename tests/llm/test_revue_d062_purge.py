"""Revue indépendante : commande `python -m amundi_agentic.llm purge-cache` (sécurité des
suppressions). Dossiers temporaires uniquement ; aucune écriture ailleurs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from amundi_agentic.llm.__main__ import main

HEX = "a" * 64


def entree(fournisseur, **extra):
    return json.dumps({"text": "x", "modele_servi": "m", "fournisseur": fournisseur, **extra})


def depose(cache: Path, cle: str, fournisseur: str):
    d = cache / cle[:2]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{cle}.json").write_text(entree(fournisseur), encoding="utf-8")


@pytest.fixture
def cache(tmp_path):
    c = tmp_path / "cache"
    for i, f in enumerate(["ollama", "ollama", "gemini", "groq"]):
        depose(c, f"{i:02x}" + "0" * 62, f)
    (c / "quotas.json").write_text('{"jour": {}}')  # journal de quotas : à la racine du cache
    return c


def noms(c):
    return sorted(p.name for p in c.glob("??/*.json"))


# --------------------------------------------------------------------------- comportement normal
def test_purge_d_un_fournisseur_ne_touche_que_ses_entrees_et_le_journal_de_quotas(cache, capsys):
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0
    out = capsys.readouterr().out
    assert "2 entrée(s) supprimée(s)" in out and str(cache) in out
    restant = [json.loads((p).read_text())["fournisseur"] for p in cache.glob("??/*.json")]
    assert sorted(restant) == ["gemini", "groq"]
    assert (cache / "quotas.json").read_text() == '{"jour": {}}'


def test_purge_idempotente_et_dossier_inexistant(cache, tmp_path, capsys):
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0
    capsys.readouterr()
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0
    assert "0 entrée(s)" in capsys.readouterr().out
    assert main(["purge-cache", "ollama", "--dir", str(tmp_path / "absent")]) == 0
    assert not (tmp_path / "absent").exists()  # n'est pas créé


def test_purge_all_et_fournisseur_inconnu(cache, capsys):
    assert main(["purge-cache", "inconnu", "--dir", str(cache)]) == 0
    assert len(noms(cache)) == 4
    assert main(["purge-cache", "--all", "--dir", str(cache)]) == 0
    assert noms(cache) == [] and (cache / "quotas.json").exists()
    assert "4 entrée(s)" in capsys.readouterr().out


def test_usage_incorrect_code_2_et_aucune_suppression(cache):
    for argv in (
        ["purge-cache"],
        ["purge-cache", "--dir"],
        ["purge-cache", "--dir", str(cache)],
        [],
    ):
        with pytest.raises(SystemExit) as e:
            main(argv)
        assert e.value.code == 2
    assert len(noms(cache)) == 4


def test_purge_le_nom_du_fournisseur_n_est_jamais_un_chemin(cache):
    assert main(["purge-cache", "../../etc", "--dir", str(cache)]) == 0
    assert len(noms(cache)) == 4


def test_purge_ollama_avec_all_purge_tout_silencieusement_constat(cache):
    """Constat (mineur) : `purge-cache ollama --all` purge TOUS les fournisseurs sans avertir."""
    assert main(["purge-cache", "ollama", "--all", "--dir", str(cache)]) == 0
    assert noms(cache) == []


def test_la_commande_s_execute_comme_module(cache):
    r = subprocess.run(
        [sys.executable, "-m", "amundi_agentic.llm", "purge-cache", "gemini", "--dir", str(cache)],
        capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": "0"}, check=False,
    )  # fmt: skip
    assert r.returncode == 0 and "1 entrée(s)" in r.stdout and r.stderr == ""


# --------------------------------------------------------------------------- sécurité
@pytest.mark.xfail(
    strict=True,
    reason=(
        "BLOQUANT : DiskCache.purge suit les liens symboliques de sous-dossiers (glo"
        "b) : un fichier JSON EXTERIEUR au dossier de cache est supprimé"
    ),
)
def test_un_lien_symbolique_vers_l_exterieur_n_entraine_aucune_suppression_hors_du_cache(
    cache, tmp_path
):
    hors = tmp_path / "hors"
    hors.mkdir()
    precieux = hors / "utilisateur.json"
    precieux.write_text(entree("ollama", precieux="oui"))
    os.symlink(hors, cache / "zz")  # sous-dossier « zz » : lien vers un dossier extérieur
    main(["purge-cache", "ollama", "--dir", str(cache)])
    assert precieux.exists(), "SUPPRESSION HORS DU DOSSIER DE CACHE via un lien symbolique"


def test_un_lien_symbolique_de_fichier_ne_supprime_pas_la_cible(cache, tmp_path):
    cible = tmp_path / "cible.json"
    cible.write_text(entree("ollama"))
    d = cache / "zy"
    d.mkdir()
    os.symlink(cible, d / ("b" * 64 + ".json"))
    main(["purge-cache", "ollama", "--dir", str(cache)])
    assert cible.exists()  # seul le lien peut disparaître


@pytest.mark.xfail(
    strict=True,
    reason=(
        "IMPORTANT : purge supprime tout ??/*.json (illisible, non dict, ou dict ave"
        "c une clé fournisseur) sans vérifier le nom SHA-256"
    ),
)
def test_ne_supprime_que_des_fichiers_de_cache_nommes_par_leur_cle(cache):
    d = cache / "ab"
    d.mkdir(exist_ok=True)
    autres = {
        "notes.json": "[1, 2]",  # JSON non dict
        "mes_notes.json": entree("ollama", titre="notes perso"),  # dict avec la clé « fournisseur »
        "casse.json": "{pas du json",
        "readme.json": json.dumps({"fournisseur": "ollama"}),
    }
    for nom, contenu in autres.items():
        (d / nom).write_text(contenu)
    main(["purge-cache", "ollama", "--dir", str(cache)])
    survivants = {n for n in autres if (d / n).exists()}
    assert survivants == set(autres), f"fichiers étrangers supprimés : {set(autres) - survivants}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "IMPORTANT : aucune garde sur --dir : sur un répertoire personnel ou tout do"
        "ssier à sous-dossiers de deux lettres, des JSON étrangers sont supprimés"
    ),
)
def test_une_purge_ne_vise_pas_un_dossier_qui_n_est_pas_un_cache_llm(tmp_path, monkeypatch):
    """`--dir` sur un répertoire personnel ou un dossier quelconque contenant des sous-dossiers à
    deux lettres (ex. `go/`) ne doit rien supprimer : seul un dossier de cache est purgé."""
    home = tmp_path / "home"
    (home / "go").mkdir(parents=True)
    projet = home / "go" / "config.json"
    projet.write_text(entree("ollama", reglage="perso"))
    monkeypatch.setenv("HOME", str(home))
    main(["purge-cache", "ollama", "--dir", str(home)])
    assert projet.exists(), "SUPPRESSION dans un dossier qui n'est pas un cache LLM"


def test_dir_avec_remontee_de_chemin_ne_sort_pas_du_cache_configure(cache, tmp_path):
    frere = tmp_path / "frere"
    depose(frere, "cd" + "0" * 62, "ollama")
    main(["purge-cache", "ollama", "--dir", str(cache / ".." / "frere")])
    # `--dir` désigne explicitement un autre dossier de cache : suppression ciblée de CE dossier
    assert not list(frere.glob("??/*.json")) and len(noms(cache)) == 4
