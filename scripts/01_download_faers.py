"""Download FAERS quarterly ASCII files from the FDA.

Usage (in WSL):
    python scripts/01_download_faers.py              # 2019Q1 to the latest quarter
    python scripts/01_download_faers.py --start 2024Q1 --end 2024Q4

Files go to $SSX_DATA/raw/faers (default ~/ssx_data/raw/faers). Each quarter
is roughly 50 to 90 MB zipped. Files already downloaded are skipped, so the
script can be re-run after an interruption.
"""

import argparse
import datetime as dt
import re
import sys

import requests

from common import RAW_FAERS, START_QUARTER, quarters

URL = "https://fis.fda.gov/content/Exports/faers_ascii_{y}q{q}.zip"
INDEX = "https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html"


def zip_path(label):
    return RAW_FAERS / f"faers_ascii_{label.lower()}.zip"


def find_url(session, label, index_html):
    """Try the usual URL first, then look for the quarter on the FDA index page."""
    y, q = label[:4], label[-1]
    url = URL.format(y=y, q=q)
    r = session.head(url, allow_redirects=True, timeout=60)
    if r.status_code == 200:
        return url
    if index_html:
        m = re.search(rf'href="([^"]*ascii[^"]*{y}q{q}[^"]*\.zip)"', index_html, re.I)
        if m:
            return requests.compat.urljoin(INDEX, m.group(1))
    return None


def download(session, url, dest):
    tmp = dest.with_suffix(".part")
    with session.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START_QUARTER)
    ap.add_argument("--end", default=None, help="last quarter, e.g. 2026Q2 (default: latest found)")
    args = ap.parse_args()

    today = dt.date.today()
    end = args.end or f"{today.year}Q{(today.month - 1) // 3 + 1}"
    RAW_FAERS.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    try:
        index_html = session.get(INDEX, timeout=60).text
    except requests.RequestException:
        index_html = ""

    got, missing = [], []
    for label in quarters(args.start, end):
        dest = zip_path(label)
        if dest.exists():
            print(f"{label}: already downloaded")
            got.append(label)
            continue
        url = find_url(session, label, index_html)
        if not url:
            print(f"{label}: not published yet or not found")
            missing.append(label)
            continue
        print(f"{label}: downloading {url}")
        download(session, url, dest)
        got.append(label)

    print(f"\n{len(got)} quarters on disk in {RAW_FAERS}")
    # Quarters missing in the middle of the range are a problem; missing ones
    # at the end are just not published yet.
    gaps = [m for m in missing if got and m < got[-1]]
    if gaps:
        print("Missing quarters inside the range:", ", ".join(gaps))
        sys.exit(1)


if __name__ == "__main__":
    main()
