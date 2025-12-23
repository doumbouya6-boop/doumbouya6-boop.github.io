import requests

BASE_URL = "https://zenodo.org/api"
ACCESS_TOKEN = "hmT2EPUXKMh3ACCsZ1MvGjkS2Ybv3A7YvaQSk8lZ0Sv6bgxZpiApSJ7sTlnj"  # <- replace this

import time
import random
import requests

import re
from datetime import datetime

BEGIN = "<!--BEGIN_AUTO_PUBLICATIONS-->"
END = "<!--END_AUTO_PUBLICATIONS-->"
INDEX_MD_PATH = "index.md"

def inject_into_index(markdown_block: str):
    with open(INDEX_MD_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), flags=re.DOTALL)
    if not pattern.search(text):
        raise RuntimeError(f"Markers {BEGIN} ... {END} not found in {INDEX_MD_PATH}")

    stamped = (
        f"{BEGIN}\n\n"
        f"## Publications (auto)\n"
        f"Last refreshed: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"{markdown_block.strip()}\n\n"
        f"{END}"
    )
    updated = pattern.sub(stamped, text, count=1)

    with open(INDEX_MD_PATH, "w", encoding="utf-8") as f:
        f.write(updated)

HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

def get_with_backoff(session, url, headers, params, max_retries=8, base_sleep=1.0):
    """
    Retry on 429/5xx with exponential backoff + jitter.
    Respects Retry-After header when present.
    """
    for attempt in range(max_retries):
        r = session.get(url, headers=headers, params=params, timeout=30)

        # Success
        if r.status_code < 400:
            return r

        # Rate limited
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                sleep_s = float(retry_after)
            else:
                # Exponential backoff with jitter
                sleep_s = base_sleep * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(sleep_s)
            continue

        # Temporary server errors
        if r.status_code in (500, 502, 503, 504):
            sleep_s = base_sleep * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(sleep_s)
            continue

        # Other errors: raise immediately (bad token, perms, etc.)
        r.raise_for_status()

    # If we got here, retries exhausted
    r.raise_for_status()


def list_all_depositions(page_size=50, polite_delay=0.8):
    """
    Lists all depositions from Zenodo deposit API.
    page_size=25/50 is safer than 100.
    polite_delay adds a small sleep between pages even when no 429 occurs.
    """
    url = f"{BASE_URL}/deposit/depositions"
    page = 1
    all_deps = []

    with requests.Session() as session:
        while True:
            params = {"size": page_size, "page": page}
            r = get_with_backoff(session, url, HEADERS, params)
            data = r.json() or []
            if not data:
                break

            all_deps.extend(data)
            page += 1

            # Always be polite to avoid 429 bursts
            time.sleep(polite_delay + random.uniform(0, 0.2))

    return all_deps


def main():
    deps = list_all_depositions(page_size=50, polite_delay=0.8)

    for dep in deps:
        md = dep.get("metadata") or {}
        title = md.get("title")
        doi = md.get("doi") or dep.get("doi")
        dep_id = dep.get("id")
        state = dep.get("state")
        record_url = dep.get("record_url") or dep.get("links", {}).get("html")
        print(f"[{state}] id={dep_id} | {title!r}")
        print(f"    DOI: {doi}")
        print(f"    URL: {record_url}")
        print()

import io
from contextlib import redirect_stdout

if __name__ == "__main__":
    buf = io.StringIO()

    with redirect_stdout(buf):
        main()   # ← whatever you already had running

    output = buf.getvalue()

    # keep original behavior
    print(output, end="")

    # NEW: write the same output into index.md
    inject_into_index(output)

    print("\nUpdated index.md")
