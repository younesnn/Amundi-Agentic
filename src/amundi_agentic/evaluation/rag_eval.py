# ruff: noqa: E501
"""Évaluation du RAG : fidélité et pertinence (juge LLM) ; rappel à k et rang réciproque (déterministes).

Écart avec AlphaAgents : le papier mesurait fidélité et pertinence avec un outil d'observabilité tiers.
Ici, aucune bibliothèque d'évaluation tierce (dépendances lourdes, juge par défaut d'un fournisseur payant,
incompatibles avec le budget 0 € et avec la règle « tout appel LLM passe par `LLMClient` ») : les deux
métriques sont réimplémentées (justification : DECISIONS.md).

* fidélité = part des affirmations de la réponse que le juge dit étayées, chacune avec une citation
  mot pour mot d'un passage ; le code VÉRIFIE que la citation figure bien dans les passages, sinon
  l'affirmation est comptée non étayée (le juge ne peut pas inventer ses preuves). Les chiffres de la
  réponse absents des passages sont listés à part (contrôle déterministe) ;
* pertinence = part des passages que le juge dit utiles pour la question (précision de la récupération
  vue par le juge) ;
* les scores sont calculés par le code, jamais par le LLM ;
* rappel à k et rang réciproque : sans LLM, sur un jeu de référence où la bonne réponse est marquée
  dans le texte (extraits-repères).

Limite d'un juge de 8 milliards de paramètres (le modèle du profil dev, voir llm.yaml) : verdicts moins stables, tendance
à juger « étayé » une paraphrase vague, sensibilité à l'ordre et à la longueur des passages, JSON parfois
invalide (redemandé par le client). Le jeu de calibration (`CALIBRATION_CASES`, `calibrate_judge`) mesure
l'accord avec des réponses connues ; il doit être relancé à chaque changement de juge, et ses résultats
sur un juge de cette taille sont indicatifs, pas une mesure de la qualité du RAG.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from amundi_agentic.llm.client import LLMClient
from amundi_agentic.llm.types import Message, PromptRef
from amundi_agentic.tools.rag import FilingsRAG, Passage
from amundi_agentic.tools.summarize import unsupported_numbers
from amundi_agentic.tools.text_config import RagEvalConfig, load_text_tools_config, prompt_ref
from amundi_agentic.tools.untrusted import detect_injection, encapsuler, signaler

JUGE_FIDELITE = "rag_judge_faithfulness_v1"
JUGE_PERTINENCE = "rag_judge_relevance_v1"
REPONSE = "rag_answer_v1"


# ------------------------------------------------------------------------------ schémas du juge
class ClaimVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    supported: bool
    evidence: str = ""


class FaithfulnessJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimVerdict]


class PassageVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passage: str
    relevant: bool
    reason: str = ""


class RelevanceJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[PassageVerdict]


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)


NOTE_JUGE = (
    "Juge de 8 milliards de paramètres, peu fiable (verdicts instables, calibration imparfaite) : "
    "les scores sont INDICATIFS, pas une mesure de la qualité du RAG."
)


class FaithfulnessScore(BaseModel):
    indicatif: bool = True  # le juge est un petit modèle : score indicatif (voir `note`)
    note: str = NOTE_JUGE
    score: float | None  # None : réponse sans affirmation factuelle
    n_claims: int
    n_supported: int
    unverified_evidence: list[
        str
    ]  # affirmations dites étayées mais dont la citation est introuvable
    numbers_not_in_passages: list[str]


class RelevanceScore(BaseModel):
    indicatif: bool = True
    note: str = NOTE_JUGE
    score: float | None  # None : aucun passage à juger
    n_passages: int
    n_relevant: int
    relevant_passages: list[bool]


# ------------------------------------------------------------------------------ juges
def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def _bloc_passages(textes: Sequence[str], limite: int) -> str:
    return "\n".join(encapsuler(f"P{i}", t[:limite]) for i, t in enumerate(textes, 1))


def _surveiller(textes: Sequence[str], contexte: str) -> None:
    for i, t in enumerate(textes, 1):
        motifs = detect_injection(t)
        if motifs:
            signaler(contexte, f"P{i}", motifs)


def _cfg(config: RagEvalConfig | None) -> RagEvalConfig:
    return config or load_text_tools_config().rag_eval


def judge_faithfulness(
    llm: LLMClient,
    question: str,
    answer: str,
    passages: Sequence[str],
    as_of: date,
    *,
    config: RagEvalConfig | None = None,
    prompts_dir: Path | None = None,
) -> FaithfulnessScore:
    """Fidélité de `answer` aux `passages` (un appel LLM)."""
    cfg = _cfg(config)
    if _RE_INDISPONIBLE.match(answer):
        # « information non disponible » ne contient aucune affirmation factuelle : rien à juger
        # (évite aussi qu'un petit juge invente des affirmations à partir des passages)
        return FaithfulnessScore(
            score=None,
            n_claims=0,
            n_supported=0,
            unverified_evidence=[],
            numbers_not_in_passages=[],
        )
    ref, prompt = prompt_ref(JUGE_FIDELITE, prompts_dir)
    _surveiller([*passages, answer], "rag_eval.fidelite")
    utilisateur = (
        f"Question : {encapsuler('question', question)}\n\nRéponse à juger :\n"
        f"{encapsuler('reponse', answer)}\n\nPassages :\n{_bloc_passages(passages, cfg.max_passage_chars)}"
    )
    res = llm.complete_structured(
        FaithfulnessJudgement,
        [Message(role="system", content=prompt), Message(role="user", content=utilisateur)],
        date_donnees=as_of,
        tier=cfg.judge_tier,
        agent="rag_eval_faithfulness",
        prompt_ref=ref,
    )
    corpus = _norm(" ".join(passages))
    n_ok, non_verifiees = 0, []
    for c in res.parsed.claims:
        if not c.supported:
            continue
        preuve = _norm(c.evidence)
        if preuve and preuve in corpus:
            n_ok += 1
        else:
            non_verifiees.append(c.claim)
    n = len(res.parsed.claims)
    return FaithfulnessScore(
        score=None if n == 0 else n_ok / n,
        n_claims=n,
        n_supported=n_ok,
        unverified_evidence=non_verifiees,
        numbers_not_in_passages=unsupported_numbers(answer, list(passages)),
    )


_RE_LIBELLE = re.compile(r"\s*(?:p|passage\s*)?(\d+)\s*[.:]?\s*", re.IGNORECASE)
_RE_INDISPONIBLE = re.compile(
    r"^\W*(?:l[’']?)?(?:information|r[eé]ponse)?\s*non disponible", re.IGNORECASE
)


def _aligner_verdicts(verdicts: Sequence[PassageVerdict], passages: Sequence[str]) -> list[bool]:
    """Un booléen par passage. Le modèle désigne le passage par « P1 », « Passage 1 », « 1 », ou (le modèle du profil dev
    le fait) en recopiant son texte : on accepte ces trois formes ; sans verdict : non pertinent."""
    normes = [_norm(p) for p in passages]
    par_rang: dict[int, bool] = {}
    for v in verdicts:
        m = _RE_LIBELLE.fullmatch(v.passage)
        if m:
            rang = int(m.group(1))
        else:
            t = _norm(v.passage)[:80]
            rang = next((i for i, n in enumerate(normes, 1) if t and (t in n or n[:80] in t)), 0)
        if 1 <= rang <= len(passages):
            par_rang.setdefault(rang, v.relevant)
    return [par_rang.get(i, False) for i in range(1, len(passages) + 1)]


def judge_relevance(
    llm: LLMClient,
    question: str,
    passages: Sequence[str],
    as_of: date,
    *,
    config: RagEvalConfig | None = None,
    prompts_dir: Path | None = None,
) -> RelevanceScore:
    """Pertinence des `passages` pour `question` (un appel LLM). Un passage sans verdict est
    compté non pertinent (jamais de bénéfice du doute)."""
    cfg = _cfg(config)
    if not passages:
        return RelevanceScore(score=None, n_passages=0, n_relevant=0, relevant_passages=[])
    ref, prompt = prompt_ref(JUGE_PERTINENCE, prompts_dir)
    _surveiller(passages, "rag_eval.pertinence")
    utilisateur = (
        f"Question : {encapsuler('question', question)}\n\nPassages :\n"
        f"{_bloc_passages(passages, cfg.max_passage_chars)}"
    )
    res = llm.complete_structured(
        RelevanceJudgement,
        [Message(role="system", content=prompt), Message(role="user", content=utilisateur)],
        date_donnees=as_of,
        tier=cfg.judge_tier,
        agent="rag_eval_relevance",
        prompt_ref=ref,
    )
    flags = _aligner_verdicts(res.parsed.verdicts, passages)
    return RelevanceScore(
        score=sum(flags) / len(flags),
        n_passages=len(flags),
        n_relevant=sum(flags),
        relevant_passages=flags,
    )


def answer_from_passages(
    llm: LLMClient,
    question: str,
    passages: Sequence[Passage],
    as_of: date,
    *,
    config: RagEvalConfig | None = None,
    prompts_dir: Path | None = None,
) -> str:
    """Réponse du générateur à partir des passages (un appel LLM), pour évaluer de bout en bout."""
    cfg = _cfg(config)
    ref, prompt = prompt_ref(REPONSE, prompts_dir)
    textes = [p.text for p in passages]
    _surveiller(textes, "rag_eval.reponse")
    utilisateur = (
        f"Date d'analyse t : {as_of.isoformat()}\nQuestion : {encapsuler('question', question)}"
        f"\n\nPassages :\n{_bloc_passages(textes, cfg.max_passage_chars)}"
    )
    res = llm.complete_structured(
        Answer,
        [Message(role="system", content=prompt), Message(role="user", content=utilisateur)],
        date_donnees=as_of,
        tier=cfg.answer_tier,
        agent="rag_eval_answer",
        prompt_ref=ref,
    )
    return res.parsed.answer


class RagEvaluation(BaseModel):
    indicatif: bool = True
    note: str = NOTE_JUGE
    ticker: str
    question: str
    as_of: date
    answer: str
    faithfulness: FaithfulnessScore
    relevance: RelevanceScore
    n_calls: int  # appels LLM de la réponse et des deux juges (hors embeddings)
    prompts: dict[str, PromptRef]


def _fmt(x: float | None) -> str:
    return "non défini" if x is None else f"{x:.2f}"


def rapport_evaluation(ev: RagEvaluation) -> str:
    """Rapport textuel d'une évaluation ; répète la réserve sur le juge."""
    return (
        f"{ev.ticker} @ {ev.as_of} : fidélité {_fmt(ev.faithfulness.score)} "
        f"({ev.faithfulness.n_supported}/{ev.faithfulness.n_claims} affirmations étayées), "
        f"pertinence {_fmt(ev.relevance.score)} "
        f"({ev.relevance.n_relevant}/{ev.relevance.n_passages} passages).\n"
        f"ATTENTION : {ev.note}"
    )


