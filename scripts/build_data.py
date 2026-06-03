from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SQUADS_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"

RESULTS_PATH = RAW_DIR / "results.csv"
SQUADS_HTML_PATH = RAW_DIR / "wiki_squads.html"

RANDOM_SEED = 20260603
BASE_ELO = 1500.0
HOME_ADVANTAGE = 65.0


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def download(url: str, destination: Path, force: bool = False) -> bool:
    if destination.exists() and not force:
        return False

    headers = {
        "User-Agent": (
            "WorldCupAIPredictor/1.0 "
            "(educational GitHub Pages project; contact via repository issues)"
        )
    }
    response = requests.get(url, headers=headers, timeout=45)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return True


def json_dump(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clean_note(value: Any) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_age(value: Any) -> int | None:
    match = re.search(r"aged\s+(\d+)", str(value))
    return int(match.group(1)) if match else None


def to_int(value: Any) -> int:
    text = clean_note(value).replace(",", "")
    match = re.search(r"-?\d+", text)
    return int(match.group(0)) if match else 0


def k_factor(tournament: str) -> float:
    tournament_lower = tournament.lower()
    if tournament_lower == "fifa world cup":
        return 58.0
    if "qualification" in tournament_lower:
        return 38.0
    if any(term in tournament_lower for term in ["copa", "euro", "african cup", "asian cup", "gold cup"]):
        return 46.0
    if "nations league" in tournament_lower:
        return 32.0
    if "friendly" in tournament_lower:
        return 20.0
    return 28.0


def elo_expect(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def outcome_label(home_score: float, away_score: float) -> int:
    if home_score > away_score:
        return 0
    if home_score == away_score:
        return 1
    return 2


def form_value(history: deque[float]) -> float:
    if not history:
        return 1.35
    weights = np.linspace(0.7, 1.4, len(history))
    return float(np.average(list(history), weights=weights))


def make_features(
    home_team: str,
    away_team: str,
    tournament: str,
    neutral: bool,
    ratings: dict[str, float],
    form: dict[str, deque[float]],
) -> list[float]:
    home_bonus = 0.0 if neutral else HOME_ADVANTAGE
    elo_diff = (ratings[home_team] + home_bonus - ratings[away_team]) / 400.0
    form_diff = form_value(form[home_team]) - form_value(form[away_team])
    tournament_lower = tournament.lower()

    return [
        elo_diff,
        form_diff,
        1.0 if neutral else 0.0,
        1.0 if tournament_lower == "fifa world cup" else 0.0,
        1.0 if "qualification" in tournament_lower else 0.0,
        math.log1p(k_factor(tournament)),
    ]


def update_ratings(
    row: pd.Series,
    ratings: dict[str, float],
    form: dict[str, deque[float]],
    records: dict[str, dict[str, Any]],
) -> None:
    home = row["home_team"]
    away = row["away_team"]
    home_score = float(row["home_score"])
    away_score = float(row["away_score"])
    neutral = bool(row["neutral"])

    home_rating = ratings[home] + (0.0 if neutral else HOME_ADVANTAGE)
    away_rating = ratings[away]
    expected_home = elo_expect(home_rating, away_rating)
    actual_home = 1.0 if home_score > away_score else 0.5 if home_score == away_score else 0.0

    margin = abs(home_score - away_score)
    margin_multiplier = 1.0 if margin == 0 else min(2.4, math.sqrt(margin))
    delta = k_factor(str(row["tournament"])) * margin_multiplier * (actual_home - expected_home)

    ratings[home] += delta
    ratings[away] -= delta

    home_points = 3.0 if home_score > away_score else 1.0 if home_score == away_score else 0.0
    away_points = 3.0 if away_score > home_score else 1.0 if home_score == away_score else 0.0
    form[home].append(home_points)
    form[away].append(away_points)

    for team, goals_for, goals_against, points in [
        (home, home_score, away_score, home_points),
        (away, away_score, home_score, away_points),
    ]:
        rec = records[team]
        rec["matches"] += 1
        rec["goals_for"] += int(goals_for)
        rec["goals_against"] += int(goals_against)
        rec["points"] += int(points)
        rec["last_match"] = str(row["date"].date())
        if points == 3:
            rec["wins"] += 1
        elif points == 1:
            rec["draws"] += 1
        else:
            rec["losses"] += 1


def train_model(results: pd.DataFrame) -> tuple[LogisticRegression, dict[str, float], dict[str, deque[float]], dict[str, dict[str, Any]], dict[str, Any]]:
    completed = results.dropna(subset=["home_score", "away_score"]).copy()
    completed["date"] = pd.to_datetime(completed["date"])
    completed = completed.sort_values("date")

    ratings: dict[str, float] = defaultdict(lambda: BASE_ELO)
    form: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=10))
    records: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "matches": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "points": 0,
            "last_match": None,
        }
    )

    x_rows: list[list[float]] = []
    y_rows: list[int] = []

    for _, row in completed.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        tournament = str(row["tournament"])
        neutral = bool(row["neutral"])

        if row["date"].year >= 2000:
            x_rows.append(make_features(home, away, tournament, neutral, ratings, form))
            y_rows.append(outcome_label(float(row["home_score"]), float(row["away_score"])))

        update_ratings(row, ratings, form, records)

    x = np.array(x_rows, dtype=float)
    y = np.array(y_rows, dtype=int)

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.22,
        random_state=RANDOM_SEED,
        stratify=y,
    )

    model = LogisticRegression(
        max_iter=1200,
        class_weight="balanced",
        multi_class="auto",
        C=0.85,
        random_state=RANDOM_SEED,
    )
    model.fit(x_train, y_train)

    test_probs = model.predict_proba(x_test)
    metadata = {
        "training_matches": int(len(y_train)),
        "validation_matches": int(len(y_test)),
        "validation_accuracy": round(float(accuracy_score(y_test, model.predict(x_test))), 4),
        "validation_log_loss": round(float(log_loss(y_test, test_probs, labels=[0, 1, 2])), 4),
        "feature_names": [
            "elo_diff_with_home_advantage",
            "recent_form_points_diff",
            "neutral_site",
            "is_world_cup",
            "is_qualifier",
            "tournament_weight",
        ],
    }
    return model, ratings, form, records, metadata


