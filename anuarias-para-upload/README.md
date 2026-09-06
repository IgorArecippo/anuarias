# Anuárias

Site estático que cruza o histórico do Last.fm (`igorarecippo`) com as playlists
Anuárias exportadas do Spotify — uma por ano, de 2017 a 2026.

A pergunta que ele responde: **dos discos que entraram na Anuária, quais você
realmente ouviu?** E o contrário: o que tocou muito no ano e ficou de fora.

## Como usar

```sh
./atualizar.sh          # baixa scrobbles novos, busca capas/links e regera o site
open site/index.html
```

Ou passo a passo:

```sh
python3 fetch_scrobbles.py   # histórico do Last.fm -> data/scrobbles.jsonl
python3 fetch_covers.py      # capas dos discos sem scrobble -> data/covers.json
python3 fetch_spotify.py     # link de cada álbum e descrição das playlists -> data/spotify.json
python3 build_site.py        # gera site/
```

Só precisa de Python 3 — nenhuma dependência externa.

Para servir o site com o botão de "atualizar" funcionando direto na página,
use `python3 serve.py` em vez de abrir o HTML direto ou usar `http.server`
(ele serve os mesmos arquivos de `site/`, mas também sabe rodar o
`atualizar.sh` quando o botão é clicado).

A primeira execução do `fetch_scrobbles.py` baixa as ~130 mil execuções (uns 5
minutos). Depois disso ela é incremental: busca só o que chegou desde o último
scrobble salvo. Use `--full` para refazer do zero.

## Configuração

As chaves de API ficam em `.env` (fora do controle de versão):

```
LASTFM_API_KEY=sua_chave
SPOTIFY_CLIENT_ID=seu_client_id
SPOTIFY_CLIENT_SECRET=seu_client_secret
```

Nova chave do Last.fm em <https://www.last.fm/api/account/create>.

O Spotify é opcional: sem ele o site funciona igual, só sem o link direto de
cada disco e sem a descrição da playlist. Para ativar, crie um app grátis em
<https://developer.spotify.com/dashboard> (qualquer nome/descrição servem; em
"Redirect URI" pode colocar `http://localhost:8888/callback`, ele não é usado
— o script só lê dados públicos via Client Credentials, sem login). Copie o
Client ID e o Client Secret gerados para o `.env`.

## Playlists

Os CSVs ficam em `playlists/`, no formato do [Exportify](https://exportify.net).
O ano vem do nome do arquivo (`Álbuns_'25.csv` → 2025), então para acrescentar um
ano basta exportar a playlist e salvar o arquivo ali com o ano no nome.

## Estrutura

| Arquivo | O que faz |
| --- | --- |
| `lastfm.py` | cliente da API (só stdlib, com retry e limite de taxa) |
| `fetch_scrobbles.py` | baixa o histórico completo, de forma incremental |
| `fetch_covers.py` | capas dos discos que não aparecem nos scrobbles |
| `spotify_api.py` | cliente mínimo da Web API do Spotify (Client Credentials) |
| `fetch_spotify.py` | link de cada álbum e descrição de cada playlist -> `data/spotify.json` |
| `playlists.py` | lê os CSVs e agrupa as faixas em discos |
| `aggregate.py` | cruza os dois lados e monta os números do site |
| `build_site.py` | gera o HTML |
| `serve.py` | serve `site/` e roda `atualizar.sh` quando o botão de atualizar é clicado |
| `export_candidatos.py` | exporta os candidatos de um ano em CSV |
| `assets/` | CSS e JS copiados para `site/assets/` |

`data/site-data.json` sai como subproduto: todo o cruzamento em JSON, caso você
queira usar em outro lugar.

## Levando os candidatos para o Spotify

```sh
python3 export_candidatos.py 2026            # só os discos inéditos
python3 export_candidatos.py 2026 --todos    # inclui os que já estiveram numa Anuária
```

Gera `data/candidatos-<ano>.csv` com uma linha por faixa — as faixas que você
realmente ouviu de cada disco, da mais para a menos tocada. O formato
(Track Name / Artist Name / Album Name) é o que Soundiiz e TuneMyMusic leem para
importar direto numa playlist do Spotify.

## Detalhes que importam

**Casamento de discos.** Spotify e Last.fm escrevem o mesmo disco de formas
diferentes ("Deluxe Edition", "- Remastered 2011", acentos). A normalização em
`playlists.normalize()` remove esses sufixos e, quando ainda assim não bate,
`Catalog.resolve()` procura o artista mais parecido entre os discos de mesmo
nome. Os discos que não casaram aparecem marcados no site.

**Coletâneas.** Em tributos e trilhas cada faixa tem um artista diferente, o que
espatifaria o disco em dezenas de entradas. Quando o título e a data de
lançamento batem e há três artistas ou mais, tudo vira uma entrada só de
"Vários artistas".

**2017 e 2018.** A conta do Last.fm é de outubro de 2018, então essas Anuárias
não têm execuções para cruzar — as capas vêm do `fetch_covers.py` e a página
mostra a playlist sem os números.

**Fuso.** Os scrobbles chegam em UTC e são convertidos para `America/Sao_Paulo`
antes de decidir a que ano pertencem.

## Limiares

Em `aggregate.py`, ajuste ao gosto:

- `MIN_PLAYS_FOR_CANDIDATE = 25` — mínimo de execuções para um disco de fora
  entrar na lista "Ficaram de fora"
- `MIN_TRACKS_FOR_CANDIDATE = 4` — evita que um single em repeat vire candidato
- `COLD_PLAY_THRESHOLD = 10` — abaixo disso o disco aparece em "Esfriaram"
