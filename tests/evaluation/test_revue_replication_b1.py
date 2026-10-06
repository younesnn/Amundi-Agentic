# ruff: noqa: E501
"""Revue indépendante de la correction B1 : l'éligibilité ne lit que des données connues à t ; un titre
dont les prix s'arrêtent est GELÉ à sa dernière clôture (jamais exclu, jamais remplacé).

Aucun réseau, aucune clé, aucun LLM réel.
"""

from __future__ import annotations

import json
import re
from datetime import date

import numpy as np
import pandas as pd
import pytest

from amundi_agentic.data.models import LookAheadError
from amundi_agentic.evaluation import analyse, perf
from amundi_agentic.evaluation import rapport as rp
from amundi_agentic.evaluation.repl_config import charger_config
from amundi_agentic.evaluation.sources import SourceReelle, etat_pool
from amundi_agentic.evaluation.tirage import Tirage, tirage_primaire
from amundi_agentic.tools.base import MissingDataError

CFG = charger_config()
T = date(2024, 2, 1)
IDX = pd.bdate_range("2024-02-01", "2024-05-31")


# ============================================================ éligibilité : espion et jeux opposés
class _Vue:
    def __init__(self, series, t_vue, journal):
        self._s, self._t, self._j = series, t_vue, journal

    def prices(self, tickers, start=None, field="adj_close"):
        for t in tickers:
            if t not in self._s:
                raise KeyError(t)
        df = pd.DataFrame({t: self._s[t] for t in tickers})
        self._j.append(("prices", self._t, None if not len(df) else df.index.max()))
        return df

    def filings(self, ticker, forms):
        self._j.append(("filings", self._t, None))
        return [object()]


class _Pit:
    def __init__(self, series):
        self.series, self.journal = series, []

    def as_of(self, d):
        self.journal.append(("as_of", d, None))
        if d > T:
            raise AssertionError(
                f"as_of({d}) demandé par l'éligibilité : lecture possible de l'après-t"
            )
        # la vue est réellement coupée à t : seules les barres < t sont servies
        coupees = {k: v[v.index < pd.Timestamp(d)] for k, v in self.series.items()}
        return _Vue(coupees, d, self.journal)


def _source(series):
    s = SourceReelle.__new__(SourceReelle)
    s._pit = _Pit(series)
    s.pool = lambda: sorted(series)  # type: ignore[method-assign]
    return s


def _serie(valeurs_apres="plat", trous=(), debut="2023-01-02", fin="2024-07-31", graine=0):
    idx = pd.bdate_range(debut, fin)
    rng = np.random.default_rng(graine)
    s = pd.Series(100.0 + rng.normal(0, 1, len(idx)).cumsum(), index=idx).abs() + 1
    apres = s.index >= pd.Timestamp(T)
    if valeurs_apres == "hausse":
        s[apres] = 100.0 * (1.02 ** np.arange(apres.sum()))
    elif valeurs_apres == "baisse":
        s[apres] = 100.0 * (0.98 ** np.arange(apres.sum()))
    return s.drop(pd.to_datetime(list(trous))) if len(trous) else s


def test_eligibilite_n_ouvre_qu_une_vue_a_t_et_ne_demande_jamais_as_of_performance():
    src = _source({"A": _serie(), "B": _serie(graine=1)})
    assert src.eligibilite("A", CFG) == (True, "utilisable")
    vues = {d for (k, d, _) in src._pit.journal if k == "as_of"}
    assert vues == {T}
    assert all(m is None or m < pd.Timestamp(T) for (k, _, m) in src._pit.journal if k == "prices")


