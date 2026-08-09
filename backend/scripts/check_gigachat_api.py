"""Manually verify GigaChat OAuth, available models, and one completion."""

import argparse
import base64
import binascii
import getpass
import re
import sys
import uuid
from typing import Any

import httpx

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
MODELS_URL = "https://api.giga.chat/v1/models"
CHAT_URL = "https://api.giga.chat/v1/chat/completions"


def normalize_authorization_key(value: str) -> str:
    normalized = value.strip().strip('"\'')
    normalized = re.sub(r"^Basic\s+", "", normalized, flags=re.IGNORECASE)
    normalized = "".join(normalized.split())
    if not normalized:
        raise ValueError("Authorization key is empty")
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Authorization key is not valid Base64") from exc
    if b":" not in decoded:
        raise ValueError(
            "Authorization key has the wrong structure; copy the full key from Configure API → Keys"
        )
    return normalized


def request_access_token(client: httpx.Client, authorization_key: str) -> str:
    response = client.post(
        OAUTH_URL,
        headers={
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {authorization_key}",
        },
        data={"scope": "GIGACHAT_API_PERS"},
    )
    if response.is_error:
        raise RuntimeError(f"OAuth failed ({response.status_code}): {response.text}")
    access_token = response.json().get("access_token")
    if not access_token:
        raise RuntimeError("OAuth response does not contain access_token")
    return str(access_token)


def list_models(client: httpx.Client, access_token: str) -> list[str]:
    response = client.get(
        MODELS_URL,
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
    )
    if response.is_error:
        raise RuntimeError(f"Model listing failed ({response.status_code}): {response.text}")
    items: list[dict[str, Any]] = response.json().get("data") or []
    model_ids = [str(item["id"]) for item in items if item.get("id")]
    if not model_ids:
        raise RuntimeError("GigaChat returned no available model ids")
    return model_ids


def send_message(client: httpx.Client, access_token: str, model: str, prompt: str) -> str:
    response = client.post(
        CHAT_URL,
        headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
    )
    if response.is_error:
        raise RuntimeError(f"Completion failed ({response.status_code}): {response.text}")
    choices = response.json().get("choices") or []
    if not choices:
        raise RuntimeError("Completion response does not contain choices")
    return str(choices[0].get("message", {}).get("content") or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Exact model id returned by GET /v1/models")
    parser.add_argument("--prompt", default="Ответь одним словом: привет")
    parser.add_argument("--ca-bundle", help="Path to a trusted CA PEM/CRT bundle")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification for this diagnostic only")
    args = parser.parse_args()

    if args.insecure:
        print("WARNING: TLS verification is disabled for this diagnostic run", file=sys.stderr)
    verify: bool | str = False if args.insecure else (args.ca_bundle or True)
    authorization_key = normalize_authorization_key(
        getpass.getpass("Paste GigaChat Authorization key (input hidden): ")
    )

    try:
        with httpx.Client(verify=verify, timeout=60) as client:
            access_token = request_access_token(client, authorization_key)
            print("OAuth succeeded; access token received (not displayed)")
            model_ids = list_models(client, access_token)
            print("Available model ids:")
            for model_id in model_ids:
                print(f"  - {model_id}")
            model = args.model or input("Exact model id to test: ").strip()
            if model not in model_ids:
                raise RuntimeError(f"Model {model!r} is not in the available model list")
            answer = send_message(client, access_token, model, args.prompt)
    except httpx.HTTPError as exc:
        raise SystemExit(f"Network/TLS error: {type(exc).__name__}: {exc}") from exc
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Completion succeeded with model {model!r}")
    print(f"Answer: {answer}")
    print(f"Set Supabase secret GIGACHAT_MODEL to: {model}")


if __name__ == "__main__":
    main()
