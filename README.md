# World Cup AI Predictor

A static 2026 FIFA World Cup prediction dashboard built for GitHub Pages. It uses public international match results, public squad tables, Elo ratings, multinomial logistic regression, and a Monte Carlo tournament simulation.

The app is intentionally simple to publish: generated JSON lives in `data/processed`, and `index.html` reads it directly in the browser. No backend is required after the data is generated.

## Features

- 72 group-stage match predictions with home win, draw, and away win probabilities
- Expected group tables for Groups A-L
- Team strength rankings and champion probabilities from Monte Carlo simulation
- Player database for the 48 squads, with caps, goals, clubs, positions, and captains
- Player photo cards with Wikimedia/Wikipedia thumbnail URLs when available
- Six-attribute, 6-star radar charts for player attack, creativity, defense, experience, physical profile, and impact
- Clickable player links to Wikipedia source pages and Hupu search pages
- Chinese/English language toggle in the browser
- Public, reproducible data build script
- GitHub Pages friendly static frontend

## Data Sources

- International match results CSV: `https://raw.githubusercontent.com/martj42/international_results/master/results.csv`
- 2026 FIFA World Cup squads page: `https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads`

The raw download cache is ignored by Git. Regenerate it whenever you want fresh data.

## Model

The data script trains a lightweight educational model:

1. Historical international matches update per-team Elo ratings.
2. Recent form is tracked from each team's latest matches.
3. Logistic regression maps Elo gap, recent form, neutral-site status, and tournament type to win/draw/loss probabilities.
4. A Monte Carlo simulation estimates advancement and champion probabilities.

This is a portfolio/demo forecast. It is not betting advice.

## Player Images And Ability Radars

`players.json` includes estimated 6-star attributes for every player. The scores are derived from public metadata: caps, goals, age, position, team Elo, and recent team form. They are not EA, FIFA, Opta, or official ratings.

`player_media.json` stores Wikimedia/Wikipedia thumbnail URLs resolved from player page links. The repository does not download or commit image binaries. Players without a reliable thumbnail use an initials-based fallback avatar in the frontend.

Player cards and table rows also include generated Hupu search links such as `https://bbs.hupu.com/search?q=C%E7%BD%97`. The app links out to public Hupu search pages instead of bulk-scraping Hupu posts into the repository, because Hupu content is forum-based and can be rate-limited or change structure.

## Run Locally

```powershell
cd D:\worldcup-ai-predictor
python -m pip install -r requirements.txt
python scripts\build_data.py --force-download --simulations 5000
python scripts\enrich_player_media.py --strategy rest --top-ranked --limit 120 --delay 0.7 --retries 2
python -m http.server 8016
```

Open:

```text
http://localhost:8016
```

## Update Data

```powershell
python scripts\build_data.py --force-download --simulations 5000
python scripts\enrich_player_media.py --strategy rest --top-ranked --limit 120 --delay 0.7 --retries 2
```

If a source page changes structure, the script will continue to use local cached files when available. For long-term production use, consider replacing the Wikipedia squad parser with an official licensed feed.

To keep enriching more player images later, increase `--limit` or run chunks with `--offset`. The script keeps existing media records and only queries unresolved players.

## Publish To GitHub

```powershell
cd D:\worldcup-ai-predictor
git init
git add .
git commit -m "Build World Cup AI predictor"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/worldcup-ai-predictor.git
git push -u origin main
```

Then enable GitHub Pages:

1. Open the repository on GitHub.
2. Go to **Settings** -> **Pages**.
3. Set source to **Deploy from a branch**.
4. Choose `main` and `/root`.
5. Save and wait for the Pages URL.

## Project Structure

```text
.
|-- data
|   |-- processed
|   |   |-- manifest.json
|   |   |-- player_media.json
|   |   |-- players.json
|   |   |-- predictions.json
|   |   `-- teams.json
|   `-- raw
|-- scripts
|   |-- build_data.py
|   `-- enrich_player_media.py
|-- src
|   |-- app.js
|   `-- styles.css
|-- index.html
|-- requirements.txt
`-- README.md
```

## Notes

- `data/processed/*.json` is committed so the site works immediately on GitHub Pages.
- `data/raw/*` is ignored because it is a large downloaded cache.
- Do not commit Kaggle API tokens, `.env`, or `kaggle.json`.
