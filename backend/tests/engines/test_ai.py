"""Moteur IA : contrôle des chiffres, contextes, lecture des réponses, requêtes vers les fournisseurs (sans réseau)."""

from decimal import Decimal

import pytest

from app.engines.ai import context as aictx
from app.engines.ai import numbers, parse, prompts, provider

ANALYSIS = {
    "indicators": [
        {
            "code": "CAF",
            "name": "Capacité d'autofinancement",
            "unit": "amount",
            "value": "1250000.00",
            "status": "ok",
            "previous_value": "980000.00",
        },
        {"code": "TN", "name": "Trésorerie nette", "unit": "amount", "value": "-45000.00", "status": "ok"},
        {"code": "R_LIQ", "name": "Liquidité générale", "unit": "ratio", "value": "0.8734", "status": "ok"},
        {
            "code": "R_X",
            "name": "Ratio non calculable",
            "unit": "ratio",
            "value": None,
            "status": "division_by_zero",
            "message": "Dénominateur nul",
        },
    ],
    "statements": {
        "balance_sheet": [
            {"code": "BZ", "label": "Total actif", "level": 0, "net": "5400000.00", "previous": "5100000.00"},
            {"code": "AD", "label": "Détail", "level": 2, "net": "100.00"},
        ]
    },
    "alerts": [{"severity": "warning", "title": "Trésorerie négative", "message": "TN < 0"}],
}


def _finance():
    return aictx.finance(
        {"name": "Société test"}, {"label": "2025", "start_date": "2025-01-01", "end_date": "2025-12-31"}, ANALYSIS
    )


# ------------------------------------------------------------------ chiffres
def test_extraction_des_nombres_formats_francais_et_anglais():
    vals = [n.value * n.scale for n in numbers.extract("1 234 567,89 ; 1.234,5 ; 1,234.5 ; -45 000 ; 12,5 % ; 1,2 million ; 3 k")]
    assert vals == [
        Decimal("1234567.89"),
        Decimal("1234.5"),
        Decimal("1234.5"),
        Decimal("-45000"),
        Decimal("12.5"),
        Decimal("1200000.0"),
        Decimal("3000"),
    ]


def test_references_et_numeros_de_liste_ignores():
    assert numbers.extract("[F12] et [F3, F4]\n1. premier point\n2) second") == []


def test_controle_des_chiffres_tracables_arrondis_et_pourcentages():
    ctx = _finance().snapshot()
    ok = numbers.check(
        "La CAF atteint 1 250 000 [F1], soit environ 1,25 million, contre 980 000 [F2]. "
        "Liquidité de 0,87 [F4], 87,3 %. Trésorerie nette négative de 45 000 [F3].",
        ctx,
    )
    assert ok["status"] == "verified" and ok["checked"] == 6


def test_chiffre_non_tracable_signale():
    res = numbers.check("La CAF progresse de 270 000 [F1].", _finance().snapshot())  # écart calculé par le modèle
    assert res["status"] == "warning" and res["untraceable"] == [{"text": "270 000", "value": "270000"}]


# ------------------------------------------------------------------ contextes
def test_contexte_financier_ne_contient_que_des_valeurs_calculees():
    c = _finance()
    labels = [(f.label, f.value, f.period) for f in c.facts]
    assert ("Capacité d'autofinancement (CAF)", "1250000.00", "2025") in labels
    assert ("Capacité d'autofinancement (CAF)", "980000.00", "N-1") in labels
    assert all("Détail" not in lbl for lbl, _, _ in labels)  # niveau > 1 exclu
    assert c.data["indicators_not_computed"][0]["code"] == "R_X"  # signalé, jamais estimé
    assert [f.ref for f in c.facts] == [f"F{i}" for i in range(1, len(c.facts) + 1)]


def test_contexte_des_anomalies_du_grand_livre():
    c = aictx.anomalies(
        {"reference": "M1"},
        {"label": "2025"},
        {
            "possible_duplicates": [{"entry_number": "12"}, {"entry_number": "13"}],
            "weekend_entries": {"count": 4, "entries": []},
            "lines_without_label": 0,
        },
    )
    assert {f.value for f in c.facts} == {"2", "4"} and set(c.data["tests"]) == {
        "possible_duplicates",
        "weekend_entries",
        "lines_without_label",
    }


# ------------------------------------------------------------------ lecture des réponses
def _risk_ctx():
    return aictx.audit_risks(
        {"reference": "M1"},
        [{"code": "R1", "title": "Fraude"}],
        [{"code": "R-EX", "title": "Existant"}],
        [{"code": "ACH", "label": "Achats"}],
        [{"code": "EXH", "label": "Exhaustivité"}],
        _finance(),
    )


