"""
Client LM Studio - serveur local OpenAI-compatible.

Utiliser a la place d'une API distante quand le serveur local LM Studio est
disponible.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "")  # vide = auto-detect
LM_STUDIO_TIMEOUT = int(os.environ.get("LM_STUDIO_TIMEOUT", "8"))
# Timeout court pour les health-checks (is_available, list_loaded_models).
# En production LM Studio répond en <50ms — 0.5s est largement suffisant.
LM_STUDIO_CONNECT_TIMEOUT = float(os.environ.get("LM_STUDIO_CONNECT_TIMEOUT", "0.5"))

# Cache du modèle actif détecté
_active_model: str | None = None


def _chat_candidates(explicit_model: str | None) -> list[str | None]:
    if explicit_model:
        return [explicit_model]

    candidates: list[str | None] = []
    resolved = _resolve_model()
    if resolved and "embedding" not in resolved.lower():
        candidates.append(resolved)

    for candidate in list_loaded_models():
        if not candidate or candidate in candidates:
            continue
        if "embedding" in candidate.lower():
            continue
        candidates.append(candidate)

    return candidates


def _resolve_model() -> str | None:
    """Détecte automatiquement le modèle chargé, utilise le cache si possible."""
    global _active_model
    models = list_loaded_models()
    if LM_STUDIO_MODEL and LM_STUDIO_MODEL in models:
        _active_model = LM_STUDIO_MODEL
        return _active_model
    if _active_model and _active_model in models:
        return _active_model
    if models:
        _active_model = models[0]
        return _active_model
    _active_model = None
    return None


def list_loaded_models() -> list[str]:
    """Retourne les modèles LLM réellement chargés dans LM Studio."""
    try:
        response = httpx.get(
            f"{LM_STUDIO_URL}/api/v0/models",
            headers=_headers(),
            timeout=LM_STUDIO_CONNECT_TIMEOUT,
        )
        response.raise_for_status()
        return [
            model["id"]
            for model in response.json().get("data", [])
            if model.get("id")
            and model.get("state") == "loaded"
            and model.get("type") != "embeddings"
        ]
    except Exception:
        try:
            response = httpx.get(
                f"{LM_STUDIO_URL}/v1/models",
                headers=_headers(),
                timeout=LM_STUDIO_CONNECT_TIMEOUT,
            )
            response.raise_for_status()
            return [
                model["id"]
                for model in response.json().get("data", [])
                if model.get("id") and "embedding" not in model["id"].lower()
            ]
        except Exception:
            return []


def _headers() -> dict:
    api_key = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def is_available() -> bool:
    """Vérifie si LM Studio est lancé (au moins un modèle connu via /v1/models)."""
    try:
        r = httpx.get(
            f"{LM_STUDIO_URL}/v1/models",
            headers=_headers(),
            timeout=LM_STUDIO_CONNECT_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> list[str]:
    """Retourne tous les modèles connus de LM Studio (chargés ou non)."""
    try:
        r = httpx.get(f"{LM_STUDIO_URL}/v1/models", headers=_headers(), timeout=10)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
    except Exception as exc:
        raise RuntimeError(f"LM Studio inaccessible : {exc}") from exc


def chat(
    prompt: str,
    system: str = "Tu es un assistant expert en trading algorithmique et Python.",
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    stream: bool = False,  # noqa: ARG001 — conservé pour compatibilité API OpenAI
) -> str:
    """
    Envoie un message a LM Studio et retourne la reponse texte.

    Le streaming est accepte dans la signature pour compatibilite avec l'API
    OpenAI, mais ce client retourne toujours le contenu final.
    """
    global _active_model
    last_http_error: httpx.HTTPStatusError | None = None
    candidates = _chat_candidates(model)
    if not candidates:
        raise RuntimeError(
            "LM Studio inaccessible : aucun modele LLM charge. "
            "Configure LM_STUDIO_MODEL ou charge un modele dans LM Studio."
        )

    for candidate in candidates:
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if candidate:
            payload["model"] = candidate

        try:
            response = httpx.post(
                f"{LM_STUDIO_URL}/v1/chat/completions",
                headers=_headers(),
                json=payload,
                timeout=LM_STUDIO_TIMEOUT,
            )
            response.raise_for_status()
            if candidate:
                _active_model = candidate
            return response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            last_http_error = exc
            can_retry = model is None and exc.response.status_code == 400
            if not can_retry:
                raise RuntimeError(
                    f"LM Studio erreur HTTP {exc.response.status_code}: "
                    f"{exc.response.text}"
                ) from exc
        except Exception as exc:
            raise RuntimeError(f"LM Studio inaccessible : {exc}") from exc

    if last_http_error is not None:
        raise RuntimeError(
            f"LM Studio erreur HTTP {last_http_error.response.status_code}: "
            f"{last_http_error.response.text}"
        ) from last_http_error

    raise RuntimeError("LM Studio inaccessible : aucun modele compatible disponible")


def complete(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Completion texte brut legacy via /v1/completions."""
    payload = {
        "model": model or LM_STUDIO_MODEL,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        r = httpx.post(
            f"{LM_STUDIO_URL}/v1/completions",
            headers=_headers(),
            json=payload,
            timeout=LM_STUDIO_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["text"]
    except Exception as exc:
        raise RuntimeError(f"LM Studio inaccessible : {exc}") from exc
