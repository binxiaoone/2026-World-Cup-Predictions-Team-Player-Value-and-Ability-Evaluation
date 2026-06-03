from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
PLAYERS_PATH = ROOT / "data" / "processed" / "players.json"
SQUADS_HTML_PATH = ROOT / "data" / "raw" / "wiki_squads.html"
MEDIA_PATH = ROOT / "data" / "processed" / "player_media.json"
API_URL = "https://en.wikipedia.org/w/api.php"
REST_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_note(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def player_key(team: str, player: str) -> str:
    return f"{team}::{player}"


def parse_team_order(soup: BeautifulSoup) -> list[tuple[str, str]]:
    team_order: list[tuple[str, str]] = []
    current_group: str | None = None
    content = soup.find(id="mw-content-text") or soup

    for heading in content.find_all(["h2", "h3"]):
        text = heading.get_text(" ", strip=True)
        text = re.sub(r"\s*\[edit\]\s*$", "", text)
        if heading.name == "h2":
            if re.fullmatch(r"Group [A-L]", text):
                current_group = text.split()[-1]
            else:
                current_group = None
        elif current_group:
            team_order.append((text, current_group))

    return team_order


def first_player_link(cell: Any) -> tuple[str | None, str | None]:
    for anchor in cell.find_all("a"):
        href = anchor.get("href") or ""
        title = anchor.get("title") or anchor.get_text(" ", strip=True)
        text = anchor.get_text(" ", strip=True)
        if not href.startswith("/wiki/"):
            continue
        if "Captain_(association_football)" in href:
            continue
        if text.lower() == "captain":
            continue
        return title, f"https://en.wikipedia.org{href}"
    return None, None


def parse_player_refs() -> dict[str, dict[str, Any]]:
    if not SQUADS_HTML_PATH.exists():
        raise FileNotFoundError(
            f"{SQUADS_HTML_PATH} not found. Run: python scripts/build_data.py --force-download"
        )

    soup = BeautifulSoup(SQUADS_HTML_PATH.read_text(encoding="utf-8"), "html.parser")
    team_order = parse_team_order(soup)
    roster_tables = soup.find_all("table", class_="wikitable")[: len(team_order)]
    refs: dict[str, dict[str, Any]] = {}

    for (team, group), table in zip(team_order, roster_tables):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            player_text = clean_note(cells[2].get_text(" ", strip=True))
            player_text = re.sub(r"\s*\(\s*captain\s*\)\s*", "", player_text, flags=re.I).strip()
            title, page_url = first_player_link(cells[2])
            refs[player_key(team, player_text)] = {
                "team": team,
                "group": group,
                "player": player_text,
                "page_title": title,
                "page_url": page_url,
            }

    return refs


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def fetch_page_images(titles: list[str], thumb_size: int, batch_size: int, delay: float, retries: int) -> dict[str, dict[str, Any]]:
    if not titles:
        return {}

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "WorldCupAIPredictor/1.0 "
                "(educational GitHub Pages project; Wikimedia thumbnails only)"
            )
        }
    )

    results: dict[str, dict[str, Any]] = {}
    for index, batch in enumerate(chunked(titles, batch_size), 1):
        params = {
            "action": "query",
            "format": "json",
            "titles": "|".join(batch),
            "redirects": 1,
            "prop": "pageimages|info",
            "piprop": "thumbnail|name|original",
            "pithumbsize": thumb_size,
            "inprop": "url",
            "origin": "*",
        }
        response = None
        for attempt in range(retries + 1):
            response = session.get(API_URL, params=params, timeout=30)
            if response.status_code != 429:
                break
            wait = max(delay, 2.0) * (attempt + 1) * 2
            print(f"Rate limited on batch {index}; waiting {wait:.1f}s before retry {attempt + 1}/{retries}.")
            time.sleep(wait)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            print(f"Skipping batch {index} after HTTP error: {exc}")
            continue
        payload = response.json()

        redirect_lookup = {
            redirect.get("from"): redirect.get("to")
            for redirect in payload.get("query", {}).get("redirects", [])
        }

        for page in payload.get("query", {}).get("pages", {}).values():
            title = page.get("title")
            candidates = [title]
            candidates.extend([source for source, target in redirect_lookup.items() if target == title])
            thumbnail = page.get("thumbnail") or {}
            original = page.get("original") or {}
            for candidate in candidates:
                if not candidate:
                    continue
                results[candidate] = {
                    "status": "found" if thumbnail.get("source") else "no_image",
                    "source_title": title,
                    "page_url": page.get("fullurl"),
                    "image_url": thumbnail.get("source"),
                    "image_width": thumbnail.get("width"),
                    "image_height": thumbnail.get("height"),
                    "original_url": original.get("source"),
                    "pageimage": page.get("pageimage"),
                }
        if delay:
            time.sleep(delay)

    return results


