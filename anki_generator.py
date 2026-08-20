"""
Generator fiszek Anki z dokumentu PDF.

Co robi ten program (po kolei):
  1. Otwiera plik PDF i wyciąga z niego tekst + obrazki (strona po stronie).
  2. Dzieli tekst na kawałki ("chunki").
  3. Dla każdego kawałka prosi Claude o wygenerowanie fiszek.
  4. (Opcjonalnie) Recenzent czyści fiszki: usuwa duplikaty i słabe karty.
  5. Zapisuje wynik jako plik .txt (pytanie|odpowiedz) oraz .apkg (z obrazkami).

Tryby (flagi):
    python anki_generator.py dokument.pdf              # zwykłe fiszki pytanie-odpowiedź
    python anki_generator.py dokument.pdf --cloze      # fiszki z lukami {{c1::...}}
    python anki_generator.py dokument.pdf --recenzja    # dodatkowy przebieg czyszczący
    python anki_generator.py dokument.pdf --demo        # test bez API (za darmo)
Flagi można łączyć, np.:  ... --cloze --recenzja
"""

import os
import sys
import hashlib

import fitz  # tak nazywa się biblioteka PyMuPDF po zaimportowaniu
import genanki
from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# USTAWIENIA - tu możesz później kręcić parametrami
# ---------------------------------------------------------------------------

MODEL = os.getenv("ANKI_MODEL", "claude-sonnet-5")   # model (GUI może nadpisać)
# Backend: "anthropic" (Claude API, płatne) lub "ollama" (lokalny model, ZA DARMO — dla siebie).
BACKEND = os.getenv("ANKI_BACKEND", "anthropic").lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")           # nazwa lokalnego modelu Ollamy
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # adres serwera Ollamy
# Tryb WIZJI: Claude widzi obraz strony (ryciny + OCR skanów) i sam oznacza, która karta dostaje rycinę.
TRYB_WIZJA = os.getenv("ANKI_WIZJA", "0") == "1"
ZNAKI_NA_CHUNK = 3500            # jak duże kawałki tekstu wysyłamy naraz
MIN_ZNAKOW_STRONY = 200          # strony krótsze niż to pomijamy (puste/okładki)
FISZEK_NA_PARTIE_RECENZJI = 50   # ile fiszek recenzent ogląda naraz

# Nazwa talii-rodzica (podtalie powstają jako "RODZIC::temat"). Nadpisywana z GUI/CLI.
TALIA_RODZIC = "Fiszki"

# Tryb treści: "ogolny" (dla każdego) lub "medycyna" (student medycyny). GUI może nadpisać.
TRYB = os.getenv("ANKI_TRYB", "ogolny")

# Język fiszek: "auto" (jak dokument) albo konkretny język (np. "polski", "angielski").
JEZYK_FISZEK = os.getenv("ANKI_JEZYK", "auto").strip().lower()

# Dyrektywa językowa — zależnie od wyboru: albo "jak materiał", albo wymuszony język.
if JEZYK_FISZEK and JEZYK_FISZEK != "auto":
    JEZYK_DYREKTYWA = (
        f"⚠️ ZASADA NADRZĘDNA — JĘZYK WYJŚCIA: Napisz KAŻDĄ fiszkę (pytanie, "
        f"odpowiedź, notatkę, temat) w języku: {JEZYK_FISZEK.upper()}. Jeśli materiał "
        f"źródłowy jest w innym języku — PRZETŁUMACZ treść na {JEZYK_FISZEK}. "
        f"Zachowaj oryginalne nazwy własne i terminy łacińskie. To nadrzędna zasada."
    )
    PRZYPOMNIENIE_JEZYK = (f"Napisz fiszki w języku: {JEZYK_FISZEK} "
                           f"(przetłumacz z języka materiału, jeśli trzeba).")
else:
    JEZYK_DYREKTYWA = (
        "⚠️ ZASADA NADRZĘDNA — JĘZYK WYJŚCIA: Najpierw rozpoznaj język MATERIAŁU "
        "źródłowego, a potem napisz KAŻDĄ fiszkę (pytanie, odpowiedź, notatkę, temat) "
        "DOKŁADNIE w tym samym języku. Materiał po angielsku → wszystko po angielsku; "
        "po niemiecku → po niemiecku itd. NIGDY nie tłumacz na inny język niż język "
        "materiału. Zachowaj oryginalną terminologię fachową i nazwy własne."
    )
    PRZYPOMNIENIE_JEZYK = ("Napisz fiszki w JĘZYKU poniższego materiału "
                           "(nie po polsku, jeśli materiał nie jest po polsku).")


# ---------------------------------------------------------------------------
# WSPÓLNE ZASADY FORMATOWANIA - wklejane do kilku promptów.
# ---------------------------------------------------------------------------

ZASADY_FORMATOWANIA = """ZASADY FORMATOWANIA (styl AnKing - dokładnie tak):
- NIE używaj znaków nowej linii w treści. Do przełamania wiersza użyj <br>.
- Pogrubienie: <b>tekst</b> (NIGDY gwiazdki). Kursywa: <i>tekst</i>. \
Podkreślenie mocnego akcentu: <u>tekst</u>. Drobne zastrzeżenie/wyjątek: \
<sup>tekst</sup>.
- Listy rób prawdziwym HTML: <ul><li>punkt</li><li>punkt</li></ul>, \
a wyliczenia kolejnością: 1. ...<br>2. ...<br>3. ...
- KLUCZOWE pojęcia zawsze WYRÓŻNIAJ: pogrubione ORAZ kolorowe, wzorem:
  <span style="color: rgb(255, 85, 0);"><b>termin</b></span>
  Używaj TYLKO tej palety (kopiuj kody kolorów dokładnie):
    - pomarańczowy: rgb(255, 85, 0)
    - zielony:      rgb(0, 170, 127)
    - różowy:       rgb(170, 0, 127)
    - czerwony:     rgb(170, 0, 0)
    - fioletowy:    rgb(170, 0, 255)
    - niebieski:    #007bff
  Koloruj pojedyncze najważniejsze terminy (jak w podręczniku), \
NIE całe zdania. W pytaniu pogrubiaj (i zwykle koloruj) termin, którego dotyczy.
- Matematyka inline: \\( a^2+b^2=c^2 \\). Matematyka blokowa: \\[ ... \\].
- Chemia (MathJax): \\( \\ce{C6H12O6 + 6O2 -> 6H2O + 6CO2} \\)."""


# Dodatek trybu MEDYCZNEGO — włączany tylko gdy TRYB == "medycyna".
# Uniwersalny (nie tylko genetyka) — pasuje do każdej dziedziny medycyny.
DODATEK_MEDYCZNY = """TRYB MEDYCZNY — celuj w poziom egzaminacyjny (materiał kliniczny).
Priorytetowo twórz fiszki o:
- skojarzeniach CHOROBA ↔ przyczyna / gen / patogen,
- skojarzeniach CHOROBA ↔ LEK / leczenie (lek z wyboru, drugi rzut) oraz o OPORNOŚCIACH \
i działaniach niepożądanych,
- KRYTERIACH diagnostycznych i charakterystycznych objawach/cechach,
- MECHANIZMACH (czynniki zjadliwości, patofizjologia) — co robią i jak,
- charakterystycznej DIAGNOSTYCE (badania, wyniki, testy swoiste vs nieswoiste),
- istotnych WARTOŚCIACH, skalach, dawkach, epidemiologii.
Gdy materiał dotyczy patogenu/choroby, ZAWSZE dodaj karty o LECZENIU i OPORNOŚCI, jeśli \
są istotne. Konkret egzaminacyjny (nazwy, leki, wartości, kryteria), nie ogólniki."""


