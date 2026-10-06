"""Régression trouvée sur le vrai stockage : une étiquette sans article faisait lever un
KeyError('published_at') dans `DataView.news` (tableau vide privé de ses colonnes)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from amundi_agentic.data.models import NewsQuery
from amundi_agentic.data.pit import PointInTimeStore
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore


def test_news_par_etiquette_sans_resultat_ne_leve_pas(tmp_path):
    store = ParquetStore(tmp_path / "store")
    publie = pd.Timestamp("2024-01-15", tz="UTC")
    store.write(
        "news/items",
        pd.DataFrame(
            {
                "item_id": ["a"],
                "source": ["s"],
                "published_at": [publie],
                "first_seen_at": [publie],
                "title": ["t"],
                "summary": ["r"],
                "url": ["u"],
                "time_semantics": ["published"],
                "tags": ["AUTRE"],
            }
        ),
    )
    vue = PointInTimeStore(store, load_yaml("data.yaml")).as_of(date(2024, 2, 1))
    assert vue.news(NewsQuery(tags=("AAPL",))) == []
    assert len(vue.news(NewsQuery(tags=("AUTRE",)))) == 1
