# ruff: noqa: E501
"""Fabriques synthétiques pour les tests du RAG, du résumé et de l'évaluation (aucun réseau, aucune clé).

Aucun texte réel de société : les rapports sont inventés (société « Apex »).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

import pandas as pd

from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore
from amundi_agentic.llm import MockLLMClient, MockTransport, load_config
from amundi_agentic.llm.types import RawEmbedding


class BagTransport(MockTransport):
    """Embeddings « sac de mots » hachés (64 dimensions) : proximité lexicale déterministe, assez
    pour tester le classement sans modèle d'embedding."""

    DIM = 64

    def embedding(self, *, model: str, inputs: list[str], timeout: float) -> RawEmbedding:
        self.calls.append({"kind": "embed", "model": model, "inputs": inputs})
        vecteurs = []
        for t in inputs:
            v = [0.0] * self.DIM
            for mot in re.findall(r"[a-zà-ÿ]{3,}", t.lower()):
                h = int(hashlib.sha256(mot.encode()).hexdigest(), 16)
                v[h % self.DIM] += 1.0
            vecteurs.append(v)
        return RawEmbedding(vecteurs, self._servi(model), 1)

    @property
    def embed_inputs(self) -> list[str]:
        return [x for c in self.calls if c["kind"] == "embed" for x in c["inputs"]]


def client(tmp_path, transport=None, **kw) -> MockLLMClient:
    return MockLLMClient(
        load_config(),
        profile="dev",
        transport=transport or BagTransport(),
        cache_dir=tmp_path / "llm_cache",
        quota_journal=tmp_path / "quotas.json",
        **kw,
    )


def paragraphes(sujet: str, n: int, mots: str = "") -> str:
    return "\n\n".join(
        f"{sujet} paragraphe {i} : {mots} {mots} " + "Phrase de remplissage sur ce sujet. " * 4
        for i in range(n)
    )


def rapport_10k(extra_fin: str = "") -> str:
    """Un 10-K synthétique avec table des matières, Item 1, 1A, 7, 8 et un renvoi trompeur."""
    return (
        "APEX CORP ANNUAL REPORT FORM 10-K\n\n"
        + "Couverture du rapport annuel synthétique. " * 12
        + "\n\nTABLE OF CONTENTS\n\nItem 1. Business 3\n\nItem 1A. Risk Factors 8\n\n"
        "Item 7. Management's Discussion and Analysis 20\n\nItem 8. Financial Statements 30\n\n"
        "PART I\n\nItem 1. Business\n\n"
        + paragraphes("Activité", 4, "capteurs industriels maintenance clients segments")
        + "\n\nItem 1A. Risk Factors\n\n"
        + paragraphes("Risque", 4, "litige procès réglementation dépendance fournisseur risque")
        + "\n\nVoir aussi\n\nItem 7 of this report décrit la liquidité.\n\n"
        "Item 7. Management's Discussion and Analysis\n\n"
        + paragraphes("Analyse", 4, "marge brute résultat flux trésorerie exploitation liquidité")
        + "\n\nItem 8. Financial Statements and Supplementary Data\n\n"
        + paragraphes("États", 3, "bilan dette emprunt échéances capitaux propres notes")
        + extra_fin
    )


def rapport_10q() -> str:
    return (
        "APEX CORP QUARTERLY REPORT FORM 10-Q\n\n"
        + "Couverture trimestrielle synthétique. " * 12
        + "\n\nPART I. FINANCIAL INFORMATION\n\nItem 1. Financial Statements\n\n"
        + paragraphes("Comptes", 3, "résultat trimestre bilan")
        + "\n\nItem 2. Management's Discussion and Analysis\n\n"
        + paragraphes("Discussion", 3, "marge ventes trimestre perspectives")
        + "\n\nPART II. OTHER INFORMATION\n\nItem 1A. Risk Factors\n\n"
        + paragraphes("Risques", 3, "changements risque nouveau")
    )


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def construire_stockage(tmp_path, depots: list[dict], ticker: str = "APEX"):
    """Stockage Parquet avec l'index des dépôts et leurs textes ; renvoie (PointInTimeStore, store).

    Chaque dépôt : accession, form, accepted (str UTC), texte, [report_date].
    """
    store = ParquetStore(tmp_path / "store")
    lignes = []
    for d in depots:
        acc = d["accession"]
        lignes.append(
            {
                "ticker": ticker,
                "cik": 1234567,
                "accession": acc,
                "form": d["form"],
                "filing_date": pd.Timestamp(d["accepted"][:10]),
                "accepted_utc": ts(d["accepted"]),
                "acceptance_raw": d["accepted"],
                "report_date": pd.Timestamp(d.get("report_date", d["accepted"][:10])),
                "primary_document": f"{acc}.htm",
                "items": "",
            }
        )
        if d.get("texte") is not None:
            store.write_text(f"filings/text/{ticker}/{acc}", d["texte"])
    store.write(f"filings/index/{ticker}", pd.DataFrame(lignes))
    return PointInTimeStore(store, load_yaml("data.yaml")), store


def depot(accession: str, form: str, accepted: str, texte: str | None = None, **kw) -> dict:
    return {
        "accession": accession,
        "form": form,
        "accepted": accepted,
        "texte": rapport_10k() if texte is None and form == "10-K" else (texte or rapport_10q()),
        **kw,
    }


def maintenant_utc() -> datetime:
    return datetime.now(UTC)