def _dodatek_trybu():
    """Zwraca dodatek medyczny, gdy tryb = medycyna; inaczej nic."""
    return ("\n\n" + DODATEK_MEDYCZNY) if TRYB == "medycyna" else ""


# Instrukcja przypisania tematu - doklejana na końcu promptów generujących.
INSTRUKCJA_TEMATU = (
    "\n\nPodaj też pole 'temat': krótka (2–4 słowa) nazwa tematu tego fragmentu, "
    "w JĘZYKU materiału (np. rozdział/zagadnienie). Gdy fragment jest ogólny — "
    "użyj sensownej ogólnej nazwy."
)

# Instrukcja pola 'notatka' (kontekst) - doklejana na końcu promptów.
INSTRUKCJA_NOTATKI = (
    "\n\nKażda fiszka ma też pole 'notatka': KRÓTKI (1 zdanie) kontekst w JĘZYKU "
    "materiału, wyjaśniający czego fiszka dotyczy — dodawaj GO TYLKO, gdy fiszka jest "
    "szczegółowa lub bez kontekstu byłaby myląca. Gdy fiszka jest jasna sama w sobie, "
    "zostaw notatkę PUSTĄ (\"\"). Notatka może używać formatowania HTML."
)


# ---------------------------------------------------------------------------
# PROMPTY - instrukcje dla Claude. To jest serce jakości.
# ---------------------------------------------------------------------------

PROMPT_SYSTEMOWY = ("""Jesteś światowej klasy twórcą fiszek Anki. """ + JEZYK_DYREKTYWA + """

ZASADY DOBREJ FISZKI:
1. Zidentyfikuj kluczowe pojęcia, fakty, definicje i zależności (w tym równania/wzory).
2. Uzupełnij własną wiedzą tak, aby każda fiszka była samowystarczalna.
3. Rób fiszki pytanie-odpowiedź; zachowaj kolejność jak w materiale.
4. Jedna fiszka = JEDNA rzecz. Wolę WIĘCEJ prostych fiszek niż jedną przeładowaną.
5. Nie pomijaj istotnych zagadnień, ale patrz niżej, czego NIE robić.

CZEGO NIE ROBIĆ (unikaj przeszczegółowienia):
- NIE rób fiszek o detalach ilustracyjnych przykładu/rysunku/zdjęcia (kolor na obrazie, \
numer slajdu, z jakiej próbki, w jakiej technice). To nie jest wiedza do zapamiętania.
- Gdy przykład ilustruje pojęcie — pytaj o SAMO POJĘCIE, nie o detal przykładu.
- Wolę MNIEJ fiszek wartościowych niż dużo trywialnych. Fakty oczywiste pomiń.
- Przy matematyce/wyprowadzeniach: fiszki o WYNIKACH, definicjach i progach decyzyjnych, \
nie o każdym kroku algebry.""" + _dodatek_trybu() + """

""" + ZASADY_FORMATOWANIA + """

Zwróć listę fiszek. Każda fiszka ma pole 'pytanie' i 'odpowiedz'.""") \
    + INSTRUKCJA_TEMATU + INSTRUKCJA_NOTATKI


PROMPT_SYSTEMOWY_CLOZE = ("""Jesteś światowej klasy twórcą fiszek Anki typu CLOZE \
(luki do uzupełnienia). """ + JEZYK_DYREKTYWA + """

Każda fiszka to jedno zdanie/fakt, w którym KLUCZOWE pojęcie jest ukryte składnią \
Anki: {{c1::ukryty tekst}}. Przykład:
  Fotosynteza zachodzi w {{c1::chloroplastach}}.
Gdy chcesz ukryć kilka rzeczy niezależnie, użyj {{c1::...}}, {{c2::...}} itd. — ale \
nie przeładowuj jednej fiszki.

ZASADY:
1. Skupiaj się na konkretnych, testowalnych faktach; jedna fiszka = jedna rzecz.
2. Uzupełniaj własną wiedzą, aby fiszka była samowystarczalna; zachowaj kolejność.
3. Ukrywaj rzeczy WARTE zapamiętania (nazwy, wartości, mechanizmy), nie słowa nieistotne.
4. Unikaj przeszczegółowienia: pomijaj detale ilustracyjne i fakty trywialne; przy \
matematyce ukrywaj wyniki/definicje, nie każdy krok.""" + _dodatek_trybu() + """

""" + ZASADY_FORMATOWANIA + """

Zwróć listę fiszek. Każda fiszka ma jedno pole 'tekst' z lukami {{c1::...}}.""") \
    + INSTRUKCJA_TEMATU + INSTRUKCJA_NOTATKI


PROMPT_BAZA = ("""Jesteś ekspertem tworzącym fiszki Anki z BAZY PYTAŃ EGZAMINACYJNYCH. """
    + JEZYK_DYREKTYWA + """

Dostajesz surowy tekst z bazy pytań jednokrotnego wyboru (a/b/c/d). Tekst bywa \
zaszumiony: komentarze, oznaczenia typu „~sprawdzone~", uwagi, literówki. \
WAŻNE: baza MOŻE ZAWIERAĆ BŁĘDNE odpowiedzi.

DLA KAŻDEGO PYTANIA:
1. Ustal POPRAWNĄ odpowiedź WŁASNĄ WIEDZĄ. NIE ufaj ślepo zaznaczeniu — jeśli jest \
sprzeczne z aktualną wiedzą, użyj poprawnej odpowiedzi.
2. Zamień pytanie na czystą fiszkę:
   - 'pytanie': treść pytania jako jasne pytanie (BEZ wypisywania opcji a/b/c/d),
   - 'odpowiedz': POPRAWNA odpowiedź, zwięźle,
   - 'notatka': krótkie wyjaśnienie DLACZEGO ta odpowiedź; gdy pomocne, czemu \
popularny dystraktor jest błędny.
3. POMIJAJ: szum, komentarze, nagłówki, pytania niekompletne/uszkodzone.
4. Jedno pytanie = jedna zwięzła fiszka (nie mnóż bez potrzeby).

Bądź dokładny merytorycznie — to ma realnie przygotować do egzaminu.""" + _dodatek_trybu() + """

""" + ZASADY_FORMATOWANIA + """

Zwróć listę fiszek (pola: pytanie, odpowiedz, notatka).""")


PROMPT_RECENZENTA_QA = """Jesteś surowym recenzentem fiszek Anki dla studentów \
medycyny. Dostajesz ponumerowaną listę fiszek w formacie:
  ID. PYTANIE: ... || ODPOWIEDZ: ...

Twoje zadania:
- usuń duplikaty i fiszki niemal identyczne (zostaw jedną, najlepszą),
- usuń fiszki trywialne lub bez wartości,
- popraw błędy merytoryczne i językowe, zadbaj o zwięzłość,
- jeśli fiszka jest przeładowana, rozbij ją na kilka prostszych (użyj wtedy tego \
samego ID dla powstałych fiszek).

Nie dodawaj nowych tematów. Zachowaj zasady formatowania (HTML <b>/<i>/<br>, \
matematyka \\(..\\), kolory <span>).

Dla KAŻDEJ zachowanej fiszki zwróć jej ID, (ewentualnie poprawione) pytanie i \
odpowiedź oraz pole 'notatka' (zachowaj lub dodaj krótki kontekst, gdy fiszka jest \
szczegółowa; w innym wypadku ""). Zwróć tylko fiszki, które zostają."""


