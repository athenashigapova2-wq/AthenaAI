"""Offline checks for the manual GigaChat diagnostic script."""

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_gigachat_api import (  # noqa: E402
    list_models,
    normalize_authorization_key,
    request_access_token,
    send_message,
)


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/oauth"):
        assert request.headers["Authorization"] == "Basic test-key"
        assert b"scope=GIGACHAT_API_PERS" in request.content
        return httpx.Response(200, json={"access_token": "access-token"})
    if request.url.path.endswith("/models"):
        assert request.headers["Authorization"] == "Bearer access-token"
        return httpx.Response(200, json={"data": [{"id": "available-model"}]})
    if request.url.path.endswith("/chat/completions"):
        payload = json.loads(request.content)
        assert payload["model"] == "available-model"
        return httpx.Response(200, json={"choices": [{"message": {"content": "Привет"}}]})
    return httpx.Response(404)


def main() -> None:
    assert normalize_authorization_key(" Basic  test-key \n") == "test-key"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        token = request_access_token(client, "test-key")
        assert token == "access-token"
        models = list_models(client, token)
        assert models == ["available-model"]
        assert send_message(client, token, models[0], "Привет") == "Привет"
    print("GigaChat API diagnostic checks passed")


if __name__ == "__main__":
    main()
