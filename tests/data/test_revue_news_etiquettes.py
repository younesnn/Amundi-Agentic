"""Revue indépendante : `DataView.news` (filtre par étiquette, correctif `.astype(bool)` de data/pit.py).

Cas adverses sur un stockage synthétique, puis lecture seule du VRAI stockage si
`AMUNDI_DATA_STORE` est défini (sinon ignoré) :

    AMUNDI_DATA_STORE="/chemin/.cache/data/store" uv run pytest tests/data/test_revue_news_etiquettes.py -q
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from amundi_agentic.data.models import NewsQuery
from amundi_agentic.data.pit import PointInTimeStore, cutoff_utc
from amundi_agentic.data.settings import load_yaml
from amundi_agentic.data.store import ParquetStore

T = date(2024, 2, 1)
COUPURE = cutoff_utc(T)  # t 00:00 Europe/Paris


def _vue(tmp_path, lignes, t=T):
    store = ParquetStore(tmp_path / "store")
    df = pd.DataFrame(
        [
            {
                "item_id": f"i{i}", "source": "s", "published_at": pub, "first_seen_at": pub,
                "title": f"titre {i}", "summary": "résumé", "url": f"u{i}",
                "time_semantics": "published", "tags": tags,
            }
            for i, (pub, tags) in enumerate(lignes)
        ]
    )  # fmt: skip
    store.write("news/items", df)
    return PointInTimeStore(store, load_yaml("data.yaml")).as_of(t)


def _avant(**kw):
    return COUPURE - timedelta(**kw)


def test_etiquette_sans_aucun_article_ne_leve_pas_et_renvoie_vide(tmp_path):
    vue = _vue(tmp_path, [(_avant(days=3), "AUTRE")])
    assert vue.news(NewsQuery(tags=("AAPL",))) == []
    assert vue.news(NewsQuery(tags=("AAPL", "MSFT"))) == []
    assert vue.news(NewsQuery(tags=("AAPL",), terms=("rate",), limit=5)) == []  # + termes sur vide
    assert vue.news(NewsQuery(tags=("AAPL",), start=T - timedelta(days=30))) == []


def test_constat_etiquette_vide_dans_la_requete_attrape_les_articles_sans_etiquette(tmp_path):
    """Quirk (mineur, sans fuite de futur) : `tags=("",)` correspond aux articles SANS étiquette
    (chaîne vide scindée en {""}). Un appelant ne doit pas passer d'étiquette vide."""
    vue = _vue(tmp_path, [(_avant(days=1), "AAPL"), (_avant(days=2), "")])
    assert [n.item_id for n in vue.news(NewsQuery(tags=("",)))] == ["i1"]
    assert [n.tags for n in vue.news(NewsQuery(tags=("AAPL",)))] == [("AAPL",)]


def test_article_a_la_coupure_exacte_exclu_une_seconde_avant_inclus(tmp_path):
    vue = _vue(
        tmp_path,
        [
            (COUPURE, "AAPL"),  # à t 00:00 Paris exactement : exclu
            (COUPURE + timedelta(hours=5), "AAPL"),  # après : exclu
            (COUPURE - timedelta(seconds=1), "AAPL"),  # une seconde avant : inclus
        ],
    )
    items = vue.news(NewsQuery(tags=("AAPL",)))
    assert [n.item_id for n in items] == ["i2"]
    assert all(pd.Timestamp(n.published_at) < COUPURE for n in items)


def test_seuls_des_articles_posterieurs_etiquetes_ne_fuient_pas(tmp_path):
    vue = _vue(tmp_path, [(COUPURE, "AAPL"), (COUPURE + timedelta(days=9), "AAPL")])
    assert vue.news(NewsQuery(tags=("AAPL",))) == []
    assert vue.news(NewsQuery()) == []


