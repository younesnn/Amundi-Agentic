# ruff: noqa: E501
"""Revue indépendante : point-in-time du RAG et du résumé de news, par tous les chemins.

Coupure de t : t 00:00 Europe/Paris, oracle recalculé ici avec `zoneinfo` (indépendant du code).
Aucun réseau, aucune clé : `MockLLMClient`.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from text_helpers import client, construire_stockage, depot, rapport_10k, rapport_10q

from amundi_agentic.data.models import NewsItem
from amundi_agentic.llm import MockTransport
from amundi_agentic.tools.rag import FilingsRAG
from amundi_agentic.tools.summarize import summarize_news
from amundi_agentic.tools.text_config import load_text_tools_config


def coupure(t: date) -> datetime:
    """Oracle : minuit à Paris de t, en UTC."""
    return datetime(t.year, t.month, t.day, tzinfo=ZoneInfo("Europe/Paris")).astimezone(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")


def _rag(tmp_path, pit, **kw):
    cfg = load_text_tools_config().rag
    llm = client(tmp_path)
    return FilingsRAG(llm, store_dir=tmp_path / "rag", data_view=pit, config=cfg, **kw), llm


def _accessions(res) -> set[str]:
    return {p.source.source_id.split(":")[2] for p in res.passages}


# ====================================================================== RAG : bornes d'acceptation
DATES_T = [
    date(2024, 2, 1),  # hiver : minuit Paris = 23:00 UTC la veille
    date(2024, 3, 31),  # jour du passage à l'heure d'été (minuit encore en heure d'hiver)
    date(2024, 4, 1),  # lendemain : minuit Paris = 22:00 UTC
    date(2024, 10, 27),  # jour du retour à l'heure d'hiver (minuit en heure d'été)
    date(2024, 10, 28),  # lendemain : minuit Paris = 23:00 UTC
    date(2024, 7, 14),  # été
]


@pytest.mark.parametrize("t", DATES_T)
def test_rag_bornes_a_la_microseconde_et_aux_changements_d_heure(tmp_path, t):
    c = coupure(t)
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(days=60))),
        depot("0009-24-000002", "10-Q", iso(c - timedelta(microseconds=1)), rapport_10q()),
        depot("0009-24-000003", "10-Q", iso(c), rapport_10q()),  # exactement à la coupure
        depot("0009-24-000004", "10-Q", iso(c + timedelta(microseconds=1)), rapport_10q()),
        depot("0009-24-000005", "10-K", iso(c + timedelta(hours=1)), rapport_10k()),
        depot("0009-24-000006", "10-K", iso(c + timedelta(days=30)), rapport_10k()),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, _ = _rag(tmp_path, pit)
    # indexe d'abord pour une date tardive : tout est sur le disque et en mémoire
    rag.index_filings("APEX", t + timedelta(days=400))
    for question in ("risque litige", "marge flux", "bilan dette"):
        res = rag.query("APEX", question, t, k=1000)
        assert _accessions(res) == {"0009-24-000001", "0009-24-000002"}, t
        assert all(p.source.date_publication < c for p in res.passages)
    assert rag.index_filings("APEX", t) == sum(
        1 for _ in rag.query("APEX", "x", t, k=1000).passages
    )


def test_rag_le_jour_suivant_la_barre_juste_apres_est_visible(tmp_path):
    t = date(2024, 4, 1)
    c = coupure(t)
    pit, _ = construire_stockage(
        tmp_path,
        [
            depot("0009-24-000002", "10-Q", iso(c + timedelta(microseconds=1)), rapport_10q()),
            depot("0009-24-000001", "10-K", iso(c - timedelta(days=9))),
        ],
    )
    rag, _ = _rag(tmp_path, pit)
    assert _accessions(rag.query("APEX", "risque", t, k=999)) == {"0009-24-000001"}
    assert _accessions(rag.query("APEX", "risque", t + timedelta(days=1), k=999)) == {
        "0009-24-000001",
        "0009-24-000002",
    }


# ====================================================================== RAG : amendements
def test_rag_dossier_amende_10ka_n_est_jamais_indexe(tmp_path):
    t = date(2024, 2, 1)
    c = coupure(t)
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(days=90))),
        {**depot("0009-24-000002", "10-K/A", iso(c - timedelta(days=10)), rapport_10k())},
        {**depot("0009-24-000003", "10-Q/A", iso(c - timedelta(days=5)), rapport_10q())},
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, _ = _rag(tmp_path, pit)
    res = rag.query("APEX", "risque", t, k=999)
    # documenté : seuls les formulaires de la configuration (10-K, 10-Q) sont servis
    assert _accessions(res) == {"0009-24-000001"}


def test_rag_original_avant_t_amendement_apres_t_seul_l_original_sort(tmp_path):
    t = date(2024, 2, 1)
    c = coupure(t)
    amende = rapport_10k() + "\n\nAMENDEMENT-FUTUR-SECRET restated figures"
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(days=90))),
        depot("0009-24-000002", "10-K", iso(c + timedelta(days=10)), amende),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, _ = _rag(tmp_path, pit)
    rag.index_filings("APEX", t + timedelta(days=100))
    res = rag.query("APEX", "restated figures amendement secret", t, k=999)
    assert all("AMENDEMENT-FUTUR-SECRET" not in p.text for p in res.passages)
    assert _accessions(res) == {"0009-24-000001"}


# ====================================================================== RAG : index et caches
def test_rag_index_deja_construit_avec_depot_futur_meme_instance_et_nouvelle_instance(tmp_path):
    t = date(2024, 2, 1)
    c = coupure(t)
    futur = rapport_10k() + "\n\nSECRET-POSTERIEUR guidance revised upward"
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(days=90))),
        depot("0009-24-000002", "10-K", iso(c + timedelta(days=1)), futur),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, llm = _rag(tmp_path, pit)
    rag.index_filings("APEX", t + timedelta(days=30))  # construit pour le futur
    # même instance (cache mémoire) : le futur ne sort jamais
    res = rag.query("APEX", "guidance revised upward SECRET-POSTERIEUR", t, k=999)
    assert _accessions(res) == {"0009-24-000001"} and "SECRET" not in " ".join(
        p.text for p in res.passages
    )
    # nouvelle instance sur le même dossier (caches disque : chunks.json et vecteurs du futur)
    rag2, _ = _rag(tmp_path, pit)
    res2 = rag2.query("APEX", "guidance revised upward SECRET-POSTERIEUR", t, k=999)
    assert _accessions(res2) == {"0009-24-000001"}
    assert res2.n_chunks_indexed == len(res2.passages)
    # le dépôt futur n'est ni lu ni embarqué pour une date antérieure
    assert rag2.n_embedding_calls == 0  # tout vient du cache de vecteurs des dépôts éligibles


def test_rag_vecteurs_de_depot_futur_pre_existants_sur_disque_ne_sortent_pas(tmp_path):
    """Cache vectoriel d'un dépôt futur déjà présent (construit par une autre exécution)."""
    t = date(2024, 2, 1)
    c = coupure(t)
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(days=90))),
        depot("0009-24-000002", "10-Q", iso(c + timedelta(days=5)), rapport_10q()),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag1, _ = _rag(tmp_path, pit)
    rag1.index_filings("APEX", t + timedelta(days=60))
    futur_dir = tmp_path / "rag" / "APEX" / "0009-24-000002"
    assert any(futur_dir.glob("vec-*.npz")) and (futur_dir / "chunks.json").is_file()
    # nouvelle exécution pour une date antérieure : aucun accès à ce dossier
    rag, llm = _rag(tmp_path, pit)
    res = rag.query("APEX", "résultat trimestre bilan", t, k=999)
    assert _accessions(res) == {"0009-24-000001"}
    lus = [str(p) for p in futur_dir.iterdir()]
    assert lus  # le cache existe toujours, mais n'a servi à rien : aucun passage du futur


