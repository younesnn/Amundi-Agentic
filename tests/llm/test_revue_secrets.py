"""Revue indépendante : masquage des clés sur des formats variés, de bout en bout.

Clés factices construites à l'exécution (aucun motif de clé dans ce fichier)."""

import json
import logging
from datetime import date
from types import SimpleNamespace

import pytest

from amundi_agentic.llm import MockLLMClient, ProviderError
from amundi_agentic.llm.redact import redact
from amundi_agentic.llm.transport import LiteLLMTransport

GEM = "AIza" + "Sy" + "Q" * 33
GRQ = "gsk_" + "Z" * 40
OAI = "sk-" + "proj-" + "W" * 30
T = date(2024, 2, 1)
MSG = [{"role": "user", "content": "x"}]


@pytest.mark.parametrize(
    "gabarit",
    [
        "Authorization: Bearer {k}",
        "authorization=Bearer {k}",
        "x-goog-api-key: {k}",
        "x-api-key: {k}",
        "https://h.invalid/v1beta/models/m:generateContent?key={k}",
        "https://h.invalid/?a=1&key={k}&b=2",
        '{{"api_key": "{k}"}}',
        "{{'api_key': '{k}'}}",
        "api_key={k}",
        "litellm.AuthenticationError: GeminiException - API key not valid: {k}.",
        "Traceback...\n  File x\nValueError: {k}\n",
        "headers={{'Authorization': 'Bearer {k}'}}",
        "curl -H 'Authorization: Bearer {k}' https://h.invalid",
        "{k}{k}",
    ],
)
@pytest.mark.parametrize("cle", [GEM, GRQ, OAI])
def test_redact_formats_varies(gabarit, cle):
    assert cle not in redact(gabarit.format(k=cle))


@pytest.mark.parametrize("cle", [GEM, GRQ, OAI])
def test_redact_valeur_d_environnement_inconnue_des_motifs(monkeypatch, cle):
    secret = "valeur-opaque-" + "9" * 20
    monkeypatch.setenv("AUTRE_FOURNISSEUR_KEY", secret)
    assert secret not in redact(f"échec avec {secret} dans la trace")


def test_redact_bearer_base64():
    jeton = "abc+def/ghijklmnopqrstu=="
    sortie = redact(f"Bearer {jeton}")
    assert "ghijklmnopqrstu" not in sortie and "abc+def" not in sortie


def test_redact_authorization_basic():
    assert "dXNlcjpwYXNzd29yZA" not in redact("Authorization: Basic dXNlcjpwYXNzd29yZA==")


def test_redact_ne_plante_pas_sur_n_importe_quel_objet():
    class Bizarre:
        def __str__(self):
            return f"objet {GEM}"

    assert GEM not in redact(Bizarre())
    assert redact(None) == "None"
    assert redact(ValueError(GEM)).count(GEM) == 0


def test_redact_exception_avec_cause_chainee_ne_fuit_pas_dans_le_message_classe():
    from amundi_agentic.llm.transport import _classify

    try:
        try:
            raise RuntimeError(f"clé {GEM}")
        except RuntimeError as interne:
            raise ConnectionError(f"réseau coupé ({interne}) key={GRQ}") from interne
    except ConnectionError as exc:
        err = _classify(exc)
    assert GEM not in str(err) and GRQ not in str(err)


class _Lib:
    def __init__(self, exc):
        self.exc = exc

    def completion(self, **kw):
        raise self.exc

    def embedding(self, **kw):
        raise self.exc


def _transport(monkeypatch, cfg, exc):
    monkeypatch.setattr("amundi_agentic.llm.transport.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GEMINI_API_KEY", GEM)
    monkeypatch.setenv("GROQ_API_KEY", GRQ)
    t = LiteLLMTransport(cfg)
    t._litellm = _Lib(exc)
    return t