def test_plusieurs_etiquettes_par_article_et_requete_multi_etiquettes(tmp_path):
    vue = _vue(
        tmp_path,
        [
            (_avant(days=1), "AAPL|MSFT"),
            (_avant(days=2), "MSFT"),
            (_avant(days=3), "NVDA|AAPL|ZS"),
            (_avant(days=4), "AAPLX"),  # préfixe : ne doit pas correspondre à AAPL
        ],
    )
    ids = lambda q: sorted(n.item_id for n in vue.news(q))  # noqa: E731
    assert ids(NewsQuery(tags=("AAPL",))) == ["i0", "i2"]
    assert ids(NewsQuery(tags=("MSFT",))) == ["i0", "i1"]
    assert ids(NewsQuery(tags=("ZS", "MSFT"))) == ["i0", "i1", "i2"]
    assert ids(NewsQuery(tags=("AAPL",), limit=1)) == ["i0"]  # le plus récent d'abord


def test_article_sans_etiquette_nan_ou_vide_n_est_servi_que_sans_filtre(tmp_path):
    vue = _vue(tmp_path, [(_avant(days=1), None), (_avant(days=2), "AAPL")])
    assert [n.item_id for n in vue.news(NewsQuery(tags=("AAPL",)))] == ["i1"]
    sans_filtre = vue.news(NewsQuery())
    assert sorted(n.item_id for n in sans_filtre) == ["i0", "i1"]
    assert next(n for n in sans_filtre if n.item_id == "i0").tags in ((), ("nan",), ("None",))


def test_correctif_astype_bool_aucune_colonne_perdue_apres_un_filtre_vide(tmp_path):
    vue = _vue(tmp_path, [(_avant(days=1), "X")])
    # sans le correctif : KeyError('published_at') au tri ; avec : liste vide
    for q in (NewsQuery(tags=("Y",)), NewsQuery(tags=("Y",), terms=("zzz",)),
              NewsQuery(tags=("Y",), sources=("s",), limit=3)):  # fmt: skip
        assert vue.news(q) == []


def test_filtre_par_etiquette_ne_change_pas_la_coupure_entre_deux_dates(tmp_path):
    pub = datetime(2024, 1, 31, 23, 30, tzinfo=UTC)  # = 2024-02-01 00:30 Paris (hiver)
    lignes = [(pd.Timestamp(pub), "AAPL")]
    avant = _vue(tmp_path / "a", lignes, t=date(2024, 2, 1))
    apres = _vue(tmp_path / "b", lignes, t=date(2024, 2, 2))
    assert avant.news(NewsQuery(tags=("AAPL",))) == []  # publié après la coupure de t=1er février
    assert len(apres.news(NewsQuery(tags=("AAPL",)))) == 1


# --------------------------------------------------------------------------- vrai stockage, lecture seule
_ENV = os.environ.get("AMUNDI_DATA_STORE")
RACINE = Path(_ENV) if _ENV else Path("/inexistant")
reel = pytest.mark.skipif(
    not _ENV or not (RACINE / "prices" / "500.PA.parquet").exists(),
    reason="variable AMUNDI_DATA_STORE absente ou stockage introuvable",
)
DATES = [
    date(2025, 6, 2),
    date(2025, 12, 15),
    date(2026, 3, 2),
    date(2026, 5, 4),
    date(2026, 6, 15),
]


@reel
def test_le_fournisseur_de_news_ne_plante_plus_pour_les_15_titres_sur_5_dates():
    from amundi_agentic.data.universe import Universe

    titres = list(Universe.load().stock_demo_tickers)
    assert len(titres) == 15
    pit = PointInTimeStore(ParquetStore(RACINE), load_yaml("data.yaml"))
    total = 0
    for t in DATES:
        vue = pit.as_of(t)
        limite = cutoff_utc(t)
        for tk in titres:
            items = vue.news(NewsQuery(tags=(tk,), start=t - timedelta(days=30), limit=25))
            total += len(items)
            assert all(pd.Timestamp(n.published_at) < limite for n in items), (t, tk)
        macro = vue.news(NewsQuery(terms=("inflation", "recession"), start=t - timedelta(days=30)))
        assert all(pd.Timestamp(n.published_at) < limite for n in macro)
    assert (
        total >= 0
    )  # des étiquettes sans article existent : l'important est l'absence d'exception
