"""RAG par sections sur les 10-K et 10-Q : découpage, point-in-time, citations, cache, idempotence.

Tout est synthétique et passe par `MockLLMClient` : aucune clé, aucun réseau (EX-NF-12).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
from text_helpers import (
    BagTransport,
    client,
    construire_stockage,
    depot,
    paragraphes,
    rapport_10k,
    rapport_10q,
    ts,
)

from amundi_agentic.data.pit import cutoff_utc
from amundi_agentic.schemas import Source
from amundi_agentic.tools.rag import (
    FilingsRAG,
    NoFilingsError,
    chunk_text,
    guide_for,
    load_guide,
    load_questions,
    rag_prompt_refs,
    section_code,
    split_sections,
)
from amundi_agentic.tools.text_config import PROMPTS_DIR, RagConfig, load_text_tools_config

T = date(2024, 2, 1)  # coupure : 2024-01-31 23:00 UTC (minuit à Paris)


def _rag(tmp_path, pit, transport=None, **cfg):
    base = load_text_tools_config().rag
    config = base.model_copy(update=cfg) if cfg else base
    llm = client(tmp_path, transport)
    return FilingsRAG(llm, store_dir=tmp_path / "rag", data_view=pit, config=config), llm


# --------------------------------------------------------------------------- découpage
def test_rag_decoupe_par_section():
    sections = split_sections(rapport_10k(), "10-K")
    codes = [s.code for s in sections]
    assert codes == ["Préambule", "Item 1", "Item 1A", "Item 7", "Item 8"]
    par_code = {s.code: s for s in sections}
    # la table des matières n'est pas retenue comme section : le corps vient du vrai en-tête
    assert "capteurs industriels" in par_code["Item 1"].text
    assert "Item 1A. Risk Factors 8" in par_code["Préambule"].text
    assert par_code["Item 1A"].label == "Item 1A - Risk Factors"
    # « Item 7 of this report » est un renvoi, pas un en-tête : il reste dans la section 1A
    assert "Item 7 of this report" in par_code["Item 1A"].text
    assert section_code("Item 1A - Risk Factors") == "Item 1A"


def test_rag_decoupe_10q_par_partie_et_item():
    codes = [s.code for s in split_sections(rapport_10q(), "10-Q")]
    assert codes == ["Préambule", "Part1-Item1", "Part1-Item2", "Part2-Item1A"]


def test_repli_explicite_sans_en_tetes():
    texte = paragraphes("Texte libre", 5, "aucun en-tête reconnu")
    sections = split_sections(texte, "10-K")
    assert [s.code for s in sections] == ["Document"]
    assert sections[0].label == "Document"
    assert split_sections("   ", "10-K") == []


def test_table_des_matieres_seule_tombe_dans_le_repli():
    toc = "Table of contents\n\nItem 1. Business 3\n\nItem 1A. Risk Factors 8\n\nItem 7. MD&A 20\n"
    assert [s.code for s in split_sections(toc, "10-K")] == ["Document"]


def test_chunk_text_paragraphes_et_coupure_longue():
    p = ["alpha " * 20, "beta " * 20, "gamma " * 20]
    morceaux = chunk_text("\n\n".join(p), size=300, overlap=40, min_chars=10)
    assert all(len(m) <= 300 for m in morceaux)
    assert "alpha" in morceaux[0] and "gamma" in morceaux[-1]
    long = "mot " * 400
    coupes = chunk_text(long, size=300, overlap=50, min_chars=10)
    assert len(coupes) >= 5 and all(len(m) <= 300 for m in coupes)
    assert chunk_text("None.", size=300, overlap=0, min_chars=80) == [
        "None."
    ]  # section très courte


# --------------------------------------------------------------------------- point-in-time
def _depots_autour_de_t():
    cut = cutoff_utc(T)
    avant = (cut - __import__("pandas").Timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S")
    exact = cut.strftime("%Y-%m-%dT%H:%M:%S")
    return [
        depot("0001-24-000001", "10-K", "2023-11-03T21:00:00"),
        depot("0001-24-000002", "10-Q", avant, rapport_10q()),
        depot("0001-24-000003", "10-Q", exact, rapport_10q()),  # exactement à la coupure : exclu
        depot("0001-24-000004", "10-K", "2024-05-10T12:00:00"),  # postérieur
    ]


def test_rag_ne_sert_que_les_depots_avant_t(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, _ = _rag(tmp_path, pit)
    # on indexe d'abord pour une date ultérieure : les quatre dépôts sont sur le disque
    assert rag.index_filings("APEX", date(2024, 6, 1)) > 0
    assert (tmp_path / "rag" / "APEX" / "0001-24-000004" / "chunks.json").is_file()
    assert (tmp_path / "rag" / "APEX" / "0001-24-000003" / "chunks.json").is_file()
    # pour t, seuls les deux premiers sortent, quelle que soit la question et k
    for question in ("risque litige", "marge brute flux", "dette échéances"):
        res = rag.query("APEX", question, T, k=500)
        accessions = {p.source.source_id.split(":")[2] for p in res.passages}
        assert accessions == {"0001-24-000001", "0001-24-000002"}
        assert all(p.source.date_publication < cutoff_utc(T) for p in res.passages)
        assert res.n_chunks_indexed == len(res.passages)  # k géant : tous les passages éligibles


def test_nombre_de_passages_indexes_ne_compte_que_les_eligibles(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, _ = _rag(tmp_path, pit)
    n_t = rag.index_filings("APEX", T)
    n_tard = rag.index_filings("APEX", date(2024, 6, 1))
    assert 0 < n_t < n_tard


def test_vue_plus_recente_que_as_of_ne_fait_pas_fuir(tmp_path):
    """Une DataView ouverte à une date ultérieure ne doit rien servir de postérieur à as_of."""
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    vue_tardive = pit.as_of(date(2024, 12, 31))
    rag = FilingsRAG(client(tmp_path), store_dir=tmp_path / "rag", data_view=vue_tardive)
    res = rag.query("APEX", "risque", T, k=500)
    assert {p.source.source_id.split(":")[2] for p in res.passages} == {
        "0001-24-000001",
        "0001-24-000002",
    }


def test_vue_plus_ancienne_que_as_of_refusee(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag = FilingsRAG(client(tmp_path), store_dir=tmp_path / "rag", data_view=pit.as_of(T))
    with pytest.raises(ValueError, match="postérieur"):
        rag.query("APEX", "risque", date(2024, 6, 1))


def test_aucun_depot_avant_t(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, llm = _rag(tmp_path, pit)
    res = rag.query("APEX", "risque", date(2020, 1, 1))
    assert res.passages == [] and res.n_chunks_indexed == 0
    assert rag.index_filings("APEX", date(2020, 1, 1)) == 0


def test_garde_fous_d_entree(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, _ = _rag(tmp_path, pit)
    with pytest.raises(TypeError):
        rag.query("APEX", "q", __import__("datetime").datetime(2024, 2, 1))  # type: ignore[arg-type]
    with pytest.raises(NoFilingsError):
        rag.query("ZZZZ", "q", T)
    with pytest.raises(ValueError):
        rag.query("APEX", "q", T, k=0)
    sans_vue = FilingsRAG(client(tmp_path), store_dir=tmp_path / "x")
    with pytest.raises(ValueError, match="data_view"):
        sans_vue.index_filings("APEX", T)


def test_depot_sans_texte_ignore(tmp_path):
    deps = [depot("0001-24-000001", "10-K", "2023-11-03T21:00:00")]
    deps.append({**depot("0001-24-000009", "10-Q", "2023-12-01T21:00:00"), "texte": None})
    pit, _ = construire_stockage(tmp_path, deps)
    rag, _ = _rag(tmp_path, pit)
    res = rag.query("APEX", "risque", T, k=500)
    assert {p.source.source_id.split(":")[2] for p in res.passages} == {"0001-24-000001"}


def test_max_filings_garde_les_plus_recents(tmp_path):
    deps = [
        depot("0001-23-000001", "10-K", "2022-11-03T21:00:00"),
        depot("0001-23-000002", "10-Q", "2023-05-03T21:00:00"),
        depot("0001-23-000003", "10-Q", "2023-08-03T21:00:00"),
    ]
    pit, _ = construire_stockage(tmp_path, deps)
    rag, _ = _rag(tmp_path, pit, max_filings=2)
    res = rag.query("APEX", "risque", T, k=500)
    assert {p.source.source_id.split(":")[2] for p in res.passages} == {
        "0001-23-000002",
        "0001-23-000003",
    }


# --------------------------------------------------------------------------- citations
def test_chaque_passage_porte_une_source_valide(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, _ = _rag(tmp_path, pit, chunk_chars=1800)
    res = rag.query("APEX", "risque litige réglementation", T, k=5)
    assert len(res.passages) == 5
    for p in res.passages:
        s = Source.model_validate(p.source.model_dump())  # citation valide, ré-analysable
        assert s.type == "depot_sec"
        assert s.date_publication.utcoffset().total_seconds() == 0
        assert len(s.extrait) <= 500 and s.extrait
        assert p.source.reference.startswith("https://www.sec.gov/Archives/edgar/data/1234567/")
        assert p.section.startswith(("Item", "Part", "Document", "Préambule"))
        assert p.source.titre.startswith("APEX 10-")
    assert res.passages[0].section == "Item 1A - Risk Factors"
    scores = [p.score for p in res.passages]
    assert scores == sorted(scores, reverse=True)


def test_extrait_tronque_a_500_caracteres(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, _ = _rag(tmp_path, pit)
    res = rag.query("APEX", "risque", T, k=20)
    longs = [p for p in res.passages if len(p.text) > 500]
    assert longs
    assert all(len(p.source.extrait) <= 500 for p in longs)


def test_source_id_stable_entre_deux_constructions(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    a, _ = _rag(tmp_path, pit)
    ids_a = [p.source.source_id for p in a.query("APEX", "risque", T, k=10).passages]
    b = FilingsRAG(client(tmp_path / "autre"), store_dir=tmp_path / "rag_bis", data_view=pit)
    ids_b = [p.source.source_id for p in b.query("APEX", "risque", T, k=10).passages]
    assert ids_a == ids_b and len(set(ids_a)) == len(ids_a)


def test_date_publication_est_la_date_d_acceptation(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    rag, _ = _rag(tmp_path, pit)
    res = rag.query("APEX", "risque", T, k=500)
    for p in res.passages:
        acc = p.source.source_id.split(":")[2]
        attendu = {"0001-24-000001": ts("2023-11-03T21:00:00")}.get(acc)
        if attendu is not None:
            assert p.source.date_publication == attendu.to_pydatetime()


# --------------------------------------------------------------------------- embeddings, cache
def test_embeddings_par_llmclient_uniquement_avec_prefixes_du_profil(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    tr = BagTransport()
    rag, llm = _rag(tmp_path, pit, transport=tr)
    rag.query("APEX", "risque litige", T, k=3)
    embeds = [c for c in tr.calls if c["kind"] == "embed"]
    assert embeds and not tr.chat_calls  # jamais d'appel de complétion
    assert all(c["model"] == llm.config.embedding_model("dev") for c in embeds)
    docs = [x for c in embeds for x in c["inputs"] if x.startswith("search_document: ")]
    assert docs and tr.embed_inputs[-1] == "search_query: risque litige"
    assert all(r.agent in {"rag_index", "rag_query"} for r in llm.records)


def test_reconstruction_idempotente_sans_nouvel_embedding(tmp_path):
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    t1 = BagTransport()
    rag1, _ = _rag(tmp_path, pit, transport=t1)
    n1 = rag1.index_filings("APEX", T)
    appels1 = len(t1.embed_inputs)
    assert n1 > 0 and appels1 == n1
    fichiers = sorted(p.name for p in (tmp_path / "rag").rglob("*") if p.is_file())
    # nouvelle instance, cache LLM vide : le cache du RAG (dépôt, empreinte, modèle) suffit
    t2 = BagTransport()
    rag2 = FilingsRAG(client(tmp_path / "frais", t2), store_dir=tmp_path / "rag", data_view=pit)
    assert rag2.index_filings("APEX", T) == n1
    assert t2.embed_inputs == []
    assert rag2.index_filings("APEX", T) == n1  # idempotent
    assert sorted(p.name for p in (tmp_path / "rag").rglob("*") if p.is_file()) == fichiers
    # le même résultat de requête avant et après reconstruction
    q1 = [p.source.source_id for p in rag1.query("APEX", "marge", T, k=5).passages]
    q2 = [p.source.source_id for p in rag2.query("APEX", "marge", T, k=5).passages]
    assert q1 == q2


def test_cache_par_empreinte_ne_reembarque_que_le_nouveau_passage(tmp_path):
    petit = {"chunk_chars": 300, "min_chunk_chars": 20, "min_section_chars": 100}
    deps = [depot("0001-24-000001", "10-K", "2023-11-03T21:00:00")]
    pit, store = construire_stockage(tmp_path, deps)
    t1 = BagTransport()
    rag, _ = _rag(tmp_path, pit, transport=t1, **petit)
    n1 = rag.index_filings("APEX", T)
    # le dépôt est corrigé en stockage : un paragraphe de plus à la fin
    store.write_text(
        "filings/text/APEX/0001-24-000001",
        rapport_10k("\n\nNouveau paragraphe inédit sur un procès récent contre la société."),
    )
    t2 = BagTransport()
    rag2 = FilingsRAG(
        client(tmp_path / "c2", t2),
        store_dir=tmp_path / "rag",
        data_view=pit,
        config=load_text_tools_config().rag.model_copy(update=petit),
    )
    n2 = rag2.index_filings("APEX", T)
    assert n2 == n1 + 1
    assert len(t2.embed_inputs) == 1 and "Nouveau paragraphe inédit" in t2.embed_inputs[0]


def test_reponse_rag_reutilisee_entre_dates(tmp_path):
    """EX-NF-04 : les embeddings d'un dépôt portent la date d'acceptation, pas la date d'analyse ;
    deux dates d'analyse différentes réutilisent donc le même cache du client LLM."""
    pit, _ = construire_stockage(tmp_path, _depots_autour_de_t())
    tr = BagTransport()
    rag, llm = _rag(tmp_path, pit, transport=tr)
    rag.index_filings("APEX", T)
    dates = {r.date_donnees for r in llm.records if r.agent == "rag_index"}
    assert dates <= {date(2023, 11, 3), date(2024, 1, 31)}
    avant = len(tr.embed_inputs)
    # autre instance de RAG (autre dossier d'index), même cache du client : aucun appel de plus
    rag_bis = FilingsRAG(llm, store_dir=tmp_path / "rag_autre", data_view=pit)
    rag_bis.index_filings("APEX", date(2024, 2, 2))
    assert len(tr.embed_inputs) == avant


