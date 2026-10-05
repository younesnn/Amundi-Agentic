"""Revue indépendante : verrou du journal de quotas (inter-processus, threads, kill -9, perf).

Tous les processus fils sont en contexte `spawn` (pas de `fork` dans un processus multi-thread),
tous les délais sont bornés, et les fils sont toujours tués en fin de test (`finally`) : un test
de concurrence ne peut pas bloquer la CI.
"""

import json
import multiprocessing as mp
import os
import signal
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

# Les fils `spawn` réimportent le module des travailleurs : son dossier doit être sur sys.path.
sys.path.insert(0, str(Path(__file__).parent))
from _quota_workers import (  # noqa: E402
    JOUR,
    boucle_infinie,
    horloge,
    record_puis_signaler,
    tenir_verrou,
    travailleur,
    travailleur_clients,
)

from amundi_agentic.llm import MockLLMClient, load_config
from amundi_agentic.llm import quotas as quotas_mod
from amundi_agentic.llm.quotas import QuotaJournal

CTX = mp.get_context("spawn")
DELAI = 90  # secondes, par lot de processus


def _vide():
    return {"requests": 0, "tokens_in": 0, "tokens_out": 0, "errors_429": 0, "alerts": []}


@contextmanager
def processus(cibles):
    """Démarre les fils ; à la sortie, tout fil encore vivant est tué (jamais de fil orphelin)."""
    procs = [CTX.Process(target=f, args=a, daemon=True) for f, a in cibles]
    try:
        for p in procs:
            p.start()
        yield procs
    finally:
        for p in procs:
            if p.is_alive():
                p.kill()
            p.join(10)


def attendre(procs, delai=DELAI):
    """Attend tous les fils au plus `delai` s ; échec explicite (et fils tués) si dépassement."""
    fin = time.monotonic() + delai
    for p in procs:
        p.join(max(0.0, fin - time.monotonic()))
    vivants = [p.pid for p in procs if p.is_alive()]
    if vivants:
        for p in procs:
            p.kill()
        pytest.fail(
            f"processus toujours en vie après {delai} s (blocage ou verrou orphelin) : {vivants}"
        )
    return [p.exitcode for p in procs]


@pytest.mark.parametrize("n_proc,n_req,essais", [(6, 80, 3), (8, 100, 2)])
def test_processus_multiples_aucun_compte_perdu_ni_crash(tmp_path, n_proc, n_req, essais):
    for e in range(essais):
        chemin = tmp_path / f"q{e}.json"
        cibles = [
            (travailleur, (str(chemin), n_req, f"gemini/m{i % 2}", i + 1)) for i in range(n_proc)
        ]
        with processus(cibles) as procs:
            codes = attendre(procs)
        assert all(c == 0 for c in codes), (e, codes)
        u = QuotaJournal(load_config(), chemin, clock=horloge).usage("gemini", JOUR)
        assert u["requests"] == n_proc * n_req, (e, u["requests"])
        assert u["tokens_in"] == n_req * sum(range(1, n_proc + 1))
        assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp")]


def test_plusieurs_llmclient_par_processus_en_threads_et_en_processus(tmp_path):
    chemin = tmp_path / "q.json"
    cible = [
        (travailleur_clients, (str(chemin), str(tmp_path / "cache"), 3, 8, g)) for g in range(3)
    ]
    with processus(cible) as procs:
        codes = attendre(procs)
    assert all(c == 0 for c in codes), codes
    j = QuotaJournal(load_config(), chemin, clock=horloge)
    total = sum(j.usage(f, JOUR).get("requests", 0) for f in ("gemini", "ollama", "groq"))
    assert total == 3 * 3 * 8


def test_clients_locaux_en_threads_pendant_que_des_processus_comptent(tmp_path):
    chemin = tmp_path / "q.json"
    cfg = load_config()
    clients = [
        MockLLMClient(
            cfg, profile="prod", cache_dir=tmp_path / f"c{k}", quota_journal=chemin, clock=horloge
        )
        for k in range(3)
    ]

    def boucle(k):
        for i in range(20):
            clients[k].complete([{"role": "user", "content": f"{k}-{i}"}], date_donnees=JOUR)

    ths = [threading.Thread(target=boucle, args=(k,), daemon=True) for k in range(3)]
    with processus([(travailleur, (str(chemin), 40, "gemini/p", 1)) for _ in range(2)]) as procs:
        [t.start() for t in ths]
        [t.join(DELAI) for t in ths]
        assert not any(t.is_alive() for t in ths), "thread bloqué sur le journal"
        codes = attendre(procs)
    assert all(c == 0 for c in codes)
    j = QuotaJournal(cfg, chemin, clock=horloge)
    assert j.usage("gemini", JOUR)["requests"] == 3 * 20 + 2 * 40


def test_meme_processus_plusieurs_clients_en_threads_aucun_compte_perdu(tmp_path):
    cfg = load_config()
    chemin = tmp_path / "q.json"
    clients = [
        MockLLMClient(
            cfg, profile="prod", cache_dir=tmp_path / f"c{k}", quota_journal=chemin, clock=horloge
        )
        for k in range(4)
    ]

    def boucle(k):
        for i in range(25):
            clients[k].complete([{"role": "user", "content": f"{k}-{i}"}], date_donnees=JOUR)

    ths = [threading.Thread(target=boucle, args=(k,), daemon=True) for k in range(4)]
    [t.start() for t in ths]
    [t.join(DELAI) for t in ths]
    assert not any(t.is_alive() for t in ths)
    assert QuotaJournal(cfg, chemin, clock=horloge).usage("gemini", JOUR)["requests"] == 100


