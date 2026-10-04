"""Budzik CardForge - otwiera apkę w prawdziwej przeglądarce, żeby Streamlit jej nie usypiał.

Streamlit Community Cloud usypia apkę po ~dobie bez ruchu. Zwykły ping HTTP
(np. UptimeRobot) się nie liczy, bo nie otwiera sesji przeglądarki. Ten skrypt
uruchamia Chromium (Playwright), wchodzi na stronę, klika "Yes, get this app
back up!" jeśli apka śpi, i czeka, aż pokaże się napis "CardForge".

Uruchamiany co kilka godzin przez GitHub Actions (.github/workflows/budzik.yml).
Kod wyjścia 1 = apka nie wstała -> GitHub wyśle maila o nieudanym przebiegu.
"""

import sys
import time

from playwright.sync_api import sync_playwright

ADRES = "https://anki-generator-eu38imyfjcmjr8jusdgdkb.streamlit.app/"
PRZYCISK_BUDZENIA = "Yes, get this app back up"
ZNAK_ZYCIA = "CardForge"
LIMIT_SEKUND = 240


def apka_dziala(strona):
    """Sprawdza, czy w którejkolwiek ramce strony widać napis CardForge."""
    for ramka in strona.frames:
        try:
            if ramka.get_by_text(ZNAK_ZYCIA).first.is_visible():
                return True
        except Exception:
            pass
    return False


def main():
    with sync_playwright() as p:
        przegladarka = p.chromium.launch()
        strona = przegladarka.new_page()
        strona.goto(ADRES, wait_until="domcontentloaded", timeout=90_000)

        start = time.time()
        obudzona = False
        while time.time() - start < LIMIT_SEKUND:
            if apka_dziala(strona):
                print(f"OK: apka działa ({int(time.time() - start)} s).")
                # Chwila na pełne załadowanie sesji, żeby liczyła się jako ruch.
                strona.wait_for_timeout(15_000)
                przegladarka.close()
                return 0

            przycisk = strona.get_by_role("button", name=PRZYCISK_BUDZENIA)
            if not obudzona and przycisk.count() and przycisk.first.is_visible():
                print("Apka spała - klikam 'Yes, get this app back up!'.")
                przycisk.first.click()
                obudzona = True

            strona.wait_for_timeout(5_000)

        print("BŁĄD: apka nie wstała w ciągu "
              f"{LIMIT_SEKUND} s. Tytuł strony: {strona.title()!r}")
        strona.screenshot(path="budzik_blad.png", full_page=True)
        przegladarka.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
