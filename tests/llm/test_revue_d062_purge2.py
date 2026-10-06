"""Revue indépendante (2e passe) : sécurité de `purge-cache` après correction. Dossiers
temporaires uniquement ; `HOME` redirigé vers un dossier temporaire, jamais le vrai répertoire
personnel ; les refus de `/`, du dépôt et de son parent sont testés SANS purge réelle."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from amundi_agentic.llm.__main__ import main
from amundi_agentic.llm.cache import DiskCache

DEPOT = Path(__file__).resolve().parents[2]


def sha(c: str, n: int = 64) -> str:
    return (c * n)[:n]


def entree(fournisseur="ollama", **extra):
    return json.dumps({"text": "x", "modele_servi": "m", "fournisseur": fournisseur, **extra})


def depose(cache: Path, cle: str, fournisseur="ollama", contenu=None):
    d = cache / cle[:2]
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{cle}.json"
    f.write_text(contenu if contenu is not None else entree(fournisseur), encoding="utf-8")
    return f


@pytest.fixture
def cache(tmp_path):
    c = tmp_path / "cache"
    depose(c, sha("a"), "ollama")
    depose(c, sha("b"), "gemini")
    (c / "quotas.json").write_text("{}")
    return c


def restants(c):
    return sorted(p.parent.name + "/" + p.name[:6] for p in c.glob("??/*.json"))


# --------------------------------------------------------------------------- liens symboliques
def test_lien_de_fichier_ni_suivi_ni_supprime_ni_sa_cible(cache, tmp_path):
    cible = tmp_path / "cible.json"
    cible.write_text(entree("ollama"))
    d = cache / "cc"
    d.mkdir()
    lien = d / (sha("c") + ".json")
    os.symlink(cible, lien)
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0
    assert cible.exists() and lien.is_symlink()  # jamais suivi, jamais supprimé
    assert not (cache / "aa" / (sha("a") + ".json")).exists()  # l'entrée valide, elle, est purgée


def test_lien_de_dossier_porte_un_nom_valide_vers_l_exterieur(cache, tmp_path):
    hors = tmp_path / "hors"
    hors.mkdir()
    precieux = hors / (sha("d") + ".json")  # nom valide ET préfixe valide ("dd")
    precieux.write_text(entree("ollama"))
    os.symlink(hors, cache / "dd")
    assert main(["purge-cache", "--all", "--dir", str(cache)]) == 0
    assert precieux.exists()


def test_dossier_de_cache_lui_meme_lien_symbolique_refuse(cache, tmp_path, capsys):
    lien = tmp_path / "lien_cache"
    os.symlink(cache, lien)
    assert main(["purge-cache", "ollama", "--dir", str(lien)]) == 3
    assert "lien symbolique" in capsys.readouterr().err
    assert len(restants(cache)) == 2


def test_lien_vers_un_dossier_etranger_a_la_racine_est_toleré_jamais_suivi(cache, tmp_path):
    hors = tmp_path / "hors"
    hors.mkdir()
    (hors / "x.json").write_text(entree("ollama"))
    os.symlink(hors, cache / "lien-etranger")
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0
    assert (hors / "x.json").exists()


# --------------------------------------------------------------------------- noms et contenus trompeurs
@pytest.mark.parametrize(
    "dossier,nom",
    [
        ("ab", sha("c") + ".json"),  # préfixe différent du sous-dossier
        ("cc", sha("c").upper() + ".json"),  # majuscules
        ("cc", sha("c", 63) + ".json"),  # 63 caractères
        ("cc", sha("c", 65) + ".json"),  # 65 caractères
        ("cc", sha("c") + ".json.bak"),
        ("cc", sha("c")),  # sans extension
        ("cc", ".tmp-" + sha("c") + ".json"),
        ("cc", "x" + sha("c") + ".json"),
        ("cc", sha("c").replace("c", "g") + ".json"),  # non hexadécimal
    ],
)
def test_noms_trompeurs_jamais_supprimes(cache, dossier, nom):
    d = cache / dossier
    d.mkdir(exist_ok=True)
    f = d / nom
    f.write_text(entree("ollama"))
    main(["purge-cache", "ollama", "--dir", str(cache)])
    assert f.exists(), nom


@pytest.mark.parametrize(
    "contenu",
    [
        "[1, 2]", "3", "null", "{pas du json", "",
        json.dumps({"fournisseur": "ollama"}),  # sans modele_servi ni text
        json.dumps({"modele_servi": "m", "fournisseur": "ollama"}),  # sans text ni vectors
        json.dumps({"text": "x", "modele_servi": "m"}),  # sans fournisseur
        json.dumps({"text": "x", "modele_servi": "m", "fournisseur": 3}),  # fournisseur non texte
        json.dumps({"text": "x", "modele_servi": "m", "fournisseur": None}),
    ],
)  # fmt: skip
def test_json_etranger_au_nom_d_une_cle_n_est_jamais_supprime(cache, contenu):
    f = depose(cache, sha("e"), contenu=contenu)
    main(["purge-cache", "--all", "--dir", str(cache)])
    assert f.exists()


def test_entree_d_embedding_valide_est_purgee_et_comptee(cache, capsys):
    depose(
        cache,
        sha("f"),
        contenu=json.dumps({"vectors": [[0.1]], "modele_servi": "e", "fournisseur": "ollama"}),
    )
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0
    out = capsys.readouterr().out
    assert "2 entrée(s)" in out and "ollama : 2" in out


def test_fichier_geant_ignore(cache, monkeypatch):
    import amundi_agentic.llm.cache as mod

    monkeypatch.setattr(mod, "_TAILLE_MAX", 10)
    f = depose(cache, sha("9"))
    main(["purge-cache", "--all", "--dir", str(cache)])
    assert f.exists()


# --------------------------------------------------------------------------- garde --dir
def test_dossier_avec_un_fichier_etranger_a_la_racine_refuse_rien_supprime(cache, capsys):
    (cache / "readme.txt").write_text("à moi")
    assert main(["purge-cache", "--all", "--dir", str(cache)]) == 3
    assert "fichier étranger" in capsys.readouterr().err
    assert len(restants(cache)) == 2


def test_dossier_avec_un_sous_dossier_etranger_refuse(cache, capsys):
    (cache / "projets").mkdir()
    assert main(["purge-cache", "--all", "--dir", str(cache)]) == 3
    assert "sous-dossier étranger" in capsys.readouterr().err
    assert len(restants(cache)) == 2


def test_fichiers_toleres_a_la_racine(cache):
    (cache / ".DS_Store").write_text("x")
    (cache / "quotas.json.lock").write_text("")
    assert main(["purge-cache", "--all", "--dir", str(cache)]) == 0
    assert restants(cache) == [] and (cache / "quotas.json").exists()


def test_dossier_vide_et_dossier_inexistant(tmp_path, capsys):
    vide = tmp_path / "vide"
    vide.mkdir()
    assert main(["purge-cache", "ollama", "--dir", str(vide)]) == 0
    assert main(["purge-cache", "ollama", "--dir", str(tmp_path / "absent")]) == 0
    assert capsys.readouterr().out.count("0 entrée(s)") == 2


def test_remontee_de_chemin_vers_le_parent_est_refusee_sans_rien_supprimer(cache, tmp_path, capsys):
    assert (
        main(["purge-cache", "--all", "--dir", str(cache / "..")]) == 3
    )  # parent : « cache » étranger
    assert len(restants(cache)) == 2
    assert main(["purge-cache", "--all", "--dir", str(cache / ".." / "cache")]) == 0  # même cache


def test_repertoire_personnel_et_ses_ancetres_refuses(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home" / "moi"
    (home / "go").mkdir(parents=True)
    projet = home / "go" / (sha("a") + ".json")
    projet.write_text(entree("ollama"))
    (home / "ab").mkdir()
    valide = home / "ab" / (sha("a") + ".json")  # ressemble à une entrée valide
    valide.write_text(entree("ollama"))
    monkeypatch.setenv("HOME", str(home))
    assert Path.home() == home
    for cible in (home, home.parent, tmp_path):
        assert main(["purge-cache", "--all", "--dir", str(cible)]) == 3, cible
    assert valide.exists() and projet.exists()
    assert "n'est pas un dossier de cache" in capsys.readouterr().err


def test_racine_depot_et_parent_du_depot_refuses_sans_purge_reelle():
    for cible in (Path("/"), DEPOT, DEPOT.parent, Path.home(), Path.home().parent):
        refus = DiskCache(cible).refus_purge()
        assert refus is not None, cible


def test_le_dossier_de_cache_par_defaut_du_depot_est_accepte(tmp_path):
    """`.cache/llm` sous le dépôt (sous-dossier du dépôt) reste purgeable ; on vérifie la garde sur
    une copie temporaire de même forme, sans toucher au vrai cache."""
    c = tmp_path / ".cache" / "llm"
    depose(c, sha("a"))
    assert DiskCache(c).refus_purge() is None


# --------------------------------------------------------------------------- idempotence, concurrence
def test_idempotence_et_ecriture_concurrente_de_cache(cache):
    ecrit = []
    stop = threading.Event()

    def ecrivain():
        dc = DiskCache(cache)
        i = 0
        while not stop.is_set() and i < 300:
            cle = f"{i:02x}".rjust(2, "0") + sha("7")[2:]
            dc.put(cle, {"text": "x", "modele_servi": "m", "fournisseur": "gemini"})
            ecrit.append(cle)
            i += 1

    t = threading.Thread(target=ecrivain, daemon=True)
    t.start()
    for _ in range(30):
        assert main(["purge-cache", "ollama", "--dir", str(cache)]) in (0, 3)
    stop.set()
    t.join(30)
    assert not t.is_alive()
    # aucune entrée gemini écrite n'a été supprimée, aucun fichier partiel laissé lisible
    for cle in ecrit:
        f = cache / cle[:2] / f"{cle}.json"
        assert f.exists(), cle
        assert json.loads(f.read_text())["fournisseur"] == "gemini"
    assert main(["purge-cache", "ollama", "--dir", str(cache)]) == 0  # idempotent


def test_all_annonce_ce_qu_il_purge_avec_le_detail_par_fournisseur(cache, capsys):
    depose(cache, sha("1"), "groq")
    assert main(["purge-cache", "--all", "--dir", str(cache)]) == 0
    out = capsys.readouterr().out
    assert "TOUS les fournisseurs" in out and "3 entrée(s)" in out
    for f in ("gemini : 1", "groq : 1", "ollama : 1"):
        assert f in out
