import requests

BASE_URL = "https://zenodo.org/api"
ACCESS_TOKEN = "hmT2EPUXKMh3ACCsZ1MvGjkS2Ybv3A7YvaQSk8lZ0Sv6bgxZpiApSJ7sTlnj"  # <- replace this


import time
import random
import re
from datetime import datetime
from collections import defaultdict

import requests

# ----------------------------
# CONFIG (keep your token here)
# ----------------------------
BASE_URL = "https://zenodo.org/api"
ACCESS_TOKEN = "xxxxxxxxxxxxxxxxxxxxx"  # <-- your real token (no quotes inside)
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

BEGIN = "<!--BEGIN_AUTO_PUBLICATIONS-->"
END = "<!--END_AUTO_PUBLICATIONS-->"
INDEX_MD_PATH = "index.md"


def get_with_backoff(session, url, headers, params, max_retries=8, base_sleep=1.0):
    for attempt in range(max_retries):
        r = session.get(url, headers=headers, params=params, timeout=30)

        if r.status_code < 400:
            return r

        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            sleep_s = float(retry_after) if retry_after else base_sleep * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(sleep_s)
            continue

        if r.status_code in (500, 502, 503, 504):
            time.sleep(base_sleep * (2 ** attempt) + random.uniform(0, 0.5))
            continue

        # Show body for debugging
        raise RuntimeError(
            f"Zenodo API error {r.status_code} for {r.url}\n"
            f"Response body (first 1500 chars):\n{(r.text or '')[:1500]}"
        )

    raise RuntimeError("Zenodo API retries exhausted.")


def list_all_depositions(page_size=25, polite_delay=0.8):
    """
    If auth is correct, Zenodo allows bigger pages.
    But 25 always works even if Zenodo decides you're unauthenticated.
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
            time.sleep(polite_delay + random.uniform(0, 0.2))

    return all_deps


def best_link(dep: dict) -> str:
    md = dep.get("metadata", {}) or {}
    doi = md.get("doi")
    if doi:
        return f"https://doi.org/{doi}"

    rec_id = dep.get("record_id")
    if rec_id:
        return f"https://zenodo.org/records/{rec_id}"

    dep_id = dep.get("id")
    if dep_id:
        return f"https://zenodo.org/deposit/{dep_id}"

    return "https://zenodo.org"


def dep_year(dep: dict) -> int:
    md = dep.get("metadata", {}) or {}
    pub = md.get("publication_date") or dep.get("created") or dep.get("modified")
    if not pub:
        return 0
    try:
        return int(str(pub)[:4])
    except Exception:
        return 0


def dep_sort_key(dep: dict) -> str:
    md = dep.get("metadata", {}) or {}
    return str(md.get("publication_date") or dep.get("modified") or dep.get("created") or "")


def render_markdown(deps: list[dict]) -> str:
    by_year = defaultdict(list)
    for d in deps:
        by_year[dep_year(d)].append(d)

    years = sorted([y for y in by_year.keys() if y], reverse=True)

    lines = []
    lines.append("Source: Zenodo Deposit API (token-authenticated)\n")

    for y in years:
        lines.append(f"\n### {y}\n")
        items = sorted(by_year[y], key=dep_sort_key, reverse=True)
        for dep in items:
            title = (dep.get("metadata", {}) or {}).get("title") or "Untitled"
            link = best_link(dep)
            lines.append(f"- **{title}**  \n  {link}")

    lines.append("\n")
    return "\n".join(lines)


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


def main():
    deps = list_all_depositions(page_size=25, polite_delay=0.8)
    md = render_markdown(deps)
    inject_into_index(md)
    print(f"Updated {INDEX_MD_PATH} with {len(deps)} depositions.")


if __name__ == "__main__":
    main()