PROMPT_RECENZENTA_CLOZE = """Jesteś surowym recenzentem fiszek Anki typu CLOZE dla \
studentów medycyny. Dostajesz ponumerowaną listę fiszek w formacie:
  ID. TEKST: ... (z lukami {{c1::...}})

Twoje zadania:
- usuń duplikaty i fiszki niemal identyczne (zostaw jedną, najlepszą),
- usuń fiszki trywialne lub bez wartości,
- popraw błędy merytoryczne i językowe, zadbaj o zwięzłość,
- upewnij się, że luki {{c1::...}} ukrywają rzeczy warte zapamiętania,
- jeśli fiszka jest przeładowana, rozbij ją na kilka prostszych (użyj wtedy tego \
samego ID dla powstałych fiszek).

Nie dodawaj nowych tematów. Zachowaj składnię cloze {{c1::...}} i zasady \
formatowania (HTML, matematyka, kolory).

Dla KAŻDEJ zachowanej fiszki zwróć jej ID, (ewentualnie poprawiony) tekst oraz pole \
'notatka' (krótki kontekst gdy potrzebny; w innym wypadku ""). Zwróć tylko fiszki, \
które zostają."""


# ---------------------------------------------------------------------------
# KROK 0: Definicje "kształtu" fiszek (co Claude ma zwrócić).
# ---------------------------------------------------------------------------

class Fiszka(BaseModel):
    pytanie: str
    odpowiedz: str
    notatka: str          # krótki kontekst; pusty "" gdy niepotrzebny


class ListaFiszek(BaseModel):
    temat: str            # temat całego fragmentu (jeden z listy TEMATY)
    fiszki: list[Fiszka]


class FiszkaCloze(BaseModel):
    tekst: str
    notatka: str          # krótki kontekst; pusty "" gdy niepotrzebny


class ListaFiszekCloze(BaseModel):
    temat: str            # temat całego fragmentu (jeden z listy TEMATY)
    fiszki: list[FiszkaCloze]


class ListaFiszekProsta(BaseModel):
    # Bez pola 'temat' - używane w trybie bazy egzaminacyjnej (temat = stały).
    fiszki: list[Fiszka]


# Wersje z ID - używane przez recenzenta (ID pozwala z powrotem przypiąć obrazek).
class FiszkaQAId(BaseModel):
    id: int
    pytanie: str
    odpowiedz: str
    notatka: str


class ListaQAId(BaseModel):
    fiszki: list[FiszkaQAId]


class FiszkaClozeId(BaseModel):
    id: int
    tekst: str
    notatka: str


class ListaClozeId(BaseModel):
    fiszki: list[FiszkaClozeId]


# ---------------------------------------------------------------------------
# KROK 1: Czytanie PDF-a - tekst i obrazki dla każdej strony.
# ---------------------------------------------------------------------------

def wczytaj_pdf(sciezka, od=None, do=None, render_slajdy=False):
    """Zwraca listę stron: {numer, tekst, obrazki, render_png}.
    'od'/'do' (1-indeksowane, włącznie) ograniczają zakres stron.
    render_slajdy=True dorzuca zrzut CAŁEGO slajdu jako PNG (dla prezentacji)."""
    dokument = fitz.open(sciezka)
    strony = []

    for numer, strona in enumerate(dokument, start=1):
        if od is not None and numer < od:
            continue
        if do is not None and numer > do:
            break

        tekst = strona.get_text()

        obrazki = []
        for info in strona.get_images(full=True):
            xref = info[0]  # wewnętrzny identyfikator obrazka w PDF
            baza = fitz.Pixmap(dokument, xref)
            # PDF-y bywają w dziwnych formatach kolorów - normalizujemy do RGB
            if baza.n - baza.alpha >= 4:
                baza = fitz.Pixmap(fitz.csRGB, baza)
            obrazki.append(baza.tobytes("png"))

        # Zrzut całej strony (slajdu) jako obrazek - przydatne w prezentacjach.
        render_png = None
        if render_slajdy:
            piksmapa = strona.get_pixmap(dpi=150)
            render_png = piksmapa.tobytes("png")

        strony.append({
            "numer": numer, "tekst": tekst,
            "obrazki": obrazki, "render_png": render_png,
        })

    dokument.close()
    return strony


# ---------------------------------------------------------------------------
# KROK 1.5: Automatyczne wykrycie hierarchii (rozdział/podrozdział) po czcionce.
# ---------------------------------------------------------------------------

def _czysc_nazwe(t):
    """Czyści tytuł na potrzeby nazwy talii Anki ('::' to separator poziomów)."""
    return t.replace("::", " - ").strip().rstrip(":").strip()


def wykryj_mape_stron(sciezka):
    """Wykrywa hierarchię nagłówków po wielkości czcionki.
    Zwraca (mapa, ma_strukture): mapa[nr_strony] = 'Rozdział::Podrozdział'.
    Gdy dokument nie ma wyraźnych nagłówków, ma_strukture=False."""
    from collections import Counter
    doc = fitz.open(sciezka)

    # 1. Rozmiar tekstu podstawowego = najczęstszy.
    licz = Counter()
    for p in doc:
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip():
                        licz[round(s["size"])] += len(s["text"])
    if not licz:
        doc.close()
        return {}, False
    body = licz.most_common(1)[0][0]

    # 2. Kandydaci na nagłówki: pogrubione, większe niż body, krótkie linie.
    naglowki_raw = []
    rozm_count = Counter()
    for i, p in enumerate(doc, start=1):
        if i <= 2:
            continue  # pomijamy stronę tytułową
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                tekst = "".join(s["text"] for s in l.get("spans", [])).strip()
                if not tekst or len(tekst) > 90:
                    continue
                rozm = max((round(s["size"]) for s in l["spans"]), default=0)
                bold = any((s["flags"] & 16) or "bold" in s["font"].lower()
                           for s in l["spans"])
                if rozm > body and bold:
                    naglowki_raw.append((rozm, tekst, i))
                    rozm_count[rozm] += 1

    # 3. Poziomy = rozmiary nagłówków powtarzające się >=2 razy (max 3 poziomy).
    poziomy = sorted([r for r, c in rozm_count.items() if c >= 2], reverse=True)[:3]
    if not poziomy or len(naglowki_raw) < 3:
        doc.close()
        return {}, False
    rozm_na_poziom = {r: idx + 1 for idx, r in enumerate(poziomy)}

    naglowki = sorted(
        [(rozm_na_poziom[r], t, s) for r, t, s in naglowki_raw if r in rozm_na_poziom],
        key=lambda x: x[2],
    )
    liczba_stron = len(doc)
    doc.close()

    # 4. Każda strona dziedziczy aktualną ścieżkę nagłówków.
    mapa = {}
    biezacy = {1: None, 2: None, 3: None}
    idx = 0
    for strona in range(1, liczba_stron + 1):
        while idx < len(naglowki) and naglowki[idx][2] == strona:
            poz, tyt, _ = naglowki[idx]
            biezacy[poz] = tyt
            for glebiej in range(poz + 1, 4):
                biezacy[glebiej] = None
            idx += 1
        czesci = [biezacy[l] for l in (1, 2, 3) if biezacy[l]]
        mapa[strona] = "::".join(_czysc_nazwe(c) for c in czesci) if czesci else "Inne"
    return mapa, True


