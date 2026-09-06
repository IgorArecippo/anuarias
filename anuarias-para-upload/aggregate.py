"""Cruza o histórico do Last.fm com as Anuárias exportadas do Spotify.

O resultado é o material do site: quanto cada disco da Anuária foi de fato
ouvido no ano, o que ficou de fora e merecia entrar, e o que entrou mas esfriou.
"""

import datetime
import difflib
import json
import os
from collections import Counter, defaultdict

import playlists
import spotify_api

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCROBBLES_PATH = os.path.join(DATA_DIR, "scrobbles.jsonl")

# Os scrobbles vêm em UTC; o ano de uma escuta é o ano no fuso de quem ouviu.
try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # pragma: no cover - fallback se faltar a base de fusos
    LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=-3))

MIN_PLAYS_FOR_CANDIDATE = 25  # abaixo disso não é "disco do ano"
MIN_TRACKS_FOR_CANDIDATE = 4  # um disco ouvido de verdade, não uma faixa em repeat
COLD_PLAY_THRESHOLD = 10  # entrou na Anuária mas quase não tocou
FUZZY_CUTOFF = 0.87


def load_scrobbles(path=SCROBBLES_PATH):
    if not os.path.exists(path):
        raise SystemExit("Não achei %s. Rode antes: python3 fetch_scrobbles.py" % path)
    scrobbles = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            moment = datetime.datetime.fromtimestamp(record["ts"], LOCAL_TZ)
            record["year"] = moment.year
            record["month"] = moment.month
            record["date"] = moment.strftime("%Y-%m-%d")
            scrobbles.append(record)
    scrobbles.sort(key=lambda record: record["ts"])
    return scrobbles


class Catalog:
    """Índice dos scrobbles por álbum, artista e faixa."""

    def __init__(self, scrobbles):
        self.scrobbles = scrobbles
        self.album_plays = defaultdict(Counter)      # chave -> {ano: execuções}
        self.album_tracks = defaultdict(set)         # chave -> faixas distintas
        self.album_meta = {}                         # chave -> nomes e capa
        self.album_dates = {}                        # chave -> (primeira, última)
        self.artist_plays = defaultdict(Counter)
        self.track_plays = defaultdict(Counter)
        self.by_year = defaultdict(list)
        self._by_album_name = defaultdict(list)      # nome normalizado -> chaves

        for record in scrobbles:
            year = record["year"]
            self.by_year[year].append(record)
            artist = record["artist"]
            self.artist_plays[artist][year] += 1
            self.track_plays[(artist, record["track"])][year] += 1

            if not record["album"]:
                continue
            key = playlists.album_key(artist, record["album"])
            self.album_plays[key][year] += 1
            self.album_tracks[key].add(record["track"])
            meta = self.album_meta.get(key)
            if meta is None:
                meta = self.album_meta[key] = {
                    "album": record["album"],
                    "artist": artist,
                    "image": record["image"],
                }
                self._by_album_name[key[1]].append(key)
            if not meta["image"] and record["image"]:
                meta["image"] = record["image"]
            first, last = self.album_dates.get(key, (record["date"], record["date"]))
            self.album_dates[key] = (min(first, record["date"]), max(last, record["date"]))

    def total_plays(self, key):
        return sum(self.album_plays[key].values())

    def resolve(self, artist, album):
        """Encontra a chave do Last.fm para um disco da Anuária.

        O mesmo disco aparece escrito de formas diferentes nos dois serviços
        (edições, acentos, "&" vs "and"), então depois da tentativa exata
        procuramos o artista mais parecido entre os discos de mesmo nome.
        """
        key = playlists.album_key(artist, album)
        if key in self.album_plays:
            return key
        candidates = self._by_album_name.get(key[1]) or []
        if not candidates:
            return None
        matches = difflib.get_close_matches(
            key[0], [candidate[0] for candidate in candidates], n=1, cutoff=FUZZY_CUTOFF
        )
        if not matches:
            return None
        for candidate in candidates:
            if candidate[0] == matches[0]:
                return candidate
        return None


def month_series(scrobbles_of_year):
    counts = Counter(record["month"] for record in scrobbles_of_year)
    return [counts.get(month, 0) for month in range(1, 13)]


def top_items(counter, limit):
    return counter.most_common(limit)


