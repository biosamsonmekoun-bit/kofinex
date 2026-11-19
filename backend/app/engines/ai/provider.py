"""Appel du fournisseur de modèle configuré (Anthropic ou OpenAI), par HTTP. Sans configuration complète (fournisseur,
clé, modèle), l'IA est indisponible et le dit : aucune réponse n'est simulée. La construction des requêtes et la
lecture des réponses sont des fonctions pures, testées sans réseau."""

from __future__ import annotations

from dataclasses import dataclass

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str  # anthropic | openai | none
    api_key: str
    model: str
    max_output_tokens: int = 4000
    timeout_seconds: float = 60.0
    base_url: str = ""  # facultatif : passerelle compatible (proxy d'entreprise)


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None = None


def status(cfg: ProviderConfig) -> tuple[bool, str | None]:
    if cfg.provider not in ("anthropic", "openai"):
        return False, "Aucun fournisseur d'IA configuré (AI_PROVIDER)."
    if not cfg.api_key:
        return False, "Clé du fournisseur d'IA absente (AI_API_KEY)."
    if not cfg.model:
        return False, "Modèle d'IA non choisi (AI_MODEL)."
    return True, None


def build_request(cfg: ProviderConfig, system: str, messages: list[dict]) -> tuple[str, dict, dict]:
    """messages : [{"role": "user" | "assistant", "content": "…"}], du plus ancien au plus récent."""
    ok, reason = status(cfg)
    if not ok:
        raise ProviderError(reason or "IA non configurée")
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
    if not msgs or msgs[-1]["role"] != "user":
        raise ProviderError("Le dernier message transmis doit être celui de l'utilisateur.")
    if cfg.provider == "anthropic":
        url = cfg.base_url or ANTHROPIC_URL
        headers = {"x-api-key": cfg.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        body = {"model": cfg.model, "max_tokens": cfg.max_output_tokens, "system": system, "messages": msgs}
    else:
        url = cfg.base_url or OPENAI_URL
        headers = {"Authorization": f"Bearer {cfg.api_key}", "content-type": "application/json"}
        body = {
            "model": cfg.model,
            "max_completion_tokens": cfg.max_output_tokens,
            "messages": [{"role": "system", "content": system}, *msgs],
        }
    return url, headers, body


def parse_response(provider: str, data: dict, requested_model: str) -> Completion:
    try:
        if provider == "anthropic":
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            usage = data.get("usage") or {}
            return Completion(
                text,
                data.get("model") or requested_model,
                usage.get("input_tokens"),
                usage.get("output_tokens"),
                data.get("stop_reason"),
            )
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return Completion(
            (choice.get("message") or {}).get("content") or "",
            data.get("model") or requested_model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            choice.get("finish_reason"),
        )
    except (AttributeError, TypeError) as exc:
        raise ProviderError("Réponse du fournisseur illisible.") from exc


def complete(cfg: ProviderConfig, system: str, messages: list[dict], transport=None) -> Completion:
    """Appel réel. `transport` (httpx) n'est fourni que par les tests."""
    import httpx

    url, headers, body = build_request(cfg, system, messages)
    try:
        with httpx.Client(timeout=cfg.timeout_seconds, transport=transport) as client:
            r = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError(f"Fournisseur d'IA injoignable : {exc.__class__.__name__}.") from exc
    if r.status_code >= 400:
        detail = ""
        try:
            err = r.json().get("error")
            detail = err.get("message", "") if isinstance(err, dict) else str(err or "")
        except ValueError:
            detail = r.text[:200]
        raise ProviderError(f"Fournisseur d'IA : erreur {r.status_code}. {detail}".strip())
    out = parse_response(cfg.provider, r.json(), cfg.model)
    if not out.text.strip():
        raise ProviderError("Le fournisseur d'IA n'a renvoyé aucun texte.")
    return out