# ---------------------------------------------------------------------------
# KROK 2: Dzielenie tekstu na kawałki.
# ---------------------------------------------------------------------------

def wczytaj_docx(sciezka):
    """Czyta cały tekst z pliku .docx (akapity rozdzielone pustą linią)."""
    import docx
    d = docx.Document(sciezka)
    return "\n\n".join(p.text for p in d.paragraphs if p.text.strip())


def podziel_na_chunki(tekst, maks_znakow):
    """Dzieli tekst na kawałki po akapitach, tak by żaden nie był za duży."""
    akapity = [a.strip() for a in tekst.split("\n\n") if a.strip()]
    chunki = []
    biezacy = ""

    for akapit in akapity:
        if len(biezacy) + len(akapit) > maks_znakow and biezacy:
            chunki.append(biezacy)
            biezacy = akapit
        else:
            biezacy = (biezacy + "\n\n" + akapit).strip()

    if biezacy:
        chunki.append(biezacy)
    return chunki


# ---------------------------------------------------------------------------
# KROK 3: Generowanie fiszek przez Claude (osobno dla QA i dla cloze).
# ---------------------------------------------------------------------------

def popraw_temat(temat):
    """Czyści dowolny temat zwrócony przez model; pusty → 'Ogólne'."""
    t = (temat or "").replace("::", " - ").strip().rstrip(":").strip()
    return t if t else "Ogólne"


# --- Licznik zużycia API (żeby raportować, ile kosztuje generowanie) ---
ZUZYCIE = {"wejscie": 0, "wyjscie": 0, "zapytania": 0}
# Ceny za 1 mln tokenów (wejście, wyjście). Sonnet 5: cena promo do 31.08.2026.
CENY = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_cena_in, _cena_out = CENY.get(MODEL, (5.0, 25.0))
CENA_WEJSCIE = _cena_in / 1_000_000
CENA_WYJSCIE = _cena_out / 1_000_000
if BACKEND == "ollama":
    CENA_WEJSCIE = CENA_WYJSCIE = 0.0   # lokalny model Ollamy = za darmo


def dolicz_zuzycie(odpowiedz):
    """Dolicza tokeny z jednej odpowiedzi API do globalnego licznika."""
    u = getattr(odpowiedz, "usage", None)
    if u:
        ZUZYCIE["wejscie"] += getattr(u, "input_tokens", 0) or 0
        ZUZYCIE["wyjscie"] += getattr(u, "output_tokens", 0) or 0
        ZUZYCIE["zapytania"] += 1


def z_ponowieniem(wywolanie, opis, domyslne):
    """Uruchamia wywołanie API; przy błędzie ponawia raz, a potem pomija fragment.
    Dzięki temu JEDEN zepsuty fragment nie kładzie całego przebiegu."""
    for proba in range(2):
        try:
            return wywolanie()
        except Exception as e:
            if proba == 0:
                continue
            print(f"    (pominięto {opis} — błąd: {type(e).__name__})")
            return domyslne


# --- Backend OLLAMA (lokalny model, za darmo) -----------------------------
# Namiastka klienta Anthropic: ten sam interfejs `.messages.parse(...)`, więc
# cała reszta silnika działa bez zmian. Woła lokalny serwer Ollamy z JSON-schema.
class _OllamaUsage:
    def __init__(self, wej, wyj):
        self.input_tokens = wej
        self.output_tokens = wyj


class _OllamaOdpowiedz:
    def __init__(self, parsed, usage):
        self.parsed_output = parsed
        self.usage = usage


class _OllamaMessages:
    def parse(self, model=None, max_tokens=None, system=None, messages=None, output_format=None):
        import json
        import urllib.request
        wiad = ([{"role": "system", "content": system}] if system else []) + list(messages or [])
        payload = {
            "model": OLLAMA_MODEL,
            "messages": wiad,
            "format": output_format.model_json_schema(),   # structured output przez JSON-schema
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": max_tokens or 4096},
        }
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            dane = json.load(r)
        tekst = (dane.get("message") or {}).get("content", "")
        parsed = output_format.model_validate_json(tekst)
        usage = _OllamaUsage(dane.get("prompt_eval_count", 0), dane.get("eval_count", 0))
        return _OllamaOdpowiedz(parsed, usage)


class OllamaKlient:
    """Namiastka klienta dla lokalnego Ollama — ten sam interfejs co Anthropic()."""
    def __init__(self):
        self.messages = _OllamaMessages()


# --- TRYB WIZJI (Claude widzi obraz strony: ryciny + OCR skanów) -----------
class FiszkaWizja(BaseModel):
    pytanie: str
    odpowiedz: str
    notatka: str
    obrazek: bool          # True = karta dotyczy ryciny/diagramu widocznego na stronie


class ListaFiszekWizja(BaseModel):
    temat: str
    fiszki: list[FiszkaWizja]


PROMPT_SYSTEMOWY_WIZJA = PROMPT_SYSTEMOWY + """

=== TRYB WIZJI — WIDZISZ OBRAZ STRONY (tekst + ewentualne ryciny/diagramy/schematy) ===
- Jeśli TEKST strony jest pusty lub to skan — ODCZYTAJ treść z obrazu i na jej podstawie zrób fiszki.
- Dla KAŻDEJ karty ustaw pole `obrazek`: TRUE tylko gdy karta dotyczy ryciny/diagramu/schematu
  widocznego na stronie (wtedy dołączymy tę rycinę do karty). Karty czysto tekstowe: FALSE.
- Zwykle 0-2 karty na stronie mają obrazek=true (te o diagramie). Nie oznaczaj wszystkich.
- NIE rób fiszek o nieistotnych detalach ilustracji (kolor strzałki, numer figury, źródło ryciny)."""


def wygeneruj_fiszki_wizja(klient, tekst, obraz_png):
    """Fiszki QA z WIZJĄ: Claude widzi obraz strony (ryciny + OCR). Zwraca (pary, temat),
    gdzie pary = [(Fiszka, czy_dolaczyc_obrazek: bool)]."""
    import base64
    b64 = base64.standard_b64encode(obraz_png).decode("ascii")
    tresc = [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        {"type": "text", "text": f"{PRZYPOMNIENIE_JEZYK}\n\n"
         f"TEKST STRONY (może być pusty — wtedy czytaj z obrazu):\n{tekst}"},
    ]
    odpowiedz = klient.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=PROMPT_SYSTEMOWY_WIZJA,
        messages=[{"role": "user", "content": tresc}],
        output_format=ListaFiszekWizja,
    )
    dolicz_zuzycie(odpowiedz)
    w = odpowiedz.parsed_output
    pary = [(Fiszka(pytanie=f.pytanie, odpowiedz=f.odpowiedz, notatka=f.notatka), bool(f.obrazek))
            for f in w.fiszki]
    return pary, popraw_temat(w.temat)


