"""Contre-vérification des corrections N-A, N-B, N-C : `canonical_params`, `source_id`, et la
séparation `actifs_indisponibles` / `indisponibles_techniques` de `RiskReport`.

Les oracles sont écrits ici (json.dumps, urllib, arithmétique), pas lus dans la sortie des outils.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import re
import subprocess
import sys
import textwrap
from datetime import date
from urllib.parse import quote

import numpy as np
import pandas as pd
import pytest
from tools_helpers import apres, marche_aleatoire

from amundi_agentic.tools import base, finance, risk
from amundi_agentic.tools.base import ToolError, ToolMeta, canonical_params

_ENV_HERITE = {k: os.environ[k] for k in ("PYTHONPATH",) if k in os.environ}


def _meta(series=None, params=None, tool="sharpe_ratio") -> ToolMeta:
    return ToolMeta(
        tool,
        "1.0.0",
        date(2024, 5, 3),
        date(2023, 5, 1),
        date(2024, 5, 2),
        253,
        params or {},
        series,
    )


# ================================================================ canonical_params
@pytest.mark.parametrize(
    "a,b",
    [
        (0.0123, np.float64(0.0123)),
        (252, np.int64(252)),
        (252, np.int32(252)),
        (True, np.bool_(True)),
        (False, np.bool_(False)),
        ([1, 2, 3], (1, 2, 3)),
        ([1, 2, 3], np.array([1, 2, 3])),
        ([0.5, 0.25], pd.Index([0.5, 0.25])),
        (date(2024, 5, 2), pd.Timestamp("2024-05-02").date()),
        ({"b": 1, "a": {"y": 2, "x": [3, 4]}}, {"a": {"x": (3, 4), "y": 2}, "b": np.int64(1)}),
        ({"s": {3, 1, 2}}, {"s": frozenset([2, 3, 1])}),
    ],
)
def test_canonical_params_types_equivalents_donnent_la_meme_chaine(a, b):
    assert canonical_params({"p": a}) == canonical_params({"p": b})


def test_canonical_params_oracle_json_et_valeurs_distinctes():
    p = {
        "window": np.int64(252),
        "rf": np.float64(0.02),
        "ok": np.bool_(True),
        "prev": None,
        "d": date(2024, 5, 2),
        "ts": pd.Timestamp("2024-05-02"),
        "arr": np.array([1.5, 2.5]),
        "nested": {"z": 1, "a": [1, {"k": "v"}]},
        "s": "é",
    }
    attendu = json.dumps(
        {
            "window": 252,
            "rf": 0.02,
            "ok": True,
            "prev": None,
            "d": "2024-05-02",
            "ts": "2024-05-02T00:00:00",
            "arr": [1.5, 2.5],
            "nested": {"z": 1, "a": [1, {"k": "v"}]},
            "s": "é",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert canonical_params(p) == attendu
    assert canonical_params({"a": 1}) != canonical_params({"a": 2})
    assert canonical_params({"a": 0.02}) != canonical_params({"a": 0.021})
    assert canonical_params({"a": [1, 2]}) != canonical_params(
        {"a": [2, 1]}
    )  # l'ordre d'une liste compte
    assert canonical_params({"a": True}) != canonical_params({"a": 1})  # bool distinct de int
    assert canonical_params({"a": "1"}) != canonical_params({"a": 1})
    assert canonical_params({"a": None}) != canonical_params({"a": "None"})
    assert canonical_params({}) == "{}"


def test_canonical_params_nan_inf_explicites_et_distincts():
    chaine = {
        "nan": canonical_params({"x": float("nan")}),
        "np_nan": canonical_params({"x": np.float64("nan")}),
        "inf": canonical_params({"x": float("inf")}),
        "ninf": canonical_params({"x": -np.inf}),
        "str": canonical_params({"x": "nan"}),
    }
    assert chaine["nan"] == chaine["np_nan"] == '{"x":{"__float__":"nan"}}'
    assert chaine["inf"] == '{"x":{"__float__":"inf"}}'
    assert chaine["ninf"] == '{"x":{"__float__":"-inf"}}'
    assert len({chaine["nan"], chaine["inf"], chaine["ninf"], chaine["str"]}) == 4
    json.loads(chaine["nan"])  # JSON strict valide (pas de NaN nu)
    assert "NaN" not in "".join(chaine.values()) and "Infinity" not in "".join(chaine.values())


def test_canonical_params_pas_de_repr_numpy():
    assert "np." not in canonical_params({"x": np.float64(0.5), "y": np.int64(3)})
    assert canonical_params({"x": np.float64(0.5)}) == '{"x":0.5}'


def test_canonical_params_insensible_a_l_ordre_d_insertion():
    a = canonical_params({"a": 1, "b": 2, "c": {"x": 1, "y": 2}})
    b = canonical_params({"c": {"y": 2, "x": 1}, "b": 2, "a": 1})
    assert a == b


def test_canonical_params_stable_entre_trois_processus_et_deux_appels():
    code = textwrap.dedent(
        """
        import numpy as np, pandas as pd
        from datetime import date
        from amundi_agentic.tools.base import canonical_params, ToolMeta
        p = {"s": {"b", "a", "c"}, "d": {"z": np.float64(0.1), "a": [np.int64(1), (2, 3)]},
             "t": pd.Timestamp("2024-01-02"), "n": float("nan")}
        m = ToolMeta("t", "1", date(2024, 1, 3), None, None, 0, p, "S 1")
        print(canonical_params(p)); print(m.source_id)
        """
    )
    sorties = []
    for graine in ("0", "7", "99999"):
        env = {"PYTHONHASHSEED": graine, "PATH": "/usr/bin:/bin", **_ENV_HERITE}
        r = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
        )
        sorties.append(r.stdout)
    assert sorties[0] == sorties[1] == sorties[2] and "S%201" in sorties[0]
    # deux appels dans le même processus
    p = {"s": {"b", "a"}, "x": np.float64(0.3)}
    assert canonical_params(p) == canonical_params(dict(p))


def test_source_id_identique_pour_types_equivalents_de_bout_en_bout():
    s = marche_aleatoire(900, 3).rename("500.PA")
    t = apres(s)
    a = finance.sharpe_ratio(s, t, 252, 0.0123).meta.source_id
    b = finance.sharpe_ratio(s, t, np.int64(252), np.float64(0.0123)).meta.source_id
    assert a == b


def test_source_id_entier_et_flottant_de_meme_valeur_difference_documentee():
    """252 et 252.0 donnent des empreintes différentes (json : '252' et '252.0') : comportement
    sûr (jamais de collision) mais à connaître pour la comparaison d'identifiants."""
    assert _meta(params={"w": 252}).source_id != _meta(params={"w": 252.0}).source_id


