#!/bin/bash
# Kliknij ten plik dwukrotnie, aby uruchomić graficzny interfejs (GUI).
# Otworzy się w przeglądarce. Aby zamknąć: wróć tu i wciśnij Ctrl+C.

cd "$(dirname "$0")"

# Włącz wirtualne środowisko, jeśli istnieje.
if [ -d "venv" ]; then
  source venv/bin/activate
fi

echo "Uruchamiam interfejs... (za chwilę otworzy się przeglądarka)"
streamlit run interfejs.py