# --------------------------------------------------------------------------- classement
def test_classement_par_similarite_cosinus(tmp_path):
    pit, _ = construire_stockage(tmp_path, [depot("0001-24-000001", "10-K", "2023-11-03T21:00:00")])
    rag, _ = _rag(tmp_path, pit)
    risque = rag.query("APEX", "litige procès réglementation dépendance fournisseur", T, k=3)
    assert risque.passages[0].section == "Item 1A - Risk Factors"
    flux = rag.query("APEX", "marge brute résultat flux trésorerie exploitation", T, k=3)
    assert flux.passages[0].section == "Item 7 - Management's Discussion and Analysis"
    assert risque == rag.query(
        "APEX", "litige procès réglementation dépendance fournisseur", T, k=3
    )


# --------------------------------------------------------------------------- guide et questions
def test_guide_et_questions_versionnes_et_haches(tmp_path):
    g = load_guide()
    for cle in (
        "Général",
        "Item 1",
        "Item 1A",
        "Item 7",
        "Item 7A",
        "Item 8",
        "Part1-Item2",
        "Document",
    ):
        assert g[cle]
    q = load_questions()
    assert [x.id for x in q] == [
        "cashflow_resultat",
        "exploitation_marge",
        "inquietudes_risques",
        "progres_objectifs",
    ]
    assert len(load_questions(include_optional=True)) == 6
    refs = rag_prompt_refs()
    for nom, ref in refs.items():
        assert ref.sha256 == hashlib.sha256((PROMPTS_DIR / f"{nom}.md").read_bytes()).hexdigest()
        assert ref.version == "v1"
    pit, _ = construire_stockage(tmp_path, [depot("0001-24-000001", "10-K", "2023-11-03T21:00:00")])
    rag, _ = _rag(tmp_path, pit)
    rag.index_filings("APEX", T)
    meta = json.loads((tmp_path / "rag/APEX/0001-24-000001/chunks.json").read_text())
    assert meta["prompts"] == {n: r.sha256 for n, r in refs.items()}
    assert rag.prompt_refs == refs


