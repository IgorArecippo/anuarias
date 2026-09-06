"""Exporta os candidatos de um ano como CSV, para importar no Spotify sem
depender do gerador automático (Soundiiz, TuneMyMusic e afins leem este formato).

    python3 export_candidatos.py 2026            # só os inéditos
    python3 export_candidatos.py 2026 --todos    # inclui os que já estiveram numa Anuária

Sai um arquivo por ano em data/candidatos-<ano>.csv com uma linha por faixa:
as faixas do disco que você realmente ouviu naquele ano, na ordem de execuções.
"""

import argparse
import csv
import os

import aggregate
import playlists


def export(year, only_new=True):
    catalog = aggregate.Catalog(aggregate.load_scrobbles())
    data = aggregate.build(playlists.load_playlists(), catalog)
    entry = next((item for item in data["years"] if item["year"] == year), None)
    if entry is None:
        raise SystemExit("Não há dados para %d" % year)

    candidates = [
        candidate for candidate in entry["candidates"]
        if not (only_new and candidate["in_earlier_anuaria"])
    ]
    if not candidates:
        raise SystemExit("Nenhum candidato para %d" % year)

    rows = []
    for candidate in candidates:
        key = playlists.album_key(candidate["artist"], candidate["album"])
        # As faixas do disco ouvidas naquele ano, da mais para a menos tocada.
        plays = {}
        for record in catalog.by_year.get(year, []):
            if record["album"] and playlists.album_key(record["artist"], record["album"]) == key:
                plays[record["track"]] = plays.get(record["track"], 0) + 1
        for track, count in sorted(plays.items(), key=lambda item: -item[1]):
            rows.append({
                "Track Name": track,
                "Artist Name": candidate["artist"],
                "Album Name": candidate["album"],
                "Plays": count,
                "Album Plays": candidate["plays_year"],
            })

    path = os.path.join(aggregate.DATA_DIR, "candidatos-%d.csv" % year)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Track Name", "Artist Name", "Album Name", "Plays", "Album Plays"])
        writer.writeheader()
        writer.writerows(rows)

    print("%d discos, %d faixas -> %s" % (len(candidates), len(rows), path))
    return path


def main():
    parser = argparse.ArgumentParser(description="Exporta os candidatos de um ano")
    parser.add_argument("year", type=int)
    parser.add_argument("--todos", action="store_true", help="inclui discos que já estiveram numa Anuária")
    args = parser.parse_args()
    export(args.year, only_new=not args.todos)


if __name__ == "__main__":
    main()
