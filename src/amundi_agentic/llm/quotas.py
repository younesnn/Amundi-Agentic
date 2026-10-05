"""Journal des quotas par fournisseur et par jour, alerte avant la limite (EX-NF-03).

Les limites viennent de `config/llm.yaml` (section `quotas`) ; `null` signifie « non relevée » :
aucune alerte ni attente n'est alors possible, et le journal ne fait que compter.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from amundi_agentic.llm.config import LLMConfig

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class _EtatVerrou:
    """Verrou réentrant d'un journal, partagé par tous les clients du processus."""

    __slots__ = ("rlock", "profondeur", "fd")

    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.profondeur = 0
        self.fd: int | None = None


_REGISTRE: dict[str, _EtatVerrou] = {}
_REGISTRE_LOCK = threading.Lock()


class QuotaJournal:
    """Compteurs persistants : {jour: {fournisseur: {requests, tokens_in, tokens_out, errors_429,
    alerts}}} et par modèle. Le fichier ne contient aucun secret."""

    _repli_signale = False

    def __init__(
        self,
        config: LLMConfig,
        path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self.path = path
        self._tz = ZoneInfo(config.quotas.day_timezone)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._fenetre: dict[str, deque[tuple[float, int]]] = {}  # modèle -> (instant, jetons)
        self.alertes: list[str] = []

    # ------------------------------------------------------------------ persistance

    def _jour(self) -> str:
        return self._clock().astimezone(self._tz).date().isoformat()

    def _lire(self) -> dict:
        """Journal complet, ou {} s'il est absent, illisible ou de forme inattendue ; les
        sous-niveaux de forme inattendue sont écartés (jamais d'exception)."""
        try:
            brut = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
            return {}
        if not isinstance(brut, dict):
            return {}
        return {
            jour: {k: v for k, v in cles.items() if isinstance(v, dict)}
            for jour, cles in brut.items()
            if isinstance(cles, dict)
        }

    def _ecrire(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _entree(data: dict, jour: str, cle: str) -> dict:
        return data.setdefault(jour, {}).setdefault(
            cle, {"requests": 0, "tokens_in": 0, "tokens_out": 0, "errors_429": 0, "alerts": []}
        )

    # ------------------------------------------------------------------ API

    def usage(self, fournisseur: str, jour: date | None = None) -> dict:
        j = (jour or self._clock().astimezone(self._tz).date()).isoformat()
        return dict(self._lire().get(j, {}).get(fournisseur, {}))

    def before_call(self, fournisseur: str, model: str) -> None:
        """Attend si la limite par minute (requêtes ou jetons) relevée est atteinte."""
        lim = self._config.limits_for(fournisseur, model)
        if lim.requests_per_minute is None and lim.tokens_per_minute is None:
            return
        fen = self._fenetre.setdefault(model, deque())
        while True:
            maintenant = self._monotonic()
            while fen and maintenant - fen[0][0] >= 60:
                fen.popleft()
            nb = len(fen)
            jetons = sum(t for _, t in fen)
            rpm_plein = lim.requests_per_minute is not None and nb >= lim.requests_per_minute
            tpm_plein = lim.tokens_per_minute is not None and jetons >= lim.tokens_per_minute
            if not (rpm_plein or tpm_plein) or not fen:
                return
            attente = 60 - (maintenant - fen[0][0])
            log.info("quota par minute atteint pour %s : attente de %.0f s", fournisseur, attente)
            self._sleep(max(attente, 0.0))
            if self._monotonic() - maintenant < attente:  # horloge simulée : sortir de la boucle
                fen.clear()

    def _version(self) -> tuple[int, int, int] | None:
        """Empreinte du fichier (mtime, taille, inode) : l'écriture par remplacement change
        l'inode, donc toute écriture concurrente est détectée."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    @contextmanager
    def _verrou_fichier(self) -> Iterator[None]:
        """Verrou exclusif bref pour tout le cycle lecture, incrément, écriture.

        - entre processus : `flock` sur le dossier du journal (pas de fichier annexe) ;
        - dans un processus : un verrou réentrant par journal, partagé entre clients et threads
          (un second `flock` du même processus sur un autre descripteur bloquerait) ;
        - repli explicite sans `fcntl` (Windows) : verrou de processus seulement, avec un
          avertissement unique ; deux processus simultanés peuvent alors perdre un incrément.
        """
        cle = str(self.path.resolve())
        with _REGISTRE_LOCK:
            etat = _REGISTRE.setdefault(cle, _EtatVerrou())
        with etat.rlock:
            etat.profondeur += 1
            try:
                if etat.profondeur == 1:
                    if fcntl is None:
                        if not QuotaJournal._repli_signale:
                            QuotaJournal._repli_signale = True
                            log.warning("fcntl indisponible : quotas sans verrou inter-processus")
                    else:
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        etat.fd = os.open(self.path.parent, os.O_RDONLY)
                        fcntl.flock(etat.fd, fcntl.LOCK_EX)
                yield
            finally:
                etat.profondeur -= 1
                if etat.profondeur == 0 and etat.fd is not None:
                    fd, etat.fd = etat.fd, None
                    os.close(fd)  # libère le verrou

    def record(
        self,
        fournisseur: str,
        model: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error_429: bool = False,
    ) -> str | None:
        """Compte un appel parti chez le fournisseur ; renvoie un message d'alerte au premier
        franchissement du seuil dans la journée, sinon None.

        Tout le cycle (relecture, incrément, écriture atomique par remplacement) se fait sous
        le verrou exclusif : aucun réessai, aucune limite, aucun incrément perdu."""
        with self._lock, self._verrou_fichier():
            data = self._lire_sous_verrou()
            jour = self._jour()
            for cle in {fournisseur, model}:
                e = self._entree(data, jour, cle)
                e["requests"] += 1
                e["tokens_in"] += tokens_in
                e["tokens_out"] += tokens_out
                e["errors_429"] += int(error_429)
            alerte = self._alerte(data, jour, fournisseur, model)
            self._ecrire(data)
            if alerte:
                self.alertes.append(alerte)
                log.warning(alerte)
            self._fenetre.setdefault(model, deque()).append(
                (self._monotonic(), tokens_in + tokens_out)
            )
            return alerte

    def _lire_sous_verrou(self) -> dict:
        """Lecture sous verrou. Seul un écrivain du même processus, entré de façon réentrante
        pendant la lecture, peut avoir modifié le fichier : on relit alors (au plus 3 fois)."""
        data: dict = {}
        for _ in range(3):
            version = self._version()
            data = self._lire()
            if self._version() == version:
                break
        return data

    def _alerte(self, data: dict, jour: str, fournisseur: str, model: str) -> str | None:
        """Alerte à `alert_threshold` du quota journalier. Une limite propre au modèle se compare
        aux requêtes de ce modèle ; sinon, aux requêtes du fournisseur."""
        limites = self._config.quotas.limits
        cle = model if model in limites else fournisseur
        limite = self._config.limits_for(fournisseur, model).requests_per_day
        if limite is None:
            return None
        e = self._entree(data, jour, cle)
        if e["requests"] >= self._config.quotas.alert_threshold * limite and not e["alerts"]:
            message = (
                f"quota journalier de {cle} : {e['requests']}/{limite} requêtes "
                f"(seuil d'alerte {self._config.quotas.alert_threshold:.0%})"
            )
            e["alerts"].append(message)
            return message
        return None