def wygeneruj_fiszki(klient, tekst):
    """Zwykłe fiszki pytanie-odpowiedź. Zwraca (lista_fiszek, temat)."""
    odpowiedz = klient.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=PROMPT_SYSTEMOWY,
        messages=[{"role": "user", "content":
                   f"{PRZYPOMNIENIE_JEZYK}\n\nMATERIAŁ:\n{tekst}"}],
        output_format=ListaFiszek,
    )
    dolicz_zuzycie(odpowiedz)
    wynik = odpowiedz.parsed_output
    return wynik.fiszki, popraw_temat(wynik.temat)


def wygeneruj_fiszki_cloze(klient, tekst):
    """Fiszki z lukami {{c1::...}}. Zwraca (lista_fiszek, temat)."""
    odpowiedz = klient.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=PROMPT_SYSTEMOWY_CLOZE,
        messages=[{"role": "user", "content":
                   f"{PRZYPOMNIENIE_JEZYK}\n\nMATERIAŁ:\n{tekst}"}],
        output_format=ListaFiszekCloze,
    )
    dolicz_zuzycie(odpowiedz)
    wynik = odpowiedz.parsed_output
    return wynik.fiszki, popraw_temat(wynik.temat)


def wygeneruj_fiszki_baza(klient, tekst):
    """Tryb bazy egzaminacyjnej: MCQ → zweryfikowana fiszka. Zwraca listę fiszek."""
    odpowiedz = klient.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=PROMPT_BAZA,
        messages=[{"role": "user", "content":
                   f"{PRZYPOMNIENIE_JEZYK}\n\nFRAGMENT BAZY PYTAŃ:\n{tekst}"}],
        output_format=ListaFiszekProsta,
    )
    dolicz_zuzycie(odpowiedz)
    return odpowiedz.parsed_output.fiszki


def wygeneruj_fiszki_demo(tekst):
    """TRYB DEMO (QA) - bez API, za darmo. Zaślepki do testu importu."""
    fragment = tekst.strip().replace("\n", " ")
    skrot = (fragment[:200] + "...") if len(fragment) > 200 else fragment
    return [
        Fiszka(pytanie="[DEMO] O czym jest ten fragment?",
               odpowiedz=skrot, notatka=""),
        Fiszka(
            pytanie=(
                '[DEMO] Na jakie trzy typy dzielą się '
                '<span style="color: rgb(255, 85, 0);"><b>mutacje punktowe</b></span>?'
            ),
            odpowiedz=(
                '<ul>'
                '<li><span style="color: rgb(255, 85, 0);"><b>Substytucja</b></span> '
                '(podstawienie)</li>'
                '<li><span style="color: rgb(170, 0, 0);"><b>Delecja</b></span> '
                '(wypadnięcie)</li>'
                '<li><span style="color: #007bff;"><b>Insercja</b></span> '
                '(wstawienie)</li>'
                '</ul>'
            ),
            notatka="Dotyczy mutacji zmieniających pojedynczy nukleotyd (DNA).",
        ),
    ]


def wygeneruj_fiszki_cloze_demo(tekst):
    """TRYB DEMO (cloze) - bez API, za darmo."""
    return [
        FiszkaCloze(tekst="[DEMO] Fotosynteza zachodzi w {{c1::chloroplastach}}.",
                    notatka=""),
        FiszkaCloze(
            tekst=(
                "[DEMO] <b>Ważne:</b> wzór \\( a^2+b^2=c^2 \\) to "
                "{{c1::twierdzenie Pitagorasa}}."
            ),
            notatka="Zależność między bokami trójkąta prostokątnego.",
        ),
    ]


# ---------------------------------------------------------------------------
# KROK 3.5: Recenzent - czyści fiszki (usuwa duplikaty i słabe karty).
# ---------------------------------------------------------------------------

def usun_duplikaty(pary, klucz):
    """Lokalne (darmowe) usunięcie dokładnych duplikatów.
    'pary' to lista (fiszka, obrazek). 'klucz' wyciąga tekst do porównania."""
    widziane = set()
    wynik = []
    for para in pary:
        k = klucz(para[0]).strip().lower()
        if k and k not in widziane:
            widziane.add(k)
            wynik.append(para)
    return wynik


def zrecenzuj_qa(klient, pary):
    """Recenzja LLM dla fiszek QA. Zachowuje obrazek i temat przez system ID.
    'pary' to lista (Fiszka, obrazek, temat)."""
    zachowane = []
    for start in range(0, len(pary), FISZEK_NA_PARTIE_RECENZJI):
        partia = pary[start:start + FISZEK_NA_PARTIE_RECENZJI]
        linie = [
            f"{start + i}. PYTANIE: {f.pytanie} || ODPOWIEDZ: {f.odpowiedz} "
            f"|| NOTATKA: {f.notatka}"
            for i, (f, _obr, _tem, _zr) in enumerate(partia)
        ]
        print(f"  Recenzja fiszek {start + 1}-{start + len(partia)}...")
        try:
            wynik = klient.messages.parse(
                model=MODEL,
                max_tokens=16000,
                system=PROMPT_RECENZENTA_QA,
                messages=[{"role": "user", "content": "\n".join(linie)}],
                output_format=ListaQAId,
            )
            dolicz_zuzycie(wynik)
            for fo in wynik.parsed_output.fiszki:
                if 0 <= fo.id < len(pary):
                    _, obrazek, temat, zrodlo = pary[fo.id]
                else:
                    obrazek, temat, zrodlo = None, "Inne", ""
                zachowane.append((
                    Fiszka(pytanie=fo.pytanie, odpowiedz=fo.odpowiedz, notatka=fo.notatka),
                    obrazek, temat, zrodlo,
                ))
        except Exception as e:
            # Recenzja tej partii padła (np. brak kredytów) — ZACHOWUJEMY oryginalne
            # fiszki bez recenzji, żeby NIC nie przepadło.
            print(f"    ⚠️ Recenzja partii {start + 1}-{start + len(partia)} nie zadziałała "
                  f"({type(e).__name__}) — zachowuję te fiszki BEZ recenzji.")
            zachowane.extend(partia)
    return zachowane


def zrecenzuj_cloze(klient, pary):
    """Recenzja LLM dla fiszek cloze. Zachowuje obrazek i temat przez system ID."""
    zachowane = []
    for start in range(0, len(pary), FISZEK_NA_PARTIE_RECENZJI):
        partia = pary[start:start + FISZEK_NA_PARTIE_RECENZJI]
        linie = [
            f"{start + i}. TEKST: {f.tekst} || NOTATKA: {f.notatka}"
            for i, (f, _obr, _tem, _zr) in enumerate(partia)
        ]
        print(f"  Recenzja fiszek {start + 1}-{start + len(partia)}...")
        try:
            wynik = klient.messages.parse(
                model=MODEL,
                max_tokens=16000,
                system=PROMPT_RECENZENTA_CLOZE,
                messages=[{"role": "user", "content": "\n".join(linie)}],
                output_format=ListaClozeId,
            )
            dolicz_zuzycie(wynik)
            for fo in wynik.parsed_output.fiszki:
                if 0 <= fo.id < len(pary):
                    _, obrazek, temat, zrodlo = pary[fo.id]
                else:
                    obrazek, temat, zrodlo = None, "Inne", ""
                zachowane.append(
                    (FiszkaCloze(tekst=fo.tekst, notatka=fo.notatka), obrazek, temat, zrodlo)
                )
        except Exception as e:
            # Recenzja tej partii padła (np. brak kredytów) — ZACHOWUJEMY oryginalne
            # fiszki bez recenzji, żeby NIC nie przepadło.
            print(f"    ⚠️ Recenzja partii {start + 1}-{start + len(partia)} nie zadziałała "
                  f"({type(e).__name__}) — zachowuję te fiszki BEZ recenzji.")
            zachowane.extend(partia)
    return zachowane