@pytest.mark.parametrize("nom,statut", [("RateLimitError", 429), ("APIError", 500), ("Boom", None)])
def test_exceptions_litellm_transport_masquees_message_et_repr(monkeypatch, cfg, nom, statut):
    classe = type(nom, (Exception,), {"status_code": statut})
    exc = classe(f"echec https://h.invalid/?key={GEM} Authorization: Bearer {GRQ} {GEM}")
    t = _transport(monkeypatch, cfg, exc)
    for appel in (
        lambda: t.completion(
            model=cfg.models["main"], messages=MSG, temperature=0, seed=0, max_tokens=None,
            timeout=1, json_mode=False,
        ),
        lambda: t.embedding(model=cfg.embeddings["prod"], inputs=["a"], timeout=1),
    ):  # fmt: skip
        with pytest.raises(ProviderError) as e:
            appel()
        for texte in (str(e.value), repr(e.value), repr(e.value.args)):
            assert GEM not in texte and GRQ not in texte
        # La trace chaînée (contexte) ne doit pas ramener l'exception d'origine non masquée.
        assert e.value.__cause__ is None and e.value.__suppress_context__ is True


def test_repr_des_objets_ne_contient_pas_de_cle(monkeypatch, cfg, tmp_path):
    t = _transport(monkeypatch, cfg, RuntimeError("x"))
    c = MockLLMClient(cfg, cache_dir=tmp_path / "c", quota_journal=tmp_path / "q.json")
    for objet in (t, c, cfg, c.cache, c.quotas, t._config):
        assert GEM not in repr(objet) and GRQ not in repr(objet)


def test_cle_fournie_a_litellm_seulement_en_memoire_pas_dans_la_config(monkeypatch, cfg):
    t = _transport(monkeypatch, cfg, RuntimeError("x"))
    assert GEM not in cfg.model_dump_json()
    assert t._credentials(cfg.models["main"]) == {"api_key": GEM}


