"""`LLMClient` : point d'entrée unique de tout appel de modèle de langage (L1 3.3, EX-NF-14).

Deux modes (L1 11.1) :

- `interactif` : relais automatique sur 429 vers le modèle suivant de `fallback_order`, nouvelle
  tentative avec attente exponentielle sur 503 et timeout ;
- `evaluation` (D-024, EX-NF-13) : un seul modèle à version figée, aucun relais ; sur 429, pause
  puis `ExecutionPausee` (reprise depuis le cache) ; sur 503, nouvelles tentatives puis pause ;
  arrêt (`ModeleServiChange`) si le modèle servi change.

Ce module ne connaît aucun nom de modèle : les identifiants viennent de `config/llm.yaml`.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from amundi_agentic.llm.cache import DiskCache, cache_key
from amundi_agentic.llm.config import (
    ConfigurationError,
    LLMConfig,
    Profil,
    load_config,
    resolve_path,
)
from amundi_agentic.llm.quotas import QuotaJournal
from amundi_agentic.llm.redact import redact
from amundi_agentic.llm.transport import LiteLLMTransport
from amundi_agentic.llm.types import (
    EmbeddingResult,
    ExecutionPausee,
    FichierFigeCorrompu,
    LLMResult,
    Message,
    ModeleServiChange,
    PromptRef,
    ProviderError,
    QuotaEpuise,
    RawCompletion,
    RawEmbedding,
    StructuredOutputError,
    Transport,
    sha256_text,
)
from amundi_agentic.schemas import ExecutionRecord, ModeExecution

log = logging.getLogger(__name__)

_EMBED = "embed"


def _extraire_json(texte: str) -> str:
    """Retire les clôtures de code et le texte autour de l'objet JSON."""
    s = texte.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s.strip("`")
        s = s.rsplit("```", 1)[0]
    s = s.strip()
    if not s.startswith(("{", "[")):
        debut, fin = s.find("{"), s.rfind("}")
        if debut != -1 and fin > debut:
            s = s[debut : fin + 1]
    return s