def test_deux_jeux_de_prix_opposes_apres_t_meme_eligibilite_meme_pool_meme_tirage():
    tickers = [f"S{i:02d}" for i in range(40)]
    monde_haut = {t: _serie("hausse", graine=i) for i, t in enumerate(tickers)}
    monde_bas = {t: _serie("baisse", graine=i) for i, t in enumerate(tickers)}
    # trous et radiations différents APRÈS t dans le second monde : ne doivent rien changer non plus
    monde_bas["S05"] = _serie("baisse", graine=5).loc[:"2024-03-15"]
    monde_bas["S06"] = _serie("baisse", graine=6, trous=["2024-03-14", "2024-04-02"])
    r1, r2 = _source(monde_haut), _source(monde_bas)
    e1, e2 = etat_pool(r1, CFG), etat_pool(r2, CFG)
    assert e1.utilisables == e2.utilisables == sorted(tickers) and e1.exclus == e2.exclus == {}
    t1 = tirage_primaire(e1.utilisables, hors_pool="ZS", n=14, graine=CFG.tirage.graine)
    t2 = tirage_primaire(e2.utilisables, hors_pool="ZS", n=14, graine=CFG.tirage.graine)
    assert t1 == t2
    # le journal des deux espions : aucune demande postérieure à t
    for r in (r1, r2):
        assert {d for (k, d, _) in r._pit.journal if k == "as_of"} == {T}


def test_titre_radie_apres_t_reste_utilisable_et_dans_le_pool():
    src = _source(
        {"A": _serie(), "RADIE": _serie(graine=3).loc[:"2024-02-20"], "C": _serie(graine=2)}
    )
    assert src.eligibilite("RADIE", CFG) == (True, "utilisable")


def test_regles_d_eligibilite_restantes_ne_lisent_que_l_avant_t():
    court = _serie(debut="2023-06-01")
    ok, motif = _source({"A": court}).eligibilite("A", CFG)
    assert not ok and "historique insuffisant" in motif
    assert (
        "suivi_complet_requis" not in CFG.model_dump()["pool"]
        and "titre_sans_prix_en_fin_de_suivi" in CFG.model_dump()["pool"]
    )
    assert CFG.pool.titre_sans_prix_en_fin_de_suivi == "derniere_valeur_connue"


# ============================================================ gel : calcul à la main
def _prix_gel(n=60, arret=20):
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2024-02-01", periods=n)
    base = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, (n, 2)), axis=0)
    p = pd.DataFrame(base, index=idx, columns=["A", "B"])
    p.iloc[0] = 100.0
    p.loc[idx[arret + 1 :], "B"] = (
        np.nan
    )  # B s'arrête après le jour `arret` (indice 20 = dernier prix)
    return p


def test_titre_radie_conserve_gele_rendement_calcule_a_la_main():
    p = _prix_gel()
    g, cas = perf.geler(p)
    assert not g.isna().any().any()
    dernier_b = p["B"].iloc[20]
    assert (g["B"].iloc[21:] == dernier_b).all()
    v = perf.valeur_portefeuille(g, ["A", "B"])
    # oracle : poids initiaux 1/2 ; B vaut dernier_b / B_0 à partir du jour 21 (position gelée)
    a0, b0 = p["A"].iloc[0], p["B"].iloc[0]
    for k in (10, 20, 21, 35, 59):
        bk = p["B"].iloc[min(k, 20)]
        assert v.iloc[k] == pytest.approx(0.5 * p["A"].iloc[k] / a0 + 0.5 * bk / b0, rel=1e-12)
    # rendement cumulé final à la main
    attendu = 0.5 * p["A"].iloc[-1] / a0 + 0.5 * dernier_b / b0 - 1
    assert v.iloc[-1] - 1 == pytest.approx(attendu, rel=1e-12)
    assert cas == {"B": {"derniere_cloture": str(p.index[20].date()), "seances_gelees": 39}}
    # jamais exclu ni remplacé : le titre reste une colonne du portefeuille, un autre titre ne le remplace pas
    assert list(g.columns) == ["A", "B"]


def test_entree_a_une_cloture_absente_premiere_cloture_disponible_et_cas_listes():
    p = _prix_gel(n=30, arret=29)
    p.loc[p.index[:3], "A"] = np.nan  # A sans clôture aux 3 premières séances
    g, cas = perf.geler(p)
    assert (g["A"].iloc[:3] == p["A"].iloc[3]).all()  # entrée = première clôture disponible
    assert cas["A"] == {"premiere_cloture": str(p.index[3].date())}
    v = perf.valeur_portefeuille(g, ["A"])
    assert v.iloc[3] == pytest.approx(1.0) and v.iloc[-1] == pytest.approx(
        p["A"].iloc[-1] / p["A"].iloc[3]
    )


