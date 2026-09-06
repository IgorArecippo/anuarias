#!/bin/sh
# Atualiza tudo: baixa os scrobbles novos, busca capas que faltam e regera o site.
set -e
cd "$(dirname "$0")"

python3 fetch_scrobbles.py
python3 fetch_covers.py
python3 fetch_spotify.py
python3 build_site.py

echo
echo "Pronto. Abra site/index.html no navegador."