def test_rag_date_donnees_des_embeddings_documents_et_requete(tmp_path):
    t = date(2024, 2, 1)
    c = coupure(t)
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(days=90) + timedelta(hours=1))),
        depot("0009-24-000002", "10-Q", iso(c - timedelta(microseconds=1)), rapport_10q()),
        depot("0009-24-000003", "10-Q", iso(c + timedelta(days=3)), rapport_10q()),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, llm = _rag(tmp_path, pit)
    vus: list[tuple[date, str]] = []
    original = llm.embed

    def espion(texts, *, date_donnees, agent="embeddings"):
        vus.append((date_donnees, agent))
        return original(texts, date_donnees=date_donnees, agent=agent)

    llm.embed = espion  # type: ignore[method-assign]
    rag.query("APEX", "risque", t, k=5)
    assert vus, "aucun embedding appelé"
    docs = [d for d, a in vus if a == "rag_index"]
    requetes = [d for d, a in vus if a == "rag_query"]
    assert docs and requetes == [t]
    # date des embeddings de documents : date d'acceptation (UTC) de leur dépôt, jamais >= t
    assert all(d <= (c - timedelta(microseconds=1)).date() for d in docs)
    assert max(docs) == (c - timedelta(microseconds=1)).date()
    assert not any(d > t for d, _ in vus)