def build(playlists_by_year, catalog, covers=None, spotify_meta=None):
    """Monta a estrutura completa que o gerador de páginas consome."""
    covers = covers or {}
    spotify_meta = spotify_meta or {"albums": {}, "playlists": {}}
    years = sorted(set(playlists_by_year) | set(catalog.by_year))
    # Um disco só é "novidade" se nunca esteve numa Anuária anterior.
    seen_before = {}
    accumulated = set()
    for year in years:
        seen_before[year] = set(accumulated)
        for album in (playlists_by_year.get(year) or {}).get("albums", []):
            accumulated.add(playlists.album_key(album["artists"], album["album"]))

    result = {"years": [], "totals": {}}

    first_data_day = catalog.scrobbles[0]["date"] if catalog.scrobbles else ""
    last_data_day = catalog.scrobbles[-1]["date"] if catalog.scrobbles else ""

    for year in years:
        playlist = playlists_by_year.get(year)
        year_scrobbles = catalog.by_year.get(year, [])
        entry = {
            "year": year,
            "has_playlist": playlist is not None,
            "scrobbles": len(year_scrobbles),
            # O histórico começa em outubro de 2018: antes disso não há o que
            # cruzar, e em 2018 só o último trimestre tem dados. Sem essa marca,
            # discos daquele ano apareceriam como "esfriaram" sem terem esfriado.
            "partial_from": first_data_day if first_data_day[:4] == str(year) and first_data_day[5:] > "01-15" else "",
            "partial_to": last_data_day if last_data_day[:4] == str(year) and last_data_day[5:] < "12-15" else "",
            "months": month_series(year_scrobbles),
            "playlist_description": (spotify_meta["playlists"].get(str(year)) or {}).get("description", ""),
            "playlist_url": (spotify_meta["playlists"].get(str(year)) or {}).get("url", ""),
            "playlist_uri": (spotify_meta["playlists"].get(str(year)) or {}).get("uri", ""),
            "albums": [],
            "candidates": [],
            "cold": [],
            "top_artists": [],
            "top_tracks": [],
        }

        in_playlist_keys = set()
        if playlist:
            for album in playlist["albums"]:
                key = catalog.resolve(album["artists"], album["album"])
                plays = catalog.album_plays[key][year] if key else 0
                all_time = catalog.total_plays(key) if key else 0
                first_last = catalog.album_dates.get(key, ("", "")) if key else ("", "")
                if key:
                    in_playlist_keys.add(key)
                image = (catalog.album_meta.get(key, {}).get("image") if key else "") or covers.get(
                    "%s|%s" % (album["artist"], album["album"]), ""
                )
                first_uri = album["track_uris"][0] if album.get("track_uris") else None
                album_url = spotify_meta["albums"].get(first_uri, "") if first_uri else ""
                entry["albums"].append({
                    "album": album["album"],
                    "artist": album["artist"],
                    "artists": album["artists"],
                    "is_compilation": album.get("is_compilation", False),
                    "track_count": album["track_count"],
                    "tracks": album["tracks"],
                    "duration_ms": album["duration_ms"],
                    "genres": album["genres"][:4],
                    "label": album["label"],
                    "release_date": album["release_date"],
                    "added_at": album["added_at"],
                    "position": album["position"],
                    "plays_year": plays,
                    "plays_all_time": all_time,
                    "first_listen": first_last[0],
                    "last_listen": first_last[1],
                    "matched": bool(key),
                    "image": image,
                    "spotify_url": album_url,
                    # O URI abre o disco direto no aplicativo do Spotify.
                    "spotify_uri": spotify_api.album_uri_from_url(album_url),
                })
            entry["cold"] = sorted(
                (album for album in entry["albums"] if album["plays_year"] < COLD_PLAY_THRESHOLD),
                key=lambda album: album["plays_year"],
            )

        # Discos muito ouvidos no ano que não entraram na Anuária daquele ano.
        for key, per_year in catalog.album_plays.items():
            plays = per_year.get(year, 0)
            if plays < MIN_PLAYS_FOR_CANDIDATE or key in in_playlist_keys:
                continue
            if len(catalog.album_tracks[key]) < MIN_TRACKS_FOR_CANDIDATE:
                continue
            meta = catalog.album_meta[key]
            entry["candidates"].append({
                "album": meta["album"],
                "artist": meta["artist"],
                "image": meta["image"],
                "plays_year": plays,
                "plays_all_time": sum(per_year.values()),
                "distinct_tracks": len(catalog.album_tracks[key]),
                "in_earlier_anuaria": key in seen_before[year],
                "first_listen": catalog.album_dates.get(key, ("", ""))[0],
            })
        entry["candidates"].sort(key=lambda album: -album["plays_year"])
        entry["candidates"] = entry["candidates"][:40]

        entry["top_artists"] = [
            {"artist": artist, "plays": per_year[year]}
            for artist, per_year in sorted(
                catalog.artist_plays.items(), key=lambda item: -item[1].get(year, 0)
            )[:15]
            if per_year.get(year, 0) > 0
        ]
        entry["top_tracks"] = [
            {"artist": artist, "track": track, "plays": per_year[year]}
            for (artist, track), per_year in sorted(
                catalog.track_plays.items(), key=lambda item: -item[1].get(year, 0)
            )[:15]
            if per_year.get(year, 0) > 0
        ]
        result["years"].append(entry)

    result["totals"] = build_totals(catalog, result["years"])
    return result


def build_totals(catalog, years):
    all_time_albums = sorted(
        (
            {
                "album": catalog.album_meta[key]["album"],
                "artist": catalog.album_meta[key]["artist"],
                "image": catalog.album_meta[key]["image"],
                "plays": sum(per_year.values()),
            }
            for key, per_year in catalog.album_plays.items()
        ),
        key=lambda album: -album["plays"],
    )[:100]
    all_time_artists = sorted(
        ({"artist": artist, "plays": sum(per_year.values())} for artist, per_year in catalog.artist_plays.items()),
        key=lambda item: -item["plays"],
    )[:100]
    all_time_tracks = sorted(
        (
            {"artist": artist, "track": track, "plays": sum(per_year.values())}
            for (artist, track), per_year in catalog.track_plays.items()
        ),
        key=lambda item: -item["plays"],
    )[:100]

    first = catalog.scrobbles[0] if catalog.scrobbles else None
    last = catalog.scrobbles[-1] if catalog.scrobbles else None
    return {
        "scrobbles": len(catalog.scrobbles),
        "artists": len(catalog.artist_plays),
        "albums": len(catalog.album_plays),
        "tracks": len(catalog.track_plays),
        "anuaria_albums": sum(len(year["albums"]) for year in years),
        "anuaria_years": sum(1 for year in years if year["has_playlist"]),
        "first_scrobble": first["date"] if first else "",
        "last_scrobble": last["date"] if last else "",
        "top_albums": all_time_albums,
        "top_artists": all_time_artists,
        "top_tracks": all_time_tracks,
    }
