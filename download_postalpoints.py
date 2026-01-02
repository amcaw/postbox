#!/usr/bin/env python3
import datetime as dt
import pathlib
import urllib.parse
import urllib.request

URL_TEMPLATE = (
    "https://biptopendata.blob.core.windows.net/opendata/postalpoints.csv"
    "?sv=2024-11-04&se=2026-01-02T22%3A00%3A27Z&sr=b&sp=r"
    "&sig=syM5luCTzr0nW%2FR1JJE6793YzMgdJbV2fjeoAp9pyX4%3D"
)


def build_url(today: dt.date) -> str:
    parsed = urllib.parse.urlparse(URL_TEMPLATE)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["sv"] = [today.strftime("%Y-%m-%d")]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


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
