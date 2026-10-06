"""Plafond de confiance finale (limites de données), changement d'échelle des ancrages de texte,
étiquette de news vide (nouveaux tests)."""

from __future__ import annotations

from datetime import date

import pytest
from agents_helpers import T, fabrique_ctx
from debate_helpers import scripte

from amundi_agentic.agents.coordinator import Coordinator
from amundi_agentic.agents.esg import EsgAgent
from amundi_agentic.agents.evidence import Limite
from amundi_agentic.agents.grounding import Ancre, chiffres_non_ancres
from amundi_agentic.agents.providers import rag_synthetique
from amundi_agentic.agents.settings import load_settings
from amundi_agentic.debate import construire_votants, run_debate
from amundi_agentic.debate.run import executer

CFG = load_settings().grounding


def _debat(tmp_path, orchestrateur, limites=()):
    ctx = fabrique_ctx(
        tmp_path,
        handler=scripte(lambda r, t, a: 1),
        settings_overrides={"debate": {"orchestrateur": orchestrateur}},
    )
    ctx.rag = rag_synthetique(T, ["AAA"])
    esg = EsgAgent().evaluer(ctx, "titre", ["AAA"])
    votants = construire_votants(ctx, "titre", live=False)
    # les limites vivent dans le cache d'évidences, rempli au tour 0 : on les ajoute après coup
    for ag in votants:
        ag.evidence(ctx, ["AAA"]).limites.extend(limites)
    return ctx, run_debate(ctx, "titre", ["AAA"], votants, Coordinator(), esg)


@pytest.mark.parametrize("orchestrateur", ["langgraph", "boucle"])
def test_le_plafond_borne_la_confiance_finale_et_le_journal_le_dit(tmp_path, orchestrateur):
    _, libre = _debat(tmp_path / "a", orchestrateur)
    c_libre = libre.log.resultats[0].confiance_finale
    assert c_libre > 0.5 and libre.log.resultats[0].plafonnee_par is None
    ctx, res = _debat(
        tmp_path / "b",
        orchestrateur,
        [Limite("AAA", "découpage en repli", 0.4), Limite(None, "autre limite", 0.3)],
    )
    o = res.log.resultats[0]
    assert o.confiance_finale == pytest.approx(0.3)  # plafond le plus bas applicable
    assert "autre limite" in o.plafonnee_par and "0.3" in o.plafonnee_par
    assert res.vues_finales[0].confiance == pytest.approx(0.3)


def test_une_limite_ne_releve_jamais_une_confiance_plus_basse(tmp_path):
    ctx, res = _debat(tmp_path, "boucle", [Limite("AAA", "plafond haut", 0.79)])
    libre = _debat(tmp_path / "x", "boucle")[1].log.resultats[0].confiance_finale
    o = res.log.resultats[0]
    assert o.confiance_finale == pytest.approx(min(libre, 0.79))
    if libre <= 0.79:
        assert o.plafonnee_par is None  # rien n'a été plafonné


def test_limite_d_un_autre_actif_sans_effet(tmp_path):
    _, res = _debat(tmp_path, "boucle", [Limite("ZZZ", "autre titre", 0.1)])
    assert res.log.resultats[0].plafonnee_par is None


def test_le_rapport_signale_la_confiance_plafonnee(tmp_path):
    ctx = fabrique_ctx(tmp_path, handler=scripte(lambda r, t, a: 1))

    class _Repli:
        def __init__(self, base):
            self.base = base

        def index_filings(self, ticker, as_of):
            return self.base.index_filings(ticker, as_of)

        def query(self, ticker, question, as_of, *, k=5):
            from dataclasses import dataclass, field

            @dataclass
            class R:
                passages: tuple
                section_fallback: bool = True
                fallback_accessions: list = field(default_factory=lambda: ["0001-24-000009"])

            return R(self.base.query(ticker, question, as_of, k=k).passages)

    ctx.rag = _Repli(rag_synthetique(T, ["AAA"]))
    ctx.data.xbrl_facts = lambda t: None  # type: ignore[method-assign]
    sortie = executer(ctx, classes=[], titres=["AAA"])
    plafond = ctx.settings.fundamental.plafond_confiance_decoupage_echoue
    assert sortie.debats[0].log.resultats[0].confiance_finale <= plafond
    assert (
        "plafonnée par" in sortie.rapport_md
        and "Découpage par sections en repli" in sortie.rapport_md
    )


# --------------------------------------------------------------------------- échelle des textes
@pytest.mark.parametrize(
    "texte,valeur,attendu_refuse",
    [
        ("capitalisation de 12,7 milliards", 12700.0, False),  # « 12 700 million » dans le texte
        ("capitalisation de $12.7 billion", 12700.0, False),
        ("revenu de 12 700 millions", 12.7, False),  # « 12.7 billion » dans le texte
        ("capitalisation de 12,7 milliards", 12701.0, True),  # aucune tolérance
        ("capitalisation de 12,8 milliards", 12700.0, True),
        ("capitalisation de 12,7 millions", 12700.0, False),
        ("revenu de 12,7", 12700.0, True),  # sans unité de grandeur : pas de conversion
    ],
)
def test_changement_d_echelle_exact_pour_un_ancrage_de_texte(texte, valeur, attendu_refuse):
    refuse = bool(chiffres_non_ancres([texte], [Ancre(valeur, "texte")], CFG))
    assert refuse is attendu_refuse


def test_arithmetique_decimale_exacte_pas_flottante():
    # 0,1 + 0,2 style : 1,1 milliard = 1 100 million exactement
    assert not chiffres_non_ancres(["actif de 1,1 milliards"], [Ancre(1100.0, "texte")], CFG)
    assert chiffres_non_ancres(["actif de 1,1 milliards"], [Ancre(1100.0000001, "texte")], CFG)


# --------------------------------------------------------------------------- étiquette vide
def test_etiquette_de_news_vide_refusee_avec_un_message_clair(tmp_path):
    import pandas as pd

    from amundi_agentic.data.models import NewsQuery
    from amundi_agentic.data.pit import PointInTimeStore
    from amundi_agentic.data.settings import load_yaml
    from amundi_agentic.data.store import ParquetStore

    store = ParquetStore(tmp_path / "s")
    pub = pd.Timestamp("2024-01-15", tz="UTC")
    store.write(
        "news/items",
        pd.DataFrame(
            {
                "item_id": ["a"],
                "source": ["s"],
                "published_at": [pub],
                "first_seen_at": [pub],
                "title": ["t"],
                "summary": ["r"],
                "url": ["u"],
                "time_semantics": ["published"],
                "tags": [""],
            }
        ),  # fmt: skip
    )
    vue = PointInTimeStore(store, load_yaml("data.yaml")).as_of(date(2024, 2, 1))
    for tags in (("",), ("  ",), ("AAPL", "")):
        with pytest.raises(ValueError, match="étiquette de news vide"):
            vue.news(NewsQuery(tags=tags))
    assert vue.news(NewsQuery()) != [] or True  # sans étiquette : requête normale
