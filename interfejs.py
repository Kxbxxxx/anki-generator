"""
Graficzny interfejs (GUI) do generatora fiszek Anki — wersja profesjonalna, PL/EN.

Uruchomienie:
    streamlit run interfejs.py

GUI jest "nakładką" na silnik anki_generator.py (wywołanie przez subprocess).
Wszystkie napisy interfejsu są w słowniku TEKSTY (pl/en) — łatwo dodać języki.
"""

import os
import re
import sys
import subprocess
import tempfile

import streamlit as st
import streamlit.components.v1 as components

# Na hostingu (Streamlit Cloud) sekrety wstrzykujemy do zmiennych środowiskowych,
# żeby czytał je zarówno ten plik (os.getenv), jak i silnik w podprocesie.
# Ustawiamy TYLKO gdy zmienna nie istnieje (setdefault) — lokalne env ma pierwszeństwo.
try:
    for _klucz_sekretu, _wartosc_sekretu in st.secrets.items():
        if isinstance(_wartosc_sekretu, str):
            os.environ.setdefault(_klucz_sekretu, _wartosc_sekretu)
except Exception:
    pass  # Brak pliku sekretów (np. lokalnie) — normalne, pomijamy.

MARKA = "CardForge"
KATALOG = os.path.dirname(os.path.abspath(__file__))

# --- TRYB PRODUKCJI / MODEL BIZNESOWY --------------------------------------
# Włączany zmienną środowiskową CARDFORGE_PROD=1 (na serwerze / Streamlit Cloud).
# Lokalnie u Ciebie = 0 → pełne opcje deweloperskie, brak płatności.
# W produkcji = 1 → schowany panel klucza/modelu, darmowa próbka + bramka płatności.
TRYB_PRODUKCJI = os.getenv("CARDFORGE_PROD", "0") == "1"
KURS_USD_PLN = 4.0        # przelicznik USD→PLN tylko do wyświetlania ceny
MARZA = 2.5               # cena = koszt_API × MARZA (~15 zł za rozdział ~30 stron, zdrowa marża)
PROG_OSTRZEZENIA = 60     # powyżej tylu stron/części pokazujemy ostrzeżenie „duży plik = drożej”
CENA_MIN_PLN = 5          # minimalna cena płatnego dokumentu (zł) = minimum PWYW na Gumroad
DARMOWE_JEDNOSTKI = 5     # dokument ≤ tyle stron/części = ZA DARMO (próbka)
LINK_PLATNOSCI = os.getenv("CARDFORGE_LINK", "")   # link do płatności za 1 dokument (Gumroad)
LINK_SUB = os.getenv("CARDFORGE_SUB_LINK", "")     # link do subskrypcji (Gumroad membership)
SUB_LIMIT_MIES = 20      # abonament: fair-use — ile dokumentów na miesiąc
try:
    SUB_CENA = int(os.getenv("CARDFORGE_SUB_CENA", "49"))   # cena abonamentu/mies. (do wyświetlenia)
except ValueError:
    SUB_CENA = 49

# --- ZABEZPIECZENIA (ochrona przed spalaniem Twojego API) ------------------
MAX_JEDNOSTKI = 400       # twardy limit rozmiaru 1 dokumentu (chroni przed gigantem)
DARMOWE_NA_SESJE = 2      # ile darmowych próbek na jedną sesję przeglądarki
LIMIT_DARMOWYCH_DZIENNIE = 15   # globalny limit darmowych próbek na dobę (wszyscy razem)
LICZNIK_PLIK = os.path.join(KATALOG, ".licznik_darmowych.json")
EMAILE_PLIK = os.path.join(KATALOG, ".darmowe_emaile.json")   # e-maile, które użyły darmowej próbki
UZYTE_KODY_PLIK = os.path.join(KATALOG, ".uzyte_kody.json")   # license keys już wykorzystane (jednorazowość)
ABONENCI_PLIK = os.path.join(KATALOG, ".abonenci_zuzycie.json")   # zużycie abonentów (fair-use/miesiąc)