def probabilities_for(
    model: LogisticRegression,
    home_team: str,
    away_team: str,
    tournament: str,
    neutral: bool,
    ratings: dict[str, float],
    form: dict[str, deque[float]],
) -> dict[str, float]:
    features = np.array([make_features(home_team, away_team, tournament, neutral, ratings, form)], dtype=float)
    raw = model.predict_proba(features)[0]
    mapped = {int(cls): float(prob) for cls, prob in zip(model.classes_, raw)}
    return {
        "home_win": mapped.get(0, 0.0),
        "draw": mapped.get(1, 0.0),
        "away_win": mapped.get(2, 0.0),
    }


def parse_groups_and_players(html: str) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    soup = BeautifulSoup(html, "html.parser")
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

    # The first 48 roster tables line up with the country headings on the page.
    tables = pd.read_html(StringIO(html))
    roster_tables = tables[: len(team_order)]

    group_map = {team: group for team, group in team_order}
    players: list[dict[str, Any]] = []
    squad_stats: dict[str, dict[str, Any]] = {}

    for (team, group), table in zip(team_order, roster_tables):
        team_players: list[dict[str, Any]] = []
        for _, row in table.iterrows():
            raw_player = clean_note(row.get("Player", ""))
            captain = "(captain)" in raw_player.lower()
            player_name = re.sub(r"\s*\(captain\)\s*", "", raw_player, flags=re.I).strip()
            item = {
                "team": team,
                "group": group,
                "number": clean_note(row.get("No.", "")),
                "position": clean_note(row.get("Pos.", "")),
                "player": player_name,
                "captain": captain,
                "date_of_birth": clean_note(row.get("Date of birth (age)", "")),
                "age": parse_age(row.get("Date of birth (age)", "")),
                "caps": to_int(row.get("Caps", 0)),
                "goals": to_int(row.get("Goals", 0)),
                "club": clean_note(row.get("Club", "")),
            }
            players.append(item)
            team_players.append(item)

        ages = [p["age"] for p in team_players if p["age"] is not None]
        total_caps = sum(p["caps"] for p in team_players)
        total_goals = sum(p["goals"] for p in team_players)
        top_players = sorted(
            team_players,
            key=lambda p: (p["goals"] * 4 + p["caps"], p["caps"]),
            reverse=True,
        )[:5]
        squad_stats[team] = {
            "squad_size": len(team_players),
            "avg_age": round(float(np.mean(ages)), 1) if ages else None,
            "total_caps": int(total_caps),
            "total_goals": int(total_goals),
            "top_players": [
                {
                    "player": p["player"],
                    "position": p["position"],
                    "club": p["club"],
                    "caps": p["caps"],
                    "goals": p["goals"],
                    "captain": p["captain"],
                }
                for p in top_players
            ],
        }

    return group_map, players, squad_stats


