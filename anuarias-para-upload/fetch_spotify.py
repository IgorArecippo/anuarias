"""Busca no Spotify o que os CSVs do Exportify não trazem: o link de cada
álbum e a descrição de cada playlist Anuária. Cacheia tudo em
data/spotify.json e é reaproveitado — só busca o que ainda não tem.

Precisa de SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env (Client
Credentials: dados públicos, sem login do usuário). Sem isso, roda sem
travar e o site fica como estava antes (sem link nem descrição).
"""

import json
import os
import re

import playlists
import spotify_api

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_PATH = os.path.join(DATA_DIR, "spotify.json")

IDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist_ids.json")


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {"albums": {}, "playlists": {}}


def save_cache(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)


def playlist_source_name(source_filename):
    """'Álbuns_'26.csv' -> 'Álbuns '26' (nome como está no Spotify)."""
    stem = os.path.splitext(source_filename)[0]
    return stem.replace("_", " ")


def fetch_album_links(cache, by_year):
    uri_to_ids = {}
    for playlist in by_year.values():
        for album in playlist["albums"]:
            if not album["track_uris"]:
                continue
            uri = album["track_uris"][0]
            if uri not in cache["albums"]:
                uri_to_ids[uri] = spotify_api.track_id_from_uri(uri)

    if not uri_to_ids:
        print("Links de álbum: nada novo para buscar")
        return

    print("Links de álbum: buscando %d faixas novas" % len(uri_to_ids))
    tracks = spotify_api.tracks_batch(list(uri_to_ids.values()))
    for uri, track_id in uri_to_ids.items():
        track = tracks.get(track_id)
        if track:
            album = track.get("album") or {}
            cache["albums"][uri] = (album.get("external_urls") or {}).get("spotify") or ""
        else:
            # Faixa que a API não devolveu (removida, indisponível etc.): marca
            # como vazia para não tentar de novo a cada rodada.
            cache["albums"][uri] = ""


def year_in_name(name):
    """'Álbuns ‘26' -> 2026. Devolve None se o nome não declara um ano."""
    digits = re.findall(r"\d{2,4}", name or "")
    if not digits:
        return None
    value = digits[-1]
    if len(value) == 4:
        return int(value)
    if len(value) == 2:
        number = int(value)
        return 2000 + number if number < 90 else 1900 + number
    return None


def load_playlist_ids():
    """Lê playlist_ids.json: {"2025": "<link ou id da playlist>", ...}.

    É a forma confiável de achar as playlists certas — a busca do Spotify não
    devolve todas, e playlist privada não aparece nela de jeito nenhum.
    """
    if not os.path.exists(IDS_PATH):
        return {}
    with open(IDS_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {
        str(year): spotify_api.id_from_link(link)
        for year, link in raw.items()
        if link and not str(year).startswith("_")
    }


def fetch_playlist_descriptions(cache, by_year, configured_ids):
    for year, playlist in sorted(by_year.items()):
        key = str(year)
        if key in cache["playlists"]:
            continue
        name = playlist_source_name(playlist["source"])
        owner = playlist.get("owner") or ""
        playlist_id = configured_ids.get(key)

        if playlist_id:
            details = spotify_api.playlist_description(playlist_id) or {}
            # Um id que aponta para playlist de outra pessoa é erro de
            # configuração: melhor avisar do que exibir a descrição errada.
            if details and owner and details.get("owner") and details["owner"] != owner:
                print(
                    "  %s: o id configurado é de '%s', não de '%s' — ignorando"
                    % (key, details["owner"], owner)
                )
                details = {}
            # É fácil colar o link do ano errado (dois anos com o mesmo id, por
            # exemplo). Se a própria playlist se chama por outro ano, é engano.
            named_year = year_in_name(details.get("name", ""))
            if details and named_year and named_year != year:
                print(
                    "  %s: o id configurado é da playlist '%s' (%d) — ignorando"
                    % (key, details.get("name"), named_year)
                )
                details = {}
        else:
            print("  %s: procurando '%s' entre as playlists de %s..." % (key, name, owner or "?"))
            found = spotify_api.find_playlist(name, owner_id=owner)
            details = spotify_api.playlist_description(found["id"]) if found else {}

        details = details or {}
        cache["playlists"][key] = {
            "name": details.get("name") or name,
            "description": details.get("description") or "",
            "url": details.get("url") or "",
            "uri": details.get("uri") or "",
        }


def main():
    if not spotify_api.load_credentials():
        print(
            "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET não configurados em .env — "
            "pulando links de álbum e descrições de playlist."
        )
        return

    cache = load_cache()
    by_year = playlists.load_playlists()

    configured_ids = load_playlist_ids()
    fetch_album_links(cache, by_year)
    save_cache(cache)
    fetch_playlist_descriptions(cache, by_year, configured_ids)
    save_cache(cache)

    found_links = sum(1 for v in cache["albums"].values() if v)
    found_desc = sum(1 for v in cache["playlists"].values() if v.get("description"))
    print("%d links de álbum em cache (%d resolvidos)" % (len(cache["albums"]), found_links))
    print("%d playlists em cache (%d com descrição)" % (len(cache["playlists"]), found_desc))
    # Sem descrição por dois motivos diferentes: falta configurar o link, ou a
    # playlist realmente não tem descrição no Spotify. Só o primeiro é acionável.
    blank = [year for year, data in cache["playlists"].items() if not data.get("description")]
    unconfigured = sorted(year for year in blank if not configured_ids.get(year))
    empty = sorted(year for year in blank if configured_ids.get(year))
    if unconfigured:
        print(
            "Sem link configurado: %s. Cole em playlist_ids.json (no Spotify: botão "
            "direito na playlist > Compartilhar > Copiar link)." % ", ".join(unconfigured)
        )
    if empty:
        print("Sem descrição no Spotify: %s (a playlist em si não tem)." % ", ".join(empty))


if __name__ == "__main__":
    main()