# --- TŁUMACZENIA INTERFEJSU ------------------------------------------------
TEKSTY = {
    "pl": {
        "title": f"{MARKA} — fiszki z Twojego skryptu i bazy pytań",
        "slogan": "Twój skrypt i baza pytań → gotowe fiszki Anki. "
                  "To, czego nie ma w gotowych deckach.",
        "trust_line": "🩺 Zrobione przez studenta medycyny — na materiał, którego "
                      "AnKing i inne decki nie mają (Twoje skrypty, wykłady, bazy pytań).",
        "chips": ["📚 Z Twojego skryptu", "📝 Baza pytań → fiszki",
                  "🎨 Styl AnKing", "🩺 Od studenta medycyny"],
        "settings": "Ustawienia",
        "language": "Język / Language",
        "api_key": "Klucz API",
        "api_help": "Zaczyna się od sk-ant-… Puste = użyje zapisanego klucza.",
        "model": "Jakość",
        "model_help": "Standard: szybki i tańszy. Pro: najwyższa jakość (droższy).",
        "model_cheap": "⚡ Standard",
        "model_best": "💎 Pro",
        "mode": "Tryb treści",
        "mode_help": "Ogólny = dowolny przedmiot. Medycyna = nacisk na fakty "
                     "egzaminacyjne (choroba↔gen/lek, leczenie, oporność, mechanizmy).",
        "mode_general": "Ogólny",
        "mode_med": "Medycyna",
        "lang_cards": "Język fiszek",
        "lang_cards_help": "Auto = w języku dokumentu. Możesz też wymusić język "
                           "(program przetłumaczy fiszki).",
        "lang_auto": "Auto (jak dokument)",
        "cost_note": "💡 Generowanie płatne jest z Twojego klucza (od zużycia). "
                     "Tryb demo jest darmowy.",
        "upload_hint": "Wgraj swój skrypt/wykład (PDF) albo bazę pytań (.docx) — "
                       "materiał, którego nie znajdziesz w gotowych deckach. "
                       "Program sam wykryje strukturę i tematy.",
        "subject": "Nazwa przedmiotu (talia)",
        "subject_ph": "np. Mikrobiologia",
        "recenzja": "Recenzent", "recenzja_help": "Usuwa duplikaty i słabe fiszki.",
        "cloze": "Fiszki cloze", "cloze_help": "Luki {{c1::…}}.",
        "slajdy": "Zrzuty slajdów", "slajdy_help": "Dla prezentacji: slajd jako obrazek.",
        "zakres": "Zakres stron / fragmentów (opcjonalnie)",
        "zakres_ph": "np. 1-20  (puste = całość)",
        "demo": "🆓 Tryb demo — za darmo, bez kosztu (zaślepki do testu)",
        "generate": "🚀 Generuj fiszki",
        "err_file": "Najpierw wgraj dokument (PDF lub .docx).",
        "err_key": "Podaj klucz API w panelu bocznym (albo zaznacz tryb demo).",
        "status_run": "Generuję fiszki…", "status_done": "Gotowe ✅",
        "status_err": "Błąd generowania",
        "err_generic": "Coś poszło nie tak. Zajrzyj do logu poniżej.",
        "created": "Utworzono **{n}** fiszek{koszt}. Pobierz i zaimportuj w Anki.",
        "cost_word": " · koszt ${c}",
        "show_log": "Pokaż pełny log",
        "preview_title": "👀 Podgląd fiszek",
        "preview_hint": "Kliknij kartę, aby odwrócić (przód → tył)",
        "try_example": "🧪 Wypróbuj na przykładzie",
        "example_title": "👀 Przykładowe fiszki (E. coli) — za darmo",
        "advanced": "⚙️ Opcje zaawansowane",
        "edit_title": "✏️ Edytuj karty przed pobraniem",
        "edit_hint": "Popraw treść w tabeli, usuwaj słabe wiersze (zaznacz + Delete). "
                     "Potem zbuduj zaktualizowany plik — za darmo, bez API.",
        "rebuild_btn": "🔧 Zbuduj zaktualizowany .apkg",
        "rebuild_done": "⬇️  Pobierz zaktualizowany .apkg",
        "estimate": "≈ {n} części do przerobienia · szacowany koszt ≈ **${c}** "
                    "(przybliżony, faktyczny może się różnić)",
        "price_free": "🎁 Ten dokument jest **za darmo** — próbka (do {n0} stron). "
                      "Kliknij „Generuj fiszki”.",
        "price_paid": "🔒 Twój dokument: **{n} stron/części** → cena **{cena} zł**. "
                      "Odblokuj, aby wygenerować wszystkie fiszki.",
        "pay_button": "💳 Zapłać {cena} zł i odbierz kod",
        "code_label": "🔑 Kod dostępu",
        "code_help": "Wklej kod, który dostajesz po opłacie.",
        "code_bad": "❌ Nieprawidłowy kod. Sprawdź go albo opłać dostęp powyżej.",
        "code_ok": "✅ Odblokowane! Możesz generować.",
        "locked_stop": "Dokument płatny — wpisz poprawny kod dostępu "
                       "(albo wgraj mniejszy plik, który jest za darmo).",
        "prod_note": "🎁 Mały dokument = za darmo. Większy = drobna opłata "
                     "(płacisz raz, za swój plik).",
        "too_large_warn": "⚠️ Duży dokument (**{n}** stron) — cena rośnie z rozmiarem. "
                          "Taniej: wgraj jeden rozdział/temat albo użyj „Zakres stron” "
                          "w Opcjach zaawansowanych.",
        "too_big": "Dokument jest bardzo duży (**{n}** części, limit {maks}). "
                   "Podziel go na mniejsze pliki albo użyj „Zakres stron” "
                   "w opcjach zaawansowanych.",
        "free_used_session": "Wykorzystałeś darmowe próbki w tej sesji 🙂 "
                             "Kup dostęp powyżej, aby generować dalej.",
        "free_used_today": "Darmowe próbki na dziś się wyczerpały. "
                           "Wróć jutro albo kup dostęp powyżej.",
        "email_label": "📧 Twój e-mail (żeby odebrać darmową próbkę)",
        "email_help": "Jedna darmowa próbka na e-mail — potem płatne. Nie wysyłamy spamu.",
        "email_bad": "Podaj poprawny adres e-mail, żeby odebrać darmową próbkę.",
        "email_used": "Ten e-mail już wykorzystał swoją jedną darmową próbkę 🙂 "
                      "Kup dostęp powyżej, aby generować dalej.",
        "sub_expander": "💎 Mam abonament CardForge (wpisz kod)",
        "sub_code_label": "🔑 Kod abonamentu",
        "sub_help": "Kod z Twojej subskrypcji — dostajesz go po wykupieniu abonamentu.",
        "sub_active": "💎 Abonament aktywny! Wykorzystano **{uzyte}/{limit}** dokumentów "
                      "w tym miesiącu. Generuj bez opłaty.",
        "sub_limit": "💎 Wyczerpałeś limit **{limit}** dokumentów w tym miesiącu. "
                     "Kup pojedynczy dokument albo poczekaj do nowego miesiąca.",
        "sub_bad": "❌ Nieprawidłowy lub nieaktywny kod abonamentu.",
        "sub_buy": "💎 Wykup abonament — {cena} zł/mies. (do {limit} dokumentów)",
        "sub_generate_note": "💎 Abonament aktywny — generujesz w ramach abonamentu "
                             "(bez dodatkowej opłaty).",
        "footer": f"{MARKA} · fiszki Anki z każdego dokumentu",
    },
    "en": {
        "title": f"{MARKA} — flashcards from your notes & question banks",
        "slogan": "Your lecture notes and question banks → ready Anki flashcards. "
                  "The stuff that isn't in premade decks.",
        "trust_line": "🩺 Built by a med student — for material AnKing and other decks "
                      "don't cover (your notes, lectures, question banks).",
        "chips": ["📚 From your notes", "📝 Question bank → cards",
                  "🎨 AnKing style", "🩺 By a med student"],
        "settings": "Settings",
        "language": "Language / Język",
        "api_key": "API key",
        "api_help": "Starts with sk-ant-… Leave empty to use the saved key.",
        "model": "Quality",
        "model_help": "Standard: fast and cheaper. Pro: top quality (pricier).",
        "model_cheap": "⚡ Standard",
        "model_best": "💎 Pro",
        "mode": "Content mode",
        "mode_help": "General = any subject. Medicine = focus on exam facts "
                     "(disease↔gene/drug, treatment, resistance, mechanisms).",
        "mode_general": "General",
        "mode_med": "Medicine",
        "lang_cards": "Flashcard language",
        "lang_cards_help": "Auto = document language. You can also force a language "
                           "(the app will translate the cards).",
        "lang_auto": "Auto (match document)",
        "cost_note": "💡 Generation is billed from your key (pay per use). "
                     "Demo mode is free.",
        "upload_hint": "Upload your notes/lecture (PDF) or a question bank (.docx) — "
                       "the material you won't find in premade decks. "
                       "The app detects structure and topics automatically.",
        "subject": "Subject name (deck)",
        "subject_ph": "e.g. Microbiology",
        "recenzja": "Reviewer", "recenzja_help": "Removes duplicates and weak cards.",
        "cloze": "Cloze cards", "cloze_help": "Blanks {{c1::…}}.",
        "slajdy": "Slide snapshots", "slajdy_help": "For slides: whole slide as an image.",
        "zakres": "Page / fragment range (optional)",
        "zakres_ph": "e.g. 1-20  (empty = whole file)",
        "demo": "🆓 Demo mode — free, no cost (placeholder cards for testing)",
        "generate": "🚀 Generate flashcards",
        "err_file": "Please upload a document first (PDF or .docx).",
        "err_key": "Enter your API key in the sidebar (or tick demo mode).",
        "status_run": "Generating flashcards…", "status_done": "Done ✅",
        "status_err": "Generation error",
        "err_generic": "Something went wrong. Check the log below.",
        "created": "Created **{n}** flashcards{koszt}. Download and import into Anki.",
        "cost_word": " · cost ${c}",
        "show_log": "Show full log",
        "preview_title": "👀 Flashcard preview",
        "preview_hint": "Click a card to flip (front → back)",
        "try_example": "🧪 Try an example",
        "example_title": "👀 Example flashcards (E. coli) — free",
        "advanced": "⚙️ Advanced options",
        "edit_title": "✏️ Edit cards before download",
        "edit_hint": "Edit content in the table, delete weak rows (select + Delete). "
                     "Then build the updated file — free, no API.",
        "rebuild_btn": "🔧 Build updated .apkg",
        "rebuild_done": "⬇️  Download updated .apkg",
        "estimate": "≈ {n} parts to process · estimated cost ≈ **${c}** "
                    "(approximate, actual may vary)",
        "price_free": "🎁 This document is **free** — a sample (up to {n0} pages). "
                      "Click “Generate flashcards”.",
        "price_paid": "🔒 Your document: **{n} pages/parts** → price **{cena} zł**. "
                      "Unlock to generate all flashcards.",
        "pay_button": "💳 Pay {cena} zł and get a code",
        "code_label": "🔑 Access code",
        "code_help": "Paste the code you receive after payment.",
        "code_bad": "❌ Invalid code. Check it or pay for access above.",
        "code_ok": "✅ Unlocked! You can generate now.",
        "locked_stop": "Paid document — enter a valid access code "
                       "(or upload a smaller file, which is free).",
        "prod_note": "🎁 Small document = free. Larger = a small one-off fee "
                     "(you pay once, for your file).",
        "too_large_warn": "⚠️ Large document (**{n}** pages) — price grows with size. "
                          "Cheaper: upload one chapter/topic or use “Page range” "
                          "in advanced options.",
        "too_big": "This document is very large (**{n}** parts, limit {maks}). "
                   "Split it into smaller files or use the “Page range” "
                   "option under advanced.",
        "free_used_session": "You've used your free samples in this session 🙂 "
                             "Buy access above to keep generating.",
        "free_used_today": "Free samples for today are used up. "
                           "Come back tomorrow or buy access above.",
        "email_label": "📧 Your email (to claim the free sample)",
        "email_help": "One free sample per email — then it's paid. No spam.",
        "email_bad": "Enter a valid email to claim the free sample.",
        "email_used": "This email already used its one free sample 🙂 "
                      "Buy access above to keep generating.",
        "sub_expander": "💎 I have a CardForge subscription (enter code)",
        "sub_code_label": "🔑 Subscription code",
        "sub_help": "The code from your subscription — you get it after subscribing.",
        "sub_active": "💎 Subscription active! Used **{uzyte}/{limit}** documents "
                      "this month. Generate at no extra cost.",
        "sub_limit": "💎 You've used your **{limit}** documents this month. "
                     "Buy a single document or wait for the new month.",
        "sub_bad": "❌ Invalid or inactive subscription code.",
        "sub_buy": "💎 Subscribe — {cena} zł/month (up to {limit} documents)",
        "sub_generate_note": "💎 Subscription active — generating within your plan "
                             "(no extra charge).",
        "footer": f"{MARKA} · Anki flashcards from any document",
    },
}

