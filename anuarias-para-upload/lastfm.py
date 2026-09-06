"""Cliente mínimo da API do Last.fm (só stdlib)."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://ws.audioscrobbler.com/2.0/"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_api_key():
    key = os.environ.get("LASTFM_API_KEY")
    if key:
        return key
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == "LASTFM_API_KEY":
                    return value.strip().strip("'\"")
    raise SystemExit(
        "LASTFM_API_KEY não encontrada. Crie um arquivo .env com:\n"
        "LASTFM_API_KEY=sua_chave_aqui"
    )


def call(method, api_key=None, retries=5, **params):
    """Chama um método da API e devolve o JSON já decodificado."""
    api_key = api_key or load_api_key()
    query = {"method": method, "api_key": api_key, "format": "json"}
    query.update({k: v for k, v in params.items() if v is not None})
    url = API_ROOT + "?" + urllib.parse.urlencode(query)

    delay = 1.0
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "anuarias/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if "error" in payload:
                # 29 = rate limit; vale a pena esperar e tentar de novo.
                if payload["error"] == 29 and attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError("Erro da API (%s): %s" % (payload["error"], payload.get("message")))
            return payload
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError("Falha ao chamar %s: %s" % (method, exc))
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("Falha ao chamar %s" % method)


def pick_image(images, preferred=("extralarge", "large", "medium")):
    """Extrai a melhor URL de capa de uma lista de imagens do Last.fm."""
    by_size = {}
    for image in images or []:
        url = image.get("#text") or ""
        if url:
            by_size[image.get("size") or ""] = url
    for size in preferred:
        if by_size.get(size):
            return by_size[size]
    return next(iter(by_size.values()), "")
