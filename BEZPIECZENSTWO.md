# 🛡️ CardForge — Bezpieczeństwo i wdrożenie (czytaj uważnie)

Ten plik to Twoja lista kroków, żeby **nikt nie mógł Cię okraść na kasę**.
Zrobione są już zabezpieczenia w kodzie. Poniżej to, co musisz zrobić **Ty sam** —
zajmuje ~20 minut i jest darmowe.

---

## 🔴 KROK 1 (NAJWAŻNIEJSZY) — Twardy limit wydatków w Anthropic

To jest Twoja **żelazna podłoga**: cokolwiek się stanie, nie stracisz więcej niż ten limit.

1. Wejdź na **console.anthropic.com** → zaloguj się.
2. Menu **Settings** → **Limits** (albo **Billing → Usage limits**).
3. Ustaw **miesięczny limit wydatków**, np. **$10-15** (ok. 40-60 zł).
4. Zapisz.

➡️ Po przekroczeniu limitu API **po prostu przestaje działać** — nie mogą Cię obciążyć więcej.
**To jest to zabezpieczenie, które gwarantuje, że nie stracisz oszczędności.**

Sprawdzaj czasem zakładkę **Usage** — widzisz na bieżąco, ile wydałeś.

> 💡 **Zasada:** na start trzymaj limit NISKO (bo to faza ryzyka — testujesz).
> Gdy zaczną wpływać prawdziwe płatności, **podnoś limit stopniowo** — bo wtedy koszt API
> jest już pokryty przez to, co zapłacili userzy. Limit ma zawsze być mniej-więcej na
> poziomie „ile jestem gotów stracić w najgorszym miesiącu”, a nie hamować zarabiania.

---

## 🟠 KROK 2 — Hosting (darmowy) + klucz schowany na serwerze

1. Załóż konto na **share.streamlit.io** (Streamlit Community Cloud) — logowanie przez GitHub.
2. Wrzuć folder `anki-generator` na **GitHub** (repozytorium może być prywatne).
   - ⚠️ **Plik `.env` NIE MOŻE trafić na GitHub.** Chroni Cię przed tym `.gitignore` (już dodany).
     Zanim wrzucisz — upewnij się, że `.env` nie jest na liście plików do wysłania.
3. W Streamlit Cloud kliknij **New app** → wskaż repo → plik `interfejs.py` → **Deploy**.
4. W ustawieniach aplikacji → **Settings → Secrets** wklej (to jest bezpieczne miejsce na klucz):

   ```
   ANTHROPIC_API_KEY = "sk-ant-…twój-klucz…"
   CARDFORGE_PROD = "1"
   CARDFORGE_KODY = "KOD-ABC-111, KOD-DEF-222, KOD-GHI-333"
   CARDFORGE_LINK = "https://twój-link-do-płatności"
   ```

➡️ Klucz siedzi **tylko na serwerze**. User w przeglądarce **nigdy go nie zobaczy**.

---

## 🟡 KROK 3 — Płatności (Gumroad, darmowe założenie)

1. Załóż konto na **gumroad.com**.
2. Stwórz produkt(y), np. progi wg wielkości:
   - „CardForge — do 60 stron” = 29 zł
   - „CardForge — do 150 stron” = 69 zł
3. Ustaw, żeby po zakupie kupujący dostał **kod** (na start możesz dać ten sam kod, co w
   `CARDFORGE_KODY`).
4. Link do produktu wklej jako `CARDFORGE_LINK`.

➡️ Gumroad zbiera płatność i obsługuje bezpieczeństwo kart — **Ty nie dotykasz danych kart**.
Kasa trafia na Twoje konto Gumroad, a stamtąd wypłacasz na bank.

> **Uwaga (uczciwie):** na start kody są WSPÓLNE — ktoś kto zapłaci może teoretycznie przekazać
> kod koledze. Dla testu na Twojej grupie to OK. **Docelowo** Gumroad daje *license keys*
> (unikalny kod na każdy zakup, weryfikowany automatycznie) — to domknie temat w 100%.
> To jest zaplanowana kolejna faza.

---

## 🟢 KROK 4 — Wyślij link na grupę

Gotowe. Wysyłasz link do aplikacji. Ludzie:
- robią **małą próbkę za darmo** (widzą jakość),
- za większe dokumenty **płacą** (dostają kod → wpisują → generują).

---

## ✅ Co już Cię chroni (wbudowane w aplikację)

| Zabezpieczenie | Co robi |
|---|---|
| **Tryb produkcji** (`CARDFORGE_PROD=1`) | chowa klucz i model przed userami |
| **Bramka płatności** | bez ważnego kodu duży dokument się nie wygeneruje (blokada na serwerze) |
| **Darmowa próbka ≤ 5 stron, BEZ recenzenta** | darmowe tylko małe pliki, tańszy tryb (grosze) |
| **Limit rozmiaru 1 dokumentu (400 części)** | nikt nie wgra „giganta”, który spali fortunę |
| **Limit darmowych: 2/sesję, 15/dobę (globalnie)** | anty-spam Twojego API |
| **Tryb demo ukryty w produkcji** | nie ma darmowego obejścia płatności |
| **`.gitignore`** | klucz `.env` nie trafi przypadkiem na GitHub |

### Twoja maksymalna możliwa strata = limit z KROKU 1 (np. 40-60 zł). Nic więcej.

---

## 🔧 Jak przetestować lokalnie (zanim wyślesz ludziom)

W terminalu, w folderze `anki-generator`:

```
CARDFORGE_PROD=1 CARDFORGE_KODY="TEST123" ./venv/bin/streamlit run interfejs.py
```

- Wgraj mały PDF → powinno być **za darmo**.
- Wgraj duży PDF → powinna pokazać się **cena + pole na kod**; wpisz `TEST123` → odblokuje.

Bez `CARDFORGE_PROD=1` aplikacja działa jak dotąd (tryb osobisty, bez płatności).