# ---------------------------------------------------------------------------
# KROK 4 + 5: Budowanie talii Anki (osobne modele dla QA i cloze).
# ---------------------------------------------------------------------------

# Anki wymaga unikalnych, STAŁYCH numerów ID dla talii i typów kart.
ID_TALII = 1607392319
ID_MODELU = 1607392320
ID_TALII_CLOZE = 1607392321
ID_MODELU_CLOZE = 1607392322

# CSS w stylu AnKing: szeryfowa czcionka (Times New Roman), jasne tło,
# a w trybie nocnym Anki ciemne tło #272828 i prawie biały tekst - jak na
# Twoich fiszkach. Pogrubienia/kursywy/podkreślenia dziedziczą kolor pojęcia.
CSS_ANKING = """
.card {
  font-family: "Times New Roman", Georgia, serif;
  font-size: 22px;
  line-height: 1.5;
  text-align: center;
  color: black;
  background-color: #f3f1ef;
}
.nightMode.card, .night_mode .card {
  color: #FFFAFA !important;
  background-color: #272828 !important;
}
img { max-width: 85%; max-height: 100%; }
.obrazek { margin-top: 22px; }
b, i, u { color: inherit; }
#answer { margin: 14px 0; }
.cloze { font-weight: bold; color: rgb(255, 85, 0); }
.nightMode .cloze, .night_mode .cloze { color: rgb(255, 130, 60); }
.notatka {
  font-size: 0.82em; margin-top: 12px; padding-top: 8px;
  border-top: 1px dashed #bbb; text-align: left;
}
.notatka summary {
  cursor: pointer; font-weight: 600; color: #2a6fdb;
  list-style: none; user-select: none;
}
.notatka summary::-webkit-details-marker { display: none; }
.notatka-tresc { color: navy; font-style: italic; margin-top: 6px; }
.nightMode .notatka, .night_mode .notatka { border-top-color: #555; }
.nightMode .notatka summary, .night_mode .notatka summary { color: #6ea8fe; }
.nightMode .notatka-tresc, .night_mode .notatka-tresc { color: #9db4d0 !important; }
.zrodlo { font-size: 0.7em; color: #999; margin-top: 14px; }
.nightMode .zrodlo, .night_mode .zrodlo { color: #777 !important; }
"""

# Pola pokazujemy tylko, gdy niepuste (składnia Anki {{#Pole}}...{{/Pole}}).
# Notatka jest ROZWIJANA (<details>): schowana, otwiera się po kliknięciu.
NOTATKA_HTML = ('{{#Notatka}}<details class="notatka"><summary>📝 Notatka '
                '(kliknij)</summary><div class="notatka-tresc">{{Notatka}}</div>'
                '</details>{{/Notatka}}')
ZRODLO_HTML = '{{#Zrodlo}}<div class="zrodlo">📄 {{Zrodlo}}</div>{{/Zrodlo}}'
# Obrazek w kontenerze z odstępem od odpowiedzi (pokazywany tylko gdy istnieje).
OBRAZEK_HTML = '{{#Obrazek}}<div class="obrazek">{{Obrazek}}</div>{{/Obrazek}}'
DODATKI_HTML = OBRAZEK_HTML + NOTATKA_HTML + ZRODLO_HTML

MODEL_ANKI = genanki.Model(
    ID_MODELU,
    "Fiszka PL (AnKing-style)",
    fields=[{"name": "Pytanie"}, {"name": "Odpowiedz"}, {"name": "Obrazek"},
            {"name": "Notatka"}, {"name": "Zrodlo"}],
    templates=[
        {
            "name": "Karta 1",
            "qfmt": "{{Pytanie}}",
            "afmt": ('{{FrontSide}}<hr id="answer">{{Odpowiedz}}' + DODATKI_HTML),
        }
    ],
    css=CSS_ANKING,
)

MODEL_CLOZE = genanki.Model(
    ID_MODELU_CLOZE,
    "Cloze PL (AnKing-style)",
    model_type=genanki.Model.CLOZE,
    fields=[{"name": "Text"}, {"name": "Obrazek"},
            {"name": "Notatka"}, {"name": "Zrodlo"}],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": "{{cloze:Text}}" + DODATKI_HTML,
        }
    ],
    css=CSS_ANKING,
)


def id_talii(nazwa):
    """Stały (deterministyczny) numer ID talii na podstawie jej nazwy."""
    return int(hashlib.md5(nazwa.encode("utf-8")).hexdigest()[:12], 16)


def zbuduj_talie(fiszki_z_temat):
    """Buduje PODTALIE tematyczne dla fiszek QA.
    fiszki_z_temat: lista (Fiszka, obrazek, temat). Zwraca listę talii."""
    wg_tematu = {}
    for fiszka, nazwa_obrazka, temat, zrodlo in fiszki_z_temat:
        wg_tematu.setdefault(temat, []).append((fiszka, nazwa_obrazka, zrodlo))

    talie = []
    for temat, pozycje in wg_tematu.items():
        nazwa = f"{TALIA_RODZIC}::{temat}"
        talia = genanki.Deck(id_talii(nazwa), nazwa)
        for fiszka, nazwa_obrazka, zrodlo in pozycje:
            html_obrazka = f'<img src="{nazwa_obrazka}">' if nazwa_obrazka else ""
            talia.add_note(genanki.Note(
                model=MODEL_ANKI,
                fields=[fiszka.pytanie, fiszka.odpowiedz, html_obrazka,
                        fiszka.notatka, zrodlo],
            ))
        talie.append(talia)
    return talie


def zbuduj_talie_cloze(fiszki_z_temat):
    """Buduje PODTALIE tematyczne dla fiszek cloze. Zwraca listę talii."""
    wg_tematu = {}
    for fiszka, nazwa_obrazka, temat, zrodlo in fiszki_z_temat:
        wg_tematu.setdefault(temat, []).append((fiszka, nazwa_obrazka, zrodlo))

    talie = []
    for temat, pozycje in wg_tematu.items():
        nazwa = f"{TALIA_RODZIC}::{temat} (cloze)"
        talia = genanki.Deck(id_talii(nazwa), nazwa)
        for fiszka, nazwa_obrazka, zrodlo in pozycje:
            html_obrazka = f'<img src="{nazwa_obrazka}">' if nazwa_obrazka else ""
            talia.add_note(genanki.Note(
                model=MODEL_CLOZE,
                fields=[fiszka.tekst, html_obrazka, fiszka.notatka, zrodlo],
            ))
        talie.append(talia)
    return talie


# ---------------------------------------------------------------------------
# GŁÓWNA FUNKCJA - spina wszystkie kroki razem.
# ---------------------------------------------------------------------------

