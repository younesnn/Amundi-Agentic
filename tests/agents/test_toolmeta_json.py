"""`ToolMeta.to_dict` : paramètres passés par `canonical_params` (JSON strict) pour les journaux.
(Test d'accompagnement du correctif ; le reviewer-tester écrit les tests de référence.)"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from amundi_agentic.tools.base import ToolMeta


def test_to_dict_json_strict_avec_date_timestamp_et_nan():
    m = ToolMeta(
        "outil",
        "1.0.0",
        date(2024, 2, 1),
        None,
        None,
        0,
        params={
            "debut": date(2024, 1, 2),
            "ts": pd.Timestamp("2024-01-03"),
            "x": float("nan"),
            "n": np.int64(3),
        },
    )
    d = m.to_dict()
    texte = json.dumps(d, allow_nan=False)  # lève sur NaN ou sur un type non sérialisable
    assert json.loads(texte)["params"]["debut"] == "2024-01-02"
    assert d["params"]["x"] == {"__float__": "nan"} and d["params"]["n"] == 3
    assert d["source_id"] == m.source_id  # l'identifiant ne change pas