def test_guide_for_sections():
    texte = guide_for(["Item 1A - Risk Factors", "Item 1A - Risk Factors", "Part9-Item9 - X"])
    assert texte.count("[Guide Item 1A]") == 1
    assert "pas de guide pour cette section" in texte


def test_aucun_chiffre_d_entreprise_dans_le_guide():
    import re

    g = " ".join(load_guide().values())
    assert not re.search(r"\d+[.,]?\d*\s?(%|millions?|milliards?)", g)


def test_configuration_par_defaut_valide():
    cfg = load_text_tools_config()
    assert isinstance(cfg.rag, RagConfig)
    assert cfg.rag.prefixes["dev"].query == "search_query: "
    assert cfg.rag.prefixes["prod"].query == ""


def test_aucun_nom_de_modele_dans_les_nouveaux_fichiers():
    import re
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    fichiers = [
        racine / "src/amundi_agentic/tools/rag.py",
        racine / "src/amundi_agentic/tools/summarize.py",
        racine / "src/amundi_agentic/tools/text_config.py",
        racine / "src/amundi_agentic/evaluation/rag_eval.py",
        racine / "config/text_tools.yaml",
    ]
    interdit = re.compile(r"gemini|llama|nomic|groq|gpt-|ollama", re.IGNORECASE)
    for f in fichiers:
        code = f.read_text(encoding="utf-8")
        # les docstrings peuvent citer un modèle à titre d'exemple ; pas le code ni la config
        sans_doc = re.sub(r'""".*?"""', "", code, flags=re.DOTALL)
        sans_doc = "\n".join(
            ligne for ligne in sans_doc.splitlines() if not ligne.lstrip().startswith("#")
        )
        assert not interdit.search(sans_doc), f.name
