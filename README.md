# Generator fiszek Anki z PDF

Program bierze dokument PDF, wyciąga z niego tekst i obrazki, a Claude
zamienia to na gotowe fiszki do Anki (plik `.apkg`, który po prostu importujesz).

To jest **wersja MVP** — czyli najprostsza działająca wersja. Najpierw
sprawdzamy, czy jakość fiszek jest dobra, a dopiero potem dokładamy fajerwerki.

---

## Zanim zaczniesz — zdobądź klucz API (jednorazowo)

Program używa Claude, więc potrzebuje "klucza API" (to jak hasło dostępu).

1. Wejdź na: https://console.anthropic.com/settings/keys
2. Zaloguj się / załóż konto, kliknij **Create Key**, skopiuj klucz.
3. Będziesz go musiał doładować drobną kwotą (to usługa płatna od zużycia —
   generowanie fiszek z jednego dokumentu to zwykle grosze).

> ⚠️ Klucz API to sekret. Nie wysyłaj go nikomu i nie wrzucaj do internetu.

---

## Instalacja (robisz raz)

Otwórz Terminal i wklej te komendy po kolei.

Wejdź do folderu z projektem:

```bash
cd "/Users/jakub/Claude Code/anki-generator"
```

Stwórz "wirtualne środowisko" (osobny, czysty kącik na biblioteki tego projektu):

```bash
python3 -m venv venv
```

Włącz to środowisko (robisz to za każdym razem, gdy wracasz do pracy):

```bash
source venv/bin/activate
```

Zainstaluj potrzebne biblioteki:

```bash
pip install -r requirements.txt
```

Stwórz swój plik z kluczem (kopiujemy szablon i wpisujemy klucz):

```bash
cp .env.example .env
```

Potem otwórz plik `.env` w dowolnym edytorze i wklej swój klucz zamiast
napisu `tutaj-wklej-swoj-klucz`.

---

## Użycie — najłatwiej: interfejs graficzny (GUI)

Nie musisz znać Terminala. Uruchom raz:

```bash
streamlit run interfejs.py
```

albo **kliknij dwukrotnie plik `uruchom_GUI.command`**. Otworzy się strona w
przeglądarce, gdzie: wgrywasz plik (PDF lub `.docx`), wpisujesz przedmiot,
zaznaczasz opcje, wybierasz model, klikasz **Generuj** i pobierasz `.apkg`.
Zaznacz **Tryb demo**, żeby przetestować za darmo (bez kosztu API).

## Użycie — z Terminala (dla zaawansowanych)

Włóż jakiś plik PDF do folderu projektu (albo znajdź jego ścieżkę), i uruchom:

```bash
python anki_generator.py twoj_dokument.pdf
```

Bazy pytań egzaminacyjnych (`.docx`) — fiszki wprost z pytań, z weryfikacją
odpowiedzi:

```bash
python anki_generator.py "baza_egzaminacyjna.docx" --przedmiot "Mikrobiologia" --recenzja
```

### Opcje (flagi)

Możesz dopisać na końcu komendy:

| Flaga | Co robi |
|-------|---------|
| `--cloze` | Fiszki z lukami `{{c1::...}}` zamiast pytanie-odpowiedź |
| `--recenzja` | Dodatkowy przebieg Claude: usuwa duplikaty i słabe fiszki (kosztuje trochę więcej, bo to dodatkowe zapytania) |
| `--slajdy` | Dołącza zrzut CAŁEGO slajdu jako obrazek do każdej fiszki z tej strony (idealne do prezentacji, gdzie wykresy/rodowody są rysowane, nie wklejone). Obrazki są tylko w `.apkg` — plik `.txt` ich nie przenosi. |
| `--strony 1-10` | Ogranicza przetwarzanie do zakresu stron |
| `--demo` | Test bez API (za darmo), fiszki-zaślepki |

Flagi można łączyć, np. cloze z recenzją:

```bash
python anki_generator.py twoj_dokument.pdf --cloze --recenzja
```

> Uwaga o imporcie plików `.txt`:
> - zwykłe fiszki → separator pól **Pipe** (`|`),
> - cloze → wybierz typ notatki **Cloze** (jedno pole).
>
> Plik `.apkg` importuje się zawsze bez żadnych ustawień — polecam go, gdy nie
> chcesz się bawić w konfigurację.

Po chwili powstaną **dwa pliki**:

- `twoj_dokument.txt` — format `pytanie|odpowiedz` (jedna fiszka na linię).
  W Anki: **Plik → Importuj** → jako separator pól wybierz **Pipe** (znak `|`).
- `twoj_dokument.apkg` — wersja z obrazkami, import bez żadnych ustawień.
  W Anki: **Plik → Importuj** → wybierz plik. Fiszki wejdą do nowej talii.

Fiszki są generowane w stylu dla studentów medycyny: wyczerpujące, po polsku,
z pogrubieniami (`<b>`), kolorami kluczowych pojęć, wzorami matematycznymi
`\( ... \)` i chemicznymi `\ce{...}`. Styl zmienisz w zmiennej
`PROMPT_SYSTEMOWY` w pliku `anki_generator.py`.

---

## Co dalej (pomysły na rozbudowę)

- Drugi przebieg Claude jako "recenzent": usuwa duplikaty i słabe fiszki.
- Obsługa innych formatów wejścia (Word, zwykły tekst).
- Prosty interfejs graficzny zamiast Terminala.
- Lepsze dopasowanie obrazków do konkretnych fiszek.
- Fiszki typu "cloze" (luki do uzupełnienia), nie tylko pytanie-odpowiedź.

---

## Jak to działa w środku (skrót)

1. `PyMuPDF` czyta PDF → tekst + obrazki dla każdej strony.
2. Tekst dzielony jest na kawałki.
3. Każdy kawałek leci do Claude, który zwraca uporządkowaną listę fiszek.
4. Obrazek ze strony przypinany jest do pierwszej fiszki z tej strony.
5. `genanki` skleja wszystko w plik `.apkg`.

Cały kod jest w pliku `anki_generator.py` i jest po polsku skomentowany —
możesz go czytać jak przepis.