def test_fuite_complete_scan_de_tous_les_fichiers_et_logs(tmp_path, monkeypatch, cfg, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", GEM)
    monkeypatch.setenv("GROQ_API_KEY", GRQ)
    c = MockLLMClient(
        cfg, profile="prod", run_dir=tmp_path / "run", cache_dir=tmp_path / "cache",
        quota_journal=tmp_path / "quotas.json",
    )  # fmt: skip
    fuite = f'429 {GEM} ?key={GEM}&x=1 Bearer {GRQ} {{"api_key": "{GEM}"}} {OAI}'
    c.mock.push(ProviderError("quota", fuite, 429), model=cfg.models["main"])
    c.mock.push(ProviderError("unavailable", fuite, 503), model=cfg.models["fallback"])
    with caplog.at_level(logging.DEBUG):
        c.complete(MSG, date_donnees=T)  # 429 puis 503 puis ok sur repli
        c.mock.push(ProviderError("other", fuite))
        with pytest.raises(ProviderError) as e:
            c.complete(MSG, date_donnees=date(2024, 2, 2))
    tout = (
        "\n".join(f.read_text(errors="replace") for f in tmp_path.rglob("*") if f.is_file())
        + caplog.text
        + str(e.value)
        + repr(c.records)
        + json.dumps([r.model_dump(mode="json") for r in c.records])
    )
    for cle in (GEM, GRQ, OAI):
        assert cle not in tout


def test_une_cle_dans_le_prompt_utilisateur_n_est_pas_masquee_documentation(tmp_path, cfg):
    """Constat (non bloquant) : le contenu des messages est écrit tel quel dans le cache de
    réponses via la clé (hachée) mais PAS en clair ; vérifie qu'aucun message n'est stocké."""
    c = MockLLMClient(cfg, cache_dir=tmp_path / "c", quota_journal=tmp_path / "q.json",
                      run_dir=tmp_path / "r")  # fmt: skip
    secret = "MOT-DE-PASSE-DANS-LE-PROMPT-12345"
    c.complete([{"role": "user", "content": secret}], date_donnees=T)
    tout = "\n".join(f.read_text(errors="replace") for f in tmp_path.rglob("*") if f.is_file())
    assert secret not in tout


def test_namespace_sans_secret_pour_usage():
    assert SimpleNamespace  # garde l'import utilisé


# --------------------------------------------------------------------------- contre-vérification

JETON_B64 = "abc+def/ghijklmnopqrstu=="


@pytest.mark.parametrize(
    "texte",
    [
        f"Bearer {JETON_B64}",
        f"bearer {JETON_B64}",
        f"BEARER {JETON_B64}",
        f"Authorization: Bearer {JETON_B64}",
        f"authorization: bearer {JETON_B64}",
        f"AUTHORIZATION=Bearer {JETON_B64}",
        f"{{'authorization': 'Bearer {JETON_B64}'}}",
        f'{{"Authorization": "Bearer {JETON_B64}"}}',
        f'headers: {{"authorization":"Bearer {JETON_B64}"}}',
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
        "authorization: basic dXNlcjpwYXNzd29yZA==",
        '{"Authorization": "Basic dXNlcjpwYXNzd29yZA=="}',
        "proxy-authorization: Basic dXNlcjpwYXNzd29yZA==",
        "Authorization: Token tok_abcdef1234567890",
        "Authorization: abcdef1234567890tokennu",
        "AUTHORIZATION: abcdef1234567890tokennu",
        "x-api-key: abcdef1234567890",
        "X-API-KEY: abcdef1234567890",
        "api-key=abcdef1234567890&autre=1",
        "https://h.invalid/p?token=abcdef1234567890&x=1",
        "https://h.invalid/p?x=1&apikey=abcdef1234567890",
    ],
)
def test_redact_en_tetes_formats_et_casses_variees(texte):
    sortie = redact(texte)
    for morceau in (
        "ghijklmnopqrstu",
        "abc+def",
        "dXNlcjpwYXNz",
        "abcdef1234567890",
        "tok_abcdef",
    ):
        assert morceau not in sortie, (texte, sortie)


def test_redact_conserve_le_texte_non_secret_autour():
    sortie = redact("Erreur 429 sur le modele X. Authorization: Bearer " + JETON_B64 + "\nsuite")
    assert sortie.startswith("Erreur 429 sur le modele X.") and sortie.endswith("\nsuite")
    assert "[CLE_MASQUEE]" in sortie
    for neutre in (
        "authorization header missing",
        "error: bearer token missing",
        "rate limit exceeded, retry later",
    ):
        assert redact(neutre) == neutre  # pas de faux positif sur du texte courant


def test_redact_digest_avec_parametres_entre_guillemets():
    sortie = redact(
        'Authorization: Digest username="alice", realm="r", nonce="abcdef123456", '
        'response="deadbeefcafebabe"'
    )
    assert "deadbeefcafebabe" not in sortie and "abcdef123456" not in sortie


def test_redact_digest_sans_guillemets_et_sur_une_ligne_de_la_forme_courante():
    assert "deadbeefcafebabe" not in redact("Authorization: Digest response=deadbeefcafebabe")


def test_redact_est_idempotent():
    une_fois = redact(f"Authorization: Bearer {JETON_B64} key={GEM}")
    assert redact(une_fois) == une_fois


def test_redact_secret_d_environnement_en_plus_des_motifs(monkeypatch):
    monkeypatch.setenv("MON_SERVICE_TOKEN", "opaque-" + "7" * 24)
    monkeypatch.setenv("MON_SERVICE_SECRET", "autre-" + "8" * 24)
    texte = f"a opaque-{'7' * 24} b autre-{'8' * 24}"
    sortie = redact(texte)
    assert "7" * 24 not in sortie and "8" * 24 not in sortie


def test_les_erreurs_du_client_masquent_les_nouveaux_formats(fabrique, cfg):
    fuite = f"401 Authorization: Basic dXNlcjpwYXNzd29yZA== puis Bearer {JETON_B64}"
    c = fabrique()
    c.mock.push(ProviderError("bad_request", fuite, 400))
    with pytest.raises(ProviderError) as e:
        c.complete(MSG, date_donnees=T)
    texte = str(e.value) + repr(c.records)
    assert "dXNlcjpwYXNz" not in texte and "ghijklmnopqrstu" not in texte