def evaluate_rag_answer(
    llm: LLMClient,
    rag: FilingsRAG,
    ticker: str,
    question: str,
    as_of: date,
    *,
    k: int = 5,
    config: RagEvalConfig | None = None,
    prompts_dir: Path | None = None,
) -> RagEvaluation:
    """Récupère, répond, puis juge fidélité et pertinence (3 appels LLM, plus les embeddings)."""
    res = rag.query(ticker, question, as_of, k=k)
    textes = [p.text for p in res.passages]
    reponse = answer_from_passages(
        llm, question, res.passages, as_of, config=config, prompts_dir=prompts_dir
    )
    fid = judge_faithfulness(
        llm, question, reponse, textes, as_of, config=config, prompts_dir=prompts_dir
    )
    rel = judge_relevance(llm, question, textes, as_of, config=config, prompts_dir=prompts_dir)
    return RagEvaluation(
        ticker=res.ticker,
        question=question,
        as_of=as_of,
        answer=reponse,
        faithfulness=fid,
        relevance=rel,
        n_calls=3 if textes else 2,
        prompts={
            n: prompt_ref(n, prompts_dir)[0] for n in (REPONSE, JUGE_FIDELITE, JUGE_PERTINENCE)
        },
    )


# ------------------------------------------------------------------------------ récupération
class RetrievalCase(BaseModel):
    """Cas de référence : la question et les extraits-repères qui prouvent qu'un passage contient la
    bonne information (un passage est pertinent s'il contient au moins un repère)."""

    model_config = ConfigDict(frozen=True)

    question: str
    gold_markers: tuple[str, ...] = Field(min_length=1)