def test_suggestions_de_risques_filtrees():
    text = """```json
{"suggestions": [
 {"code": "R-IA-1", "title": "Tensions de trésorerie", "rationale": "Trésorerie nette de -45 000 [F3]", "cycle_code": "ACH",
  "assertion_codes": ["EXH"], "sources": ["F3"]},
 {"code": "R-EX", "title": "Doublon", "rationale": "déjà là", "sources": []},
 {"code": "R-IA-2", "title": "Cycle inventé", "rationale": "x x x", "cycle_code": "ZZZ", "sources": []},
 {"code": "R-IA-3", "title": "Source inventée", "rationale": "x x x", "sources": ["F999"]},
 {"code": "R-IA-4", "title": "Chiffre inventé", "rationale": "Perte de 777 777", "sources": []},
 {"title": "Sans code", "rationale": "x x x"}
]}
```"""
    kept, rejected = parse.suggestions("engagement_risk", text, _risk_ctx())
    assert [k.payload["code"] for k in kept] == ["R-IA-1", "R-IA-4"]
    assert kept[0].validation["status"] == "verified" and kept[1].validation["status"] == "warning"
    assert "likelihood" not in kept[0].payload  # aucune cotation reprise
    assert len(rejected) == 4


def test_procedures_limitees_aux_programmes_types():
    ctx = aictx.audit_procedures(
        {"reference": "M1"},
        [{"code": "PT1", "label": "Revue des factures", "content": {"nature": "detail_test"}}],
        [{"code": "R1", "title": "Fraude"}],
        [],
    )
    kept, rejected = parse.suggestions(
        "procedure",
        '{"suggestions": [{"template_code": "PT1", "risk_codes": ["R1"], "rationale": "Couvre R1"},'
        '{"template_code": "INVENTE", "rationale": "x x x"}]}',
        ctx,
    )
    assert [k.payload["template_code"] for k in kept] == ["PT1"] and "absent de la méthodologie" in rejected[0]


def test_reponse_non_json_refusee():
    with pytest.raises(parse.ParseError):
        parse.suggestions("synthesis_draft", "Voici ma synthèse en prose.", aictx.synthesis_draft({}, []))


# ------------------------------------------------------------------ fournisseurs
CFG_A = provider.ProviderConfig("anthropic", "cle", "modele-a", 1000)
CFG_O = provider.ProviderConfig("openai", "cle", "modele-o", 1000)


def test_statut_sans_configuration_complete():
    assert provider.status(provider.ProviderConfig("none", "", "")) == (False, "Aucun fournisseur d'IA configuré (AI_PROVIDER).")
    assert provider.status(provider.ProviderConfig("anthropic", "", "m"))[0] is False
    assert provider.status(provider.ProviderConfig("anthropic", "k", ""))[1] == "Modèle d'IA non choisi (AI_MODEL)."
    with pytest.raises(provider.ProviderError):
        provider.build_request(provider.ProviderConfig("none", "", ""), "s", [{"role": "user", "content": "q"}])


def test_requetes_anthropic_et_openai():
    url, headers, body = provider.build_request(CFG_A, "SYS", [{"role": "user", "content": "Q"}])
    assert (
        url == provider.ANTHROPIC_URL
        and headers["x-api-key"] == "cle"
        and headers["anthropic-version"] == provider.ANTHROPIC_VERSION
    )
    assert body == {"model": "modele-a", "max_tokens": 1000, "system": "SYS", "messages": [{"role": "user", "content": "Q"}]}
    url, headers, body = provider.build_request(CFG_O, "SYS", [{"role": "user", "content": "Q"}])
    assert url == provider.OPENAI_URL and headers["Authorization"] == "Bearer cle"
    assert body["messages"][0] == {"role": "system", "content": "SYS"} and body["max_completion_tokens"] == 1000
    with pytest.raises(provider.ProviderError):
        provider.build_request(CFG_A, "SYS", [{"role": "assistant", "content": "R"}])


def test_lecture_des_reponses_fournisseurs():
    a = provider.parse_response(
        "anthropic",
        {
            "content": [{"type": "text", "text": "Bonjour"}],
            "model": "m",
            "usage": {"input_tokens": 10, "output_tokens": 3},
            "stop_reason": "end_turn",
        },
        "x",
    )
    assert (a.text, a.input_tokens, a.output_tokens) == ("Bonjour", 10, 3)
    o = provider.parse_response(
        "openai",
        {
            "choices": [{"message": {"content": "Salut"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        },
        "modele-o",
    )
    assert (o.text, o.model, o.output_tokens) == ("Salut", "modele-o", 2)


def test_appel_http_et_erreurs():
    httpx = pytest.importorskip("httpx")
    seen = {}

    def ok(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "Réponse"}], "usage": {}})

    assert provider.complete(CFG_A, "S", [{"role": "user", "content": "Q"}], transport=httpx.MockTransport(ok)).text == "Réponse"
    assert seen["url"] == provider.ANTHROPIC_URL
    err = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "clé invalide"}}))
    with pytest.raises(provider.ProviderError, match="401"):
        provider.complete(CFG_A, "S", [{"role": "user", "content": "Q"}], transport=err)


def test_consignes_versionnees_et_interdits_rappeles():
    assert prompts.PROMPT_VERSION == "KOFINEX-AI-1"
    assert set(prompts.TASKS) == set(parse.MAX_ITEMS)
    assert "opinion d'audit" in prompts.BASE and "[F3]" in prompts.BASE