def test_titre_sans_aucune_cloture_dans_le_suivi_erreur_explicite_au_niveau_de_geler():
    p = _prix_gel()
    with pytest.raises(MissingDataError):
        perf.geler(p.assign(Z=np.nan))


class _VuePrix:
    def __init__(self, series):
        self.s = series

    def prices(self, tickers, start=None, field="adj_close"):
        df = pd.DataFrame({t: self.s[t] for t in tickers if t in self.s})
        if start is not None:
            df = df[df.index >= pd.Timestamp(start)]
        return df


class _PitPrix:
    def __init__(self, series):
        self.series = series

    def as_of(self, d):
        return _VuePrix({k: v[v.index < pd.Timestamp(d)] for k, v in self.series.items()})


def test_source_reelle_titre_sans_aucune_cloture_dans_le_suivi_recoit_sa_derniere_cloture_connue_a_t():
    idx = pd.bdate_range("2023-06-01", "2024-07-31")
    plein = pd.Series(100.0, index=idx)
    mort = pd.Series(
        np.linspace(50, 60, len(idx[idx < pd.Timestamp("2024-01-25")])),
        index=idx[idx < pd.Timestamp("2024-01-25")],
    )
    s = SourceReelle.__new__(SourceReelle)
    s._pit = _PitPrix({"VIVANT": plein, "MORT": mort})
    df = s.prix_suivi(["VIVANT", "MORT"], CFG)
    assert df.index.min() == pd.Timestamp("2024-02-01") and df.index.max() == pd.Timestamp(
        "2024-05-31"
    )
    assert df["MORT"].iloc[0] == pytest.approx(mort.iloc[-1]) and df["MORT"].iloc[1:].isna().all()
    g, cas = perf.geler(df)
    assert (g["MORT"] == mort.iloc[-1]).all() and cas["MORT"]["seances_gelees"] == len(df) - 1
    # rendement du titre : 0 % sur tout le suivi (position gelée à sa dernière valeur connue)
    assert perf.valeur_portefeuille(g, ["MORT"]).iloc[-1] == pytest.approx(1.0)


def test_la_regle_de_gel_ne_depend_d_aucun_rendement_seulement_du_masque_de_disponibilite():
    p1 = _prix_gel()
    p2 = p1.copy()
    p2.loc[:, "A"] = 1e3 / (1 + np.arange(len(p2)))  # valeurs radicalement différentes
    p2.loc[p2["B"].notna(), "B"] = np.linspace(500, 1, int(p2["B"].notna().sum()))
    assert p1.isna().equals(p2.isna())
    _, c1 = perf.geler(p1)
    _, c2 = perf.geler(p2)
    assert c1 == c2  # les informations de gel ne contiennent que des dates et des comptes
    import inspect

    assert (
        "pct_change" not in inspect.getsource(perf.geler)
        and "rendement" not in inspect.getsource(perf.geler).split('"""')[2]
    )


def test_geler_ne_change_aucune_valeur_connue_et_ne_remplit_que_les_trous_de_fin_et_d_entree():
    p = _prix_gel()
    g, _ = perf.geler(p)
    connu = p.notna()
    assert g.where(connu).equals(p.where(connu))  # les valeurs connues sont intactes
    # trou INTÉRIEUR : reporté par la dernière valeur (aucune interpolation)
    q = _prix_gel(arret=59)
    q.loc[q.index[10:13], "A"] = np.nan
    gq, _ = perf.geler(q)
    assert (gq["A"].iloc[10:13] == q["A"].iloc[9]).all()


# ============================================================ de bout en bout via analyser
TIT = ["ZS"] + [f"T{i:02d}" for i in range(14)]


class _Src:
    synthetique = True

    def __init__(self, arret_t05=None):
        rng = np.random.default_rng(2)
        r = rng.normal(0.0004, 0.014, (len(IDX), len(TIT)))
        r[0] = 0
        self.p = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=IDX, columns=TIT)
        if arret_t05 is not None:
            self.p.loc[IDX[arret_t05 + 1 :], "T05"] = np.nan
        self.tx = pd.Series(5.3, index=pd.bdate_range("2024-01-02", "2024-05-31"))

    def prix_suivi(self, titres, cfg):
        return self.p[list(titres)]

    def taux_suivi(self, cfg):
        return self.tx