def fetch_rest_images(
    selected: list[dict[str, Any]],
    refs: dict[str, dict[str, Any]],
    existing_by_key: dict[str, dict[str, Any]],
    delay: float,
    retries: int,
) -> dict[str, dict[str, Any]]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "WorldCupAIPredictor/1.0 "
                "(educational GitHub Pages project; Wikimedia page summaries)"
            )
        }
    )

    resolved: dict[str, dict[str, Any]] = {}
    to_query = [
        player
        for player in selected
        if existing_by_key.get(player_key(player["team"], player["player"]), {}).get("status")
        not in {"found", "no_image"}
        and refs.get(player_key(player["team"], player["player"]), {}).get("page_title")
    ]
    print(f"REST titles to query: {len(to_query)}")

    for index, player in enumerate(to_query, 1):
        key = player_key(player["team"], player["player"])
        ref = refs[key]
        title = ref["page_title"]
        url = REST_SUMMARY_URL + quote(title.replace(" ", "_"), safe="")

        response = None
        for attempt in range(retries + 1):
            response = session.get(url, timeout=20)
            if response.status_code != 429:
                break
            wait = max(delay, 1.0) * (attempt + 1) * 2
            print(f"REST rate limited at {index}/{len(to_query)}; waiting {wait:.1f}s.")
            time.sleep(wait)

        if response is None:
            continue

        if response.status_code == 404:
            resolved[key] = {
                "status": "no_image",
                "source_title": title,
                "page_url": ref.get("page_url"),
                "image_url": None,
            }
        elif response.ok:
            payload = response.json()
            thumbnail = payload.get("thumbnail") or {}
            original = payload.get("originalimage") or {}
            resolved[key] = {
                "status": "found" if thumbnail.get("source") else "no_image",
                "source_title": payload.get("title") or title,
                "page_url": payload.get("content_urls", {}).get("desktop", {}).get("page") or ref.get("page_url"),
                "image_url": thumbnail.get("source"),
                "image_width": thumbnail.get("width"),
                "image_height": thumbnail.get("height"),
                "original_url": original.get("source"),
                "pageimage": None,
            }
        else:
            safe_title = title.encode("ascii", "ignore").decode("ascii") or "<non-ascii title>"
            print(f"Skipping {safe_title}: HTTP {response.status_code}")

        if index % 25 == 0 or index == len(to_query):
            found = sum(1 for item in resolved.values() if item.get("status") == "found")
            print(f"REST queried {index}/{len(to_query)} | found {found}")
        if delay:
            time.sleep(delay)

    return resolved


def player_rank_value(player: dict[str, Any]) -> int:
    return int(player.get("goals", 0)) * 4 + int(player.get("caps", 0))