# ================================================================ source_id : échappement
@pytest.mark.parametrize(
    "nom",
    [
        "a b",
        "a#b",
        "a:b",
        "a%b",
        "é",
        "500.PA",
        "fred:DGS10",
        "a~b",
        "日本",
        "a/b",
        "a+b",
        "x\ty",
        "",
        "-",
        "~",
        "%7E",
        "a%20b",
    ],
)
def test_source_id_echappement_oracle_urllib(nom):
    # oracle : percent-encoding de tous les octets hors [A-Za-z0-9_.-] (urllib, safe vide, avec
    # « ~ » aussi échappé car quote() le laisse passer par défaut)
    attendu = quote(nom, safe="").replace("~", "%7E")
    assert base._escape_series(nom) == attendu
    sid = _meta(series=nom).source_id
    champs = sid.split(":")
    assert len(champs) == 5  # outil, série, début, fin, version#empreinte : 4 « : » seulement
    assert champs[1] == attendu
    assert re.fullmatch(r"[A-Za-z0-9_.:%#~\-]+", sid), sid


def test_source_id_caracteres_dangereux_jamais_bruts_dans_le_champ_serie():
    for nom in ("a b", "a#b", "a:b", "a%b", "é"):
        champ = _meta(series=nom).source_id.split(":")[1]
        for c in " #:é":
            assert c not in champ
    assert _meta(series="é").source_id.split(":")[1] == "%C3%A9"
    assert _meta(series="a b").source_id.split(":")[1] == "a%20b"
    assert _meta(series="a#b").source_id.split(":")[1] == "a%23b"
    assert _meta(series="a:b").source_id.split(":")[1] == "a%3Ab"
    assert _meta(series="a%b").source_id.split(":")[1] == "a%25b"