def _erreurs_courtes(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        lignes = [f"{'.'.join(map(str, e['loc'])) or 'racine'} : {e['msg']}" for e in exc.errors()]
        return " ; ".join(lignes[:6])
    return str(exc)[:300]


class LLMClient:
    """Client LLM unique. `transport` est injectable (mock en test) ; par défaut LiteLLM."""

    def __init__(
        self,
        config: LLMConfig | None = None,
        *,
        mode: ModeExecution = "interactif",
        profile: Profil | None = None,
        transport: Transport | None = None,
        run_id: str = "adhoc",
        run_dir: Path | str | None = None,
        cache_dir: Path | str | None = None,
        quota_journal: Path | str | None = None,
        seed: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if mode not in ("interactif", "evaluation"):
            raise ValueError(f"mode inconnu : {mode!r}")
        self.config = config or load_config()
        self.mode: ModeExecution = mode
        if mode == "evaluation" and profile == "dev":
            raise ConfigurationError(
                "le mode évaluation exige le profil prod (modèles figés, D-024) ; "
                "le profil dev n'est autorisé qu'en mode interactif"
            )
        self.profile: Profil = profile or (
            "prod" if mode == "evaluation" else self.config.default_mode
        )
        self.run_id = run_id
        self.run_dir = Path(run_dir) if run_dir else None
        self.seed = self.config.defaults.seed if seed is None else seed
        self._transport = transport or LiteLLMTransport(self.config)
        self._sleep = sleep
        self._monotonic = monotonic
        self._clock = clock or (lambda: datetime.now(UTC))
        self.cache = DiskCache(
            Path(cache_dir) if cache_dir else resolve_path(self.config.cache.dir),
            enabled=self.config.cache.enabled,
        )
        self.quotas = QuotaJournal(
            self.config,
            Path(quota_journal) if quota_journal else resolve_path(self.config.quotas.journal),
            clock=self._clock,
            sleep=sleep,
            monotonic=monotonic,
        )
        self.records: list[ExecutionRecord] = []
        self._cooldown: dict[str, float] = {}
        self._lock = threading.Lock()
        self._fige: dict[str, str] = self._charger_fige()

    @property
    def _scope(self) -> str:
        return f"{self.mode}/{self.profile}"

    def _entree_acceptable(self, entree: dict[str, Any], modele_demande: str, champ: str) -> bool:
        """Une entrée de cache illisible, ou (en évaluation) produite par un relais ou par un
        autre modèle que celui du run, est ignorée : on relit auprès du fournisseur."""
        if champ not in entree:
            return False
        if self.mode == "evaluation":
            return (not entree.get("relais_utilise")) and entree.get("modele_demande") == (
                modele_demande
            )
        return True

    def _config_sha256(self) -> str:
        """Hash du fichier de config (ou de la config fusionnée) si la config vient de
        `load_config` ; sinon hash du JSON canonique de la configuration effective."""
        if self.config.source_sha256:
            return self.config.source_sha256
        canon = json.dumps(self.config.model_dump(mode="json"), sort_keys=True)
        return sha256_text(canon)

    def run_fields(self) -> dict[str, Any]:
        """Champs de `RunRecord` que le client connaît (le reste vient de l'appelant : commande,
        commit, uv.lock, pré-enregistrement)."""
        demandes = dict(self.config.evaluation.models)
        if self.profile in self.config.embeddings:
            demandes["embed"] = self.config.embeddings[self.profile]
        u = self.usage()
        return {
            "profile": self.profile,
            "mode": self.mode,
            "graine": self.seed,
            "modeles_demandes": demandes,
            "llm_config_sha256": self._config_sha256(),
            "modele_servi_fige": dict(self._fige) or None,
            "fin_entrainement": {n: self._fin_entrainement(m) for n, m in self._fige.items()},
            "usage": {"appels": u["appels"], "cache_hits": u["cache_hits"]},
        }

    # ------------------------------------------------------------------ API publique

    def complete(
        self,
        messages: Sequence[Message | Mapping[str, str]],
        *,
        date_donnees: date,
        tier: str = "main",
        schema: type[BaseModel] | None = None,
        agent: str = "adhoc",
        prompt_ref: PromptRef | None = None,
        seed: int | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Appel de complétion. Avec `schema`, la sortie est validée par Pydantic (`parsed`) ;
        une sortie invalide est redemandée au plus `defaults.structured_retries` fois."""
        msgs = [m if isinstance(m, Message) else Message.model_validate(dict(m)) for m in messages]
        graine = self.seed if seed is None else seed
        temp = self.config.defaults.temperature if temperature is None else temperature
        max_tok = max_tokens if max_tokens is not None else self.config.defaults.max_output_tokens
        chaine = self.config.chain(tier, mode=self.mode, profile=self.profile)
        schema_json = schema.model_json_schema() if schema else None
        ref = prompt_ref or PromptRef(
            prompt_id="adhoc",
            version="0",
            sha256=sha256_text(json.dumps([m.model_dump() for m in msgs], ensure_ascii=False)),
        )
        cle = cache_key(
            kind="chat",
            model=chaine[0][1],
            messages=[m.model_dump() for m in msgs],
            schema=schema_json,
            params={"temperature": temp, "seed": graine, "max_tokens": max_tok},
            date_donnees=date_donnees,
            scope=self._scope,
        )
        ctx = _Contexte(agent, ref, cle, graine, temp, date_donnees, chaine[0][1], tier)

        entree = self.cache.get(cle)
        if entree is not None and self._entree_acceptable(entree, chaine[0][1], "text"):
            parsed = None
            ok = True
            if schema is not None:
                try:
                    parsed = schema.model_validate_json(_extraire_json(entree["text"]))
                except (ValidationError, ValueError):
                    ok = False  # entrée devenue invalide : traitée comme absente
            if ok:
                rec = self._enregistrer_cache(entree, ctx, chaine[0][0], chaine[0][0])
                return LLMResult(entree["text"], parsed, rec)

        envoyes = self._avec_consigne_schema(msgs, schema_json) if schema else msgs
        tentatives: list[ExecutionRecord] = []
        retries = self.config.defaults.structured_retries if schema else 0
        derniere_erreur, dernier_texte = "", ""
        for _ in range(retries + 1):
            raw, rec, relais = self._invoquer(
                chaine, envoyes, ctx, max_tok, json_mode=schema is not None
            )
            tentatives.append(rec)
            parsed = None
            if schema is not None:
                try:
                    parsed = schema.model_validate_json(_extraire_json(raw.text))
                except (ValidationError, ValueError) as exc:
                    derniere_erreur, dernier_texte = _erreurs_courtes(exc), raw.text
                    log.info("sortie structurée invalide (%s), nouvelle tentative", agent)
                    envoyes = [
                        *envoyes,
                        Message(role="assistant", content=raw.text),
                        Message(
                            role="user",
                            content=(
                                "Ta réponse précédente est invalide : "
                                f"{derniere_erreur}. Renvoie uniquement l'objet JSON corrigé, "
                                "sans texte autour."
                            ),
                        ),
                    ]
                    continue
            self.cache.put(
                cle,
                {
                    "text": raw.text,
                    "modele_servi": rec.modele_servi,
                    "modele_demande": rec.modele_demande,
                    "fournisseur": rec.fournisseur,
                    "tier": rec.tier,
                    "relais_utilise": relais,
                    "tokens_entree": raw.tokens_in,
                    "tokens_sortie": raw.tokens_out,
                    "date_donnees": date_donnees.isoformat(),
                },
            )
            return LLMResult(raw.text, parsed, rec, tentatives[:-1])
        raise StructuredOutputError(
            f"sortie non conforme au schéma {schema.__name__ if schema else '?'} après "
            f"{retries + 1} tentative(s) : {derniere_erreur}",
            dernier_texte,
        )

    def complete_structured(
        self,
        schema: type[BaseModel],
        messages: Sequence[Message | Mapping[str, str]],
        **kwargs: Any,
    ) -> LLMResult:
        """`complete` avec un schéma Pydantic obligatoire ; `result.parsed` est une instance."""
        return self.complete(messages, schema=schema, **kwargs)

    def embed(
        self, texts: Sequence[str], *, date_donnees: date, agent: str = "embeddings"
    ) -> EmbeddingResult:
        """Embeddings (EX-NF-14) : même cache, mêmes quotas, même journal que `complete`."""
        textes = list(texts)
        modele = self.config.embedding_model(self.profile)
        fournisseur = modele.split("/", 1)[0]
        cle = cache_key(
            kind="embed",
            model=modele,
            messages=textes,
            schema=None,
            params={},
            date_donnees=date_donnees,
            scope=self._scope,
        )
        ref = PromptRef(
            prompt_id=_EMBED,
            version="0",
            sha256=sha256_text(json.dumps(textes, ensure_ascii=False)),
        )
        ctx = _Contexte(agent, ref, cle, self.seed, 0.0, date_donnees, modele, "embed")
        niveau = "dev" if self.profile == "dev" else "main"
        entree = self.cache.get(cle)
        if entree is not None and self._entree_acceptable(entree, modele, "vectors"):
            rec = self._enregistrer_cache(entree, ctx, niveau, _EMBED)
            return EmbeddingResult(entree["vectors"], rec)

        def appel() -> RawEmbedding:
            return self._transport.embedding(
                model=modele, inputs=textes, timeout=self.config.defaults.timeout_s
            )

        try:
            raw, latence = self._tenter(modele, fournisseur, _EMBED, appel, ctx, niveau, False)
        except ProviderError as exc:
            if exc.kind == "quota":
                raise QuotaEpuise("quota épuisé pour les embeddings (aucun relais)") from None
            raise
        rec = self._enregistrer(raw, ctx, niveau, modele, False, latence)
        vecteurs = raw.vectors
        self.cache.put(
            cle,
            {
                "vectors": vecteurs,
                "modele_servi": rec.modele_servi,
                "modele_demande": modele,
                "fournisseur": fournisseur,
                "tier": niveau,
                "relais_utilise": False,
                "tokens_entree": raw.tokens_in,
                "tokens_sortie": 0,
                "date_donnees": date_donnees.isoformat(),
            },
        )
        return EmbeddingResult(vecteurs, rec)

    def usage(self) -> dict[str, float]:
        """Totaux de l'exécution : appels réels, appels servis par le cache, jetons, coût (EUR)."""
        reels = [r for r in self.records if not r.cache_hit and r.erreur is None]
        return {
            "appels": len(reels),
            "cache_hits": sum(r.cache_hit for r in self.records),
            "erreurs": sum(r.erreur is not None for r in self.records),
            "tokens_entree": sum(r.tokens_entree for r in self.records),
            "tokens_sortie": sum(r.tokens_sortie for r in self.records),
            "cout_eur": sum(r.cout_eur for r in self.records),
        }

    @property
    def modeles_servis_figes(self) -> dict[str, str]:
        """Mode évaluation : modèle servi observé pour chaque niveau (gelé au premier appel)."""
        return dict(self._fige)

    # ------------------------------------------------------------------ internes

    @staticmethod
    def _avec_consigne_schema(msgs: list[Message], schema_json: dict | None) -> list[Message]:
        consigne = (
            "Réponds uniquement par un objet JSON valide, sans texte autour, conforme à ce "
            "JSON Schema :\n" + json.dumps(schema_json, ensure_ascii=False, sort_keys=True)
        )
        if msgs and msgs[0].role == "system":
            return [Message(role="system", content=msgs[0].content + "\n\n" + consigne), *msgs[1:]]
        return [Message(role="system", content=consigne), *msgs]

    def _invoquer(
        self,
        chaine: list[tuple[str, str]],
        msgs: list[Message],
        ctx: _Contexte,
        max_tokens: int | None,
        *,
        json_mode: bool,
    ) -> tuple[RawCompletion, ExecutionRecord, bool]:
        """Parcourt la chaîne de modèles ; renvoie (réponse, enregistrement, relais utilisé)."""
        dicts = [m.model_dump() for m in msgs]
        dernier_indice = len(chaine) - 1
        derniere_erreur: ProviderError | None = None
        for i, (niveau, modele) in enumerate(chaine):
            fournisseur = modele.split("/", 1)[0]
            if i < dernier_indice and self._monotonic() < self._cooldown.get(modele, 0.0):
                continue  # modèle récemment à court de quota : relais direct

            def appel(modele: str = modele) -> RawCompletion:
                return self._transport.completion(
                    model=modele,
                    messages=dicts,
                    temperature=ctx.temperature,
                    seed=ctx.graine,
                    max_tokens=max_tokens,
                    timeout=self.config.defaults.timeout_s,
                    json_mode=json_mode,
                )

            try:
                raw, latence = self._tenter(modele, fournisseur, niveau, appel, ctx, niveau, i > 0)
            except ProviderError as exc:
                derniere_erreur = exc
                if exc.kind == "quota":
                    self._cooldown[modele] = self._monotonic() + self.config.relay.cooldown_s
                    continue
                if (
                    exc.kind in ("unavailable", "timeout")
                    and self.config.relay.on_unavailable_exhausted
                ):
                    continue
                raise
            rec = self._enregistrer(raw, ctx, niveau, modele, i > 0, latence)
            return raw, rec, i > 0
        # Le dernier modèle n'est jamais ignoré : on n'arrive ici qu'après une erreur.
        if derniere_erreur is None or derniere_erreur.kind == "quota":
            raise QuotaEpuise(
                "quota épuisé sur tous les modèles de la chaîne de relais (mode interactif)"
            ) from None
        raise derniere_erreur

    def _tenter(
        self,
        modele: str,
        fournisseur: str,
        cle_fige: str,
        appel: Callable[[], Any],
        ctx: _Contexte,
        niveau_enreg: str,
        relais: bool,
    ) -> tuple[Any, int]:
        """Un modèle, avec nouvelles tentatives (503, timeout) et gestion du 429 selon le mode.

        Renvoie (réponse brute, latence en ms). Lève `ProviderError` quand ce modèle est
        définitivement inutilisable pour cette requête (mode interactif), `ExecutionPausee` en
        mode évaluation.
        """
        retry = self.config.retry
        tentative = 0
        pauses = 0
        while True:
            self.quotas.before_call(fournisseur, modele)
            debut = self._monotonic()
            try:
                raw = appel()
            except ProviderError as exc:
                latence = int((self._monotonic() - debut) * 1000)
                message = redact(exc)
                self._enregistrer_erreur(
                    ctx, niveau_enreg, modele, relais, latence, exc.kind, message
                )
                if exc.kind in ("quota", "unavailable", "timeout"):
                    self.quotas.record(fournisseur, modele, error_429=exc.kind == "quota")
                if exc.kind == "quota":
                    if self.mode == "evaluation":
                        if pauses < retry.pause_429_max_waits:
                            pauses += 1
                            log.warning(
                                "429 en mode évaluation : pause de %.0f s", retry.pause_429_wait_s
                            )
                            self._sleep(retry.pause_429_wait_s)
                            continue
                        raise ExecutionPausee(
                            "quota 429 persistant en mode évaluation : exécution mise en pause, "
                            "relancer la même commande pour reprendre depuis le cache",
                            "quota",
                        ) from None
                    raise ProviderError("quota", message, 429) from None
                if exc.kind in ("unavailable", "timeout"):
                    tentative += 1
                    if tentative < retry.max_attempts:
                        attente = min(
                            retry.backoff_base_s * retry.backoff_factor ** (tentative - 1),
                            retry.backoff_max_s,
                        )
                        log.info(
                            "%s indisponible (tentative %d) : attente %.1f s",
                            exc.kind,
                            tentative,
                            attente,
                        )
                        self._sleep(attente)
                        continue
                    if self.mode == "evaluation":
                        raise ExecutionPausee(
                            f"{exc.kind} persistant en mode évaluation après "
                            f"{retry.max_attempts} tentatives : exécution mise en pause",
                            exc.kind,
                        ) from None
                raise ProviderError(exc.kind, message, exc.status) from None
            latence = int((self._monotonic() - debut) * 1000)
            tokens_in = getattr(raw, "tokens_in", 0)
            tokens_out = getattr(raw, "tokens_out", 0)
            self.quotas.record(fournisseur, modele, tokens_in=tokens_in, tokens_out=tokens_out)
            try:
                self._verifier_modele_servi(cle_fige, getattr(raw, "model_served", ""))
            except ModeleServiChange as exc:
                self._enregistrer_erreur(
                    ctx,
                    niveau_enreg,
                    modele,
                    relais,
                    latence,
                    "modele_servi_change",
                    redact(exc),
                    servi=getattr(raw, "model_served", ""),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )
                raise
            return raw, latence

    # --- mode évaluation : modèle servi constant

    def _fichier_fige(self) -> Path | None:
        return self.run_dir / "modele_servi_fige.json" if self.run_dir else None

    def _charger_fige(self) -> dict[str, str]:
        """Mode évaluation : relit le gel d'un run repris. Un fichier illisible ou de forme
        inattendue arrête l'exécution (jamais de regel silencieux)."""
        chemin = self._fichier_fige()
        if self.mode != "evaluation" or chemin is None or not chemin.is_file():
            return {}
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise FichierFigeCorrompu(
                f"{chemin.name} illisible ({type(exc).__name__}) : run d'évaluation arrêté, "
                "ne pas regeler sur une version quelconque (EX-NF-13)"
            ) from None
        if not (
            isinstance(brut, dict)
            and all(isinstance(k, str) and isinstance(v, str) and v for k, v in brut.items())
        ):
            raise FichierFigeCorrompu(
                f"{chemin.name} de forme inattendue (attendu : niveau -> modèle servi) : "
                "run d'évaluation arrêté"
            )
        return dict(brut)

    def _ecrire_fige(self, chemin: Path) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._fige, f, sort_keys=True)
            os.replace(tmp, chemin)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _verifier_modele_servi(self, niveau: str, servi: str) -> None:
        if self.mode != "evaluation":
            return
        if not servi:
            raise ModeleServiChange(
                "réponse sans identifiant de modèle servi : constance invérifiable (EX-NF-13)"
            )
        with self._lock:
            attendu = self._fige.get(niveau)
            if attendu is None:
                self._fige[niveau] = servi
                chemin = self._fichier_fige()
                if chemin:
                    self._ecrire_fige(chemin)
            elif attendu != servi:
                raise ModeleServiChange(
                    f"le modèle servi du niveau {niveau!r} a changé en cours de run : "
                    f"{attendu!r} puis {servi!r} (mode évaluation, EX-NF-13) ; run arrêté"
                )

    # --- enregistrements

    def _cout(self, fournisseur: str, tokens_in: int, tokens_out: int) -> float:
        prix = self.config.pricing.get(fournisseur)
        if prix is None:
            return 0.0
        return (
            tokens_in * prix.input_eur_per_mtok + tokens_out * prix.output_eur_per_mtok
        ) / 1_000_000

    def _fin_entrainement(self, servi: str) -> date | None:
        return self.config.training_cutoff.get(servi)

    def _base(self, ctx: _Contexte, niveau: str, modele: str, relais: bool) -> dict[str, Any]:
        return {
            "appel_id": f"{self.run_id}-{uuid.uuid4().hex[:12]}",
            "run_id": self.run_id,
            "horodatage": self._clock(),
            "agent": ctx.agent,
            "tier": niveau,
            "tier_demande": ctx.tier_demande,
            "mode": self.mode,
            "modele_demande": modele,
            "fournisseur": modele.split("/", 1)[0],
            "relais_utilise": relais,
            "prompt_id": ctx.ref.prompt_id,
            "prompt_version": ctx.ref.version,
            "prompt_sha256": ctx.ref.sha256,
            "cle_cache": ctx.cle,
            "graine": ctx.graine,
            "temperature": ctx.temperature,
            "date_donnees": ctx.date_donnees,
        }

    def _publier(self, rec: ExecutionRecord) -> ExecutionRecord:
        with self._lock:
            self.records.append(rec)
            if self.run_dir:
                self.run_dir.mkdir(parents=True, exist_ok=True)
                with (self.run_dir / "calls.jsonl").open("a", encoding="utf-8") as f:
                    f.write(rec.model_dump_json() + "\n")
        return rec

    def _enregistrer(
        self, raw: Any, ctx: _Contexte, niveau: str, modele: str, relais: bool, latence_ms: int
    ) -> ExecutionRecord:
        tin, tout = getattr(raw, "tokens_in", 0), getattr(raw, "tokens_out", 0)
        servi = getattr(raw, "model_served", "") or "inconnu"
        fournisseur = modele.split("/", 1)[0]
        return self._publier(
            ExecutionRecord(
                **self._base(ctx, niveau, modele, relais),
                modele_servi=servi,
                fin_entrainement_modele=self._fin_entrainement(servi),
                cache_hit=False,
                tokens_entree=tin,
                tokens_sortie=tout,
                cout_eur=self._cout(fournisseur, tin, tout),
                latence_ms=latence_ms,
            )
        )

    def _enregistrer_erreur(
        self,
        ctx: _Contexte,
        niveau: str,
        modele: str,
        relais: bool,
        latence: int,
        kind: str,
        msg: str,
        *,
        servi: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cache_hit: bool = False,
    ) -> None:
        self._publier(
            ExecutionRecord(
                **self._base(ctx, niveau, modele, relais),
                modele_servi=servi,
                cache_hit=cache_hit,
                tokens_entree=tokens_in,
                tokens_sortie=tokens_out,
                cout_eur=self._cout(modele.split("/", 1)[0], tokens_in, tokens_out),
                latence_ms=latence,
                erreur=f"{kind}: {msg}"[:500],
            )
        )

    def _enregistrer_cache(
        self, entree: dict[str, Any], ctx: _Contexte, niveau: str, cle_fige: str
    ) -> ExecutionRecord:
        servi = entree.get("modele_servi", "") or "inconnu"
        try:
            self._verifier_modele_servi(cle_fige, entree.get("modele_servi", ""))
        except ModeleServiChange as exc:
            self._enregistrer_erreur(
                ctx,
                entree.get("tier", niveau),
                entree.get("modele_demande", ctx.modele),
                bool(entree.get("relais_utilise")),
                0,
                "modele_servi_change",
                redact(exc),
                servi=entree.get("modele_servi", ""),
                cache_hit=True,
            )
            raise
        base = self._base(
            ctx, entree.get("tier", niveau), entree.get("modele_demande", ctx.modele), False
        )
        base["relais_utilise"] = bool(entree.get("relais_utilise"))
        base["fournisseur"] = entree.get("fournisseur", base["fournisseur"])
        return self._publier(
            ExecutionRecord(
                **base,
                modele_servi=servi,
                fin_entrainement_modele=self._fin_entrainement(servi),
                cache_hit=True,
                tokens_entree=0,
                tokens_sortie=0,
                cout_eur=0.0,
                latence_ms=0,
            )
        )


class _Contexte:
    """Paramètres d'un appel partagés par les enregistrements."""

    __slots__ = (
        "agent",
        "ref",
        "cle",
        "graine",
        "temperature",
        "date_donnees",
        "modele",
        "tier_demande",
    )

    def __init__(
        self,
        agent: str,
        ref: PromptRef,
        cle: str,
        graine: int,
        temperature: float,
        date_donnees: date,
        modele: str,
        tier_demande: str,
    ) -> None:
        self.tier_demande = tier_demande
        self.agent = agent
        self.ref = ref
        self.cle = cle
        self.graine = graine
        self.temperature = temperature
        self.date_donnees = date_donnees
        self.modele = modele