def test_rag_ticker_en_minuscules_meme_filtre(tmp_path):
    t = date(2024, 2, 1)
    c = coupure(t)
    pit, _ = construire_stockage(
        tmp_path,
        [
            depot("0009-24-000001", "10-K", iso(c - timedelta(days=5))),
            depot("0009-24-000002", "10-K", iso(c + timedelta(days=5))),
        ],
    )
    rag, _ = _rag(tmp_path, pit)
    assert _accessions(rag.query("apex", "risque", t, k=999)) == {"0009-24-000001"}


def test_rag_aucun_chemin_ne_sert_un_passage_posterieur_k_et_questions_variees(tmp_path):
    t = date(2024, 2, 1)
    c = coupure(t)
    deps = [
        depot(f"0009-24-00000{i}", "10-Q" if i % 2 else "10-K", iso(c + timedelta(days=d)))
        for i, d in enumerate([-100, -50, -1, 0, 1, 20, 200], 1)
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, _ = _rag(tmp_path, pit, prompts_dir=None)
    rag.index_filings("APEX", t + timedelta(days=500))
    rng = random.Random(4)
    mots = [
        "risque",
        "litige",
        "marge",
        "flux",
        "dette",
        "bilan",
        "liquidité",
        "fournisseur",
        "clients",
        "capteurs",
    ]
    for _ in range(30):
        q = " ".join(rng.sample(mots, 3))
        for k in (1, 5, 50, 5000):
            res = rag.query("APEX", q, t, k=k)
            assert all(p.source.date_publication < c for p in res.passages)
            assert _accessions(res) <= {"0009-24-000001", "0009-24-000002", "0009-24-000003"}


# ====================================================================== résumé : bornes
def article(i, quand: datetime, titre=None, resume="", sem="published", tz=UTC):
    return NewsItem(
        item_id=f"n{i:03d}",
        source="src",
        published_at=quand if tz is None else quand.astimezone(tz) if quand.tzinfo else quand,
        title=titre or f"Titre {i}",
        summary=resume,
        url=f"https://x.test/{i}",
        time_semantics=sem,
        tags=(),
    )


class Scenario:
    def __init__(self):
        self.messages: list[list[dict]] = []

    def __call__(self, model, messages):
        self.messages.append(messages)
        s = messages[0]["content"]
        if "RESUME" in s or "AFFINAGE" in s:
            return json.dumps(
                {"summary": "Résumé.", "key_points": [{"text": "Point", "sources": ["N1"]}]}
            )
        return json.dumps({"problems": [], "missing": [], "verdict": "ok"})


@pytest.fixture
def prompts(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    for nom, m in (
        ("summary_summarize_v1", "RESUME"),
        ("summary_critique_v1", "CRITIQUE"),
        ("summary_refine_v1", "AFFINAGE"),
    ):
        (d / f"{nom}.md").write_text(f"{nom} {m}\n", encoding="utf-8")
    return d


def lancer(tmp_path, prompts, items, t, **kw):
    sc = Scenario()
    llm = client(tmp_path, MockTransport(handler=sc))
    out = summarize_news(llm, items, t, focus="thème", prompts_dir=prompts, **kw)
    return out, sc


@pytest.mark.parametrize("t", DATES_T)
def test_resume_bornes_a_la_microseconde_et_changements_d_heure(tmp_path, prompts, t):
    c = coupure(t)
    items = [
        article(1, c - timedelta(microseconds=1), "AVANT-1US"),
        article(2, c, "PILE-A-T"),
        article(3, c + timedelta(microseconds=1), "APRES-1US"),
        article(4, c + timedelta(days=2), "FUTUR-LOIN", "chiffres 999"),
        article(5, c - timedelta(days=1), "VEILLE"),
    ]
    out, sc = lancer(tmp_path, prompts, items, t)
    assert {s.source_id for s in out.sources} <= {"news:n001", "news:n005"}
    texte = json.dumps(sc.messages, ensure_ascii=False)
    assert "AVANT-1US" in texte and "VEILLE" in texte
    for interdit in ("PILE-A-T", "APRES-1US", "FUTUR-LOIN"):
        assert interdit not in texte
    assert out.n_items == 2
    assert all(s.date_publication < c for s in out.sources)


def test_resume_fuseau_autre_que_utc_compare_en_instants(tmp_path, prompts):
    t = date(2024, 4, 1)
    c = coupure(t)  # 2024-03-31 22:00 UTC = 2024-04-01 00:00 Paris
    paris = ZoneInfo("Europe/Paris")
    ny = ZoneInfo("America/New_York")
    items = [
        article(1, (c - timedelta(seconds=1)).astimezone(paris), "PARIS-AVANT"),
        article(2, c.astimezone(paris), "PARIS-PILE"),  # 00:00 Paris le 1er avril : exclu
        article(3, (c - timedelta(seconds=1)).astimezone(ny), "NY-AVANT"),
        article(4, (c + timedelta(seconds=1)).astimezone(ny), "NY-APRES"),
    ]
    out, sc = lancer(tmp_path, prompts, items, t)
    texte = json.dumps(sc.messages, ensure_ascii=False)
    assert "PARIS-AVANT" in texte and "NY-AVANT" in texte
    assert "PARIS-PILE" not in texte and "NY-APRES" not in texte


def test_resume_gdelt_seendate_meme_borne_et_signale(tmp_path, prompts):
    t = date(2024, 2, 1)
    c = coupure(t)
    items = [
        article(1, c - timedelta(microseconds=1), "GDELT-AVANT", sem="seendate"),
        article(2, c, "GDELT-PILE", sem="seendate"),
        article(3, c - timedelta(days=1), "RSS-OK", sem="published"),
    ]
    out, sc = lancer(tmp_path, prompts, items, t)
    texte = json.dumps(sc.messages, ensure_ascii=False)
    assert "GDELT-PILE" not in texte
    # l'article GDELT d'avant la coupure est cité avec la mention de sa sémantique de date
    gd = [s for s in out.sources if s.source_id == "news:n001"]
    assert gd and "date d'observation GDELT" in gd[0].titre


def test_resume_dates_sans_fuseau_et_semantique_inconnue_refusees(tmp_path, prompts):
    c = coupure(date(2024, 2, 1))
    naif = NewsItem(
        item_id="x1",
        source="s",
        published_at=(c - timedelta(hours=1)).replace(tzinfo=None),
        title="t",
        summary="",
        url="u",
        time_semantics="published",
        tags=(),
    )
    with pytest.raises(ValueError):
        lancer(tmp_path, prompts, [naif], date(2024, 2, 1))
    inconnu = article(2, c - timedelta(hours=1), sem="fetched")
    with pytest.raises(ValueError):
        lancer(tmp_path, prompts, [inconnu], date(2024, 2, 1))
    # un article futur avec une sémantique inconnue lève aussi (jamais accepté en silence)
    futur_inconnu = article(3, c + timedelta(hours=1), sem="fetched")
    with pytest.raises(ValueError):
        lancer(tmp_path, prompts, [futur_inconnu], date(2024, 2, 1))


def test_resume_ordre_d_insertion_sans_effet_et_doublons_ecartes(tmp_path, prompts):
    t = date(2024, 2, 1)
    c = coupure(t)
    base = [article(i, c - timedelta(hours=i), f"T{i}", f"corps {i}") for i in range(1, 9)]
    doublon_futur = article(1, c + timedelta(days=1), "T1-FUTUR")  # même id, date future
    doublon_identique = article(2, c - timedelta(hours=2), "T2", "corps 2")  # copie exacte
    items = [*base, doublon_futur, doublon_identique]
    a, sa = lancer(tmp_path / "a", prompts, items, t)
    melange = list(items)
    random.Random(1).shuffle(melange)
    b, sb = lancer(tmp_path / "b", prompts, melange, t)
    # même résumé, mêmes sources, mêmes messages (la sélection est triée, pas dépendante de l'ordre)
    assert a.sources == b.sources and a.n_items == b.n_items == 8
    assert json.dumps(sa.messages[0]) == json.dumps(sb.messages[0])
    assert "T1-FUTUR" not in json.dumps(sa.messages) + json.dumps(sb.messages)


def test_resume_tous_futurs_aucun_appel_et_aucune_source(tmp_path, prompts):
    t = date(2024, 2, 1)
    c = coupure(t)
    out, sc = lancer(tmp_path, prompts, [article(i, c + timedelta(hours=i)) for i in range(5)], t)
    assert sc.messages == [] and out.sources == [] and out.n_calls == 0 and out.n_items == 0


def test_resume_plafond_max_items_garde_les_plus_recents_avant_t(tmp_path, prompts):
    from amundi_agentic.tools.text_config import SummaryConfig

    t = date(2024, 2, 1)
    c = coupure(t)
    items = [article(i, c - timedelta(hours=i), f"T{i}") for i in range(1, 11)]
    items += [article(99, c + timedelta(minutes=1), "FUTUR-PLAFOND")]
    sc = Scenario()
    llm = client(tmp_path, MockTransport(handler=sc))
    out = summarize_news(
        llm, items, t, focus="x", prompts_dir=prompts, config=SummaryConfig(max_items=3)
    )
    assert out.n_items == 3
    texte = json.dumps(sc.messages, ensure_ascii=False)
    assert "T1" in texte and "T2" in texte and "T3" in texte
    assert "FUTUR-PLAFOND" not in texte and "T4" not in texte and "T10" not in texte


_ = pd


def test_resume_doublon_d_identifiant_version_la_plus_ancienne_avant_t_quel_que_soit_l_ordre(
    tmp_path, prompts
):
    """Règle (corrigée) : pour un même item_id, on garde la version de date de publication la plus
    ancienne avant t (celle de date >= t est ignorée) ; à date égale, une règle déterministe fondée
    sur le contenu. Le résultat ne dépend jamais de l'ordre d'entrée."""
    import itertools

    t = date(2024, 2, 1)
    c = coupure(t)
    recente = article(7, c - timedelta(hours=1), "VERSION-RECENTE")
    ancienne = article(7, c - timedelta(days=9), "VERSION-ANCIENNE")
    future = article(7, c + timedelta(days=1), "VERSION-FUTURE")
    reste = article(8, c - timedelta(hours=3), "AUTRE")
    versions = [recente, ancienne, future, reste]
    sorties = set()
    for n, perm in enumerate(itertools.permutations(versions)):
        _, sc = lancer(tmp_path / f"p{n}", prompts, list(perm), t)
        texte = json.dumps(sc.messages[0], ensure_ascii=False)
        assert "VERSION-ANCIENNE" in texte
        assert "VERSION-RECENTE" not in texte and "VERSION-FUTURE" not in texte and "AUTRE" in texte
        sorties.add(texte)
    assert len(sorties) == 1  # messages identiques pour les 24 permutations


def test_resume_doublon_a_date_egale_departage_deterministe_independant_de_l_ordre(
    tmp_path, prompts
):
    import itertools

    t = date(2024, 2, 1)
    c = coupure(t)
    quand = c - timedelta(hours=2)
    versions = [article(9, quand, f"CONTENU-{k}", resume=f"corps {k}") for k in "ABC"]
    sorties = set()
    for n, perm in enumerate(itertools.permutations(versions)):
        _, sc = lancer(tmp_path / f"e{n}", prompts, list(perm), t)
        sorties.add(json.dumps(sc.messages[0], ensure_ascii=False))
    assert len(sorties) == 1
    (texte,) = sorties
    assert sum(f"CONTENU-{k}" in texte for k in "ABC") == 1  # une seule version conservée


@pytest.mark.parametrize("t", DATES_T)
def test_rag_double_garde_vue_plus_tardive_bornes_a_la_microseconde(tmp_path, t):
    """Le filtre propre au RAG (indépendant de celui de la couche de données) doit être strict :
    avec une vue ouverte bien après t, un dépôt accepté EXACTEMENT à la coupure ne sort pas."""
    c = coupure(t)
    deps = [
        depot("0009-24-000001", "10-K", iso(c - timedelta(microseconds=1))),
        depot("0009-24-000002", "10-Q", iso(c), rapport_10q()),
        depot("0009-24-000003", "10-Q", iso(c + timedelta(microseconds=1)), rapport_10q()),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    vue_tardive = pit.as_of(t + timedelta(days=400))
    rag = FilingsRAG(
        client(tmp_path),
        store_dir=tmp_path / "rag",
        data_view=vue_tardive,
        config=load_text_tools_config().rag,
    )
    res = rag.query("APEX", "risque", t, k=999)
    assert _accessions(res) == {"0009-24-000001"}
    assert rag.index_filings("APEX", t) == len(res.passages)
