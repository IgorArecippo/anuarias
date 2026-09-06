"""Baixa o histórico completo de scrobbles do Last.fm.

Guarda tudo em data/scrobbles.jsonl (uma linha por scrobble, do mais antigo pro
mais novo). Rodar de novo só busca o que chegou depois do último scrobble salvo,
então dá pra manter o site atualizado sem rebaixar as 130 mil execuções.

    python3 fetch_scrobbles.py              # incremental
    python3 fetch_scrobbles.py --full       # refaz do zero
"""

import argparse
import json
import os
import sys
import time

import lastfm

USER = "igorarecippo"
PAGE_SIZE = 200
SLEEP_BETWEEN_PAGES = 0.25
DATA_DIR = os.path.join(lastfm.BASE_DIR, "data")
SCROBBLES_PATH = os.path.join(DATA_DIR, "scrobbles.jsonl")


def identity(record):
    """O Last.fm não registra a mesma faixa duas vezes no mesmo segundo, então
    isto identifica um scrobble sem ambiguidade."""
    return (record["ts"], record["artist"], record["track"])


def read_existing():
    """Devolve (timestamp mais recente, chaves já gravadas)."""
    if not os.path.exists(SCROBBLES_PATH):
        return 0, set()
    newest = 0
    keys = set()
    with open(SCROBBLES_PATH, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                keys.add(identity(record))
                newest = max(newest, record["ts"])
            except (json.JSONDecodeError, KeyError):
                continue
    return newest, keys


def normalize(track):
    """Converte um item da API no registro enxuto que o site usa."""
    date = track.get("date") or {}
    timestamp = int(date.get("uts", 0))
    if not timestamp:
        return None
    album = track.get("album") or {}
    artist = track.get("artist") or {}
    return {
        "ts": timestamp,
        "track": track.get("name") or "",
        "artist": artist.get("#text") or artist.get("name") or "",
        "album": album.get("#text") or "",
        "mbid_album": album.get("mbid") or "",
        "image": lastfm.pick_image(track.get("image")),
    }


def fetch(user, since=0, until=None):
    """Percorre todas as páginas de user.getRecentTracks no intervalo pedido."""
    api_key = lastfm.load_api_key()
    until = until or int(time.time())
    page = 1
    total_pages = None
    collected = []

    while True:
        payload = lastfm.call(
            "user.getRecentTracks",
            api_key=api_key,
            user=user,
            limit=PAGE_SIZE,
            page=page,
            **{"from": since + 1 if since else None, "to": until}
        )
        recent = payload.get("recenttracks") or {}
        attrs = recent.get("@attr") or {}
        if total_pages is None:
            total_pages = int(attrs.get("totalPages", 1))
            total = int(attrs.get("total", 0))
            print("  %s scrobbles em %s páginas" % (total, total_pages), flush=True)
            if total == 0:
                return []

        tracks = recent.get("track") or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        for track in tracks:
            # A faixa tocando agora não tem data e não deve ser salva ainda.
            if (track.get("@attr") or {}).get("nowplaying"):
                continue
            record = normalize(track)
            if record:
                collected.append(record)

        sys.stdout.write("\r  página %d/%d (%d scrobbles)" % (page, total_pages, len(collected)))
        sys.stdout.flush()

        if page >= total_pages:
            break
        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)

    print(flush=True)
    return collected


def main():
    parser = argparse.ArgumentParser(description="Baixa o histórico do Last.fm")
    parser.add_argument("--user", default=USER)
    parser.add_argument("--full", action="store_true", help="refaz o download do zero")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    newest, known = read_existing()
    since = 0 if args.full else newest
    if args.full:
        known = set()
    if since:
        print("Atualizando a partir de %s" % time.strftime("%d/%m/%Y %H:%M", time.localtime(since)))
    else:
        print("Baixando o histórico completo de %s" % args.user)

    fetched = fetch(args.user, since=since)
    fetched.sort(key=lambda record: record["ts"])

    # Uma mesma execução pode voltar em duas páginas quando o feed se desloca
    # durante o download, então a gravação filtra o que já está no arquivo.
    scrobbles = []
    for record in fetched:
        key = identity(record)
        if key in known:
            continue
        known.add(key)
        scrobbles.append(record)
    repeated = len(fetched) - len(scrobbles)

    mode = "w" if (args.full or not os.path.exists(SCROBBLES_PATH)) else "a"
    with open(SCROBBLES_PATH, mode, encoding="utf-8") as fh:
        for record in scrobbles:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print("%d scrobbles novos gravados em %s" % (len(scrobbles), SCROBBLES_PATH))
    if repeated:
        print("%d repetidos ignorados" % repeated)


if __name__ == "__main__":
    main()