def test_source_id_injectif_jeu_adversarial_et_exhaustif_court():
    noms = [
        "-",
        "~",
        "%7E",
        "a b",
        "a%20b",
        "a-b",
        "a%2Db",
        "%",
        "%25",
        "%2525",
        "é",
        "%C3%A9",
        "a:b",
        "a%3Ab",
        "a#b",
        "a%23b",
        "",
        "na",
        "~~",
        "a~",
        "%7E%7E",
        "A",
        "a",
        "ab",
        "a%",
        "%a",
        "%41",
        "A%",
        "é",
        "é",
    ]  # « é » composé et décomposé sont distincts
    ids = {nom: _meta(series=nom).source_id for nom in noms}
    ids["__aucune__"] = _meta(series=None).source_id
    assert len(set(ids.values())) == len(ids), "collision de source_id"
    # le marqueur d'absence « ~ » ne collisionne avec aucun nom, y compris « ~ » et « %7E »
    champ_absent = ids["__aucune__"].split(":")[1]
    assert champ_absent == "~"
    assert all(v.split(":")[1] != "~" for k, v in ids.items() if k != "__aucune__")
    # exhaustif : toutes les chaînes de longueur ≤ 3 sur un alphabet adversarial
    alphabet = ["a", "-", "~", "%", "7", "E", " ", "é", "#", ":", "2", "0"]
    tous = ["".join(c) for n in range(0, 4) for c in itertools.product(alphabet, repeat=n)]
    codes = [base._escape_series(x) for x in tous]
    assert len(set(codes)) == len(tous)
    assert "~" not in "".join(codes)  # jamais produit par le codage


def test_source_id_decodable_et_inverse_exact():
    from urllib.parse import unquote

    for nom in ["a b", "é", "%", "~", "日本:x#y", "a%20b", "-"]:
        assert unquote(base._escape_series(nom)) == nom


def test_source_id_parametres_distincts_empreintes_distinctes_et_hexa():
    ids = {_meta(params={"rf": r}).source_id for r in (0.0, 0.01, 0.02, float("nan"))}
    assert len(ids) == 4
    for sid in ids:
        assert re.search(r"#[0-9a-f]{8}$", sid)
    assert _meta(params={"rf": 0.01}).source_id == _meta(params={"rf": np.float64(0.01)}).source_id


def test_source_id_aucune_serie_tilde_sur_un_outil_sans_nom():
    r = finance.sharpe_ratio(
        marche_aleatoire(900, 1).rename(None), apres(marche_aleatoire(900, 1)), 252
    )
    assert r.meta.series is None and r.meta.source_id.split(":")[1] == "~"
    r2 = finance.sharpe_ratio(
        marche_aleatoire(900, 1).rename("~"), apres(marche_aleatoire(900, 1)), 252
    )
    assert r2.meta.source_id.split(":")[1] == "%7E" != r.meta.source_id.split(":")[1]


def test_to_dict_expose_source_id_echappe_et_json():
    m = _meta(series="a b#c", params={"x": np.float64(1.5), "d": "2024-01-01"})
    d = json.loads(json.dumps(m.to_dict()))
    assert d["source_id"] == m.source_id and d["series"] == "a b#c"  # le nom reste lisible


