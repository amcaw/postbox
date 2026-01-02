#!/usr/bin/env python3
import datetime as dt
import pathlib
import urllib.request
import html
import re

LANDING_PAGE_URL = "https://www.postaalpunt.be/fr/"
URL_TEMPLATE = (
    "https://biptopendata.blob.core.windows.net/opendata/postalpoints.csv"
    "?sv=2024-11-04&se=2026-01-02T22%3A22%3A03Z&sr=b&sp=r"
    "&sig=V4CkPzauszEi1Ko%2FKAOoJbs3zPkok79JkOQJO9fDt1Q%3D"
)


def build_url(_: dt.date) -> str:
    # The SAS signature is bound to the full query string. Fetch the latest link.
    try:
        with urllib.request.urlopen(LANDING_PAGE_URL) as response:
            page = response.read().decode("utf-8", errors="replace")
    except Exception:
        return URL_TEMPLATE

    page = html.unescape(page)
    match = re.search(
        r"https://biptopendata\.blob\.core\.windows\.net/opendata/"
        r"postalpoints\.csv\?[^\"'>\\s]+",
        page,
    )
    return match.group(0) if match else URL_TEMPLATE


def pick_output_path(today: dt.date) -> pathlib.Path:
    base = pathlib.Path(f"postalpoints_{today.strftime('%Y-%m-%d')}.csv")
    if not base.exists():
        return base
    timestamp = dt.datetime.now().strftime("%H%M%S")
    return pathlib.Path(f"postalpoints_{today.strftime('%Y-%m-%d')}_{timestamp}.csv")


def download(url: str, dest: pathlib.Path) -> None:
    with urllib.request.urlopen(url) as response:
        dest.write_bytes(response.read())


def main() -> None:
    today = dt.date.today()
    url = build_url(today)
    dest = pick_output_path(today)
    download(url, dest)
    print(f"Downloaded to {dest}")


if __name__ == "__main__":
    main()
