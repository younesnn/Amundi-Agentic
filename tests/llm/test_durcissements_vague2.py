# ruff: noqa: E501
"""Durcissements hérités des revues : limites strictement entières, `fork`, fichiers `.tmp-*` orphelins.

Tous les délais sont bornés ; le test de `fork` tourne dans un sous-processus séparé (aucun `fork`
dans le processus de pytest).
"""

import os
import subprocess
import sys
import textwrap
import time

import pytest

from amundi_agentic.llm import ConfigurationError, load_config
from amundi_agentic.llm import quotas as quotas_mod
from amundi_agentic.llm.quotas import QuotaJournal

GROQ = "groq/openai/gpt-oss-120b"


# --------------------------------------------------------------------------- StrictInt
@pytest.mark.parametrize("champ", ["requests_per_day", "requests_per_minute", "tokens_per_minute"])
@pytest.mark.parametrize("valeur", [True, False, 1.5, "10", 0, -3])
def test_limite_non_entiere_ou_non_positive_refusee(champ, valeur):
    with pytest.raises(ConfigurationError):
        load_config(overrides={"quotas": {"limits": {GROQ: {champ: valeur}}}})


def test_limites_entieres_ou_nulles_acceptees():
    cfg = load_config(
        overrides={
            "quotas": {"limits": {GROQ: {"requests_per_day": 12, "tokens_per_minute": None}}}
        }
    )
    assert cfg.quotas.limits[GROQ].requests_per_day == 12
    assert cfg.quotas.limits[GROQ].tokens_per_minute is None


# --------------------------------------------------------------------------- fichiers orphelins
def _journal(tmp_path):
    return QuotaJournal(load_config(), tmp_path / "q" / "quotas.json")


def test_tmp_orphelins_anciens_supprimes_au_demarrage(tmp_path):
    dossier = tmp_path / "q"
    dossier.mkdir()
    vieux = dossier / ".tmp-abandonne.json"
    vieux.write_text("{")
    ancien = time.time() - 7200
    os.utime(vieux, (ancien, ancien))
    recent = dossier / ".tmp-en-cours.json"  # écriture d'un autre processus peut-être en cours
    recent.write_text("{}")
    autre = dossier / "notes.txt"
    autre.write_text("à garder")
    donnees = dossier / "quotas.json"
    donnees.write_text("{}")
    _journal(tmp_path)
    assert not vieux.exists()
    assert recent.exists() and autre.exists() and donnees.exists()


def test_demarrage_sans_dossier_ne_leve_pas(tmp_path):
    _journal(tmp_path)  # le dossier du journal n'existe pas encore


def test_ecriture_normale_ne_laisse_aucun_tmp(tmp_path):
    j = _journal(tmp_path)
    j.record("groq", GROQ, tokens_in=1)
    assert list((tmp_path / "q").glob(".tmp-*")) == []


# --------------------------------------------------------------------------- fork
def test_reinitialisation_apres_fork_vide_registre_et_verrou():
    quotas_mod._REGISTRE["x"] = quotas_mod._EtatVerrou()
    ancien = quotas_mod._REGISTRE_LOCK
    quotas_mod._reinitialiser_apres_fork()
    assert quotas_mod._REGISTRE == {}
    assert quotas_mod._REGISTRE_LOCK is not ancien
    assert not quotas_mod._REGISTRE_LOCK.locked()


def test_fork_pendant_qu_un_thread_tient_le_verrou_ne_bloque_pas(tmp_path):
    script = textwrap.dedent(
        f"""
        import os, sys, threading, time
        from amundi_agentic.llm import load_config
        from amundi_agentic.llm import quotas as q

        j = q.QuotaJournal(load_config(), __import__("pathlib").Path({str(tmp_path / "f")!r}) / "q.json")
        j.record("groq", "m")  # crée l'entrée du registre
        pret, fin = threading.Event(), threading.Event()

        def tenir():
            with q._REGISTRE_LOCK:  # un thread du père tient le verrou global au moment du fork
                cle = str(j.path.resolve())
                etat = q._REGISTRE[cle]
                with etat.rlock:
                    pret.set()
                    fin.wait(30)

        t = threading.Thread(target=tenir, daemon=True)
        t.start()
        pret.wait(10)
        pid = os.fork()
        if pid == 0:  # fils : sans la réinitialisation, ce record bloquerait à jamais
            try:
                j.record("groq", "m")
                os._exit(0)
            except BaseException:
                os._exit(2)
        limite = time.monotonic() + 20
        code = None
        while time.monotonic() < limite:
            r, statut = os.waitpid(pid, os.WNOHANG)
            if r:
                code = os.waitstatus_to_exitcode(statut)
                break
            time.sleep(0.05)
        fin.set()
        if code is None:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            sys.exit(3)
        sys.exit(code)
        """
    )
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.returncode, r.stderr[-800:])
