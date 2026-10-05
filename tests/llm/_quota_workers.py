"""Fonctions exécutées dans des processus fils (contexte `spawn`, importables) pour les tests de
concurrence du journal de quotas. Aucune attente sans délai : toute attente a un `timeout`."""

import os
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path

from amundi_agentic.llm import MockLLMClient, load_config
from amundi_agentic.llm import quotas as quotas_mod
from amundi_agentic.llm.quotas import QuotaJournal

JOUR = date(2024, 2, 1)


def horloge():
    return datetime(2024, 2, 1, tzinfo=UTC)


def travailleur(chemin, n, modele, jetons, sans_flock=False, pret=None, depart=None):
    if sans_flock:
        quotas_mod.fcntl.flock = lambda fd, op: None  # neutralise le verrou de fichier (test)
    j = QuotaJournal(load_config(), Path(chemin), clock=horloge)
    if pret is not None:
        pret.set()
    if depart is not None:
        depart.wait(60)  # départ simultané, borné
    for _ in range(n):
        j.record("gemini", modele, tokens_in=jetons)


def travailleur_clients(chemin, cache, n_clients, n_appels, graine):
    """Plusieurs LLMClient (donc plusieurs QuotaJournal) par processus, en threads."""
    cfg = load_config()

    def un_client(k):
        c = MockLLMClient(cfg, profile="prod", cache_dir=cache, quota_journal=chemin, clock=horloge)
        for i in range(n_appels):
            c.complete([{"role": "user", "content": f"p{graine}-c{k}-{i}"}], date_donnees=JOUR)

    ths = [threading.Thread(target=un_client, args=(k,), daemon=True) for k in range(n_clients)]
    [t.start() for t in ths]
    [t.join(120) for t in ths]


def boucle_infinie(chemin, pret):
    """Compte sans fin jusqu'à être tué (kill -9) ; s'arrête seul après 120 s au pire."""
    j = QuotaJournal(load_config(), Path(chemin), clock=horloge)
    pret.set()
    fin = time.time() + 120
    while time.time() < fin:
        j.record("gemini", "gemini/m", tokens_in=1)


def tenir_verrou(dossier, pret, arret):
    """Prend le flock exclusif sur `dossier`, le garde jusqu'à `arret` (60 s au plus)."""
    import fcntl

    fd = os.open(dossier, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    pret.set()
    arret.wait(60)
    os.close(fd)


def record_puis_signaler(chemin, demarre, fini):
    """`demarre` : signalé juste avant `record` (le journal est construit, le fils est prêt) ;
    `fini` : signalé quand `record` a rendu la main."""
    j = QuotaJournal(load_config(), Path(chemin), clock=horloge)
    demarre.set()
    j.record("gemini", "gemini/m", tokens_in=1)
    fini.set()