st.set_page_config(page_title=MARKA, page_icon="⚡", layout="centered",
                   initial_sidebar_state="collapsed" if TRYB_PRODUKCJI else "expanded")

# Wybór języka INTERFEJSU — WIDOCZNY na górze strony (nie chowa się w panelu bocznym).
_kol_puste, _kol_jezyk = st.columns([3, 1])
jezyk = _kol_jezyk.selectbox("Język / Language", ["Polski", "English"],
                             label_visibility="collapsed")
L = "en" if jezyk == "English" else "pl"
t = TEKSTY[L]


# --- STYL (ukrycie chromu Streamlit + własny wygląd) ----------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
#MainMenu {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}
footer {visibility: hidden;}
[data-testid="stToolbar"] {display: none;}
.stDeployButton, [data-testid="stAppDeployButton"] {display: none;}
html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
.block-container { padding-top: 2.2rem; max-width: 780px; }
.hero { text-align: center; margin: 0 0 1.6rem; }
.hero h1 {
  font-size: 3rem; font-weight: 800; letter-spacing: -1.5px; margin: 0;
  background: linear-gradient(100deg, #818cf8 0%, #6366f1 45%, #a855f7 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.hero p { color: #9aa3b2; font-size: 1.08rem; margin: .5rem 0 0; }
.chips { display: flex; gap: .5rem; justify-content: center; flex-wrap: wrap; margin: 1rem 0 .2rem; }
.chip { background: #151a24; border: 1px solid #262d3a; color: #c7cdd8;
  padding: .32rem .8rem; border-radius: 999px; font-size: .82rem; font-weight: 500; }
.panel-hint { color:#7b8494; font-size:.9rem; margin:-.4rem 0 1rem; }
.stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 600; border: none; }
div[data-testid="stFileUploader"] { border-radius: 12px; }
.foot { text-align:center; color:#5b6472; font-size:.8rem; margin-top:2.5rem;
        border-top:1px solid #1c2230; padding-top:1rem; }
</style>
""", unsafe_allow_html=True)


# --- HERO ------------------------------------------------------------------
chipy = "".join(f'<span class="chip">{c}</span>' for c in t["chips"])
st.markdown(f"""
<div class="hero">
  <h1>⚡ {MARKA}</h1>
  <p>{t["slogan"]}</p>
  <div class="chips">{chipy}</div>
  <p style="color:#7b8494;font-size:.88rem;margin:.9rem auto 0;max-width:560px;">{t["trust_line"]}</p>
</div>
""", unsafe_allow_html=True)


# --- USTAWIENIA ------------------------------------------------------------
# Wszystko WIDOCZNE dla użytkownika na głównej stronie (język, tryb, jakość).
# Ukryty jest TYLKO klucz API — w produkcji siedzi bezpiecznie na serwerze.
JEZYKI_FISZEK = {
    t["lang_auto"]: "auto", "Polski": "polski", "English": "English",
    "Deutsch": "Deutsch", "Español": "Español", "Français": "Français",
    "Italiano": "Italiano", "Українська": "Ukrainian",
}
if TRYB_PRODUKCJI:
    # Produkcja: klucz API schowany na serwerze (sekrety). Reszta widoczna niżej.
    klucz = ""
else:
    # Lokalnie (dev): klucz + notka o koszcie w panelu bocznym.
    with st.sidebar:
        st.markdown(f"### ⚡ {MARKA}")
        st.caption(t["settings"])
        klucz = st.text_input(t["api_key"], type="password", help=t["api_help"],
                              placeholder="sk-ant-…")
        st.divider()
        st.caption(t["cost_note"])


# --- WYCENA / BRAMKA PŁATNOŚCI (funkcje pomocnicze) ------------------------
def szacuj_koszt(plik, model, recenzja):
    """Zwraca (liczba_części, koszt_usd) — przybliżony koszt generowania."""
    try:
        dane = plik.getvalue()
        if plik.name.lower().endswith(".pdf"):
            import fitz
            d = fitz.open(stream=dane, filetype="pdf")
            jednostki = sum(1 for i in range(len(d))
                            if len(d[i].get_text().strip()) > 200)
            d.close()
        else:
            import io
            import docx
            d = docx.Document(io.BytesIO(dane))
            znaki = sum(len(p.text) for p in d.paragraphs)
            jednostki = max(1, znaki // 3500)
    except Exception:
        return None
    if jednostki <= 0:
        return None
    na_jednostke = 0.12 if "opus" in model else 0.035     # rząd wielkości z danych
    koszt = jednostki * na_jednostke * (1.4 if recenzja else 1.0)
    return jednostki, koszt


def oblicz_cene(koszt_usd):
    """Cena dla użytkownika (zł) = koszt API × marża, min. CENA_MIN_PLN."""
    cena = koszt_usd * KURS_USD_PLN * MARZA
    return max(CENA_MIN_PLN, round(cena))


def _uzyte_kody():
    """Zbiór license keys już wykorzystanych (jeden kod = jeden dokument)."""
    import json
    try:
        return set(json.load(open(UZYTE_KODY_PLIK, encoding="utf-8")))
    except Exception:
        return set()


def zapisz_uzyty_kod(kod):
    """Oznacza license key jako wykorzystany (na zawsze)."""
    import json
    uzyte = _uzyte_kody()
    uzyte.add((kod or "").strip())
    try:
        json.dump(sorted(uzyte), open(UZYTE_KODY_PLIK, "w", encoding="utf-8"))
    except Exception:
        pass


def _gumroad_verify(kod, product_id):
    """Zwraca dict 'purchase' z Gumroada jeśli license key ważny dla product_id, inaczej None."""
    if not (kod and product_id):
        return None
    try:
        import json
        import urllib.request
        import urllib.parse
        dane = urllib.parse.urlencode({
            "product_id": product_id,
            "license_key": kod,
            "increment_uses_count": "false",   # nie zużywamy licznika Gumroada — pilnujemy sami
        }).encode()
        req = urllib.request.Request(
            "https://api.gumroad.com/v2/licenses/verify", data=dane)
        with urllib.request.urlopen(req, timeout=10) as odp:
            wynik = json.load(odp)
        if wynik.get("success"):
            return wynik.get("purchase", {}) or {}
    except Exception:
        pass
    return None   # błąd/nieznany kod = None (traktujemy jako nieważny — bezpiecznie)


def _kod_zweryfikowany(kod):
    """True, jeśli kod to ważny kod testowy (CARDFORGE_KODY) LUB license key z Gumroada (1 dokument)."""
    wazne = [k.strip() for k in os.getenv("CARDFORGE_KODY", "").split(",") if k.strip()]
    if kod in wazne:
        return True
    zakup = _gumroad_verify(kod, os.getenv("GUMROAD_PRODUCT_ID", "").strip())
    if zakup is None:
        return False
    if zakup.get("refunded") or zakup.get("chargebacked") or zakup.get("disputed"):
        return False   # zwrot/reklamacja → kod nieważny
    return True


def subskrypcja_aktywna(kod):
    """True, jeśli kod to license key AKTYWNEJ subskrypcji (Gumroad membership)."""
    kod = (kod or "").strip()
    if not kod:
        return False
    testowe = [k.strip() for k in os.getenv("CARDFORGE_SUB_KODY", "").split(",") if k.strip()]
    if kod in testowe:
        return True
    zakup = _gumroad_verify(kod, os.getenv("GUMROAD_SUB_PRODUCT_ID", "").strip())
    if zakup is None:
        return False
    # Subskrypcja nieaktywna, jeśli anulowana / zakończona / nieudana płatność / zwrot.
    for pole in ("subscription_cancelled_at", "subscription_ended_at",
                 "subscription_failed_at", "refunded", "chargebacked", "disputed"):
        if zakup.get(pole):
            return False
    return True


def _abonenci_dane():
    import json
    try:
        return json.load(open(ABONENCI_PLIK, encoding="utf-8"))
    except Exception:
        return {}


def zuzycie_abonenta(kod):
    """Ile dokumentów wygenerował ten abonament w BIEŻĄCYM miesiącu."""
    import datetime
    miesiac = datetime.date.today().strftime("%Y-%m")
    return _abonenci_dane().get(f"{miesiac}|{(kod or '').strip()}", 0)


def dolicz_abonenta(kod):
    """Zwiększa licznik dokumentów abonenta w bieżącym miesiącu (fair-use)."""
    import json
    import datetime
    d = _abonenci_dane()
    miesiac = datetime.date.today().strftime("%Y-%m")
    klucz = f"{miesiac}|{(kod or '').strip()}"
    d[klucz] = d.get(klucz, 0) + 1
    try:
        json.dump(d, open(ABONENCI_PLIK, "w", encoding="utf-8"))
    except Exception:
        pass


def kod_wazny(kod):
    """Czy kod odblokowuje płatny dokument. License key jest JEDNORAZOWY (raz użyty = nieważny).
    Sprawdza kody testowe (CARDFORGE_KODY) oraz prawdziwe license keys z Gumroada."""
    kod = (kod or "").strip()
    if not kod:
        return False
    if kod in _uzyte_kody():                 # już wykorzystany — jednorazowość
        return False
    cache = st.session_state.setdefault("_ok_kody", set())
    if kod in cache:                         # zweryfikowany w tej sesji → nie wołaj API znów
        return True
    if _kod_zweryfikowany(kod):
        cache.add(kod)
        return True
    return False


def _licznik_dzis():
    """Wczytuje globalny licznik darmowych próbek na dziś (plik JSON)."""
    import json
    import datetime
    try:
        d = json.load(open(LICZNIK_PLIK, encoding="utf-8"))
    except Exception:
        d = {}
    if d.get("data") != datetime.date.today().isoformat():
        d = {"data": datetime.date.today().isoformat(), "darmowe": 0}
    return d


def darmowe_dzis():
    """Ile darmowych próbek wygenerowano dziś (globalnie)."""
    return _licznik_dzis().get("darmowe", 0)


def dolicz_darmowe():
    """Zwiększa globalny licznik darmowych próbek na dziś."""
    import json
    d = _licznik_dzis()
    d["darmowe"] = d.get("darmowe", 0) + 1
    try:
        json.dump(d, open(LICZNIK_PLIK, "w", encoding="utf-8"))
    except Exception:
        pass


def _uzyte_emaile():
    """Zbiór e-maili, które już wykorzystały darmową próbkę."""
    import json
    try:
        return set(json.load(open(EMAILE_PLIK, encoding="utf-8")))
    except Exception:
        return set()


def email_uzyl_darmo(email):
    """Czy ten e-mail już odebrał swoją jedną darmową próbkę."""
    return email in _uzyte_emaile()


def zapisz_email_darmo(email):
    """Zapisuje e-mail jako taki, który wykorzystał darmową próbkę (na zawsze)."""
    import json
    uzyte = _uzyte_emaile()
    uzyte.add(email)
    try:
        json.dump(sorted(uzyte), open(EMAILE_PLIK, "w", encoding="utf-8"))
    except Exception:
        pass


def email_ok(email):
    """Podstawowa walidacja formatu e-maila."""
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", (email or "").strip()))


# --- FORMULARZ -------------------------------------------------------------
plik = st.file_uploader("upload", type=["pdf", "docx"], label_visibility="collapsed")
st.markdown(f'<div class="panel-hint">{t["upload_hint"]}</div>', unsafe_allow_html=True)
if TRYB_PRODUKCJI:
    st.info(t["prod_note"])

przedmiot = st.text_input(t["subject"], placeholder=t["subject_ph"])

# USTAWIENIA WIDOCZNE dla użytkownika: język fiszek, tryb treści, jakość.
_c1, _c2 = st.columns(2)
jezyk_label = _c1.selectbox(t["lang_cards"], list(JEZYKI_FISZEK.keys()),
                            help=t["lang_cards_help"])
ANKI_JEZYK = JEZYKI_FISZEK[jezyk_label]
tryb_wybor = _c2.selectbox(t["mode"], [t["mode_general"], t["mode_med"]], help=t["mode_help"])
TRYB = "medycyna" if tryb_wybor == t["mode_med"] else "ogolny"
model_wybor = st.radio(t["model"], [t["model_cheap"], t["model_best"]],
                       help=t["model_help"], horizontal=True)
MODEL = "claude-sonnet-5" if model_wybor == t["model_cheap"] else "claude-opus-4-8"

opt_recenzja = st.checkbox(t["recenzja"], value=True, help=t["recenzja_help"])

with st.expander(t["advanced"]):
    ac1, ac2 = st.columns(2)
    opt_cloze = ac1.checkbox(t["cloze"], help=t["cloze_help"])
    opt_slajdy = ac2.checkbox(t["slajdy"], help=t["slajdy_help"])
    zakres = st.text_input(t["zakres"], placeholder=t["zakres_ph"])
    opt_demo = False if TRYB_PRODUKCJI else st.checkbox(t["demo"])

# --- ABONAMENT (subskrypcja) — kod abonenta odblokowuje generowanie bez opłaty ---
subskrybent = False
sub_kod_aktywny = ""
if TRYB_PRODUKCJI:
    with st.expander(t["sub_expander"]):
        _sub_kod = st.text_input(t["sub_code_label"], help=t["sub_help"], key="sub_kod_in")
        if _sub_kod.strip():
            _cache_sub = st.session_state.setdefault("_ok_sub", set())
            _aktywny = _sub_kod.strip() in _cache_sub or subskrypcja_aktywna(_sub_kod)
            if _aktywny:
                _cache_sub.add(_sub_kod.strip())
                _uzyte = zuzycie_abonenta(_sub_kod)
                if _uzyte < SUB_LIMIT_MIES:
                    subskrybent = True
                    sub_kod_aktywny = _sub_kod.strip()
                    st.success(t["sub_active"].format(uzyte=_uzyte, limit=SUB_LIMIT_MIES))
                else:
                    st.warning(t["sub_limit"].format(limit=SUB_LIMIT_MIES))
            else:
                st.warning(t["sub_bad"])
        if LINK_SUB:
            st.markdown(f"[{t['sub_buy'].format(cena=SUB_CENA, limit=SUB_LIMIT_MIES)}]({LINK_SUB})")


# WYCENA + BRAMKA — liczymy rozmiar dokumentu i decydujemy: darmowe czy płatne.
szac = None
darmowy = True
cena_pln = 0
odblokowane = True   # lokalnie zawsze odblokowane; w produkcji zależy od kodu
email_darmo = ""     # e-mail do odebrania darmowej próbki (tylko produkcja)
kod = ""             # license key / kod dostępu (płatny dokument, tylko produkcja)

if plik is not None and not opt_demo:
    szac = szacuj_koszt(plik, MODEL, opt_recenzja)

if szac:
    jednostki, koszt_usd = szac
    darmowy = jednostki <= DARMOWE_JEDNOSTKI
    # Cena zależna od ROZMIARU i MODELU (szacuj_koszt liczy oba) × marża.
    cena_pln = oblicz_cene(koszt_usd)
    if TRYB_PRODUKCJI and jednostki > PROG_OSTRZEZENIA:
        st.warning(t["too_large_warn"].format(n=jednostki))
    if subskrybent:
        st.success(t["sub_generate_note"])
    elif not TRYB_PRODUKCJI:
        # Tryb lokalny/deweloperski: pokaż tylko szacowany koszt API (jak dotąd).
        st.caption(t["estimate"].format(n=jednostki, c=f"{koszt_usd:.2f}"))
    elif darmowy:
        st.success(t["price_free"].format(n0=DARMOWE_JEDNOSTKI))
        email_darmo = st.text_input(t["email_label"], help=t["email_help"],
                                    placeholder="ty@student.pl")
    else:
        st.warning(t["price_paid"].format(n=jednostki, cena=cena_pln))
        if LINK_PLATNOSCI:
            # Doklejamy wyliczoną cenę do linku — Gumroad (PWYW) podpowie tę kwotę.
            sep = "&" if "?" in LINK_PLATNOSCI else "?"
            link_z_cena = f"{LINK_PLATNOSCI}{sep}price={cena_pln}"
            st.link_button(t["pay_button"].format(cena=cena_pln), link_z_cena,
                           use_container_width=True)
        kod = st.text_input(t["code_label"], help=t["code_help"])
        odblokowane = kod_wazny(kod)
        if kod and not odblokowane:
            st.error(t["code_bad"])
        elif odblokowane:
            st.success(t["code_ok"])

col_gen, col_ex = st.columns([3, 1])
generuj = col_gen.button(t["generate"], type="primary", use_container_width=True)
if col_ex.button(t["try_example"], use_container_width=True):
    st.session_state["pokaz_przyklad"] = True


# --- URUCHOMIENIE ----------------------------------------------------------
CSS_PODGLAD = """
<style>
 * { box-sizing: border-box; }
 body { margin:0; background:transparent; font-family:'Times New Roman',Georgia,serif; }
 .hint { color:#8b93a7; font-size:13px; text-align:center; margin:0 0 12px;
         font-family:-apple-system,sans-serif; }
 .grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
 @media (max-width:640px){ .grid{grid-template-columns:1fr;} }
 .card { background:#272828; color:#FFFAFA; border:1px solid #333a48;
   border-radius:14px; padding:20px; cursor:pointer; font-size:16px; line-height:1.55;
   transition:border-color .15s, transform .05s; }
 .card:hover { border-color:#6366f1; }
 .card:active { transform:scale(.995); }
 .card b,.card i,.card u { color:inherit; }
 .card ul { text-align:left; display:inline-block; margin:6px 0; }
 .card > input { display:none; }
 .card .a { display:none; margin-top:14px; }
 .card > input:checked ~ .a { display:block; }
 .card hr { border:none; border-top:1px solid #4a5163; margin:0 0 12px; }
 .note { font-size:.85em; color:#9db4d0; border-top:1px dashed #555; margin-top:12px;
         padding-top:8px; font-style:italic; text-align:left; }
 .src { font-size:.72em; color:#6b7280; margin-top:10px; text-align:left; }
</style>
"""


def zbuduj_podglad(txt_path, tryb_cloze, teksty, limit=8):
    """Buduje HTML podglądu kart (styl Anki, klik = obrót) z pliku .txt."""
    try:
        linie = [l.rstrip("\n") for l in open(txt_path, encoding="utf-8") if l.strip()]
    except OSError:
        return None
    karty = []
    for l in linie[:limit]:
        cz = l.split("|")
        if tryb_cloze:
            tekst = cz[0] if cz else ""
            notatka = cz[1] if len(cz) > 1 else ""
            zrodlo = cz[2] if len(cz) > 2 else ""
            front = re.sub(r"\{\{c\d+::(.*?)\}\}", "[…]", tekst)
            back = re.sub(r"\{\{c\d+::(.*?)\}\}", r"<b>\1</b>", tekst)
        else:
            front = cz[0] if cz else ""
            back = cz[1] if len(cz) > 1 else ""
            notatka = cz[2] if len(cz) > 2 else ""
            zrodlo = cz[3] if len(cz) > 3 else ""
        extra = ""
        if notatka.strip():
            extra += f'<div class="note">📝 {notatka}</div>'
        if zrodlo.strip():
            extra += f'<div class="src">📄 {zrodlo}</div>'
        karty.append(
            '<label class="card"><input type="checkbox">'
            f'<div class="q">{front}</div>'
            f'<div class="a"><hr>{back}{extra}</div></label>'
        )
    if not karty:
        return None
    return (CSS_PODGLAD + f'<div class="hint">{teksty["preview_hint"]}</div>'
            '<div class="grid">' + "".join(karty) + "</div>")


def wczytaj_karty_df(txt_path, tryb_cloze):
    """Wczytuje wygenerowane fiszki z .txt do edytowalnej tabeli (DataFrame)."""
    import pandas as pd
    rows = []
    try:
        for l in open(txt_path, encoding="utf-8"):
            l = l.rstrip("\n")
            if not l.strip():
                continue
            cz = l.split("|")
            if tryb_cloze:
                rows.append({"Tekst": cz[0] if len(cz) > 0 else "",
                             "Notatka": cz[1] if len(cz) > 1 else "",
                             "Źródło": cz[2] if len(cz) > 2 else "",
                             "Talia": cz[3] if len(cz) > 3 else "Fiszki"})
            else:
                rows.append({"Pytanie": cz[0] if len(cz) > 0 else "",
                             "Odpowiedź": cz[1] if len(cz) > 1 else "",
                             "Notatka": cz[2] if len(cz) > 2 else "",
                             "Źródło": cz[3] if len(cz) > 3 else "",
                             "Talia": cz[4] if len(cz) > 4 else "Fiszki"})
    except OSError:
        pass
    return pd.DataFrame(rows)


def przebuduj_apkg(df, tryb_cloze):
    """Buduje .apkg z EDYTOWANYCH kart (bez API). Zwraca ścieżkę lub None."""
    import genanki
    from anki_generator import MODEL_ANKI, MODEL_CLOZE, id_talii
    wg = {}
    for _, r in df.iterrows():
        talia = str(r.get("Talia") or "Fiszki").strip() or "Fiszki"
        wg.setdefault(talia, []).append(r)
    talie = []
    for nazwa_t, rr in wg.items():
        d = genanki.Deck(id_talii(nazwa_t), nazwa_t)
        for r in rr:
            if tryb_cloze:
                tekst = str(r.get("Tekst", "")).strip()
                if not tekst:
                    continue
                d.add_note(genanki.Note(model=MODEL_CLOZE, fields=[
                    tekst, "", str(r.get("Notatka", "")), str(r.get("Źródło", ""))]))
            else:
                pyt = str(r.get("Pytanie", "")).strip()
                if not pyt:
                    continue
                d.add_note(genanki.Note(model=MODEL_ANKI, fields=[
                    pyt, str(r.get("Odpowiedź", "")), "",
                    str(r.get("Notatka", "")), str(r.get("Źródło", ""))]))
        if d.notes:
            talie.append(d)
    if not talie:
        return None
    out = os.path.join(tempfile.gettempdir(), "edytowane_fiszki.apkg")
    genanki.Package(talie).write_to_file(out)
    return out


def zbuduj_komende(sciezka_pliku, recenzja):
    cmd = [sys.executable, "-u", os.path.join(KATALOG, "anki_generator.py"), sciezka_pliku]
    if przedmiot.strip():
        cmd += ["--przedmiot", przedmiot.strip()]
    if zakres.strip():
        cmd += ["--strony", zakres.strip()]
    if opt_cloze:
        cmd.append("--cloze")
    if recenzja:
        cmd.append("--recenzja")
    if opt_slajdy:
        cmd.append("--slajdy")
    if opt_demo:
        cmd.append("--demo")
    return cmd


if generuj:
    if plik is None:
        st.error(t["err_file"]); st.stop()
    # OCHRONA 1 — limit rozmiaru: żaden pojedynczy dokument nie spali fortuny.
    if szac and szac[0] > MAX_JEDNOSTKI:
        st.error(t["too_big"].format(n=szac[0], maks=MAX_JEDNOSTKI)); st.stop()
    # OCHRONA 2 — bramka płatności (produkcja): płatny dokument wymaga kodu.
    # Abonent (subskrybent) omija — generuje w ramach abonamentu.
    if TRYB_PRODUKCJI and szac and not darmowy and not odblokowane and not subskrybent:
        st.error(t["locked_stop"]); st.stop()
    # OCHRONA 3 — limity darmowych próbek (produkcja): anty-spam Twojego API.
    # Abonent omija (płaci abonamentem, nie potrzebuje darmowej próbki/e-maila).
    if TRYB_PRODUKCJI and szac and darmowy and not subskrybent:
        # 3a. Bramka e-mail: 1 darmowa próbka na e-mail (na zawsze).
        email_norm = (email_darmo or "").strip().lower()
        if not email_ok(email_norm):
            st.warning(t["email_bad"]); st.stop()
        if email_uzyl_darmo(email_norm):
            st.warning(t["email_used"]); st.stop()
        # 3b. Backstopy globalne (nawet gdyby ktoś podmieniał e-maile).
        if st.session_state.get("darmowe_uzyte", 0) >= DARMOWE_NA_SESJE:
            st.warning(t["free_used_session"]); st.stop()
        if darmowe_dzis() >= LIMIT_DARMOWYCH_DZIENNIE:
            st.warning(t["free_used_today"]); st.stop()
    # Klucz API: w produkcji jest na serwerze (env), więc user go nie podaje.
    if not TRYB_PRODUKCJI and not opt_demo and not klucz \
            and not os.path.exists(os.path.join(KATALOG, ".env")):
        st.error(t["err_key"]); st.stop()

    rozszerzenie = os.path.splitext(plik.name)[1]
    bezpieczna_nazwa = re.sub(r"[^\w\- .]", "_", os.path.splitext(plik.name)[0])
    sciezka_pliku = os.path.join(tempfile.gettempdir(), bezpieczna_nazwa + rozszerzenie)
    with open(sciezka_pliku, "wb") as f:
        f.write(plik.getbuffer())

    # Standard wymuszamy dla DARMOWEJ próbki i dla ABONENTA (ochrona kosztu — abonament
    # jest „prawie nieograniczony"). Płatne pojedyncze dokumenty respektują wybór (cena rośnie).
    model_efektywny = ("claude-sonnet-5"
                       if (TRYB_PRODUKCJI and (subskrybent or (szac and darmowy)))
                       else MODEL)

    env = os.environ.copy()
    env["ANKI_MODEL"] = model_efektywny
    env["ANKI_TRYB"] = TRYB
    env["ANKI_JEZYK"] = ANKI_JEZYK
    if klucz:
        env["ANTHROPIC_API_KEY"] = klucz

    # Darmowa próbka w produkcji → BEZ recenzenta (tańsza dla Ciebie).
    recenzja_efektywna = opt_recenzja and not (TRYB_PRODUKCJI and szac and darmowy)

    okno_log = st.empty()
    linie = []
    proc = subprocess.Popen(zbuduj_komende(sciezka_pliku, recenzja_efektywna),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            cwd=KATALOG, env=env)
    with st.status(t["status_run"], expanded=True) as status:
        for linia in proc.stdout:
            linie.append(linia.rstrip())
            okno_log.code("\n".join(linie[-18:]))
        proc.wait()
        status.update(label=t["status_done"] if proc.returncode == 0 else t["status_err"],
                      state="complete" if proc.returncode == 0 else "error")

    pelny_log = "\n".join(linie)
    if proc.returncode != 0:
        st.error(t["err_generic"]); st.code(pelny_log); st.stop()

    # Udana DARMOWA próbka → dolicz do limitów + zapisz e-mail (1 darmowa/e-mail).
    if TRYB_PRODUKCJI and szac and darmowy and not subskrybent:
        st.session_state["darmowe_uzyte"] = st.session_state.get("darmowe_uzyte", 0) + 1
        dolicz_darmowe()
        zapisz_email_darmo((email_darmo or "").strip().lower())

    # Udany dokument ABONENTA → dolicz do jego miesięcznego limitu (fair-use).
    if TRYB_PRODUKCJI and subskrybent and sub_kod_aktywny:
        dolicz_abonenta(sub_kod_aktywny)

    # Udany PŁATNY dokument → oznacz license key jako wykorzystany (jednorazowość).
    # Kody testowe (CARDFORGE_KODY) NIE są zużywane — zostają wielorazowe dla właściciela.
    if TRYB_PRODUKCJI and szac and not darmowy and not subskrybent and kod.strip():
        _testowe = [k.strip() for k in os.getenv("CARDFORGE_KODY", "").split(",") if k.strip()]
        if kod.strip() not in _testowe:
            zapisz_uzyty_kod(kod)

    pliki_wynikowe = []
    for l in linie:
        if l.startswith("Pliki:"):
            for kawalek in l.replace("Pliki:", "").split("  oraz  "):
                if kawalek.strip():
                    pliki_wynikowe.append(os.path.join(KATALOG, kawalek.strip()))

    m_licz = re.search(r"Sukces! (\d+) fiszek", pelny_log)
    m_koszt = re.search(r"Szacowany koszt: \$([\d.]+)", pelny_log)
    koszt = t["cost_word"].format(c=m_koszt.group(1)) if m_koszt else ""
    st.success(t["created"].format(n=m_licz.group(1) if m_licz else "?", koszt=koszt))

    # PODGLĄD KART — zobacz zanim pobierzesz.
    txt_path = next((p for p in pliki_wynikowe if p.endswith(".txt")), None)
    if txt_path and os.path.exists(txt_path):
        podglad = zbuduj_podglad(txt_path, opt_cloze, t)
        if podglad:
            st.markdown(f"#### {t['preview_title']}")
            components.html(podglad, height=560, scrolling=True)
        # Zapamiętaj karty do edycji (tabela pojawi się niżej).
        st.session_state["edit_txt"] = txt_path
        st.session_state["edit_cloze"] = opt_cloze
        st.session_state.pop("df_karty", None)

    for sciezka in pliki_wynikowe:
        if os.path.exists(sciezka):
            with open(sciezka, "rb") as f:
                st.download_button(f"⬇️  {os.path.basename(sciezka)}", data=f.read(),
                                   file_name=os.path.basename(sciezka),
                                   use_container_width=True)

    with st.expander(t["show_log"]):
        st.code(pelny_log)


# PRZYKŁAD — gotowe, prawdziwe fiszki bez kosztu (pokazuje jakość od razu).
if st.session_state.get("pokaz_przyklad") and not generuj:
    st.markdown(f"#### {t['example_title']}")
    ex_txt = os.path.join(KATALOG, "przyklady", "przyklad_fiszki.txt")
    podglad_ex = zbuduj_podglad(ex_txt, False, t)
    if podglad_ex:
        components.html(podglad_ex, height=560, scrolling=True)
    ex_apkg = os.path.join(KATALOG, "przyklady", "przyklad_fiszki.apkg")
    if os.path.exists(ex_apkg):
        with open(ex_apkg, "rb") as f:
            st.download_button("⬇️  przyklad_fiszki.apkg", f.read(),
                               "przyklad_fiszki.apkg", use_container_width=True)


# EDYCJA KART — edytowalna tabela + przebudowa .apkg bez API.
if st.session_state.get("edit_txt") and os.path.exists(st.session_state["edit_txt"]):
    st.markdown(f"#### {t['edit_title']}")
    st.caption(t["edit_hint"])
    if "df_karty" not in st.session_state:
        st.session_state["df_karty"] = wczytaj_karty_df(
            st.session_state["edit_txt"], st.session_state.get("edit_cloze", False))
    edited_df = st.data_editor(st.session_state["df_karty"], num_rows="dynamic",
                               use_container_width=True, key="edytor_kart", height=360)
    if st.button(t["rebuild_btn"], use_container_width=True):
        out = przebuduj_apkg(edited_df, st.session_state.get("edit_cloze", False))
        if out and os.path.exists(out):
            with open(out, "rb") as f:
                st.download_button(t["rebuild_done"], f.read(),
                                   os.path.basename(out), use_container_width=True)


st.markdown(f'<div class="foot">{t["footer"]}</div>', unsafe_allow_html=True)
