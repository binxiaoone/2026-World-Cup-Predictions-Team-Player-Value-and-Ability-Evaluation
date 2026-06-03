from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
PLAYERS_PATH = PROCESSED_DIR / "players.json"
TEAMS_PATH = PROCESSED_DIR / "teams.json"
MANIFEST_PATH = PROCESSED_DIR / "manifest.json"
TM_PLAYERS_PATH = RAW_DIR / "transfermarkt_players.csv.gz"
TM_PLAYERS_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"

TEAM_COUNTRY_ALIASES = {
    "Bosnia and Herzegovina": ["Bosnia-Herzegovina", "Bosnia and Herzegovina"],
    "Cape Verde": ["Cape Verde", "Cabo Verde"],
    "Curaçao": ["Curacao", "Curaçao"],
    "Czech Republic": ["Czech Republic", "Czechia"],
    "DR Congo": ["DR Congo", "Congo DR", "Democratic Republic of the Congo"],
    "England": ["England"],
    "Haiti": ["Haiti"],
    "Iran": ["Iran"],
    "Ivory Coast": ["Cote d'Ivoire", "Ivory Coast"],
    "New Zealand": ["New Zealand"],
    "Qatar": ["Qatar"],
    "Scotland": ["Scotland"],
    "South Africa": ["South Africa"],
    "South Korea": ["Korea, South", "South Korea", "Korea Republic"],
    "United States": ["United States", "United States of America", "USA"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def normalize(value: Any) -> str:
    text = "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text = text.replace("ß", "ss").replace("ø", "o").replace("đ", "d").replace("ł", "l")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def compact_name(value: str) -> str:
    return normalize(value).replace(" ", "")


def parse_birth_year(value: Any) -> int | None:
    match = re.search(r"(\d{4})", str(value))
    return int(match.group(1)) if match else None


def team_country_norms(team: str) -> set[str]:
    aliases = TEAM_COUNTRY_ALIASES.get(team, [team])
    aliases.append(team)
    return {normalize(alias) for alias in aliases}


def club_similarity(roster_club: str, tm_club: str) -> float:
    left = normalize(roster_club)
    right = normalize(tm_club)
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def value_label(eur: int | None) -> str | None:
    if eur is None:
        return None
    if eur >= 1_000_000_000:
        return f"€{eur / 1_000_000_000:.2f}bn"
    if eur >= 1_000_000:
        return f"€{eur / 1_000_000:.1f}m"
    if eur >= 1_000:
        return f"€{eur / 1_000:.0f}k"
    return f"€{eur}"


def json_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def download_transfermarkt(force: bool) -> bool:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if TM_PLAYERS_PATH.exists() and not force:
        return False
    response = requests.get(
        TM_PLAYERS_URL,
        headers={"User-Agent": "WorldCupAIPredictor/1.0 market value enrichment"},
        timeout=90,
    )
    response.raise_for_status()
    TM_PLAYERS_PATH.write_bytes(response.content)
    return True


def load_transfermarkt() -> pd.DataFrame:
    columns = [
        "player_id",
        "name",
        "country_of_citizenship",
        "date_of_birth",
        "sub_position",
        "position",
        "image_url",
        "international_caps",
        "international_goals",
        "url",
        "current_club_name",
        "market_value_in_eur",
        "highest_market_value_in_eur",
    ]
    df = pd.read_csv(TM_PLAYERS_PATH, usecols=columns)
    df["norm_name"] = df["name"].map(normalize)
    df["compact_name"] = df["name"].map(compact_name)
    df["country_norm"] = df["country_of_citizenship"].map(normalize)
    df["birth_year"] = pd.to_datetime(df["date_of_birth"], errors="coerce").dt.year
    df["market_value_in_eur"] = pd.to_numeric(df["market_value_in_eur"], errors="coerce")
    return df


def candidate_score(player: dict[str, Any], candidate: pd.Series) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    player_norm = normalize(player["player"])
    candidate_norm = candidate["norm_name"]
    if player_norm == candidate_norm:
        score += 55.0
        reasons.append("exact_name")
    elif compact_name(player["player"]) == candidate["compact_name"]:
        score += 50.0
        reasons.append("compact_name")
    else:
        name_ratio = SequenceMatcher(None, player_norm, candidate_norm).ratio()
        score += name_ratio * 42.0
        if name_ratio >= 0.86:
            reasons.append("fuzzy_name")

    country_norms = team_country_norms(player["team"])
    if candidate["country_norm"] in country_norms:
        score += 20.0
        reasons.append("country")

    player_year = parse_birth_year(player.get("date_of_birth"))
    if player_year and not pd.isna(candidate["birth_year"]) and int(candidate["birth_year"]) == player_year:
        score += 12.0
        reasons.append("birth_year")

    club_ratio = club_similarity(player.get("club", ""), candidate.get("current_club_name", ""))
    if club_ratio >= 0.88:
        score += 10.0
        reasons.append("club")
    elif club_ratio >= 0.62:
        score += 5.0
        reasons.append("club_fuzzy")

    if not pd.isna(candidate.get("market_value_in_eur")):
        score += 3.0
        reasons.append("has_value")

    return score, reasons


def find_match(player: dict[str, Any], by_name: dict[str, pd.DataFrame], by_compact: dict[str, pd.DataFrame], all_rows: pd.DataFrame) -> tuple[pd.Series | None, float, list[str]]:
    norm = normalize(player["player"])
    compact = compact_name(player["player"])
    frames: list[pd.DataFrame] = []

    if norm in by_name:
        frames.append(by_name[norm])
    if compact in by_compact:
        frames.append(by_compact[compact])

    if not frames:
        surname = norm.split()[-1] if norm else ""
        if surname:
            surname_hits = all_rows[all_rows["norm_name"].str.endswith(f" {surname}", na=False)]
            if len(surname_hits) <= 30:
                frames.append(surname_hits)

    if not frames:
        return None, 0.0, []

    candidates = pd.concat(frames).drop_duplicates("player_id")
    best: tuple[pd.Series | None, float, list[str]] = (None, 0.0, [])
    for _, candidate in candidates.iterrows():
        score, reasons = candidate_score(player, candidate)
        if score > best[1]:
            best = (candidate, score, reasons)

    return best


def enrich(force_download: bool) -> None:
    downloaded = download_transfermarkt(force_download)
    players_payload = load_json(PLAYERS_PATH)
    teams_payload = load_json(TEAMS_PATH)
    manifest = load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}

    tm = load_transfermarkt()
    by_name = {name: group for name, group in tm.groupby("norm_name")}
    by_compact = {name: group for name, group in tm.groupby("compact_name")}

    matched = 0
    valued = 0
    team_totals: dict[str, dict[str, Any]] = {}

    for player in players_payload["players"]:
        match, score, reasons = find_match(player, by_name, by_compact, tm)
        value_eur: int | None = None
        value_status = "not_matched"
        confidence = "none"

        market_value: dict[str, Any] = {
            "eur": None,
            "label": None,
            "source": "Transfermarkt datasets",
            "source_url": TM_PLAYERS_URL,
            "player_url": None,
            "matched_name": None,
            "matched_club": None,
            "highest_eur": None,
            "highest_label": None,
            "confidence": confidence,
            "status": value_status,
            "match_score": round(float(score), 2),
            "match_reasons": reasons,
        }

        if match is not None and score >= 70:
            matched += 1
            confidence = "high" if score >= 90 else "medium"
            raw_value = match.get("market_value_in_eur")
            raw_highest = match.get("highest_market_value_in_eur")
            value_eur = None if pd.isna(raw_value) else int(raw_value)
            highest_eur = None if pd.isna(raw_highest) else int(raw_highest)
            value_status = "valued" if value_eur is not None else "matched_no_value"
            if value_eur is not None:
                valued += 1
            market_value.update(
                {
                    "eur": value_eur,
                    "label": value_label(value_eur),
                    "player_url": json_cell(match.get("url")),
                    "matched_name": json_cell(match.get("name")),
                    "matched_club": json_cell(match.get("current_club_name")),
                    "highest_eur": highest_eur,
                    "highest_label": value_label(highest_eur),
                    "confidence": confidence,
                    "status": value_status,
                }
            )

        player["market_value"] = market_value

        total = team_totals.setdefault(
            player["team"],
            {"team": player["team"], "matched_players": 0, "valued_players": 0, "total_eur": 0, "players": 0},
        )
        total["players"] += 1
        if market_value["status"] != "not_matched":
            total["matched_players"] += 1
        if value_eur is not None:
            total["valued_players"] += 1
            total["total_eur"] += value_eur

    for total in team_totals.values():
        total["total_label"] = value_label(total["total_eur"])
        total["coverage"] = round(total["valued_players"] / total["players"], 3) if total["players"] else 0

    for team in teams_payload["teams"]:
        value = team_totals.get(team["team"], {"total_eur": 0, "total_label": "€0", "coverage": 0})
        team.setdefault("squad", {})["market_value"] = value

    source_record = {
        "name": "Transfermarkt datasets players.csv.gz",
        "url": TM_PLAYERS_URL,
        "cached_file": str(TM_PLAYERS_PATH.relative_to(ROOT)).replace("\\", "/"),
        "downloaded_this_run": downloaded,
    }
    data_sources = [
        source for source in manifest.setdefault("data_sources", []) if source.get("url") != TM_PLAYERS_URL
    ]
    data_sources.append(source_record)
    manifest["data_sources"] = data_sources
    manifest.setdefault("counts", {})["market_values_matched"] = matched
    manifest.setdefault("counts", {})["market_values_valued"] = valued
    manifest["market_values_generated_at"] = now_iso()
    manifest["market_value_note"] = (
        "Market values are matched from a public Transfermarkt dataset mirror. "
        "Unmatched players are left blank; team totals sum only matched player values."
    )

    dump_json(PLAYERS_PATH, players_payload)
    dump_json(TEAMS_PATH, teams_payload)
    dump_json(MANIFEST_PATH, manifest)

    print(
        {
            "players": len(players_payload["players"]),
            "matched": matched,
            "valued": valued,
            "teams": len(team_totals),
            "downloaded": downloaded,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich roster players with Transfermarkt market values.")
    parser.add_argument("--force-download", action="store_true", help="Refresh Transfermarkt dataset cache.")
    args = parser.parse_args()
    enrich(args.force_download)


if __name__ == "__main__":
    main()