def _debat(v, f, final):
    return {
        "statut_debat": "ok",
        "votes_tour0": {"valuation": v, "fundamental": f},
        "final": {
            "niveau": final,
            "statut": "consensus",
            "confiance": 0.5,
            "tours": 1,
            "plafonnee_par": None,
        },
        "sans_decision": None,
        "votants": [],
        "rejets": [],
        "prompts_sha256": {},
        "modeles_servis": [],
        "appels_reels": 0,
        "cache_hits": 0,
        "par_fournisseur": {},
        "tokens_entree": 0,
        "tokens_sortie": 0,
        "duree_s": 0.0,
    }


def _analyse(src):
    cfg = charger_config(
        overrides={
            "tirage": {"n_titres": 14, "n_tirages_secondaires": 0},
            "inference": {"bootstrap": {"n_reechantillonnages": 100}},
            "profils": ["risk_averse"],
            "executions": [
                {"nom": "baseline", "temperature": 0.0, "paraphrase": None, "graine_llm": 0}
            ],
        }
    )
    debats = {f"baseline|risk_averse|{t}": _debat(1, 1, 1) for t in TIT}
    tir = Tirage(tuple(TIT[1:]), tuple(TIT), tuple(TIT[1:]))
    return analyse.analyser(cfg, src, debats, {}, tir, TIT, ["baseline"])


def test_analyser_garde_le_titre_radie_dans_le_portefeuille_et_calcule_le_rendement_gele():
    src = _Src(arret_t05=20)
    res = _analyse(src)
    pf = res["executions"]["baseline"]["risk_averse"]["portefeuilles"]["multi_agent"]
    assert "T05" in pf["titres"] and pf["m"] == 15  # jamais exclu, jamais remplacé
    gele = src.p.ffill()
    attendu = (gele.iloc[-1] / gele.iloc[0]).mean() - 1
    assert pf["cumul"] == pytest.approx(attendu, rel=1e-12)
    assert res["prix_arretes_avant_la_fin"] == {
        "T05": {"derniere_cloture": str(IDX[20].date()), "seances_gelees": len(IDX) - 21}
    }
    assert res["titres"]["primaire"] == TIT  # le tirage primaire est inchangé


def test_sans_arret_aucun_gel_et_section_du_rapport_dit_aucun():
    res = _analyse(_Src())
    assert res["prix_arretes_avant_la_fin"] == {}


def _rendre(res_extra):
    # rapport minimal à partir d'un run analysé : on réutilise rendre_rapport avec des méta de test
    res = _analyse(_Src(arret_t05=20))
    cfg = charger_config(
        overrides={
            "profils": ["risk_averse"],
            "executions": [
                {"nom": "baseline", "temperature": 0.0, "paraphrase": None, "graine_llm": 0}
            ],
        }
    )
    verdict = rp.calculer_verdict(res, cfg)
    meta = {
        "etiquettes": [("(simulé)", cfg.modele.etiquette_simule)],
        "preenregistrement": {"statut": "absent", "sha256": None},
        "graine_sha256": "x",
        "graine_verifiee": False,
        "n_pool": 1,
        "n_utilisables": 1,
        "exclus": {},
        "remplaces": {},
        "executions": ["baseline"],
        "modeles_servis": {},
        "qualitatif": [],
        "simule": True,
    }
    return rp.rendre_rapport(cfg, res, verdict, meta)


def test_section_du_rapport_liste_les_titres_geles_avec_dates_et_regle():
    texte = _rendre(None)
    bloc = texte.split("## Titres dont les prix s'arrêtent avant la fin du suivi")[1].split(
        "\n## "
    )[0]
    assert "T05" in bloc and "dernière clôture 2024-02-29" in bloc.replace(
        "2024-02-29", "2024-02-29"
    )
    assert (
        "position gelée" in bloc
        and "ne sont pas exclus" in bloc
        and "Règle fixée avant les résultats" in bloc
    )
    assert "ESSAI DE MÉCANIQUE" in texte  # bandeau (simulé)
    assert rp.formulations_interdites(texte) == []


_ = (json, re, LookAheadError)
