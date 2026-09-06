"""Leitura das Anuárias exportadas do Spotify (formato Exportify) e normalização
de nomes para cruzar com o Last.fm."""

import csv
import glob
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_DIR = os.path.join(BASE_DIR, "playlists")

# Sufixos que o Spotify e o Last.fm escrevem de formas diferentes para o mesmo
# disco: só atrapalham na hora de casar os dois catálogos.
EDITION_NOISE = re.compile(
    r"\s*[\(\[\-–—]+\s*[^\(\)\[\]]*\b("
    r"deluxe|remaster|remastered|remasterizado|expanded|edition|edição|version|versão|"
    r"bonus|b-sides|anniversary|aniversário|reissue|mono|stereo|explicit|clean|"
    r"special|super|complete|extended|ao vivo em|live at|live from|"
    r"\d{4}\s*mix|\d+th)\b[^\(\)\[\]]*[\)\]]?\s*$",
    re.IGNORECASE,
)
PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
SPACES = re.compile(r"\s+")


def strip_accents(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text):
    """Chave de comparação: sem acento, sem pontuação, sem sufixo de edição."""
    if not text:
        return ""
    text = strip_accents(text).lower().strip()
    previous = None
    while previous != text:
        previous = text
        text = EDITION_NOISE.sub("", text).strip()
    text = PUNCTUATION.sub(" ", text)
    return SPACES.sub(" ", text).strip()


def primary_artist(artist_field):
    """A coluna do Spotify traz todos os artistas separados por ';' (participações
    inclusive); o Last.fm credita só o primeiro. Vírgula não serve de separador
    porque há nomes que a contêm ("Crosby, Stills & Nash")."""
    return (artist_field or "").split(";")[0].strip()


def album_key(artist, album):
    return (normalize(primary_artist(artist)), normalize(album))


def year_from_filename(path):
    """Álbuns_'17.csv -> 2017. Aceita 2 ou 4 dígitos."""
    digits = re.findall(r"(\d{2,4})", os.path.basename(path))
    if not digits:
        return None
    value = digits[-1]
    if len(value) == 4:
        return int(value)
    number = int(value)
    return 2000 + number if number < 90 else 1900 + number


def load_playlists(directory=PLAYLIST_DIR):
    """Devolve {ano: {"tracks": [...], "albums": [...]}} lido dos CSVs."""
    playlists = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.csv"))):
        year = year_from_filename(path)
        if year is None:
            print("Ignorando %s: não consegui identificar o ano pelo nome" % os.path.basename(path))
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        playlists[year] = {
            "year": year,
            "source": os.path.basename(path),
            "tracks": [_clean_row(row) for row in rows if (row.get("Track Name") or "").strip()],
        }
    for year, playlist in playlists.items():
        playlist["albums"] = group_albums(playlist["tracks"])
        playlist["owner"] = dominant_owner(playlist["tracks"])
    return playlists


def dominant_owner(tracks):
    """Quem adicionou a maior parte das faixas — é o dono da playlist no Spotify.
    Sai do próprio CSV, então não precisa ser configurado à mão."""
    counts = {}
    for track in tracks:
        if track["added_by"]:
            counts[track["added_by"]] = counts.get(track["added_by"], 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


def _clean_row(row):
    return {
        "uri": (row.get("Track URI") or "").strip(),
        "track": (row.get("Track Name") or "").strip(),
        "album": (row.get("Album Name") or "").strip(),
        "artists": (row.get("Artist Name(s)") or "").strip(),
        "release_date": (row.get("Release Date") or "").strip(),
        "added_at": (row.get("Added At") or "").strip(),
        "added_by": (row.get("Added By") or "").strip(),
        "duration_ms": _to_int(row.get("Duration (ms)")),
        "genres": [g.strip() for g in (row.get("Genres") or "").split(",") if g.strip()],
        "label": (row.get("Record Label") or "").strip(),
    }


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def group_albums(tracks):
    """Agrupa as faixas da playlist em álbuns (é assim que ele monta a Anuária)."""
    albums = {}
    for index, track in enumerate(tracks):
        key = album_key(track["artists"], track["album"])
        album = albums.get(key)
        if album is None:
            album = albums[key] = {
                "key": key,
                "album": track["album"],
                "artist": primary_artist(track["artists"]),
                "artists": track["artists"],
                "release_date": track["release_date"],
                "label": track["label"],
                "genres": [],
                "tracks": [],
                "track_uris": [],
                "duration_ms": 0,
                "added_at": track["added_at"],
                "position": index,
            }
        album["tracks"].append(track["track"])
        if track["uri"]:
            album["track_uris"].append(track["uri"])
        album["duration_ms"] += track["duration_ms"]
        for genre in track["genres"]:
            if genre not in album["genres"]:
                album["genres"].append(genre)
        if track["added_at"] and track["added_at"] < album["added_at"]:
            album["added_at"] = track["added_at"]
    ordered = merge_compilations(sorted(albums.values(), key=lambda album: album["position"]))
    for album in ordered:
        album["track_count"] = len(album["tracks"])
    return ordered


COMPILATION_LABEL = "Vários artistas"
MIN_ARTISTS_FOR_COMPILATION = 3


def merge_compilations(albums):
    """Junta trilhas, tributos e coletâneas.

    Nelas cada faixa tem um artista principal diferente, então o agrupamento por
    (artista, álbum) estoura o mesmo disco em dezenas de entradas. Só juntamos
    quando o título e a data de lançamento batem e há três artistas ou mais —
    assim dois discos homônimos de artistas diferentes continuam separados.
    """
    groups = {}
    for album in albums:
        groups.setdefault((normalize(album["album"]), album["release_date"]), []).append(album)

    merged = []
    for group in groups.values():
        artists = {album["artist"] for album in group}
        if len(group) < 2 or len(artists) < MIN_ARTISTS_FOR_COMPILATION:
            merged.extend(group)
            continue
        head = dict(group[0])
        head["artist"] = COMPILATION_LABEL
        head["artists"] = "; ".join(sorted(artists))
        head["is_compilation"] = True
        head["tracks"] = [track for album in group for track in album["tracks"]]
        head["track_uris"] = [uri for album in group for uri in album["track_uris"]]
        head["duration_ms"] = sum(album["duration_ms"] for album in group)
        head["genres"] = list(dict.fromkeys(g for album in group for g in album["genres"]))
        head["added_at"] = min(album["added_at"] for album in group if album["added_at"]) or head["added_at"]
        head["position"] = min(album["position"] for album in group)
        merged.append(head)

    return sorted(merged, key=lambda album: album["position"])
