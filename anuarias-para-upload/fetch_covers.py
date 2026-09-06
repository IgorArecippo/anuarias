"""Busca capas no Last.fm para os discos das Anuárias que não aparecem nos
scrobbles — casos de 2017/2018, antes da conta existir, ou de discos ouvidos
fora do Spotify. O cache fica em data/covers.json e é reaproveitado."""

import json
import os
import time

import aggregate
import lastfm
import playlists

COVERS_PATH = os.path.join(aggregate.DATA_DIR, "covers.json")
SLEEP = 0.25


def load_cache():
    if os.path.exists(COVERS_PATH):
        with open(COVERS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_cache(cache):
    os.makedirs(aggregate.DATA_DIR, exist_ok=True)
    with open(COVERS_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)


def main():
    cache = load_cache()
    catalog = aggregate.Catalog(aggregate.load_scrobbles())
    by_year = playlists.load_playlists()

    missing = []
    for year in sorted(by_year):
        for album in by_year[year]["albums"]:
            key = catalog.resolve(album["artists"], album["album"])
            if key and (catalog.album_meta.get(key) or {}).get("image"):
                continue
            cache_key = "%s|%s" % (album["artist"], album["album"])
            if cache_key in cache:
                continue
            missing.append((cache_key, album["artist"], album["album"]))

    print("%d discos sem capa para buscar" % len(missing))
    api_key = lastfm.load_api_key()
    for index, (cache_key, artist, album) in enumerate(missing, 1):
        try:
            payload = lastfm.call("album.getinfo", api_key=api_key, artist=artist, album=album)
            cache[cache_key] = lastfm.pick_image((payload.get("album") or {}).get("image"))
        except RuntimeError:
            cache[cache_key] = ""  # não existe no Last.fm; não insiste nas próximas rodadas
        print("\r  %d/%d" % (index, len(missing)), end="", flush=True)
        if index % 25 == 0:
            save_cache(cache)
        time.sleep(SLEEP)

    print()
    save_cache(cache)
    found = sum(1 for value in cache.values() if value)
    print("%d capas no cache (%d com imagem)" % (len(cache), found))


if __name__ == "__main__":
    main()