def build_fixture_predictions(
    results: pd.DataFrame,
    model: LogisticRegression,
    ratings: dict[str, float],
    form: dict[str, deque[float]],
    group_map: dict[str, str],
) -> list[dict[str, Any]]:
    future = results[
        results["home_score"].isna()
        & results["away_score"].isna()
        & (results["tournament"] == "FIFA World Cup")
    ].copy()
    future["date"] = pd.to_datetime(future["date"])
    future = future.sort_values(["date", "city", "home_team"])

    fixtures: list[dict[str, Any]] = []
    for idx, row in future.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        probs = probabilities_for(
            model,
            home,
            away,
            str(row["tournament"]),
            bool(row["neutral"]),
            ratings,
            form,
        )
        expected_home_points = 3 * probs["home_win"] + probs["draw"]
        expected_away_points = 3 * probs["away_win"] + probs["draw"]
        outcome_probs = {
            home: probs["home_win"],
            "Draw": probs["draw"],
            away: probs["away_win"],
        }
        pick = max(outcome_probs, key=outcome_probs.get)
        fixtures.append(
            {
                "id": f"wc26-{int(idx)}",
                "date": str(row["date"].date()),
                "home_team": home,
                "away_team": away,
                "group": group_map.get(home) or group_map.get(away),
                "city": clean_note(row["city"]),
                "host_country": clean_note(row["country"]),
                "neutral": bool(row["neutral"]),
                "probabilities": {
                    "home_win": round(probs["home_win"], 4),
                    "draw": round(probs["draw"], 4),
                    "away_win": round(probs["away_win"], 4),
                },
                "expected_points": {
                    home: round(float(expected_home_points), 3),
                    away: round(float(expected_away_points), 3),
                },
                "pick": pick,
                "confidence": round(float(max(outcome_probs.values())), 4),
                "rating_gap": round(float(ratings[home] - ratings[away]), 1),
            }
        )
    return fixtures


def expected_group_tables(fixtures: list[dict[str, Any]], teams: list[str]) -> dict[str, list[dict[str, Any]]]:
    table: dict[str, dict[str, Any]] = {
        team: {
            "team": team,
            "group": None,
            "played": 0,
            "expected_points": 0.0,
            "expected_wins": 0.0,
            "expected_draws": 0.0,
            "expected_losses": 0.0,
        }
        for team in teams
    }

    for fixture in fixtures:
        home = fixture["home_team"]
        away = fixture["away_team"]
        group = fixture["group"]
        probs = fixture["probabilities"]
        table[home]["group"] = group
        table[away]["group"] = group
        table[home]["played"] += 1
        table[away]["played"] += 1
        table[home]["expected_points"] += 3 * probs["home_win"] + probs["draw"]
        table[away]["expected_points"] += 3 * probs["away_win"] + probs["draw"]
        table[home]["expected_wins"] += probs["home_win"]
        table[away]["expected_wins"] += probs["away_win"]
        table[home]["expected_draws"] += probs["draw"]
        table[away]["expected_draws"] += probs["draw"]
        table[home]["expected_losses"] += probs["away_win"]
        table[away]["expected_losses"] += probs["home_win"]

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table.values():
        if row["group"]:
            for key in ["expected_points", "expected_wins", "expected_draws", "expected_losses"]:
                row[key] = round(float(row[key]), 3)
            groups[row["group"]].append(row)

    for group in groups:
        groups[group].sort(key=lambda r: (r["expected_points"], r["expected_wins"]), reverse=True)
        for rank, row in enumerate(groups[group], 1):
            row["rank"] = rank

    return dict(sorted(groups.items()))


