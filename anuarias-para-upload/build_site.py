"""Gera o site estático das Anuárias em site/.

    python3 build_site.py

Cada página é HTML puro (sem build, sem servidor obrigatório): dá pra abrir o
site/index.html direto no navegador.
"""

import html
import json
import os
import shutil

import aggregate
import playlists

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(BASE_DIR, "site")
ASSETS_DIR = os.path.join(SITE_DIR, "assets")

MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
PLACEHOLDER = (
    "data:image/svg+xml;charset=utf-8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
    "%3Crect width='100' height='100' fill='%231c1c26'/%3E"
    "%3Ccircle cx='50' cy='50' r='26' fill='none' stroke='%23343044' stroke-width='2'/%3E"
    "%3Ccircle cx='50' cy='50' r='4' fill='%23343044'/%3E%3C/svg%3E"
)


def esc(value):
    return html.escape(str(value or ""), quote=True)


def number(value):
    return "{:,}".format(int(value)).replace(",", ".")


def duration_label(milliseconds):
    minutes = int(milliseconds / 60000)
    if minutes < 60:
        return "%d min" % minutes
    return "%dh%02d" % (minutes // 60, minutes % 60)


def year_label(year):
    return str(year)


def month_label(added_at):
    if not added_at or len(added_at) < 7:
        return ""
    try:
        return MONTHS[int(added_at[5:7]) - 1]
    except (ValueError, IndexError):
        return ""


def cover(url, size="md"):
    source = url or PLACEHOLDER
    return '<div class="cover cover-%s"><img src="%s" loading="lazy" alt="" onerror="this.src=\'%s\'"></div>' % (
        size, esc(source), PLACEHOLDER
    )


def page(title, body, active="", subtitle=""):
    return """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="topbar">
  <a class="brand" href="index.html"><span class="brand-mark"></span>Anuárias</a>
  <nav>
    <a href="index.html" class="%(nav_home)s">Os anos</a>
    <a href="historico.html" class="%(nav_hist)s">Histórico</a>
    <button type="button" id="refresh-button" class="refresh-button" title="Busca scrobbles novos, links e capas, e regera o site">
      <span class="refresh-label">Atualizar dados</span>
    </button>
  </nav>
</header>
%(body)s
<footer class="footer">
  <p>Gerado a partir do histórico do Last.fm de <a href="https://www.last.fm/user/igorarecippo">igorarecippo</a> e das Anuárias exportadas do Spotify.</p>
</footer>
<script src="assets/app.js"></script>
</body>
</html>
""" % {
        "title": esc(title),
        "body": body,
        "nav_home": "active" if active == "home" else "",
        "nav_hist": "active" if active == "hist" else "",
    }


def bar_chart(values, labels, height=90):
    """Gráfico de barras simples em CSS — evita dependência de biblioteca."""
    peak = max(values) if values and max(values) else 1
    bars = []
    for value, label in zip(values, labels):
        percent = (value / peak) * 100
        bars.append(
            '<div class="bar" title="%s: %s execuções">'
            '<div class="bar-fill" style="height:%.1f%%"></div>'
            '<span class="bar-label">%s</span></div>' % (esc(label), number(value), percent, esc(label))
        )
    return '<div class="chart" style="--chart-height:%dpx">%s</div>' % (height, "".join(bars))


def stat(value, label, hint=""):
    hint_html = '<span class="stat-hint">%s</span>' % esc(hint) if hint else ""
    return '<div class="stat"><strong>%s</strong><span>%s</span>%s</div>' % (esc(value), esc(label), hint_html)


# --------------------------------------------------------------------------- #
# Página de um ano
# --------------------------------------------------------------------------- #

def album_card(album, year):
    plays = album["plays_year"]
    badges = ['<li>%s faixas</li>' % album["track_count"]]
    if album["duration_ms"]:
        badges.append("<li>%s</li>" % duration_label(album["duration_ms"]))
    month = month_label(album["added_at"])
    if month:
        badges.append("<li>entrou em %s</li>" % month)
    if album["genres"]:
        badges.append('<li class="genre">%s</li>' % esc(album["genres"][0]))

    if plays:
        plays_html = '<div class="plays"><strong>%s</strong><span>execuções em %d</span></div>' % (number(plays), year)
    elif album["plays_all_time"]:
        plays_html = (
            '<div class="plays plays-off"><strong>%s</strong><span>execuções, mas fora de %d</span></div>'
            % (number(album["plays_all_time"]), year)
        )
    else:
        plays_html = '<div class="plays plays-none"><strong>—</strong><span>sem scrobble</span></div>'

    classes = "album"
    if plays < aggregate.COLD_PLAY_THRESHOLD:
        classes += " is-cold"

    # spotify:album:<id> abre direto no aplicativo; o https abre o navegador
    # antes. Sem target="_blank": o URI não navega, só entrega ao app.
    spotify_link = album.get("spotify_uri") or album.get("spotify_url")
    if spotify_link:
        link_open = '<a class="album-link" href="%s" title="Abrir no Spotify">' % esc(spotify_link)
        link_close = "</a>"
    else:
        link_open = '<div class="album-link">'
        link_close = "</div>"

    return (
        '<article class="%s" data-pos="%d" data-plays="%d" data-tracks="%d" data-search="%s">'
        "%s"
        "%s"
        '<div class="album-body"><h3>%s</h3><p class="artist">%s</p><ul class="badges">%s</ul></div>'
        "%s"
        "%s"
        "</article>"
    ) % (
        classes,
        album["position"],
        plays,
        album["track_count"],
        esc((album["artist"] + " " + album["album"]).lower()),
        link_open,
        cover(album["image"]),
        esc(album["album"]),
        esc(album["artist"]),
        "".join(badges),
        link_close,
        plays_html,
    )


def candidate_row(candidate, year):
    note = ""
    if candidate["in_earlier_anuaria"]:
        note = '<li class="tag-soft">já esteve em outra Anuária</li>'
    return (
        '<article class="row" data-plays="%d" data-earlier="%d" data-search="%s">'
        "%s"
        '<div class="row-body"><h3>%s</h3><p class="artist">%s</p>'
        '<ul class="badges"><li>%d faixas distintas</li><li>%s no total</li>%s</ul></div>'
        '<div class="plays"><strong>%s</strong><span>execuções em %d</span></div>'
        "</article>"
    ) % (
        candidate["plays_year"],
        1 if candidate["in_earlier_anuaria"] else 0,
        esc((candidate["artist"] + " " + candidate["album"]).lower()),
        cover(candidate["image"], "sm"),
        esc(candidate["album"]),
        esc(candidate["artist"]),
        candidate["distinct_tracks"],
        number(candidate["plays_all_time"]),
        note,
        number(candidate["plays_year"]),
        year,
    )


MONTHS_FULL = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def pretty_date(iso_date):
    if not iso_date or len(iso_date) < 10:
        return iso_date
    return "%d de %s de %s" % (int(iso_date[8:10]), MONTHS_FULL[int(iso_date[5:7]) - 1], iso_date[:4])


def coverage_notice(entry):
    """Deixa claro quando os números do ano não cobrem o ano inteiro."""
    if not entry["albums"]:
        return ""
    if not entry["scrobbles"]:
        return (
            '<p class="notice">Esta Anuária é anterior ao seu Last.fm (o histórico começa em '
            "outubro de 2018), então não há execuções para cruzar — a página mostra a playlist como ela é.</p>"
        )
    if entry["partial_from"]:
        return (
            '<p class="notice">O histórico deste ano só começa em %s, então as execuções cobrem '
            "apenas parte de %d. Os discos ouvidos antes disso aparecem com números baixos.</p>"
            % (esc(pretty_date(entry["partial_from"])), entry["year"])
        )
    if entry["partial_to"]:
        return (
            '<p class="notice">Ano em andamento: os números vão até %s.</p>'
            % esc(pretty_date(entry["partial_to"]))
        )
    return ""


def year_page(entry, all_years):
    year = entry["year"]
    albums = entry["albums"]
    played = [album for album in albums if album["plays_year"] > 0]
    total_tracks = sum(album["track_count"] for album in albums)
    total_duration = sum(album["duration_ms"] for album in albums)
    plays_in_anuaria = sum(album["plays_year"] for album in albums)
    coverage = (100.0 * plays_in_anuaria / entry["scrobbles"]) if entry["scrobbles"] else 0

    parts = []
    parts.append('<main class="wrap">')

    # Cabeçalho com navegação entre anos
    index = all_years.index(year)
    previous_link = (
        '<a class="year-nav" href="ano-%d.html">← %s</a>' % (all_years[index - 1], year_label(all_years[index - 1]))
        if index > 0 else "<span></span>"
    )
    next_link = (
        '<a class="year-nav" href="ano-%d.html">%s →</a>' % (all_years[index + 1], year_label(all_years[index + 1]))
        if index < len(all_years) - 1 else "<span></span>"
    )
    parts.append(
        '<div class="year-head">%s<h1><span class="year-big">%s</span><small>Anuária</small></h1>%s</div>'
        % (previous_link, esc(year_label(year)), next_link)
    )

    parts.append('<section class="stats">')
    parts.append(stat(len(albums), "discos na playlist"))
    parts.append(stat(total_tracks, "faixas", duration_label(total_duration)))
    parts.append(stat(number(entry["scrobbles"]), "execuções no ano"))
    if entry["scrobbles"]:
        parts.append(stat("%.0f%%" % coverage, "do ano veio da Anuária"))
    parts.append("</section>")

    if entry["playlist_description"]:
        # O URI abre no app; se não houver, cai para o link do navegador.
        link = entry.get("playlist_uri") or entry["playlist_url"]
        if link:
            parts.append(
                '<p class="playlist-description"><a href="%s">%s</a></p>'
                % (esc(link), esc(entry["playlist_description"]))
            )
        else:
            parts.append('<p class="playlist-description">%s</p>' % esc(entry["playlist_description"]))

    parts.append(coverage_notice(entry))

    if not albums:
        parts.append('<p class="empty">Não há playlist exportada para %d.</p>' % year)
    else:
        # A Anuária
        parts.append('<section class="block" id="anuaria">')
        parts.append(
            '<div class="block-head"><h2>A Anuária</h2>'
            '<div class="controls">'
            '<input type="search" class="filter" data-target="#album-grid" placeholder="filtrar por artista ou disco...">'
            '<div class="sorts" data-target="#album-grid">'
            '<button class="active" data-sort="pos">ordem da playlist</button>'
            '<button data-sort="plays-desc">mais ouvidos</button>'
            '<button data-sort="plays-asc">menos ouvidos</button>'
            '<button data-sort="tracks-desc">mais faixas</button>'
            "</div></div></div>"
        )
        parts.append('<div class="grid" id="album-grid">%s</div>' % "".join(album_card(a, year) for a in albums))
        parts.append("</section>")

    # Candidatos que ficaram de fora
    if entry["candidates"]:
        novelties = sum(1 for candidate in entry["candidates"] if not candidate["in_earlier_anuaria"])
        parts.append('<section class="block" id="candidatos">')
        parts.append(
            '<div class="block-head"><h2>Ficaram de fora</h2>'
            '<div class="controls">'
            '<input type="search" class="filter" data-target="#candidate-rows" placeholder="filtrar...">'
            '<div class="sorts" data-target="#candidate-rows">'
            '<button class="active" data-only="all">todos (%d)</button>'
            '<button data-only="new">só os inéditos (%d)</button>'
            "</div></div>"
            '<p class="lead">Discos com %d execuções ou mais em %d que não estão na Anuária. '
            "Bons candidatos a entrar — ou lembrete do que você ouviu sem registrar.</p></div>"
            % (len(entry["candidates"]), novelties, aggregate.MIN_PLAYS_FOR_CANDIDATE, year)
        )
        parts.append(
            '<div class="rows" id="candidate-rows">%s</div>'
            % "".join(candidate_row(c, year) for c in entry["candidates"])
        )
        parts.append("</section>")

    # Esfriaram — só faz sentido em anos com histórico do começo ao fim.
    if entry["cold"] and entry["scrobbles"] and not entry["partial_from"]:
        parts.append('<section class="block" id="esfriaram">')
        parts.append(
            '<div class="block-head"><h2>Esfriaram</h2>'
            "<p class=\"lead\">Entraram na Anuária mas ficaram abaixo de %d execuções em %d. "
            "Vale rever se ainda merecem o lugar.</p></div>" % (aggregate.COLD_PLAY_THRESHOLD, year)
        )
        parts.append(
            '<div class="rows">%s</div>'
            % "".join(
                '<article class="row"><div class="cover cover-sm"><img src="%s" loading="lazy" alt=""></div>'
                '<div class="row-body"><h3>%s</h3><p class="artist">%s</p>'
                '<ul class="badges"><li>%d faixas</li>%s</ul></div>'
                '<div class="plays plays-none"><strong>%s</strong><span>execuções em %d</span></div></article>'
                % (
                    esc(album["image"] or PLACEHOLDER),
                    esc(album["album"]),
                    esc(album["artist"]),
                    album["track_count"],
                    '<li class="tag-soft">sem correspondência no Last.fm</li>' if not album["matched"] else "",
                    number(album["plays_year"]),
                    year,
                )
                for album in entry["cold"]
            )
        )
        parts.append("</section>")

    # O ano em números
    if entry["scrobbles"]:
        parts.append('<section class="block" id="numeros">')
        parts.append('<div class="block-head"><h2>O ano em números</h2></div>')
        parts.append('<div class="two-col">')
        parts.append('<div class="panel"><h3>Execuções por mês</h3>%s</div>' % bar_chart(entry["months"], MONTHS))
        parts.append(
            '<div class="panel"><h3>Artistas do ano</h3><ol class="ranking">%s</ol></div>'
            % "".join(
                "<li><span>%s</span><b>%s</b></li>" % (esc(item["artist"]), number(item["plays"]))
                for item in entry["top_artists"][:10]
            )
        )
        parts.append("</div>")
        parts.append(
            '<div class="panel"><h3>Faixas do ano</h3><ol class="ranking two">%s</ol></div>'
            % "".join(
                "<li><span>%s <em>— %s</em></span><b>%s</b></li>"
                % (esc(item["track"]), esc(item["artist"]), number(item["plays"]))
                for item in entry["top_tracks"][:10]
            )
        )
        parts.append("</section>")

    parts.append("</main>")
    return page("Anuária %s" % year_label(year), "".join(parts))


# --------------------------------------------------------------------------- #
# Índice e histórico
# --------------------------------------------------------------------------- #

def year_card(entry):
    year = entry["year"]
    albums = entry["albums"]
    mosaic_source = sorted(albums, key=lambda album: -album["plays_year"])[:4] or albums[:4]
    mosaic = "".join(
        '<img src="%s" loading="lazy" alt="" onerror="this.src=\'%s\'">' % (esc(album["image"] or PLACEHOLDER), PLACEHOLDER)
        for album in mosaic_source
    )
    while mosaic_source and len(mosaic_source) < 4:
        mosaic += '<img src="%s" alt="">' % PLACEHOLDER
        mosaic_source = mosaic_source + [None]
    if not albums:
        mosaic = ('<img src="%s" alt="">' % PLACEHOLDER) * 4

    lines = []
    if albums:
        lines.append("%d discos" % len(albums))
        lines.append("%s faixas" % number(sum(album["track_count"] for album in albums)))
    else:
        lines.append("sem playlist exportada")
    if entry["scrobbles"]:
        lines.append("%s execuções" % number(entry["scrobbles"]))

    highlight = ""
    if albums:
        best = max(albums, key=lambda album: album["plays_year"])
        if best["plays_year"]:
            highlight = '<p class="card-top">disco do ano: <b>%s</b> — %s</p>' % (
                esc(best["album"]), esc(best["artist"])
            )

    return (
        '<a class="year-card" href="ano-%d.html">'
        '<div class="mosaic">%s</div>'
        '<div class="year-card-body"><h2>%s</h2><p>%s</p>%s</div></a>'
    ) % (entry["year"], mosaic, esc(year_label(year)), esc(" · ".join(lines)), highlight)


def index_page(data):
    totals = data["totals"]
    years = sorted((entry for entry in data["years"]), key=lambda entry: -entry["year"])
    parts = ['<main class="wrap">']
    parts.append(
        '<section class="hero">'
        "<h1>Dez anos de Anuárias</h1>"
        '<p class="lead">Toda a coleção de discos do ano, cruzada com o histórico de escuta do Last.fm. '
        "Cada ano mostra o que entrou na playlist, o quanto cada disco realmente tocou, "
        "e o que ficou de fora merecendo um lugar.</p>"
        '<div class="stats">%s%s%s%s</div>'
        "</section>"
        % (
            stat(number(totals["anuaria_albums"]), "discos nas Anuárias", "%d anos" % totals["anuaria_years"]),
            stat(number(totals["scrobbles"]), "execuções registradas", "desde %s" % totals["first_scrobble"][:7]),
            stat(number(totals["artists"]), "artistas ouvidos"),
            stat(number(totals["albums"]), "álbuns diferentes"),
        )
    )
    parts.append('<section class="year-grid">%s</section>' % "".join(year_card(entry) for entry in years))
    parts.append("</main>")
    return page("Anuárias", "".join(parts), active="home")


def history_page(data):
    totals = data["totals"]
    years = sorted(data["years"], key=lambda entry: entry["year"])
    parts = ['<main class="wrap">']
    parts.append(
        '<section class="hero small"><h1>Histórico completo</h1>'
        '<p class="lead">%s execuções entre %s e %s.</p>'
        '<div class="stats">%s%s%s%s</div></section>'
        % (
            number(totals["scrobbles"]),
            esc(totals["first_scrobble"]),
            esc(totals["last_scrobble"]),
            stat(number(totals["scrobbles"]), "execuções"),
            stat(number(totals["artists"]), "artistas"),
            stat(number(totals["albums"]), "álbuns"),
            stat(number(totals["tracks"]), "faixas"),
        )
    )

    parts.append('<section class="block"><div class="block-head"><h2>Execuções por ano</h2></div>')
    parts.append(
        bar_chart(
            [entry["scrobbles"] for entry in years],
            [year_label(entry["year"]) for entry in years],
            height=140,
        )
    )
    parts.append("</section>")

    def ranking_block(title, items, render, target):
        return (
            '<section class="block"><div class="block-head"><h2>%s</h2>'
            '<div class="controls"><input type="search" class="filter" data-target="#%s" placeholder="filtrar..."></div></div>'
            '<ol class="ranking numbered" id="%s">%s</ol></section>'
        ) % (title, target, target, "".join(render(item) for item in items))

    parts.append(
        ranking_block(
            "Álbuns mais ouvidos",
            totals["top_albums"],
            lambda item: '<li data-search="%s"><span>%s <em>— %s</em></span><b>%s</b></li>'
            % (
                esc((item["artist"] + " " + item["album"]).lower()),
                esc(item["album"]),
                esc(item["artist"]),
                number(item["plays"]),
            ),
            "top-albums",
        )
    )
    parts.append(
        ranking_block(
            "Artistas mais ouvidos",
            totals["top_artists"],
            lambda item: '<li data-search="%s"><span>%s</span><b>%s</b></li>'
            % (esc(item["artist"].lower()), esc(item["artist"]), number(item["plays"])),
            "top-artists",
        )
    )
    parts.append(
        ranking_block(
            "Faixas mais ouvidas",
            totals["top_tracks"],
            lambda item: '<li data-search="%s"><span>%s <em>— %s</em></span><b>%s</b></li>'
            % (
                esc((item["artist"] + " " + item["track"]).lower()),
                esc(item["track"]),
                esc(item["artist"]),
                number(item["plays"]),
            ),
            "top-tracks",
        )
    )
    parts.append("</main>")
    return page("Histórico", "".join(parts), active="hist")


# --------------------------------------------------------------------------- #

def write(path, content):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def main():
    covers = {}
    covers_path = os.path.join(aggregate.DATA_DIR, "covers.json")
    if os.path.exists(covers_path):
        with open(covers_path, encoding="utf-8") as fh:
            covers = json.load(fh)

    spotify_meta = {"albums": {}, "playlists": {}}
    spotify_path = os.path.join(aggregate.DATA_DIR, "spotify.json")
    if os.path.exists(spotify_path):
        with open(spotify_path, encoding="utf-8") as fh:
            spotify_meta = json.load(fh)

    scrobbles = aggregate.load_scrobbles()
    catalog = aggregate.Catalog(scrobbles)
    data = aggregate.build(playlists.load_playlists(), catalog, covers, spotify_meta)

    os.makedirs(ASSETS_DIR, exist_ok=True)
    shutil.copyfile(os.path.join(BASE_DIR, "assets", "style.css"), os.path.join(ASSETS_DIR, "style.css"))
    shutil.copyfile(os.path.join(BASE_DIR, "assets", "app.js"), os.path.join(ASSETS_DIR, "app.js"))

    all_years = sorted(entry["year"] for entry in data["years"])
    write(os.path.join(SITE_DIR, "index.html"), index_page(data))
    write(os.path.join(SITE_DIR, "historico.html"), history_page(data))
    for entry in data["years"]:
        write(os.path.join(SITE_DIR, "ano-%d.html" % entry["year"]), year_page(entry, all_years))

    with open(os.path.join(aggregate.DATA_DIR, "site-data.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    print("Site gerado em %s" % SITE_DIR)
    print("  %d páginas de ano + índice + histórico" % len(data["years"]))
    for entry in data["years"]:
        print(
            "  %d: %2d discos | %6s execuções | %2d candidatos | %2d esfriaram"
            % (entry["year"], len(entry["albums"]), number(entry["scrobbles"]), len(entry["candidates"]), len(entry["cold"]))
        )


if __name__ == "__main__":
    main()