def enrich(
    offset: int,
    limit: int | None,
    thumb_size: int,
    batch_size: int,
    delay: float,
    retries: int,
    strategy: str,
    top_ranked: bool,
) -> None:
    players = load_json(PLAYERS_PATH, {"players": []})["players"]
    existing_payload = load_json(MEDIA_PATH, {"media": []})
    existing_by_key = {item["key"]: item for item in existing_payload.get("media", [])}
    refs = parse_player_refs()

    selection_base = sorted(players, key=player_rank_value, reverse=True) if top_ranked else players
    selected = selection_base[offset : offset + limit] if limit else selection_base[offset:]
    images_by_title: dict[str, dict[str, Any]] = {}
    images_by_key: dict[str, dict[str, Any]] = {}

    if strategy == "rest":
        print(f"Selected players: {len(selected)} | strategy: REST summary")
        images_by_key = fetch_rest_images(selected, refs, existing_by_key, delay, retries)
    else:
        titles = sorted(
            {
                refs.get(player_key(player["team"], player["player"]), {}).get("page_title")
                for player in selected
                if refs.get(player_key(player["team"], player["player"]), {}).get("page_title")
                and existing_by_key.get(player_key(player["team"], player["player"]), {}).get("status")
                not in {"found", "no_image"}
            }
        )
        print(f"Selected players: {len(selected)} | titles to query: {len(titles)}")
        images_by_title = fetch_page_images(titles, thumb_size, batch_size, delay, retries)

    media: list[dict[str, Any]] = []

    for player in players:
        key = player_key(player["team"], player["player"])
        ref = refs.get(key, {})
        page_title = ref.get("page_title")
        existing = existing_by_key.get(key)
        if existing and key not in images_by_key and page_title not in images_by_title:
            media.append(existing)
            continue
        image = images_by_key.get(key) or (images_by_title.get(page_title, {}) if page_title else {})
        status = image.get("status") or ("no_page_link" if not page_title else "not_selected")
        page_url = image.get("page_url") or ref.get("page_url")

        media.append(
            {
                "key": key,
                "player": player["player"],
                "team": player["team"],
                "group": player["group"],
                "source": "Wikipedia/Wikimedia Commons",
                "status": status,
                "page_title": page_title,
                "page_url": page_url,
                "image_url": image.get("image_url"),
                "image_width": image.get("image_width"),
                "image_height": image.get("image_height"),
                "original_url": image.get("original_url"),
                "pageimage": image.get("pageimage"),
                "attribution_note": (
                    "Thumbnail URL is served by Wikimedia. See page_url/original_url for source context."
                    if image.get("image_url")
                    else None
                ),
            }
        )

    payload = {
        "source_note": (
            "Images are Wikimedia/Wikipedia thumbnail URLs resolved from player page links in the public "
            "2026 FIFA World Cup squads page. Missing players fall back to generated initials in the frontend."
        ),
        "media": media,
        "counts": {
            "players_in_roster": len(players),
            "media_records": len(media),
            "page_links_found": sum(1 for item in media if item.get("page_title")),
            "images_found": sum(1 for item in media if item.get("status") == "found"),
        },
    }
    status_counts: dict[str, int] = defaultdict(int)
    for item in media:
        status_counts[item.get("status") or "unknown"] += 1
    payload["counts"]["status_counts"] = dict(sorted(status_counts.items()))
    dump_json(MEDIA_PATH, payload)
    print(payload["counts"])
    print(f"Wrote {MEDIA_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve player image thumbnails through public Wikipedia page links.")
    parser.add_argument("--offset", type=int, default=0, help="Start index in players.json.")
    parser.add_argument("--limit", type=int, default=None, help="Only resolve images for the first N players from players.json.")
    parser.add_argument("--thumb-size", type=int, default=360, help="Requested thumbnail width.")
    parser.add_argument("--batch-size", type=int, default=12, help="MediaWiki titles per request.")
    parser.add_argument("--delay", type=float, default=0.8, help="Delay between API requests.")
    parser.add_argument("--retries", type=int, default=3, help="Retries after HTTP 429.")
    parser.add_argument("--strategy", choices=["batch", "rest"], default="batch", help="Image lookup strategy.")
    parser.add_argument("--top-ranked", action="store_true", help="Select highest caps/goals players before offset/limit.")
    args = parser.parse_args()
    enrich(
        max(0, args.offset),
        args.limit,
        args.thumb_size,
        max(1, args.batch_size),
        max(0.0, args.delay),
        max(0, args.retries),
        args.strategy,
        args.top_ranked,
    )


if __name__ == "__main__":
    main()