def main():
    global TALIA_RODZIC
    # Rozpoznajemy flagi i odfiltrowujemy je od nazwy pliku.
    flagi = {"--demo", "--cloze", "--recenzja", "--slajdy"}
    tryb_demo = "--demo" in sys.argv
    tryb_cloze = "--cloze" in sys.argv
    tryb_recenzja = "--recenzja" in sys.argv
    tryb_slajdy = "--slajdy" in sys.argv

    # Flagi z wartością: --strony 1-10 (lub =), --przedmiot "Nazwa" (lub =).
    od, do = None, None
    przedmiot = None
    argumenty = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a in flagi:
            i += 1
            continue
        if a == "--strony" or a.startswith("--strony="):
            zakres = a.split("=", 1)[1] if "=" in a else (
                args[i + 1] if i + 1 < len(args) else "")
            if "=" not in a:
                i += 1
            try:
                czesci = zakres.split("-")
                od = int(czesci[0])
                do = int(czesci[1]) if len(czesci) > 1 and czesci[1] else od
            except (ValueError, IndexError):
                print("Zły format --strony. Użyj np. --strony 1-10")
                sys.exit(1)
        elif a == "--przedmiot" or a.startswith("--przedmiot="):
            przedmiot = a.split("=", 1)[1] if "=" in a else (
                args[i + 1] if i + 1 < len(args) else "")
            if "=" not in a:
                i += 1
        else:
            argumenty.append(a)
        i += 1

    if len(argumenty) < 1:
        print("Użycie: python anki_generator.py <plik.pdf> "
              "[--przedmiot \"Nazwa\"] [--strony 1-10] [--cloze] [--recenzja] [--demo]")
        sys.exit(1)

    sciezka_pdf = argumenty[0]
    if not os.path.exists(sciezka_pdf):
        print(f"Nie znaleziono pliku: {sciezka_pdf}")
        sys.exit(1)

    # W trybie normalnym potrzebujemy klucza API. W demo - nie.
    klient = None
    if tryb_demo:
        print(">>> TRYB DEMO: bez API, fiszki są zaślepkami (za darmo). <<<")
    elif BACKEND == "ollama":
        print(f">>> TRYB OLLAMA: lokalny model '{OLLAMA_MODEL}' — ZA DARMO, bez API. <<<")
        print("    (wymaga uruchomionego Ollama: `ollama serve` + `ollama pull " + OLLAMA_MODEL + "`)")
        klient = OllamaKlient()
    else:
        load_dotenv()
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("Brak klucza API. Uzupełnij plik .env (patrz README.md).")
            print("Chcesz przetestować bez klucza? Dodaj --demo na końcu komendy.")
            sys.exit(1)
        klient = Anthropic()  # sam znajdzie klucz w ANTHROPIC_API_KEY

    tryb_opis = "CLOZE (luki)" if tryb_cloze else "pytanie-odpowiedź"
    print(f"Typ fiszek: {tryb_opis}")

    # Nazwa przedmiotu (talia-rodzic): z --przedmiot albo z nazwy pliku.
    TALIA_RODZIC = przedmiot or os.path.splitext(os.path.basename(sciezka_pdf))[0]
    print(f"Przedmiot (talia): {TALIA_RODZIC}")

    wszystkie_fiszki = []   # krotki (fiszka, obrazek, temat, zrodlo)
    pliki_multimedialne = []
    folder_obrazkow = "obrazki_tymczasowe"
    os.makedirs(folder_obrazkow, exist_ok=True)
    nazwa_zrodla = os.path.splitext(os.path.basename(sciezka_pdf))[0]

    jest_docx = sciezka_pdf.lower().endswith(".docx")
    mapa_struktury, ma_strukture = {}, False
    strony = []

    if jest_docx:
        # === TRYB BAZY EGZAMINACYJNEJ (.docx → fiszki z pytań MCQ) ===
        tryb_cloze = False  # baza = pytanie-odpowiedź
        temat_bazy = f"Baza egzaminacyjna — {nazwa_zrodla}"
        print("Tryb: BAZA EGZAMINACYJNA (.docx → fiszki z pytań, z weryfikacją odpowiedzi)")
        tekst_docx = wczytaj_docx(sciezka_pdf)
        chunki = podziel_na_chunki(tekst_docx, ZNAKI_NA_CHUNK)
        if od is not None:                       # --strony ogranicza tu ZAKRES FRAGMENTÓW
            chunki = chunki[od - 1:do]
            print(f"Zakres fragmentów: {od}-{do}")
        print(f"Fragmentów do przerobienia: {len(chunki)}")
        for idx, chunk in enumerate(chunki, start=1):
            print(f"  Fragment {idx}/{len(chunki)}...")
            if tryb_demo:
                fiszki = [Fiszka(pytanie="[DEMO baza] Przykładowe pytanie?",
                                 odpowiedz="Przykładowa odpowiedź", notatka="")]
            else:
                fiszki = z_ponowieniem(
                    lambda: wygeneruj_fiszki_baza(klient, chunk),
                    f"fragment {idx}", [])
            for fiszka in fiszki:
                wszystkie_fiszki.append((fiszka, None, temat_bazy, nazwa_zrodla))
    else:
        # === TRYB DOKUMENTU (PDF: struktura + strony) ===
        mapa_struktury, ma_strukture = wykryj_mape_stron(sciezka_pdf)
        if ma_strukture:
            print(f"Wykryto strukturę dokumentu: "
                  f"{len(set(mapa_struktury.values()))} rozdziałów/podrozdziałów.")
        else:
            print("Brak wyraźnej struktury — tematy przypisze Claude z listy.")
        if od is not None:
            print(f"Zakres stron: {od}-{do}")
        if tryb_slajdy:
            print("Tryb slajdów: do fiszek dołączę zrzut całego slajdu.")
        if TRYB_WIZJA:
            print("🔬 TRYB WIZJI: Claude widzi obrazy stron (ryciny + OCR skanów). "
                  "Droższy, ale dołącza właściwe diagramy do kart.")
        print(f"Czytam PDF: {sciezka_pdf}")
        # W trybie wizji renderujemy strony (Claude musi zobaczyć obraz strony).
        strony = wczytaj_pdf(sciezka_pdf, od=od, do=do,
                             render_slajdy=(tryb_slajdy or TRYB_WIZJA))

    for strona in strony:
        numer_strony = strona["numer"]
        tekst = strona["tekst"]
        render_png = strona.get("render_png")
        # Prawie puste strony pomijamy — CHYBA że tryb wizji (Claude odczyta treść z obrazu/skanu).
        if len(tekst) < MIN_ZNAKOW_STRONY and not (TRYB_WIZJA and render_png):
            continue

        # Obraz do PRZYPIĘCIA na karcie: preferuj czystą wbudowaną rycinę, potem zrzut strony.
        nazwa_obrazka = None
        do_wszystkich = False
        if tryb_slajdy and render_png:
            dane_png = render_png
            do_wszystkich = True
        elif strona["obrazki"]:
            dane_png = strona["obrazki"][0]
        elif TRYB_WIZJA and render_png:
            dane_png = render_png
        else:
            dane_png = None

        if dane_png is not None:
            skrot = hashlib.md5(dane_png).hexdigest()[:10]
            nazwa_obrazka = f"obrazek_{skrot}.png"
            sciezka_obrazka = os.path.join(folder_obrazkow, nazwa_obrazka)
            if not os.path.exists(sciezka_obrazka):
                with open(sciezka_obrazka, "wb") as f:
                    f.write(dane_png)
            if sciezka_obrazka not in pliki_multimedialne:
                pliki_multimedialne.append(sciezka_obrazka)

        # W trybie wizji dopuszczamy pusty tekst (skan) — jeden przebieg na samym obrazie.
        chunki_strony = (podziel_na_chunki(tekst, ZNAKI_NA_CHUNK)
                         or ([""] if (TRYB_WIZJA and render_png) else []))
        for chunk in chunki_strony:
            print(f"  Strona {numer_strony}: generuję fiszki...")
            flagi = None   # tryb wizji: lista bool (czy dana karta dostaje rycinę)
            if tryb_demo:
                fiszki, temat = (wygeneruj_fiszki_cloze_demo(chunk) if tryb_cloze
                                 else wygeneruj_fiszki_demo(chunk)), "Inne"
            elif TRYB_WIZJA and render_png and not tryb_cloze and BACKEND != "ollama":
                pary, temat = z_ponowieniem(
                    lambda: wygeneruj_fiszki_wizja(klient, chunk, render_png),
                    f"strona {numer_strony} (wizja)", ([], "Inne"))
                fiszki = [f for f, _ in pary]
                flagi = [fl for _, fl in pary]
            elif tryb_cloze:
                fiszki, temat = z_ponowieniem(
                    lambda: wygeneruj_fiszki_cloze(klient, chunk),
                    f"strona {numer_strony}", ([], "Inne"))
            else:
                fiszki, temat = z_ponowieniem(
                    lambda: wygeneruj_fiszki(klient, chunk),
                    f"strona {numer_strony}", ([], "Inne"))
            # Gdy dokument ma strukturę - temat = ścieżka rozdziału (nie z Claude).
            if ma_strukture:
                temat = mapa_struktury.get(numer_strony, "Inne")
            zrodlo = f"{nazwa_zrodla}, str. {numer_strony}"
            for i, fiszka in enumerate(fiszki):
                if flagi is not None:   # WIZJA: rycina tylko na kartach oznaczonych przez Claude
                    obrazek_dla_tej = nazwa_obrazka if (flagi[i] and nazwa_obrazka) else None
                elif do_wszystkich:
                    obrazek_dla_tej = nazwa_obrazka          # slajd do każdej fiszki
                else:
                    obrazek_dla_tej = nazwa_obrazka if i == 0 else None
                wszystkie_fiszki.append((fiszka, obrazek_dla_tej, temat, zrodlo))

    if not wszystkie_fiszki:
        print("Nie udało się wygenerować żadnych fiszek. Czy PDF ma tekst?")
        sys.exit(1)

    print(f"Wygenerowano: {len(wszystkie_fiszki)} fiszek.")

    # --- Recenzent: najpierw darmowe usunięcie dokładnych duplikatów... ---
    klucz = ((lambda f: f.tekst) if tryb_cloze else (lambda f: f.pytanie))
    przed = len(wszystkie_fiszki)
    wszystkie_fiszki = usun_duplikaty(wszystkie_fiszki, klucz)
    if len(wszystkie_fiszki) < przed:
        print(f"Usunięto {przed - len(wszystkie_fiszki)} dokładnych duplikatów.")

    # --- ...a potem (opcjonalnie) recenzja przez Claude. ---
    if tryb_recenzja:
        if tryb_demo:
            print("(Recenzja LLM pominięta w trybie demo — wymaga API.)")
        else:
            print("Recenzent czyści fiszki...")
            wszystkie_fiszki = (zrecenzuj_cloze(klient, wszystkie_fiszki)
                                if tryb_cloze
                                else zrecenzuj_qa(klient, wszystkie_fiszki))
            print(f"Po recenzji zostało {len(wszystkie_fiszki)} fiszek.")

    print("Zapisuję pliki...")
    nazwa_bazowa = os.path.splitext(os.path.basename(sciezka_pdf))[0]
    # Gdy podano zakres stron, dodaj go do nazwy - partie się nie nadpiszą.
    if od is not None:
        nazwa_bazowa = f"{nazwa_bazowa}_strony_{od}-{do}"
    if tryb_cloze:
        nazwa_bazowa += "_cloze"
    nazwa_talii = nazwa_bazowa

    # WYJŚCIE 1: plik .txt. Kolumna z tematem pozwala Anki utworzyć podtalie
    # przy imporcie (zaznacz "Deck" jako 2./3. pole).
    nazwa_txt = f"{nazwa_talii}.txt"
    with open(nazwa_txt, "w", encoding="utf-8") as f:
        for fiszka, _obr, temat, zrodlo in wszystkie_fiszki:
            nazwa_podtalii = f"{TALIA_RODZIC}::{temat}"
            notatka = fiszka.notatka.replace("\n", "<br>").strip()
            if tryb_cloze:
                t = fiszka.tekst.replace("\n", "<br>").strip()
                f.write(f"{t}|{notatka}|{zrodlo}|{nazwa_podtalii}\n")
            else:
                pyt = fiszka.pytanie.replace("\n", "<br>").strip()
                odp = fiszka.odpowiedz.replace("\n", "<br>").strip()
                f.write(f"{pyt}|{odp}|{notatka}|{zrodlo}|{nazwa_podtalii}\n")

    # WYJŚCIE 2: plik .apkg z PODTALIAMI tematycznymi (z obrazkami).
    if tryb_cloze:
        talie = zbuduj_talie_cloze(wszystkie_fiszki)
    else:
        talie = zbuduj_talie(wszystkie_fiszki)
    paczka = genanki.Package(talie)
    paczka.media_files = pliki_multimedialne
    nazwa_apkg = f"{nazwa_talii}.apkg"
    paczka.write_to_file(nazwa_apkg)

    # Podsumowanie: ile fiszek w każdym temacie.
    from collections import Counter
    licznik = Counter(temat for _f, _o, temat, _z in wszystkie_fiszki)
    print(f"\nSukces! {len(wszystkie_fiszki)} fiszek w {len(licznik)} podtaliach:")
    for temat, ile in sorted(licznik.items(), key=lambda x: -x[1]):
        print(f"  - {TALIA_RODZIC}::{temat}: {ile}")
    print(f"Pliki: {nazwa_txt}  oraz  {nazwa_apkg}")
    print("Zaimportuj .apkg w Anki: Plik -> Importuj (podtalie utworzą się same).")

    # Raport zużycia klucza API (koszt) — TYLKO dla właściciela (lokalnie).
    # W produkcji (ANKI_UKRYJ_KOSZT=1) NIE pokazujemy kosztów/tokenów użytkownikom.
    if not tryb_demo and ZUZYCIE["zapytania"] > 0 and os.getenv("ANKI_UKRYJ_KOSZT") != "1":
        koszt = ZUZYCIE["wejscie"] * CENA_WEJSCIE + ZUZYCIE["wyjscie"] * CENA_WYJSCIE
        print("\n--- ZUŻYCIE KLUCZA API (ten przebieg) ---")
        print(f"  Zapytań do Claude: {ZUZYCIE['zapytania']}")
        print(f"  Tokeny wejścia:  {ZUZYCIE['wejscie']:,}")
        print(f"  Tokeny wyjścia:  {ZUZYCIE['wyjscie']:,}")
        print(f"  Szacowany koszt: ${koszt:.3f} (model {MODEL})")


if __name__ == "__main__":
    main()
