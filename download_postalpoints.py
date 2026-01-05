#!/usr/bin/env python3
import datetime as dt
import pathlib
import urllib.request
import csv
import io
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

LANDING_PAGE_URL = "https://www.postaalpunt.be/fr/"
LINK_BUTTON_XPATH = "/html/body/app-root/div/div[2]/app-filter/div/div[1]/app-header/header/div"
CSV_LINK_SELECTOR = "a[href*='biptopendata.blob.core.windows.net/opendata/postalpoints.csv']"
SNAPSHOT_DIR = pathlib.Path("static/snapshots")
INDEX_PATH = SNAPSHOT_DIR / "index.csv"

MOJIBAKE_MAP = {
    # Minuscules accentuées
    "Ã ": "à",
    "Ã¢": "â",
    "Ã¤": "ä",
    "Ã§": "ç",
    "Ã¨": "è",
    "Ã©": "é",
    "Ãª": "ê",
    "Ã«": "ë",
    "Ã®": "î",
    "Ã¯": "ï",
    "Ã´": "ô",
    "Ã¶": "ö",
    "Ã¹": "ù",
    "Ã»": "û",
    "Ã¼": "ü",
    "Å\"": "œ",
    # Majuscules accentuées
    "Ã€": "À",
    "Ã‚": "Â",
    "Ã„": "Ä",
    "Ã‡": "Ç",
    "Ãˆ": "È",
    "Ã‰": "É",
    "ÃŠ": "Ê",
    "Ã‹": "Ë",
    "ÃŽ": "Î",
    "Ã": "Ï",
    "Ã\"": "Ô",
    "Ã–": "Ö",
    "Ã™": "Ù",
    "Ã›": "Û",
    "Åœ": "Œ",
    # Autres caractères spéciaux
    "â€™": "'",
    "â€œ": "\"",
    "â€": "\"",
    "â€\"": "–",
    "Â°": "°",
    "Â ": " ",
}


def fetch_latest_url() -> str:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,720")

    chrome_bin = os.getenv("CHROME_BIN") or os.getenv("CHROMIUM_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    service = None
    chromedriver = os.getenv("CHROMEDRIVER")
    if chromedriver:
        service = Service(executable_path=chromedriver)

    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(LANDING_PAGE_URL)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.element_to_be_clickable((By.XPATH, LINK_BUTTON_XPATH))).click()
        link = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, CSV_LINK_SELECTOR)))
        href = link.get_attribute("href")
    finally:
        driver.quit()

    if not href:
        raise RuntimeError("CSV link not found on landing page.")
    return href


def fix_mojibake(text: str) -> str:
    for bad, good in MOJIBAKE_MAP.items():
        text = text.replace(bad, good)
    return text


def decode_payload(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("iso-8859-1")
    return fix_mojibake(text)


def write_text(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def pick_output_path(today: dt.date) -> pathlib.Path:
    base = pathlib.Path(f"postalpoints_{today.strftime('%Y-%m-%d')}.csv")
    if not base.exists():
        return base
    timestamp = dt.datetime.now().strftime("%H%M%S")
    return pathlib.Path(f"postalpoints_{today.strftime('%Y-%m-%d')}_{timestamp}.csv")


def count_categories(content: str) -> tuple[int, int]:
    reader = csv.DictReader(io.StringIO(content))
    total = 0
    pbus = 0
    for row in reader:
        total += 1
        if row.get("Category") == "PBUS":
            pbus += 1
    return pbus, total


def update_index(date_str: str, filename: str) -> None:
    rows = []
    if INDEX_PATH.exists():
        raw = INDEX_PATH.read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(raw))
        rows = [row for row in reader if row.get("date") and row.get("file")]

    rows.append({"date": date_str, "file": filename})
    rows.sort(key=lambda row: row["date"])

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "file"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    today = dt.date.today()
    url = fetch_latest_url()
    with urllib.request.urlopen(url) as response:
        payload = response.read()

    content = decode_payload(payload)

    dest = pick_output_path(today)
    write_text(dest, content)

    snapshot_path = SNAPSHOT_DIR / dest.name
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    write_text(snapshot_path, content)
    update_index(today.strftime("%Y-%m-%d"), dest.name)

    print(f"Downloaded to {dest}")
    print(f"Updated {snapshot_path}")
    print(f"Updated {INDEX_PATH}")


if __name__ == "__main__":
    main()