class RetrievalMetrics(BaseModel):
    k: int
    recall_at_k: float  # moyenne sur les cas de la part des repères couverts par les k premiers
    mrr: float  # moyenne du rang réciproque du premier passage pertinent (0 si aucun)
    per_case: list[dict[str, float]]


def _contient(passage: str, repere: str) -> bool:
    return _norm(repere) in _norm(passage)


def retrieval_metrics(
    cases: Sequence[RetrievalCase], retrieved: Sequence[Sequence[str]], k: int
) -> RetrievalMetrics:
    """Rappel à k et rang réciproque moyen. `retrieved[i]` : textes des passages classés pour le cas i
    (le rang réciproque porte sur la liste entière donnée, le rappel sur ses `k` premiers)."""
    if len(cases) != len(retrieved):
        raise ValueError("un classement par cas est attendu")
    if k < 1 or not cases:
        raise ValueError("k >= 1 et au moins un cas")
    lignes = []
    for cas, passages in zip(cases, retrieved, strict=True):
        top = list(passages)[:k]
        couverts = sum(any(_contient(p, m) for p in top) for m in cas.gold_markers)
        rang = next(
            (
                i
                for i, p in enumerate(passages, 1)
                if any(_contient(p, m) for m in cas.gold_markers)
            ),
            None,
        )
        lignes.append(
            {"recall": couverts / len(cas.gold_markers), "rr": 0.0 if rang is None else 1 / rang}
        )
    n = len(lignes)
    return RetrievalMetrics(
        k=k,
        recall_at_k=sum(x["recall"] for x in lignes) / n,
        mrr=sum(x["rr"] for x in lignes) / n,
        per_case=lignes,
    )


