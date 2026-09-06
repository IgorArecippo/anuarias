"""Cliente mínimo da API do Spotify (só stdlib), usando Client Credentials.

Serve só para dados públicos: resolver o link de um álbum a partir do URI de
uma faixa, e ler nome/descrição de uma playlist pública. Não precisa de login
do usuário — só de um Developer App gratuito em
https://developer.spotify.com/dashboard.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_ROOT = "https://api.spotify.com/v1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_token_cache = {"value": None, "expires_at": 0}


class SpotifyError(RuntimeError):
    """Erro da API com o código HTTP preservado, para quem chama decidir."""

    def __init__(self, status, path):
        super().__init__("Erro da API do Spotify (%s) em %s" % (status, path))
        self.status = status
        self.path = path


def _read_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    values = {}
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                values[name.strip()] = value.strip().strip("'\"")
    return values


def load_credentials():
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        env = _read_env_file()
        client_id = client_id or env.get("SPOTIFY_CLIENT_ID")
        client_secret = client_secret or env.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def get_token():
    """Client Credentials flow: um token só para dados públicos, sem login."""
    now = time.time()
    if _token_cache["value"] and _token_cache["expires_at"] > now + 30:
        return _token_cache["value"]

    creds = load_credentials()
    if not creds:
        raise SystemExit(
            "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET não encontrados. Crie um app em\n"
            "https://developer.spotify.com/dashboard e coloque as chaves no .env:\n"
            "SPOTIFY_CLIENT_ID=...\nSPOTIFY_CLIENT_SECRET=..."
        )
    client_id, client_secret = creds
    basic = base64.b64encode(("%s:%s" % (client_id, client_secret)).encode("utf-8")).decode("ascii")
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": "Basic %s" % basic,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    _token_cache["value"] = payload["access_token"]
    _token_cache["expires_at"] = now + payload.get("expires_in", 3600)
    return _token_cache["value"]


def call(path, params=None, retries=5):
    """GET num endpoint da Web API e devolve o JSON já decodificado."""
    query = "?" + urllib.parse.urlencode(params) if params else ""
    url = API_ROOT + path + query

    delay = 1.0
    for attempt in range(retries):
        token = get_token()
        request = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % token})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                wait = int(exc.headers.get("Retry-After", "2")) if exc.headers else 2
                time.sleep(wait + 0.5)
                continue
            if exc.code == 401:
                _token_cache["value"] = None  # token expirou/inválido: pega outro e tenta de novo
                if attempt < retries - 1:
                    continue
            if exc.code == 404:
                return None
            raise SpotifyError(exc.code, path)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                raise RuntimeError("Falha ao chamar %s: %s" % (path, exc))
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("Falha ao chamar %s" % path)


def track_id_from_uri(uri):
    if not uri:
        return None
    return uri.rsplit(":", 1)[-1]


# Nem todo app tem acesso ao /tracks em lote — alguns recebem 403 nele e
# funcionam normalmente no endpoint de faixa única. Ao levar o primeiro 403,
# o cliente troca de modo e não tenta o lote de novo nesta execução.
_batch_blocked = {"value": False}


def tracks_batch(track_ids, pause=0.05):
    """Busca faixas por id. Devolve {track_id: track_json}.

    Usa /tracks?ids= (até 50 por vez) e, se esse endpoint for negado ao app,
    cai para uma requisição por faixa.
    """
    result = {}
    ids = [i for i in track_ids if i]

    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]

        if not _batch_blocked["value"]:
            try:
                payload = call("/tracks", {"ids": ",".join(chunk)})
            except SpotifyError as exc:
                if exc.status != 403:
                    raise
                _batch_blocked["value"] = True
                print("  /tracks em lote negado ao app; buscando uma faixa por vez")
            else:
                for track in (payload or {}).get("tracks", []) or []:
                    if track:
                        result[track["id"]] = track
                continue

        for index, track_id in enumerate(chunk, 1):
            track = call("/tracks/%s" % track_id)
            if track:
                result[track["id"]] = track
            print("\r  %d/%d faixas" % (start + index, len(ids)), end="", flush=True)
            time.sleep(pause)

    if _batch_blocked["value"] and ids:
        print()
    return result


# A busca de playlist deste app recusa limit > 10 (400 Bad Request).
PLAYLIST_SEARCH_LIMIT = 10


def find_playlist(name, owner_id):
    """Procura uma playlist DO DONO informado pelo nome.

    Só devolve playlist cujo dono seja exatamente `owner_id`. Playlist homônima
    de outra pessoa é descartada: uma descrição errada é pior que nenhuma.
    A busca do Spotify também não é exaustiva — vários nomes não aparecem no
    resultado mesmo existindo —, então quem chama deve tratar None como normal.
    """
    if not owner_id:
        return None
    for query in _name_variants(name):
        try:
            payload = call("/search", {"q": query, "type": "playlist", "limit": PLAYLIST_SEARCH_LIMIT})
        except SpotifyError:
            continue
        items = [item for item in ((payload or {}).get("playlists") or {}).get("items") or [] if item]
        mine = [item for item in items if (item.get("owner") or {}).get("id") == owner_id]
        if not mine:
            continue
        exact = [item for item in mine if item.get("name") == name]
        return (exact or mine)[0]
    return None


def _name_variants(name):
    """O nome tem aspa curva ('), que nem sempre casa na busca."""
    variants = [name, name.replace("‘", "'"), name.replace("‘", "").replace("’", "")]
    return list(dict.fromkeys(variant for variant in variants if variant.strip()))


def playlist_description(playlist_id):
    payload = call("/playlists/%s" % playlist_id, {"fields": "name,description,external_urls,owner(id)"})
    if not payload:
        return None
    return {
        "name": payload.get("name") or "",
        "description": payload.get("description") or "",
        "url": (payload.get("external_urls") or {}).get("spotify") or "",
        "uri": "spotify:playlist:%s" % playlist_id,
        "owner": (payload.get("owner") or {}).get("id") or "",
    }


def id_from_link(link):
    """Extrai o id de um link ou URI do Spotify.

    Aceita as três formas que aparecem ao copiar no app ou no site:
    https://open.spotify.com/playlist/<id>?si=..., spotify:playlist:<id>, ou o
    id solto.
    """
    if not link:
        return ""
    value = link.strip()
    if value.startswith("spotify:"):
        return value.rsplit(":", 1)[-1]
    if "open.spotify.com" in value:
        path = urllib.parse.urlparse(value).path.rstrip("/")
        return path.rsplit("/", 1)[-1]
    return value.split("?")[0]


def album_uri_from_url(url):
    """https://open.spotify.com/album/<id> -> spotify:album:<id>

    O URI abre direto no aplicativo do Spotify; o link https abre o navegador
    primeiro. Conversão local, sem chamar a API.
    """
    album_id = id_from_link(url)
    return "spotify:album:%s" % album_id if album_id else ""