def sample_score(home_win_prob: float, draw_prob: float, away_win_prob: float, rng: random.Random) -> tuple[int, int]:
    roll = rng.random()
    if roll < home_win_prob:
        margin = 1 + int(rng.random() < 0.24) + int(rng.random() < 0.08)
        away_goals = rng.choice([0, 0, 1, 1, 2])
        return away_goals + margin, away_goals
    if roll < home_win_prob + draw_prob:
        goals = rng.choice([0, 1, 1, 2, 2, 3])
        return goals, goals
    margin = 1 + int(rng.random() < 0.24) + int(rng.random() < 0.08)
    home_goals = rng.choice([0, 0, 1, 1, 2])
    return home_goals, home_goals + margin


def win_probability_neutral(
    team_a: str,
    team_b: str,
    ratings: dict[str, float],
    form: dict[str, deque[float]],
) -> float:
    elo_component = (ratings[team_a] - ratings[team_b]) / 400.0
    form_component = (form_value(form[team_a]) - form_value(form[team_b])) * 0.28
    z = (elo_component + form_component) * 1.45
    return 1.0 / (1.0 + math.exp(-z))


def simulate_tournament(
    fixtures: list[dict[str, Any]],
    group_map: dict[str, str],
    ratings: dict[str, float],
    form: dict[str, deque[float]],
    runs: int,
) -> dict[str, dict[str, float]]:
    rng = random.Random(RANDOM_SEED)
    teams = sorted(group_map.keys())
    counters: dict[str, dict[str, int]] = {
        team: {
            "advance_r32": 0,
            "advance_r16": 0,
            "quarterfinal": 0,
            "semifinal": 0,
            "final": 0,
            "champion": 0,
        }
        for team in teams
    }

    by_group_fixtures: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fixture in fixtures:
        by_group_fixtures[fixture["group"]].append(fixture)

    teams_by_group: dict[str, list[str]] = defaultdict(list)
    for team, group in group_map.items():
        teams_by_group[group].append(team)

    for _ in range(runs):
        qualified: list[dict[str, Any]] = []
        third_place: list[dict[str, Any]] = []

        for group, group_teams in teams_by_group.items():
            rows = {
                team: {"team": team, "group": group, "points": 0, "gd": 0, "gf": 0}
                for team in group_teams
            }
            for fixture in by_group_fixtures[group]:
                probs = fixture["probabilities"]
                hg, ag = sample_score(probs["home_win"], probs["draw"], probs["away_win"], rng)
                home = fixture["home_team"]
                away = fixture["away_team"]
                rows[home]["gf"] += hg
                rows[away]["gf"] += ag
                rows[home]["gd"] += hg - ag
                rows[away]["gd"] += ag - hg
                if hg > ag:
                    rows[home]["points"] += 3
                elif hg < ag:
                    rows[away]["points"] += 3
                else:
                    rows[home]["points"] += 1
                    rows[away]["points"] += 1

            ranked = sorted(
                rows.values(),
                key=lambda r: (r["points"], r["gd"], r["gf"], ratings[r["team"]], rng.random()),
                reverse=True,
            )
            for pos, row in enumerate(ranked, 1):
                row["group_rank"] = pos
                if pos <= 2:
                    qualified.append(row)
                elif pos == 3:
                    third_place.append(row)

        best_thirds = sorted(
            third_place,
            key=lambda r: (r["points"], r["gd"], r["gf"], ratings[r["team"]], rng.random()),
            reverse=True,
        )[:8]
        qualified.extend(best_thirds)

        bracket = sorted(
            qualified,
            key=lambda r: (r["group_rank"] * -1, r["points"], r["gd"], r["gf"], ratings[r["team"]]),
            reverse=True,
        )
        alive = [row["team"] for row in bracket]
        for team in alive:
            counters[team]["advance_r32"] += 1

        round_keys = ["advance_r16", "quarterfinal", "semifinal", "final", "champion"]
        for round_key in round_keys:
            winners: list[str] = []
            for i in range(len(alive) // 2):
                left = alive[i]
                right = alive[-(i + 1)]
                p_left = win_probability_neutral(left, right, ratings, form)
                winner = left if rng.random() < p_left else right
                counters[winner][round_key] += 1
                winners.append(winner)
            alive = winners

    return {
        team: {key: round(value / runs, 4) for key, value in values.items()}
        for team, values in counters.items()
    }


def build_teams(
    group_map: dict[str, str],
    ratings: dict[str, float],
    form: dict[str, deque[float]],
    records: dict[str, dict[str, Any]],
    squad_stats: dict[str, dict[str, Any]],
    simulations: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    ranked = sorted(group_map.keys(), key=lambda team: ratings[team], reverse=True)
    rank_lookup = {team: idx + 1 for idx, team in enumerate(ranked)}
    teams: list[dict[str, Any]] = []
    for team in ranked:
        rec = records.get(team, {})
        teams.append(
            {
                "team": team,
                "group": group_map[team],
                "elo": round(float(ratings[team]), 1),
                "rank": rank_lookup[team],
                "recent_form_points": round(float(form_value(form[team])), 3),
                "record": rec,
                "squad": squad_stats.get(team, {}),
                "simulation": simulations.get(team, {}),
            }
        )
    return teams


def build(force_download: bool, simulations: int) -> None:
    ensure_dirs()

    downloaded_results = download(RESULTS_URL, RESULTS_PATH, force_download)
    downloaded_squads = download(SQUADS_URL, SQUADS_HTML_PATH, force_download)

    results = pd.read_csv(RESULTS_PATH)
    results["date"] = pd.to_datetime(results["date"])
    html = SQUADS_HTML_PATH.read_text(encoding="utf-8")

    group_map, players, squad_stats = parse_groups_and_players(html)
    model, ratings, form, records, model_metadata = train_model(results)
    fixtures = build_fixture_predictions(results, model, ratings, form, group_map)
    group_tables = expected_group_tables(fixtures, sorted(group_map.keys()))
    sim = simulate_tournament(fixtures, group_map, ratings, form, simulations)
    teams = build_teams(group_map, ratings, form, records, squad_stats, sim)

    json_dump(
        OUT_DIR / "predictions.json",
        {
            "fixtures": fixtures,
            "groups": group_tables,
            "simulation_runs": simulations,
            "format_note": (
                "Round-of-32 qualification follows the 2026 format: top two teams "
                "from each group plus the eight best third-placed teams. Knockout "
                "pairings are an approximate strength-seeded bracket, not the official FIFA bracket."
            ),
        },
    )
    json_dump(OUT_DIR / "players.json", {"players": players})
    json_dump(OUT_DIR / "teams.json", {"teams": teams})
    json_dump(
        OUT_DIR / "manifest.json",
        {
            "generated_at": now_iso(),
            "data_sources": [
                {
                    "name": "International football results by martj42",
                    "url": RESULTS_URL,
                    "cached_file": str(RESULTS_PATH.relative_to(ROOT)).replace("\\", "/"),
                    "downloaded_this_run": downloaded_results,
                },
                {
                    "name": "2026 FIFA World Cup squads on Wikipedia",
                    "url": SQUADS_URL,
                    "cached_file": str(SQUADS_HTML_PATH.relative_to(ROOT)).replace("\\", "/"),
                    "downloaded_this_run": downloaded_squads,
                },
            ],
            "model": {
                "type": "Elo ratings + multinomial logistic regression + Monte Carlo simulation",
                "home_advantage_elo_points": HOME_ADVANTAGE,
                "random_seed": RANDOM_SEED,
                **model_metadata,
            },
            "counts": {
                "teams": len(group_map),
                "players": len(players),
                "fixtures_predicted": len(fixtures),
                "historical_rows": int(len(results)),
            },
            "disclaimer": (
                "This is an educational forecasting model for a portfolio/GitHub project. "
                "It is not betting advice and does not use private team information."
            ),
        },
    )

    print(f"Generated {len(group_map)} teams, {len(players)} players, {len(fixtures)} fixtures.")
    print(f"Output directory: {OUT_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build processed data for the World Cup AI predictor.")
    parser.add_argument("--force-download", action="store_true", help="Refresh raw CSV/HTML files from the web.")
    parser.add_argument("--simulations", type=int, default=5000, help="Monte Carlo runs for tournament probabilities.")
    args = parser.parse_args()
    build(force_download=args.force_download, simulations=max(500, args.simulations))


if __name__ == "__main__":
    main()
