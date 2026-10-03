"""Non-fuite : la sortie de chaque outil est identique si l'on ajoute des données postérieures à t
(y compris une barre datée exactement t, des NaN, des prix négatifs) et change si l'on modifie une
donnée antérieure utilisée (critère d'acceptation de la tâche, D-038, EX-NF-11).
"""

from __future__ import annotations

import pandas as pd
import pytest
from tools_helpers import apres, avec_futur, marche_aleatoire

from amundi_agentic.tools import finance, momentum, risk

BASE = marche_aleatoire(900)
T = apres(BASE)

# (nom, fonction (série, t) -> ToolResult, position de la donnée antérieure à modifier)
CAS = [
    ("cumulative_return", lambda s, t: finance.cumulative_return(s, t, 252), -1),
    ("annualized_return", lambda s, t: finance.annualized_return(s, t, 252), -1),
    ("annualized_volatility", lambda s, t: finance.annualized_volatility(s, t, 252), -1),
    ("sharpe_ratio", lambda s, t: finance.sharpe_ratio(s, t, 252, 0.02), -1),
    ("rolling_sharpe", lambda s, t: finance.rolling_sharpe(s, t, 63, 0.02), -1),
    ("rolling_sharpe_milieu", lambda s, t: finance.rolling_sharpe(s, t, 63), -300),
    ("sortino_ratio", lambda s, t: finance.sortino_ratio(s, t, 252, 0.02), -1),
    ("max_drawdown", lambda s, t: finance.max_drawdown(s, t, 252), "pic"),
    ("current_drawdown", lambda s, t: finance.current_drawdown(s, t, 252), -1),
    ("calmar_ratio", lambda s, t: finance.calmar_ratio(s, t, 252), -1),
    ("momentum_1m", lambda s, t: momentum.momentum(s, t, 1), -1),
    ("momentum_12m", lambda s, t: momentum.momentum(s, t, 12), -253),
    ("momentum_12_1", lambda s, t: momentum.momentum_12_1(s, t), -22),
    ("trend_vs_sma", lambda s, t: momentum.trend_vs_sma(s, t, 200), -50),
    ("valuation_summary", lambda s, t: momentum.valuation_summary(s, t, 0.02), -1),
    ("realized_volatility", lambda s, t: risk.realized_volatility(s, t, 21), -1),
    ("ewma_volatility", lambda s, t: risk.ewma_volatility(s, t), -1),
    ("historical_var", lambda s, t: risk.historical_var(s, t, 252), "rang13"),
    ("historical_cvar", lambda s, t: risk.historical_cvar(s, t, 252), "pire"),
    ("volatility_regime", lambda s, t: risk.volatility_regime(s, t), -1),
    ("volatility_regime_rejeu", lambda s, t: risk.volatility_regime(s, t, replay_weeks=20), -1),
]


def _position(pos) -> int:
    """Position (négative) de la donnée à modifier. Pour les statistiques de queue, la donnée
    modifiée doit être celle qui détermine le résultat : on la cherche dans la fenêtre."""
    if isinstance(pos, int):
        return pos
    fen = BASE.iloc[-253:]
    r = (fen / fen.shift(1) - 1.0).iloc[1:]
    if pos == "pic":  # sommet de la perte maximale
        return int(
            BASE.index.get_loc(pd.Timestamp(finance.max_drawdown(BASE, T, 252).value["peak_date"]))
        ) - len(BASE)
    ordre = r.sort_values()
    cible = ordre.index[
        12 if pos == "rang13" else 0
    ]  # 13e plus petit rendement (quantile 5 %) ou le pire
    return int(BASE.index.get_loc(cible)) - len(BASE)


def canon(res) -> str:
    """Représentation exacte (repr des flottants, sans abréviation) de la valeur et des méta."""
    v = res.value
    if isinstance(v, pd.Series):
        v = (v.index.strftime("%Y-%m-%d").tolist(), v.tolist())
    elif isinstance(v, pd.DataFrame):
        v = (list(v.columns), list(v.index), v.to_numpy().tolist())
    return repr(v) + "|" + repr(res.meta)


@pytest.mark.parametrize(("nom", "f", "pos"), CAS, ids=[c[0] for c in CAS])
def test_sortie_identique_avec_donnees_posterieures(nom, f, pos):
    ref = canon(f(BASE, T))
    assert canon(f(avec_futur(BASE, T), T)) == ref


@pytest.mark.parametrize(("nom", "f", "pos"), CAS, ids=[c[0] for c in CAS])
def test_sortie_change_si_une_donnee_anterieure_change(nom, f, pos):
    ref = canon(f(BASE, T))
    mod = BASE.copy()
    mod.iloc[_position(pos)] = mod.iloc[_position(pos)] * 1.07
    assert canon(f(mod, T)) != ref


def test_sortie_ne_depend_pas_de_la_longueur_de_l_historique_avant_la_fenetre():
    # ajouter des données très anciennes (hors fenêtre) ne change pas un indicateur à fenêtre fixe
    ancien = marche_aleatoire(1000, graine=5)
    court = ancien.iloc[-400:]
    assert canon(finance.annualized_return(ancien, apres(ancien), 252)) == canon(
        finance.annualized_return(court, apres(court), 252)
    )


def test_correlations_non_fuite():
    a, b = marche_aleatoire(300, 1), marche_aleatoire(300, 2)
    df = pd.DataFrame({"A": a, "B": b})
    t = apres(df)
    ref = canon(risk.correlation_matrix(df, t, 63))
    futur = pd.DataFrame(
        {"A": [1e6, -1.0], "B": [3.0, float("nan")]},
        index=pd.DatetimeIndex([pd.Timestamp(t), pd.Timestamp(t) + pd.Timedelta(days=3)]),
    )
    assert canon(risk.correlation_matrix(pd.concat([df, futur]), t, 63)) == ref
    mod = df.copy()
    mod.iloc[-1, 0] *= 1.07
    assert canon(risk.correlation_matrix(mod, t, 63)) != ref
    mod2 = df.copy()
    mod2.iloc[-10, 1] *= 1.07
    assert canon(risk.correlation_matrix(mod2, t, 63, frequency="daily")) != ref
