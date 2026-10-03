"""Source ESG manuelle et historisée par ETF (D-048, EX-O1-18, L1 §9.4).

Le fichier de saisie est `config/esg_etf_sources.yaml`. Chaque valeur est recopiée à la main depuis un
document de la gestionnaire du fonds (prospectus, DIC/KID, fiche produit, document SFDR, avis aux
actionnaires) ou de l'administrateur de l'indice (page de l'indice). Une valeur qu'aucun document
n'établit n'est pas saisie : elle vaut `inconnu` (entrée explicite avec sa raison). Rien n'est déduit
d'un nom de fonds ou d'indice.

Schéma d'une entrée (liste `entries` de chaque ETF, clé = ticker de `universe.yaml`)
------------------------------------------------------------------------------------
- `id` : unique dans le fichier, de la forme `<ticker>:<champ>:<nnn>` ;
- `champ` : `sfdr` | `indice` | `caractere_indice` | `exclusions` (chacun au moins une entrée par ETF) ;
- `valeur` : `sfdr` -> `article_6` | `article_8` | `article_9` | `non_applicable` (ETC) ; `indice` -> libellé
  tel qu'écrit par le document ; `caractere_indice` -> `esg` | `pab` | `ctb` | `standard` ;
  `exclusions` -> table critère -> portée (critères de `config/esg.yaml`, portée `indice`,
  `portefeuille_replication_directe` ou `titres_detenus_hors_swap`) ; toujours possible : `inconnu` ;
- valeur établie : `emetteur` (`gestionnaire_fonds` | `administrateur_indice`), `source`
  (`type_document`, `titre`, `url` https), `date_document` (date de publication connue), `date_effet`,
  `effet_documente` (vrai si le document donne lui-même la date d'effet ; faux : borne prudente =
  date du document), `date_consultation`, `date_saisie`, `extrait` (obligatoire pour `esg`, `pab`, `ctb`
  et pour `exclusions`), `sources_complementaires`, `note`, `corrige` ;
- `inconnu` : `raison` et `date_saisie`, sans source. Sans `corrige` c'est un marqueur d'information
  (ignoré par la résolution). Avec `corrige` (+ `date_effet`) c'est un retrait : la valeur redevient inconnue.

Historisation append-only (D-043)
---------------------------------
Une entrée existante n'est jamais modifiée ni supprimée. Une correction AJOUTE une entrée (nouvel `id`,
`corrige: <id corrigé>`, `date_saisie` strictement postérieure). Le contrôle est mécanique :
`verify_and_snapshot` compare le fichier aux instantanés datés déjà écrits dans
`.cache/data/snapshots/esg_etf_sources/` (même mécanisme que `ParquetStore.snapshot`) et refuse toute
entrée altérée ou disparue (`RetroactiveModificationError`). Les instantanés entrent dans le manifeste
`data_manifest.json` comme les autres jeux (SHA-256). Le fichier lui-même n'est PAS ajouté à
`CONFIGS` de `manifest.py` (le test existant impose l'ensemble exact des trois configurations) :
`EtfSources.file_sha256` est enregistré dans chaque instantané.

Point-in-time (D-031)
---------------------
`EtfSources.as_of(t)` applique la coupure t 00:00 heure de Paris (`pit.cutoff_utc`) : une entrée est servie
si et seulement si `max(date_effet, date_document, date_saisie)` est STRICTEMENT antérieure à t. Une valeur
n'est donc jamais servie avant sa date d'effet, ni avant la publication du document, ni avant sa saisie :
une correction rétroactive ne réécrit pas ce qu'on savait à t. Mode `non_pit` : la date de saisie est
ignorée (le document était public) mais les deux autres bornes restent ; toute valeur dont la saisie est
postérieure à t porte `non_point_in_time=True`. Entre plusieurs entrées connues, on sert celle de
`date_effet` la plus récente, puis de `date_saisie` la plus récente, puis la dernière du fichier.

Limites (à répéter dans tout rapport)
-------------------------------------
- SFDR classe des produits : ce n'est pas un score ESG. Un article 8 n'implique pas l'exclusion des armes
  controversées, du tabac ou du charbon thermique ; seule une entrée `exclusions` appuyée sur un document
  le prouve, et elle reste soumise aux seuils de la méthodologie.
- CT-06 reste suspendue (D-035) : aucun score ESG n'est produit ici.
- La matrice ESG reste `inconnu` pour tout ce que les documents ne prouvent pas ; une exclusion portée
  par les titres détenus d'un fonds à swap (`titres_detenus_hors_swap`) n'est pas l'exposition à l'indice
  et n'est pas comptée comme déterminée.
- Les dates d'effet sont des bornes prudentes quand le document ne les donne pas (`effet_documente: false`) :
  la classification a pu être identique plus tôt ; avant la première entrée, la valeur est `inconnu`.
- Une fiche produit n'est pas datée : sa `date_document` est la date de consultation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from amundi_agentic.data.pit import cutoff_utc
from amundi_agentic.data.settings import CONFIG_DIR
from amundi_agentic.data.store import ParquetStore

INCONNU = "inconnu"
CHAMPS = ("sfdr", "indice", "caractere_indice", "exclusions")
SFDR_VALEURS = frozenset({"article_6", "article_8", "article_9", "non_applicable"})
CARACTERES = frozenset({"esg", "pab", "ctb", "standard"})
TYPES_DOCUMENT = frozenset(
    {"prospectus", "dic_kid", "fiche_produit", "page_indice", "document_sfdr", "avis_actionnaires"}
)
EMETTEURS = frozenset({"gestionnaire_fonds", "administrateur_indice"})
PORTEES = frozenset({"indice", "portefeuille_replication_directe", "titres_detenus_hors_swap"})
PORTEES_COMPTEES = frozenset({"indice", "portefeuille_replication_directe"})
CARACTERES_AVEC_EXTRAIT = frozenset({"esg", "pab", "ctb"})
MODES = ("strict", "non_pit")
SNAPSHOT_SOURCE = "esg_etf_sources"
DEFAULT_FILE = "esg_etf_sources.yaml"
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class EsgSourceError(ValueError):
    """Fichier de saisie invalide (toutes les erreurs sont listées dans le message)."""


class RetroactiveModificationError(EsgSourceError):
    """Une entrée déjà historisée a été modifiée ou supprimée (violation de l'append-only)."""


def _date(v: Any, nom: str, erreurs: list[str], ctx: str, obligatoire: bool = True) -> date | None:
    if v is None or v == "":
        if obligatoire:
            erreurs.append(f"{ctx}: `{nom}` obligatoire")
        return None
    if isinstance(v, datetime):
        erreurs.append(f"{ctx}: `{nom}` doit être une date (AAAA-MM-JJ), pas un datetime")
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        erreurs.append(f"{ctx}: `{nom}` n'est pas une date ISO (reçu {v!r})")
        return None


def _canon(brut: Mapping[str, Any]) -> str:
    def plat(x: Any) -> Any:
        if isinstance(x, datetime | date):
            return x.isoformat()
        if isinstance(x, Mapping):
            return {str(k): plat(v) for k, v in x.items()}
        if isinstance(x, list | tuple):
            return [plat(v) for v in x]
        return x

    return json.dumps(plat(dict(brut)), sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class Entry:
    """Une entrée validée du fichier (immuable)."""

    id: str
    ticker: str
    champ: str
    valeur: Any  # str, ou tuple de (critère, portée) pour `exclusions`
    emetteur: str | None
    source: Mapping[str, Any] | None
    date_document: date | None
    date_effet: date | None
    effet_documente: bool
    date_consultation: date | None
    date_saisie: date
    corrige: str | None
    extrait: str | None
    raison: str | None
    note: str | None
    ordre: int
    sha256: str
    brut: Mapping[str, Any]

    @property
    def est_inconnu(self) -> bool:
        return self.valeur == INCONNU

    @property
    def est_marqueur(self) -> bool:
        """`inconnu` sans `corrige` : information seulement, jamais servi."""
        return self.est_inconnu and self.corrige is None

    @property
    def connue_a_partir_de(self) -> date:
        """Premier jour où l'entrée peut être servie en mode strict."""
        jours = [d for d in (self.date_effet, self.date_document, self.date_saisie) if d]
        return max(jours)

    @property
    def exclusions(self) -> dict[str, str]:
        return dict(self.valeur) if self.champ == "exclusions" and not self.est_inconnu else {}


@dataclass(frozen=True)
class Resolved:
    """Valeur servie à t pour (ticker, champ)."""

    ticker: str
    champ: str
    valeur: Any
    entry_id: str | None
    source: Mapping[str, Any] | None
    date_effet: date | None
    date_saisie: date | None
    non_point_in_time: bool = False

    @property
    def est_inconnu(self) -> bool:
        return self.valeur == INCONNU


def _valider_valeur(
    champ: str, v: Any, criteres: frozenset[str] | None, ctx: str, erreurs: list[str]
) -> Any:
    if v is None or v == "":
        erreurs.append(f"{ctx}: `valeur` obligatoire (utiliser `inconnu` si non établie)")
        return INCONNU
    if v == INCONNU:
        return INCONNU
    if champ == "sfdr":
        if v not in SFDR_VALEURS:
            erreurs.append(
                f"{ctx}: sfdr doit être parmi {sorted(SFDR_VALEURS)} ou inconnu (reçu {v!r})"
            )
    elif champ == "caractere_indice":
        if v not in CARACTERES:
            erreurs.append(
                f"{ctx}: caractere_indice doit être parmi {sorted(CARACTERES)} ou inconnu (reçu {v!r})"
            )
    elif champ == "indice":
        if not isinstance(v, str) or not v.strip():
            erreurs.append(f"{ctx}: indice doit être un libellé non vide")
    elif champ == "exclusions":
        if not isinstance(v, Mapping) or not v:
            erreurs.append(f"{ctx}: exclusions doit être une table critère -> portée non vide")
            return INCONNU
        for crit, portee in v.items():
            if criteres is not None and crit not in criteres:
                erreurs.append(f"{ctx}: critère d'exclusion inconnu de esg.yaml : {crit!r}")
            if portee not in PORTEES:
                erreurs.append(
                    f"{ctx}: portée {portee!r} invalide pour {crit!r} (permis : {sorted(PORTEES)})"
                )
        return tuple(sorted((str(k), str(p)) for k, p in v.items()))
    return v


def _valider_source(src: Any, ctx: str, erreurs: list[str], date_obligatoire: bool) -> None:
    if not isinstance(src, Mapping):
        erreurs.append(f"{ctx}: source absente ou mal formée")
        return
    if src.get("type_document") not in TYPES_DOCUMENT:
        erreurs.append(
            f"{ctx}: type_document {src.get('type_document')!r} invalide (permis : {sorted(TYPES_DOCUMENT)})"
        )
    if not str(src.get("titre") or "").strip():
        erreurs.append(f"{ctx}: source.titre obligatoire")
    url = str(src.get("url") or "")
    if not url.startswith("https://"):
        erreurs.append(f"{ctx}: source.url obligatoire et en https (reçu {url!r})")
    if date_obligatoire:
        _date(src.get("date_document"), "source.date_document", erreurs, ctx)


def _parse_entry(
    ticker: str,
    brut: Mapping[str, Any],
    ordre: int,
    criteres: frozenset[str] | None,
    today: date | None,
    erreurs: list[str],
) -> Entry | None:
    ctx = f"{ticker}#{ordre + 1} ({brut.get('id', 'sans id')})"
    n0 = len(erreurs)
    ident = str(brut.get("id") or "")
    champ = brut.get("champ")
    if champ not in CHAMPS:
        erreurs.append(f"{ctx}: champ {champ!r} invalide (permis : {list(CHAMPS)})")
        return None
    if not ident.startswith(f"{ticker}:{champ}:"):
        erreurs.append(f"{ctx}: id doit commencer par '{ticker}:{champ}:'")
    valeur = _valider_valeur(champ, brut.get("valeur"), criteres, ctx, erreurs)
    saisie = _date(brut.get("date_saisie"), "date_saisie", erreurs, ctx)
    inconnu = valeur == INCONNU
    corrige = brut.get("corrige") or None
    d_doc = d_eff = d_cons = None
    effet_doc = bool(brut.get("effet_documente", False))
    if inconnu:
        if not str(brut.get("raison") or "").strip():
            erreurs.append(f"{ctx}: une valeur inconnue exige une `raison`")
        if corrige:
            d_eff = _date(brut.get("date_effet"), "date_effet", erreurs, ctx)
    else:
        if brut.get("emetteur") not in EMETTEURS:
            erreurs.append(f"{ctx}: emetteur doit être parmi {sorted(EMETTEURS)}")
        _valider_source(brut.get("source"), ctx, erreurs, date_obligatoire=False)
        for c in brut.get("sources_complementaires") or []:
            _valider_source(c, ctx + " (source complémentaire)", erreurs, date_obligatoire=True)
        d_doc = _date(brut.get("date_document"), "date_document", erreurs, ctx)
        d_eff = _date(brut.get("date_effet"), "date_effet", erreurs, ctx)
        d_cons = _date(brut.get("date_consultation"), "date_consultation", erreurs, ctx)
        if not isinstance(brut.get("effet_documente"), bool):
            erreurs.append(f"{ctx}: `effet_documente` doit être un booléen explicite")
        if d_doc and d_eff and d_eff < d_doc and not effet_doc:
            erreurs.append(
                f"{ctx}: date_effet {d_eff} antérieure à date_document {d_doc} sans `effet_documente: true` "
                "(un effet antérieur au document doit être écrit par le document)"
            )
        if d_doc and d_cons and d_cons < d_doc:
            erreurs.append(f"{ctx}: date_consultation {d_cons} antérieure à date_document {d_doc}")
        if d_cons and saisie and saisie < d_cons:
            erreurs.append(f"{ctx}: date_saisie {saisie} antérieure à date_consultation {d_cons}")
        needs = (
            champ == "caractere_indice" and valeur in CARACTERES_AVEC_EXTRAIT
        ) or champ == "exclusions"
        if needs and not str(brut.get("extrait") or "").strip():
            erreurs.append(f"{ctx}: `extrait` du document obligatoire pour {champ}={valeur!r}")
    if today and saisie and saisie > today:
        erreurs.append(f"{ctx}: date_saisie {saisie} dans le futur")
    if len(erreurs) > n0 or saisie is None:
        return None
    return Entry(
        id=ident, ticker=ticker, champ=champ, valeur=valeur,
        emetteur=brut.get("emetteur"), source=brut.get("source"),
        date_document=d_doc, date_effet=d_eff, effet_documente=effet_doc,
        date_consultation=d_cons, date_saisie=saisie, corrige=corrige,
        extrait=brut.get("extrait"), raison=brut.get("raison"), note=brut.get("note"),
        ordre=ordre, sha256=hashlib.sha256(_canon(brut).encode("utf-8")).hexdigest(), brut=dict(brut),
    )  # fmt: skip


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class EtfSources:
    """Fichier de saisie validé : lecture historisée et accès point-in-time."""

    def __init__(
        self, entrees: dict[str, tuple[Entry, ...]], isin: dict[str, str], file_sha256: str | None
    ):
        self.entries = entrees
        self.isin = isin
        self.file_sha256 = file_sha256

    @property
    def tickers(self) -> list[str]:
        return sorted(self.entries)

    def all_entries(self) -> list[Entry]:
        return [e for t in self.tickers for e in self.entries[t]]

    def as_of(self, t: date, *, mode: str = "strict") -> EtfEsgView:
        return EtfEsgView(self, t, mode)


def parse_sources(
    data: Mapping[str, Any],
    *,
    universe_tickers: set[str] | None = None,
    criteres: set[str] | None = None,
    today: date | None = None,
    file_sha256: str | None = None,
) -> EtfSources:
    """Validation stricte ; lève `EsgSourceError` avec toutes les erreurs."""
    erreurs: list[str] = []
    if not isinstance(data, Mapping) or data.get("version") != 1:
        raise EsgSourceError("fichier invalide : `version: 1` attendue")
    etfs = data.get("etfs")
    if not isinstance(etfs, Mapping) or not etfs:
        raise EsgSourceError("fichier invalide : table `etfs` vide ou absente")
    crit = frozenset(criteres) if criteres is not None else None
    sortie: dict[str, tuple[Entry, ...]] = {}
    isin: dict[str, str] = {}
    ids: dict[str, Entry] = {}
    for ticker, bloc in etfs.items():
        ticker = str(ticker)
        if universe_tickers is not None and ticker not in universe_tickers:
            erreurs.append(f"{ticker}: absent de config/universe.yaml")
        if not isinstance(bloc, Mapping):
            erreurs.append(f"{ticker}: bloc mal formé")
            continue
        code = str(bloc.get("isin") or "")
        if not _ISIN.match(code):
            erreurs.append(f"{ticker}: isin invalide ({code!r})")
        isin[ticker] = code
        liste = bloc.get("entries")
        if not isinstance(liste, list) or not liste:
            erreurs.append(
                f"{ticker}: `entries` vide (au moins une entrée par champ, même `inconnu`)"
            )
            continue
        valides: list[Entry] = []
        for i, brut in enumerate(liste):
            if not isinstance(brut, Mapping):
                erreurs.append(f"{ticker}#{i + 1}: entrée mal formée")
                continue
            e = _parse_entry(ticker, brut, i, crit, today, erreurs)
            if e is None:
                continue
            if e.id in ids:
                erreurs.append(f"{ticker}: id dupliqué {e.id}")
                continue
            ids[e.id] = e
            valides.append(e)
        for champ in CHAMPS:
            if not any(e.champ == champ for e in valides):
                erreurs.append(
                    f"{ticker}: aucune entrée pour le champ `{champ}` (saisir une valeur ou un `inconnu` motivé)"
                )
        sortie[ticker] = tuple(valides)
    for e in ids.values():
        if not e.corrige:
            continue
        cible = ids.get(e.corrige)
        if cible is None:
            erreurs.append(f"{e.id}: `corrige` désigne un id inexistant ({e.corrige})")
        elif (cible.ticker, cible.champ) != (e.ticker, e.champ):
            erreurs.append(
                f"{e.id}: `corrige` doit viser le même ETF et le même champ ({e.corrige})"
            )
        elif cible.ordre >= e.ordre:
            erreurs.append(
                f"{e.id}: une correction vient APRÈS l'entrée corrigée dans le fichier (append-only)"
            )
        elif e.date_saisie <= cible.date_saisie:
            erreurs.append(
                f"{e.id}: date_saisie de la correction ({e.date_saisie}) doit être postérieure à celle de {cible.id} ({cible.date_saisie})"
            )
    if erreurs:
        raise EsgSourceError("\n".join(f"- {m}" for m in erreurs))
    return EtfSources(sortie, isin, file_sha256)


def load_etf_sources(
    path: Path | None = None,
    *,
    universe_tickers: set[str] | None = None,
    criteres: set[str] | None = None,
    today: date | None = None,
) -> EtfSources:
    """Charge et valide `config/esg_etf_sources.yaml` (ou `path`)."""
    p = Path(path) if path else CONFIG_DIR / DEFAULT_FILE
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return parse_sources(
        data, universe_tickers=universe_tickers, criteres=criteres, today=today,
        file_sha256=sha256_file(p),
    )  # fmt: skip


class EtfEsgView:
    """Ce qui était connu à t (coupure t 00:00 Europe/Paris, D-031)."""

    def __init__(self, sources: EtfSources, t: date, mode: str = "strict") -> None:
        if mode not in MODES:
            raise ValueError(f"mode invalide {mode!r} (permis : {MODES})")
        self._s = sources
        self.t = t
        self.mode = mode
        self.cutoff = cutoff_utc(t)  # lève TypeError pour un datetime

    def _connue(self, e: Entry) -> bool:
        bornes = [e.date_effet, e.date_document] + (
            [e.date_saisie] if self.mode == "strict" else []
        )
        if self.mode == "non_pit" and e.est_marqueur:
            return False
        return all(cutoff_utc(d) < self.cutoff for d in bornes if d is not None)

    def get(self, ticker: str, champ: str) -> Resolved:
        if champ not in CHAMPS:
            raise KeyError(f"champ inconnu {champ!r}")
        candidates = [
            e
            for e in self._s.entries.get(ticker, ())
            if e.champ == champ and not e.est_marqueur and self._connue(e)
        ]
        if not candidates:
            return Resolved(ticker, champ, INCONNU, None, None, None, None, False)
        e = max(candidates, key=lambda x: (x.date_effet or date.min, x.date_saisie, x.ordre))
        non_pit = cutoff_utc(e.date_saisie) >= self.cutoff
        return Resolved(ticker, champ, e.valeur if not e.est_inconnu else INCONNU, e.id,
                        e.source, e.date_effet, e.date_saisie, non_pit)  # fmt: skip

    def state(self, ticker: str) -> dict[str, Resolved]:
        return {c: self.get(ticker, c) for c in CHAMPS}

    def sfdr(self, ticker: str) -> str:
        return self.get(ticker, "sfdr").valeur

    def exclusions(self, ticker: str) -> dict[str, str]:
        """Critère -> portée, tels que prouvés par un document connu à t."""
        r = self.get(ticker, "exclusions")
        return {} if r.est_inconnu else dict(r.valeur)

    def proven_exclusions(self, ticker: str) -> frozenset[str]:
        """Critères dont un document prouve l'exclusion de l'exposition (portée comptée par la matrice)."""
        return frozenset(c for c, p in self.exclusions(ticker).items() if p in PORTEES_COMPTEES)


# ------------------------------------------------------------------ historisation append-only (D-043)
def entries_frame(sources: EtfSources) -> pd.DataFrame:
    """Une ligne par entrée : id, empreinte et contenu canonique (pour l'instantané daté)."""
    return pd.DataFrame(
        [
            {"ticker": e.ticker, "id": e.id, "champ": e.champ, "entry_sha256": e.sha256,
             "content_json": _canon(e.brut), "file_sha256": sources.file_sha256}
            for e in sources.all_entries()
        ],
        columns=["ticker", "id", "champ", "entry_sha256", "content_json", "file_sha256"],
    )  # fmt: skip


def check_append_only(sources: EtfSources, store: ParquetStore) -> list[str]:
    """Violations par rapport à tous les instantanés déjà écrits (liste vide : conforme)."""
    passe = store.read_snapshots(SNAPSHOT_SOURCE, "entries")
    if passe.empty:
        return []
    actuel = {e.id: e.sha256 for e in sources.all_entries()}
    violations = []
    for r in passe.drop_duplicates(["id", "entry_sha256"]).itertuples():
        if r.id not in actuel:
            violations.append(f"entrée supprimée : {r.id} (instantané du {r.snapshot_date})")
        elif actuel[r.id] != r.entry_sha256:
            violations.append(
                f"entrée modifiée : {r.id} (instantané du {r.snapshot_date}) ; ajouter une entrée `corrige` au lieu de modifier"
            )
    return violations


def verify_and_snapshot(sources: EtfSources, store: ParquetStore) -> Path | None:
    """Refuse toute modification rétroactive, puis écrit l'instantané daté du jour (idempotent)."""
    violations = check_append_only(sources, store)
    if violations:
        raise RetroactiveModificationError("\n".join(f"- {v}" for v in violations))
    return store.snapshot(
        SNAPSHOT_SOURCE,
        "entries",
        entries_frame(sources),
        note="saisie manuelle D-048 (append-only)",
    )


def load_for_universe(path: Path | None = None) -> EtfSources:
    """Charge le fichier en le validant contre `universe.yaml` et `esg.yaml` (points d'entrée des outils)."""
    from amundi_agentic.data.settings import load_yaml
    from amundi_agentic.data.universe import Universe

    tickers = set(Universe.load().etf_tickers())
    esg = load_yaml("esg.yaml")
    return load_etf_sources(
        path, universe_tickers=tickers, criteres=set(esg["normative_exclusions"])
    )


def main(argv: list[str] | None = None) -> int:
    """`python -m amundi_agentic.data.connectors.esg_etf_sources [snapshot]` : valide, affiche, historise."""
    import sys

    from amundi_agentic.data.settings import DataSettings

    args = list(sys.argv[1:] if argv is None else argv)
    src = load_etf_sources()
    print(
        f"{len(src.all_entries())} entrées valides, {len(src.tickers)} ETF, sha256 {src.file_sha256}"
    )
    if args[:1] == ["snapshot"]:
        s = DataSettings.load()
        chemin = verify_and_snapshot(src, ParquetStore(s.store_dir, s.snapshot_dir))
        print(f"instantané : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
