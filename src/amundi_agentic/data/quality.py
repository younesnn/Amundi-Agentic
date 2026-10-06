"""Contrôle qualité : trous, splits, doublons, valeurs aberrantes, séries trop courtes, devises.

Principe : on SIGNALE, on ne corrige jamais. Rien n'est interpolé, supprimé ni comblé ; chaque
anomalie devient un `QualityIssue` repris dans le rapport de couverture.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from amundi_agentic.data.models import QualityIssue

RETOUR_MIN_RATIO = 0.6  # (H) part du saut reprise le lendemain pour parler de « retour »
TOLERANCE_FLOTTANTE = 1e-9  # (H) absorbe l'erreur d'arrondi flottante (ex. 0,5999999999999982)


def _d(x) -> date | None:
    return None if x is None or pd.isna(x) else pd.Timestamp(x).date()


def check_prices(
    df: pd.DataFrame,
    ticker: str,
    qcfg: dict,
    *,
    meta: dict | None = None,
    expected_currency: str | None = None,
    distribution: str | None = None,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if df is None or df.empty:
        return [QualityIssue("short_history", "error", ticker, "aucune donnée de prix")]
    df = df.sort_values("date").reset_index(drop=True)

    dup = df[df.duplicated("date", keep=False)]
    if not dup.empty:
        issues.append(
            QualityIssue("duplicate", "error", ticker, f"{dup['date'].nunique()} dates en double",
                         _d(dup["date"].min()), _d(dup["date"].max()))
        )  # fmt: skip
    df = df.drop_duplicates("date", keep="last").reset_index(drop=True)

    nonpos = df[df["close"] <= 0]
    if not nonpos.empty:
        issues.append(
            QualityIssue("non_positive", "error", ticker, f"{len(nonpos)} clôtures <= 0",
                         _d(nonpos["date"].min()), _d(nonpos["date"].max()))
        )  # fmt: skip

    # Trous : jours ouvrés (lundi-vendredi) sans cotation entre deux barres consécutives
    dates = df["date"].values.astype("datetime64[D]")
    if len(dates) > 1:
        manquants = np.busday_count(dates[:-1], dates[1:]) - 1
        seuil = qcfg["max_gap_bdays"]
        for i in np.where(manquants > seuil)[0]:
            issues.append(
                QualityIssue("gap", "warning", ticker,
                             f"{int(manquants[i])} jours ouvrés sans cotation (hors fériés non distingués)",
                             _d(dates[i]), _d(dates[i + 1]))
            )  # fmt: skip

    # Splits déclarés et sauts non expliqués
    splits = df[df["splits"] > 0]
    for r in splits.itertuples():
        issues.append(
            QualityIssue(
                "split", "info", ticker, f"split déclaré x{r.splits:g}", _d(r.date), _d(r.date)
            )
        )
    ret = df["close"].pct_change()
    proche_split = pd.Series(False, index=df.index)
    for i in splits.index:
        proche_split.iloc[max(0, i - 1) : i + 2] = True
    gros = ret.abs() > qcfg["split_jump"]
    vol_med = df["volume"].shift(1).rolling(20, min_periods=5).median()
    for i in df.index[gros & ~proche_split]:
        ratio = df["volume"][i] / vol_med[i] if vol_med[i] and vol_med[i] > 0 else float("nan")
        reel = bool(ratio >= 3)  # pic de volume : le mouvement est probablement réel
        detail = f"saut de cours de {ret[i]:+.0%} sans split déclaré"
        if reel:
            detail += f" (volume x{ratio:.1f} : mouvement probablement réel)"
        else:
            detail += " (volume sans pic : split non ajusté possible, à vérifier)"
        issues.append(
            QualityIssue("split", "warning", ticker, detail, _d(df["date"][i]), _d(df["date"][i]))
        )
    moyens = (ret.abs() > qcfg["outlier_abs_return"]) & ~gros & ~proche_split
    for i in df.index[moyens]:
        issues.append(
            QualityIssue("outlier", "warning", ticker, f"rendement quotidien de {ret[i]:+.1%}",
                         _d(df["date"][i]), _d(df["date"][i]))
        )  # fmt: skip

    # Plafond de mouvement journalier propre à la classe d'actifs (config `class_abs_return`) : signale sans
    # corriger ni masquer. Un saut suivi d'un retour le lendemain signe un écart de cotation (prix de
    # clôture éloigné de la valeur liquidative) plutôt qu'un mouvement de la valeur liquidative.
    classe = (qcfg.get("class_abs_return") or {}).get(ticker)
    if classe:
        plafond = float(classe["max"])
        exempt = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in classe.get("exempt", [])]
        suivant = ret.shift(-1)
        # Plafond « exact » (|r| = plafond à l'erreur flottante près) : NON signalé, le plafond est une borne
        # incluse ; seul un dépassement strict au-delà de TOLERANCE_FLOTTANTE l'est.
        for i in df.index[(ret.abs() > plafond + TOLERANCE_FLOTTANTE) & ~gros & ~proche_split]:
            jour = pd.Timestamp(df["date"][i])
            if any(a <= jour <= b for a, b in exempt):
                continue
            # retour « d'au moins 60 % » du saut (borne incluse, à la tolérance près)
            retour = bool(
                pd.notna(suivant[i])
                and np.sign(suivant[i]) != np.sign(ret[i])
                and abs(suivant[i]) >= RETOUR_MIN_RATIO * abs(ret[i]) - TOLERANCE_FLOTTANTE
            )
            volume = pd.to_numeric(df["volume"][i], errors="coerce")
            texte_volume = "volume inconnu" if pd.isna(volume) else f"volume {int(volume)}"
            detail = (
                f"rendement quotidien de {ret[i]:+.2%} au-delà du plafond de classe de "
                f"{plafond:.1%} ({texte_volume})"
            )
            if retour:
                detail += f" ; retour le lendemain ({suivant[i]:+.2%}) : écart de cotation probable"
            issues.append(
                QualityIssue(
                    "outlier", "warning", ticker, detail, _d(df["date"][i]), _d(df["date"][i])
                )
            )

    # Séries figées
    run = qcfg["stale_run"]
    egal = df["close"].eq(df["close"].shift(1))
    groupe = (~egal).cumsum()
    longueurs = egal.groupby(groupe).sum() + 1
    for g, n in longueurs.items():
        if n >= run:
            bloc = df[groupe == g]
            issues.append(
                QualityIssue("stale", "warning", ticker, f"{int(n)} clôtures identiques consécutives",
                             _d(bloc["date"].min()), _d(bloc["date"].max()))
            )  # fmt: skip

    # Politique de distribution déclarée dans config/universe.yaml
    ndiv = int((df["dividends"] > 0).sum())
    if distribution == "dist" and ndiv == 0:
        issues.append(QualityIssue("distribution", "error", ticker,
                                   "déclaré distribuant (dist) sans aucun dividende enregistré"))  # fmt: skip
    elif distribution == "acc" and ndiv > 0:
        issues.append(QualityIssue("distribution", "error", ticker,
                                   f"déclaré capitalisant (acc) mais {ndiv} dividendes enregistrés"))  # fmt: skip
    elif distribution == "a_verifier":
        issues.append(QualityIssue("distribution", "info", ticker,
                                   f"distribution à vérifier ({ndiv} dividendes enregistrés)"))  # fmt: skip

    # Profondeur d'historique
    semaines = (df["date"].max() - df["date"].min()).days / 7
    if semaines < qcfg["min_history_weeks"]:
        issues.append(
            QualityIssue("short_history", "warning", ticker,
                         f"{semaines:.0f} semaines d'historique < {qcfg['min_history_weeks']}",
                         _d(df["date"].min()), _d(df["date"].max()))
        )  # fmt: skip

    # Devise et première cotation annoncée
    if meta:
        cur = meta.get("currency")
        if expected_currency and cur and cur != expected_currency:
            issues.append(
                QualityIssue("currency", "warning", ticker,
                             f"devise Yahoo {cur} différente de la devise attendue {expected_currency}")
            )  # fmt: skip
        ftd = meta.get("first_trade_date")
        if ftd and pd.notna(ftd):
            premiere = pd.Timestamp(ftd)
            premiere = premiere.tz_localize(None) if premiere.tzinfo else premiere
            ecart = (df["date"].min() - premiere).days
            if ecart > 30:
                issues.append(
                    QualityIssue("short_history", "info", ticker,
                                 f"première barre {_d(df['date'].min())} postérieure de {ecart} j à la "
                                 f"première cotation annoncée par Yahoo ({ftd})")
                )  # fmt: skip
    return issues


def check_dated_series(
    df: pd.DataFrame, subject: str, max_gap_days: int, *, date_col: str = "date"
) -> list[QualityIssue]:
    """Doublons de date et trous (en jours calendaires) d'une série macro ou de change."""
    issues: list[QualityIssue] = []
    if df is None or df.empty:
        return [QualityIssue("short_history", "error", subject, "série vide")]
    d = df[date_col].sort_values()
    dup = d[d.duplicated(keep=False)]
    if not dup.empty:
        issues.append(
            QualityIssue("duplicate", "error", subject, f"{dup.nunique()} dates en double")
        )
    uniq = d.drop_duplicates().reset_index(drop=True)
    ecarts = uniq.diff().dt.days
    for i in ecarts.index[ecarts > max_gap_days]:
        issues.append(
            QualityIssue("gap", "warning", subject, f"{int(ecarts[i])} jours sans observation",
                         _d(uniq[i - 1]), _d(uniq[i]))
        )  # fmt: skip
    return issues


def check_duplicates(df: pd.DataFrame, key: list[str], subject: str) -> list[QualityIssue]:
    n = int(df.duplicated(key).sum()) if df is not None and not df.empty else 0
    return [QualityIssue("duplicate", "error", subject, f"{n} doublons sur {key}")] if n else []