def evaluate_retrieval(
    rag: FilingsRAG, ticker: str, as_of: date, cases: Sequence[RetrievalCase], *, k: int = 5
) -> RetrievalMetrics:
    """Rappel à k et rang réciproque de `FilingsRAG.query` sur un jeu de référence."""
    classements = [
        [p.text for p in rag.query(ticker, c.question, as_of, k=k).passages] for c in cases
    ]
    return retrieval_metrics(cases, classements, k)


# ------------------------------------------------------------------------------ calibration
class JudgeCase(BaseModel):
    """Cas dont la bonne réponse est connue, pour tester un juge."""

    model_config = ConfigDict(frozen=True)

    name: str
    question: str
    passages: tuple[str, ...]
    answer: str
    expected_faithful: bool
    expected_relevant: tuple[bool, ...]


CALIBRATION_CASES: tuple[JudgeCase, ...] = (
    JudgeCase(
        name="reponse_fondee",
        question="Quelles sont les principales sources de revenus de la société Alpha ?",
        passages=(
            "Alpha Corp tire l'essentiel de son chiffre d'affaires de la vente de capteurs "
            "industriels et des contrats de maintenance associés.",
            "Le siège social d'Alpha Corp est situé dans une zone industrielle.",
        ),
        answer="Alpha Corp tire ses revenus de la vente de capteurs industriels et de contrats de maintenance.",
        expected_faithful=True,
        expected_relevant=(True, False),
    ),
    JudgeCase(
        name="reponse_inventee",
        question="Quelles sont les principales sources de revenus de la société Alpha ?",
        passages=(
            "Alpha Corp tire l'essentiel de son chiffre d'affaires de la vente de capteurs "
            "industriels et des contrats de maintenance associés.",
        ),
        answer="Alpha Corp tire ses revenus de ses services de streaming vidéo et de publicité en ligne.",
        expected_faithful=False,
        expected_relevant=(True,),
    ),
    JudgeCase(
        name="passage_hors_sujet",
        question="Quels risques de litige la société Beta signale-t-elle ?",
        passages=(
            "La cantine de Beta Inc. propose des repas végétariens trois jours par semaine.",
            "Beta Inc. a ouvert un nouveau centre de distribution au cours de l'exercice.",
        ),
        answer="Information non disponible dans les passages.",
        expected_faithful=True,  # aucune affirmation factuelle : fidèle par construction
        expected_relevant=(False, False),
    ),
    JudgeCase(
        name="chiffre_invente",
        question="Quel est le montant de la dette de la société Gamma ?",
        passages=("Gamma SA a une dette à long terme de 120 millions d'euros à fin d'exercice.",),
        answer="Gamma SA a une dette à long terme de 450 millions d'euros.",
        expected_faithful=False,
        expected_relevant=(True,),
    ),
)


