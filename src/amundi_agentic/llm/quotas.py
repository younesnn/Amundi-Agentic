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
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from amundi_agentic.llm.config import LLMConfig

log = logging.getLogger(__name__)


class QuotaJournal:
    """Compteurs persistants : {jour: {fournisseur: {requests, tokens_in, tokens_out, errors_429,
    alerts}}} et par modèle. Le fichier ne contient aucun secret."""

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
        self._lock = threading.Lock()
        self._fenetre: dict[str, deque[tuple[float, int]]] = {}  # modèle -> (instant, jetons)
        self.alertes: list[str] = []

    # ------------------------------------------------------------------ persistance

    def _jour(self) -> str:
        return self._clock().astimezone(self._tz).date().isoformat()

    def _lire(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

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
        franchissement du seuil dans la journée, sinon None."""
        with self._lock:
            data = self._lire()
            jour = self._jour()
            alerte = None
            for cle in {fournisseur, model}:
                e = self._entree(data, jour, cle)
                e["requests"] += 1
                e["tokens_in"] += tokens_in
                e["tokens_out"] += tokens_out
                e["errors_429"] += int(error_429)
            limite = self._config.limits_for(fournisseur, model).requests_per_day
            if limite is not None:
                e = self._entree(data, jour, fournisseur)
                if (
                    e["requests"] >= self._config.quotas.alert_threshold * limite
                    and not e["alerts"]
                ):
                    alerte = (
                        f"quota journalier de {fournisseur} : {e['requests']}/{limite} requêtes "
                        f"(seuil d'alerte {self._config.quotas.alert_threshold:.0%})"
                    )
                    e["alerts"].append(alerte)
                    self.alertes.append(alerte)
                    log.warning(alerte)
            self._ecrire(data)
            self._fenetre.setdefault(model, deque()).append(
                (self._monotonic(), tokens_in + tokens_out)
            )
            return alerte