# ================================================================ N-B : RiskReport
def _cas_reel():
    p = pd.DataFrame(
        {
            "A": marche_aleatoire(900, 31),
            "B": marche_aleatoire(900, 32),
            "C": marche_aleatoire(900, 33),
        }
    )
    p.loc[p.index[-3], "B"] = np.nan  # B : valeur manquante dans la fenêtre -> indisponible
    d = p.index[-1]
    vix_perime = pd.DataFrame(
        {
            "date": [d - pd.Timedelta(days=40)],
            "value": [30.0],
            "available_from": [d - pd.Timedelta(days=39)],
        }
    )
    return p, vix_perime


def test_n_b_actifs_et_cles_techniques_separes_sur_un_cas_reel():
    p, vix = _cas_reel()
    t = apres(p)
    rep = risk.risk_report(p, p["A"], t, vix=vix).value
    assert rep.actifs_indisponibles == ["B"]
    assert set(rep.indisponibles_techniques) == {"__vix__"}
    assert "VIX" in rep.indisponibles_techniques["__vix__"]
    # interface historique inchangée : `indisponibles` = union des deux, mêmes raisons
    assert set(rep.indisponibles) == {"B", "__vix__"}
    assert rep.indisponibles["__vix__"] == rep.indisponibles_techniques["__vix__"]
    assert rep.indisponibles["B"].startswith(("MissingDataError", "DegenerateSeriesError"))
    assert set(rep.alertes) == {"A", "C"} and "B" not in rep.alertes
    assert all(not k.startswith("__") for k in rep.actifs_indisponibles)


def test_n_b_regime_indisponible_est_technique_pas_un_actif():
    p, _ = _cas_reel()
    rep = risk.risk_report(p, p["A"].iloc[:300], apres(p)).value  # benchmark trop court
    assert "__regime__" in rep.indisponibles_techniques and rep.regime_volatilite is None
    assert "__regime__" not in rep.actifs_indisponibles and rep.actifs_indisponibles == ["B"]
    assert set(rep.indisponibles) == {"B", "__regime__", "__vix__"} - {"__vix__"}


def test_n_b_sans_indisponible_listes_vides_et_ordre_stable():
    p = pd.DataFrame({"Z": marche_aleatoire(900, 31), "A": marche_aleatoire(900, 32)})
    rep = risk.risk_report(p, p["Z"], apres(p)).value
    assert rep.actifs_indisponibles == [] and rep.indisponibles_techniques == {}
    assert rep.indisponibles == {}
    q = p.copy()
    q.loc[q.index[-2], ["Z", "A"]] = np.nan
    r2 = risk.risk_report(q, p["Z"], apres(q)).value
    assert r2.actifs_indisponibles == [
        str(c) for c in q.columns
    ]  # ordre des colonnes, déterministe
    assert (
        r2.actifs_indisponibles == risk.risk_report(q, p["Z"], apres(q)).value.actifs_indisponibles
    )


def test_n_b_de_bout_en_bout_avec_aggregate_alerts_by_class_sans_filtrage():
    p, vix = _cas_reel()
    rep = risk.risk_report(p, p["A"], apres(p), vix=vix).value
    classes = {"A": "actions", "B": "actions", "C": "taux"}
    out = risk.aggregate_alerts_by_class(rep.alertes, classes, rep.actifs_indisponibles)
    assert out["actions"].indisponibles == ("B",) and out["actions"].actifs == ("A",)
    assert out["actions"].alerte == rep.alertes["A"]  # B indisponible n'abaisse pas la classe
    assert out["taux"].alerte == rep.alertes["C"] and out["taux"].indisponibles == ()
    # l'ancienne interface, elle, lève toujours (clés techniques) : non-régression documentée
    with pytest.raises(ToolError):
        risk.aggregate_alerts_by_class(rep.alertes, classes, rep.indisponibles)


def test_n_b_rapport_serialisable_avec_les_nouveaux_champs():
    import dataclasses

    p, vix = _cas_reel()
    rep = risk.risk_report(p, p["A"], apres(p), vix=vix).value
    d = dataclasses.asdict(rep)
    assert d["actifs_indisponibles"] == ["B"] and "__vix__" in d["indisponibles_techniques"]
    assert math.isfinite(rep.indicateurs["vol21:A"])