class CalibrationReport(BaseModel):
    indicatif: bool = True
    note: str = NOTE_JUGE
    n_cases: int
    faithfulness_accuracy: float
    relevance_accuracy: float
    mismatches: list[str]


def rapport_calibration(r: CalibrationReport) -> str:
    """Rapport textuel de calibration ; répète la réserve sur le juge."""
    ecarts = "\n".join(f"  - {m}" for m in r.mismatches) or "  (aucun)"
    return (
        f"Calibration du juge sur {r.n_cases} cas : accord fidélité {r.faithfulness_accuracy:.2f}, "
        f"accord pertinence {r.relevance_accuracy:.2f}.\nÉcarts :\n{ecarts}\nATTENTION : {r.note}"
    )


def calibrate_judge(
    llm: LLMClient,
    as_of: date,
    cases: Sequence[JudgeCase] = CALIBRATION_CASES,
    *,
    config: RagEvalConfig | None = None,
    prompts_dir: Path | None = None,
) -> CalibrationReport:
    """Accord du juge avec les cas connus. Fidélité : `score == 1` (ou aucune affirmation) contre
    `expected_faithful` ; pertinence : verdict par passage contre `expected_relevant`."""
    ok_f = ok_r = n_pass = 0
    ecarts: list[str] = []
    for c in cases:
        f = judge_faithfulness(
            llm, c.question, c.answer, c.passages, as_of, config=config, prompts_dir=prompts_dir
        )
        fidele = f.score is None or f.score >= 1.0
        if fidele == c.expected_faithful:
            ok_f += 1
        else:
            ecarts.append(f"{c.name}: fidélité jugée {fidele}, attendue {c.expected_faithful}")
        r = judge_relevance(
            llm, c.question, c.passages, as_of, config=config, prompts_dir=prompts_dir
        )
        for i, (obtenu, attendu) in enumerate(
            zip(r.relevant_passages, c.expected_relevant, strict=True), 1
        ):
            n_pass += 1
            if obtenu == attendu:
                ok_r += 1
            else:
                ecarts.append(f"{c.name}: passage P{i} jugé pertinent={obtenu}, attendu {attendu}")
    return CalibrationReport(
        n_cases=len(cases),
        faithfulness_accuracy=ok_f / len(cases),
        relevance_accuracy=ok_r / n_pass,
        mismatches=ecarts,
    )


__all__ = [
    "CALIBRATION_CASES",
    "CalibrationReport",
    "JudgeCase",
    "RagEvaluation",
    "RetrievalCase",
    "RetrievalMetrics",
    "answer_from_passages",
    "calibrate_judge",
    "evaluate_rag_answer",
    "evaluate_retrieval",
    "judge_faithfulness",
    "judge_relevance",
    "retrieval_metrics",
    "rapport_calibration",
    "rapport_evaluation",
    "NOTE_JUGE",
]