def test_kill_9_pendant_l_ecriture_pas_de_fichier_tronque_ni_verrou_orphelin(tmp_path):
    chemin = tmp_path / "q.json"
    QuotaJournal(load_config(), chemin, clock=horloge)._ecrire(
        {"2024-02-01": {f"gemini/m{i}": _vide() for i in range(2000)}}  # écriture plus longue
    )
    precedent = 0
    for _ in range(4):
        pret = CTX.Event()
        with processus([(boucle_infinie, (str(chemin), pret))]) as (p,):
            assert pret.wait(60), "le fils n'a pas démarré"
            time.sleep(0.2)
            os.kill(p.pid, signal.SIGKILL)
            p.join(30)
            assert p.exitcode == -signal.SIGKILL
        data = json.loads(chemin.read_text())  # jamais tronqué : JSON complet
        compte = data["2024-02-01"]["gemini"]["requests"]
        assert compte >= precedent
        # pas de verrou orphelin : un autre processus passe, borné
        with processus([(travailleur, (str(chemin), 1, "gemini/m", 1))]) as procs:
            assert attendre(procs, 30) == [0]
        precedent = compte + 1
        assert json.loads(chemin.read_text())["2024-02-01"]["gemini"]["requests"] == precedent
    # une mort en cours d'écriture peut laisser un `.tmp-*` ; jamais un journal tronqué
    assert chemin.exists()


def test_verrou_libere_par_le_noyau_a_la_mort_du_processus_qui_le_tient(tmp_path):
    pret, arret = CTX.Event(), CTX.Event()
    with processus([(tenir_verrou, (str(tmp_path), pret, arret))]) as (p,):
        assert pret.wait(60), "le fils n'a pas pris le verrou"
        os.kill(p.pid, signal.SIGKILL)
        p.join(30)
        j = QuotaJournal(load_config(), tmp_path / "q.json", clock=horloge)
        debut = time.monotonic()
        j.record("gemini", "gemini/m")  # ne doit pas attendre un verrou orphelin
        assert time.monotonic() - debut < 10
    assert j.usage("gemini", JOUR)["requests"] == 1


def test_le_verrou_bloque_un_autre_processus_tant_qu_il_est_tenu_puis_le_laisse_passer(tmp_path):
    """Preuve bornée de l'exclusion : le détenteur est un processus à part (un `fork` ferait
    hériter le descripteur et empêcherait la libération : cause du blocage du premier essai)."""
    pret, arret, fini = CTX.Event(), CTX.Event(), CTX.Event()
    chemin = tmp_path / "q.json"
    with processus([(tenir_verrou, (str(tmp_path), pret, arret))]) as (detenteur,):
        assert pret.wait(60), "le détenteur n'a pas pris le verrou"
        with processus([(record_puis_signaler, (str(chemin), fini))]) as (worker,):
            assert not fini.wait(3.0), "record() a passé alors que le verrou était tenu"
            assert worker.is_alive()
            arret.set()  # le détenteur libère
            assert fini.wait(60), "record() n'a pas repris après la libération du verrou"
            attendre([worker], 30)
        detenteur.join(30)
    assert QuotaJournal(load_config(), chemin, clock=horloge).usage("gemini", JOUR)["requests"] == 1


def test_journal_de_10000_entrees_verrou_rapide(tmp_path):
    chemin = tmp_path / "q.json"
    j = QuotaJournal(load_config(), chemin, clock=horloge)
    j._ecrire({"2024-02-01": {f"gemini/m{i}": _vide() for i in range(10_000)}})
    taille = chemin.stat().st_size
    n = 10
    t = time.perf_counter()
    for _ in range(n):
        j.record("gemini", "gemini/m1")
    moyenne = (time.perf_counter() - t) / n
    assert moyenne < 0.5, f"{moyenne:.3f} s par record pour {taille} octets"


def test_deux_processus_sur_un_journal_de_10000_entrees_restent_rapides(tmp_path):
    chemin = tmp_path / "q.json"
    QuotaJournal(load_config(), chemin, clock=horloge)._ecrire(
        {"2024-02-01": {f"gemini/m{i}": _vide() for i in range(10_000)}}
    )
    debut = time.monotonic()
    with processus([(travailleur, (str(chemin), 10, "gemini/m1", 1)) for _ in range(3)]) as procs:
        codes = attendre(procs)
    assert all(c == 0 for c in codes) and time.monotonic() - debut < 60
    j = QuotaJournal(load_config(), chemin, clock=horloge)
    assert j.usage("gemini", JOUR)["requests"] == 30


# --------------------------------------------------------------------------- sensibilité


def test_sans_flock_la_suite_detecte_la_perte_de_comptes(tmp_path):
    """Verrou de fichier neutralisé dans les fils : au moins un essai doit perdre des comptes ou
    planter, sinon les tests ci-dessus ne protégeraient pas le verrou."""
    if quotas_mod.fcntl is None:
        pytest.skip("fcntl indisponible")
    anomalie = False
    for e in range(4):
        chemin = tmp_path / f"q{e}.json"
        cibles = [(travailleur, (str(chemin), 120, "gemini/m", 1, True)) for _ in range(8)]
        with processus(cibles) as procs:
            codes = attendre(procs)
        try:
            n = QuotaJournal(load_config(), chemin, clock=horloge).usage("gemini", JOUR)["requests"]
        except Exception:
            n = -1
        if any(codes) or n != 8 * 120:
            anomalie = True
            break
    assert anomalie, "sans flock aucune perte observée : la suite ne détecte pas le retrait"
