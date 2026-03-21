"""
=============================================================================
BRASILEIRÃO SÉRIE A — CARD EVENTS EXTRACTOR (2018–2023)
Source  : SofaScore unofficial API  (tournament ID = 325)
Output  : cartoes_brasileirao_2018_2023.csv
          jogadores_unicos_com_foto.csv

Columns in output:
    season, match_date, match_id, round,
    home_team, home_team_id, away_team, away_team_id,
    player_id, player_name, player_slug, position,
    club, club_id, home_away,
    card_type,   ← yellow | red | yellow_red
    minute, minute_extra,
    score_home_at_card, score_away_at_card,
    player_photo_url

Runtime : ~1–2 hours for ~2280 matches (2s delay + jitter between calls)
=============================================================================
"""

import cloudscraper
import time
import random
import json
import csv
import os
from datetime import datetime

# ── CONFIG ─────────────────────────────────────────────────────────────────
TOURNAMENT_ID   = 325
TARGET_YEARS    = [2018, 2019, 2020, 2021, 2022, 2023]
DELAY_MATCH     = 2.0
DELAY_ROUND     = 0.8
OUTPUT_FILE     = "cartoes_brasileirao_2018_2023.csv"
CHECKPOINT_FILE = "checkpoint_processed_matches.json"
MAX_RETRIES     = 4

BASE = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent"       : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept"           : "application/json, text/plain, */*",
    "Accept-Language"  : "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding"  : "gzip, deflate, br",
    "Referer"          : "https://www.sofascore.com/",
    "Origin"           : "https://www.sofascore.com",
    "Sec-Ch-Ua"        : '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile" : "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest"   : "empty",
    "Sec-Fetch-Mode"   : "cors",
    "Sec-Fetch-Site"   : "same-site",
    "Cache-Control"    : "no-cache",
    "Pragma"           : "no-cache",
}

def make_scraper():
    s = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    s.headers.update(HEADERS)
    return s

scraper = make_scraper()


# ── HTTP GET with retry logic ───────────────────────────────────────────────
def get(url):
    global scraper
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = scraper.get(url, timeout=20)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 404:
                return None
            elif r.status_code == 429:
                wait = 60 * attempt
                print(f"    [429] Rate limited — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
            elif r.status_code == 403:
                wait = 30 * attempt
                print(f"    [403] Blocked — refreshing session and waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                scraper = make_scraper()
                time.sleep(wait)
            else:
                print(f"    [HTTP {r.status_code}] {url} — waiting 5s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(5)
        except Exception as e:
            print(f"    [Error] {e} — retry {attempt}/{MAX_RETRIES}")
            time.sleep(5)
    return None


# ── STEP 1: GET ALL SEASON IDs ──────────────────────────────────────────────
def get_seasons():
    print("\n[1/4] Fetching season IDs for tournament 325 (Brasileirão Série A)...")
    data = get(f"{BASE}/unique-tournament/{TOURNAMENT_ID}/seasons")
    if not data:
        raise RuntimeError("Could not fetch seasons list — check connectivity.")

    seasons = {}
    for s in data.get("seasons", []):
        year_raw = s.get("year", "")
        sid      = s.get("id")
        try:
            year_int = int(str(year_raw)[:4])
            if year_int in TARGET_YEARS:
                seasons[year_int] = sid
                print(f"  Season {year_raw!r} → ID {sid}")
        except (ValueError, TypeError):
            pass

    if not seasons:
        raise RuntimeError("No matching seasons found.")
    return seasons


# ── STEP 2: GET ALL MATCH IDs PER SEASON ───────────────────────────────────
def get_match_ids_for_season(season_id, year):
    print(f"\n[2/4] Collecting match IDs — season {year} (season_id={season_id})...")
    matches = []

    for round_n in range(1, 39):
        url  = f"{BASE}/unique-tournament/{TOURNAMENT_ID}/season/{season_id}/events/round/{round_n}"
        data = get(url)

        if not data or not data.get("events"):
            print(f"  Round {round_n:2d}: no events — stopping")
            break

        for event in data["events"]:
            ts = event.get("startTimestamp", 0)
            matches.append({
                "season"      : year,
                "match_id"    : event["id"],
                "round"       : round_n,
                "match_date"  : datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "",
                "home_team"   : event.get("homeTeam", {}).get("name", ""),
                "home_team_id": event.get("homeTeam", {}).get("id", ""),
                "away_team"   : event.get("awayTeam", {}).get("name", ""),
                "away_team_id": event.get("awayTeam", {}).get("id", ""),
            })

        print(f"  Round {round_n:2d}: {len(data['events'])} matches")
        time.sleep(DELAY_ROUND)

    print(f"  → {len(matches)} matches found for {year}")
    return matches


# ── STEP 3: EXTRACT CARD INCIDENTS ─────────────────────────────────────────
CARD_TYPE_MAP = {
    "yellow"    : "yellow",
    "red"       : "red",
    "yellowRed" : "yellow_red",
}

def extract_cards_from_match(match):
    url  = f"{BASE}/event/{match['match_id']}/incidents"
    data = get(url)
    if not data:
        return []

    cards = []
    for inc in data.get("incidents", []):
        if inc.get("incidentType") != "card":
            continue

        card_type = CARD_TYPE_MAP.get(inc.get("incidentClass", ""))
        if not card_type:
            continue

        player = inc.get("player", {}) or {}
        player_id = player.get("id")
        if not player_id:
            continue

        home_away = "home" if inc.get("isHome", False) else "away"
        club      = match["home_team"]    if home_away == "home" else match["away_team"]
        club_id   = match["home_team_id"] if home_away == "home" else match["away_team_id"]

        score_raw     = inc.get("score", {}) or {}
        score_current = score_raw.get("current", {}) if isinstance(score_raw, dict) else {}
        score_home    = score_current.get("home", "") if isinstance(score_current, dict) else ""
        score_away    = score_current.get("away", "") if isinstance(score_current, dict) else ""

        cards.append({
            "season"             : match["season"],
            "match_date"         : match["match_date"],
            "match_id"           : match["match_id"],
            "round"              : match["round"],
            "home_team"          : match["home_team"],
            "home_team_id"       : match["home_team_id"],
            "away_team"          : match["away_team"],
            "away_team_id"       : match["away_team_id"],
            "player_id"          : player_id,
            "player_name"        : player.get("name", ""),
            "player_slug"        : player.get("slug", ""),
            "position"           : player.get("position", ""),
            "club"               : club,
            "club_id"            : club_id,
            "home_away"          : home_away,
            "card_type"          : card_type,
            "minute"             : inc.get("time", ""),
            "minute_extra"       : inc.get("addedTime", ""),
            "score_home_at_card" : score_home,
            "score_away_at_card" : score_away,
            "player_photo_url"   : f"https://api.sofascore.com/api/v1/player/{player_id}/image",
        })

    return cards


# ── STEP 4: MAIN LOOP ───────────────────────────────────────────────────────
CSV_COLUMNS = [
    "season","match_date","match_id","round",
    "home_team","home_team_id","away_team","away_team_id",
    "player_id","player_name","player_slug","position",
    "club","club_id","home_away",
    "card_type","minute","minute_extra",
    "score_home_at_card","score_away_at_card",
    "player_photo_url",
]

def main():
    print("=" * 65)
    print("BRASILEIRÃO SÉRIE A — CARD EVENTS EXTRACTOR")
    print("SofaScore tournament ID: 325  |  Seasons: 2018–2023")
    print("=" * 65)

    processed_match_ids = set()
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            processed_match_ids = set(json.load(f))
        print(f"\nResuming — {len(processed_match_ids)} matches already processed.")

    file_exists = os.path.exists(OUTPUT_FILE)
    out_f  = open(OUTPUT_FILE, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=CSV_COLUMNS)
    if not file_exists:
        writer.writeheader()

    total_cards = 0
    seasons     = get_seasons()

    for year, season_id in sorted(seasons.items()):
        all_matches = get_match_ids_for_season(season_id, year)
        pending     = [m for m in all_matches if m["match_id"] not in processed_match_ids]

        print(f"\n[3/4] Extracting cards — {year}: {len(pending)} matches to process "
              f"({len(all_matches) - len(pending)} already done)")

        for i, match in enumerate(pending, start=1):
            cards = extract_cards_from_match(match)
            for c in cards:
                writer.writerow(c)
            out_f.flush()

            total_cards += len(cards)
            processed_match_ids.add(match["match_id"])

            print(f"  [{year}] Match {i}/{len(pending)} (id={match['match_id']}) "
                  f"— {len(cards)} cards | total so far: {total_cards}")

            if i % 50 == 0:
                with open(CHECKPOINT_FILE, "w") as f:
                    json.dump(list(processed_match_ids), f)
                print(f"  >> Checkpoint saved ({i}/{len(pending)} done, {total_cards} cards)")

            time.sleep(DELAY_MATCH + random.uniform(0, 0.5))

        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(list(processed_match_ids), f)
        print(f"  ✓ Season {year} complete")

    out_f.close()

    print("\n" + "=" * 65)
    print("EXTRACTION COMPLETE")
    print(f"Output : {OUTPUT_FILE}")
    print(f"Cards  : {total_cards}")
    print("=" * 65)

    validate_and_save_players()


# ── STEP 5: VALIDATION + UNIQUE PLAYER LIST ─────────────────────────────────
def validate_and_save_players():
    import pandas as pd

    print("\n[4/4] Validating output and building player list...")

    if not os.path.exists(OUTPUT_FILE):
        print(f"ERROR: {OUTPUT_FILE} not found!")
        return

    df = pd.read_csv(OUTPUT_FILE)

    print("\n" + "=" * 55)
    print("VALIDATION REPORT")
    print("=" * 55)
    print(f"Total card rows          : {len(df):,}")
    print(f"Unique player IDs        : {df['player_id'].nunique():,}")
    print(f"Rows with missing player  : {df['player_id'].isna().sum()}")

    print("\nCards by type:")
    print(df["card_type"].value_counts().to_string())

    print("\nCards by season:")
    print(df.groupby("season")["card_type"].count().rename("cards").to_string())

    player_list = (
        df[["player_id","player_name","player_slug","position","player_photo_url"]]
        .drop_duplicates(subset="player_id")
        .sort_values("player_name")
        .reset_index(drop=True)
    )
    player_list.to_csv("jogadores_unicos_com_foto.csv", index=False)

    print(f"\nFile: {OUTPUT_FILE}  → {len(df):,} rows")
    print(f"File: jogadores_unicos_com_foto.csv → {len(player_list):,} unique players")
    print("\nDone. Ready for R analysis.")


if __name__ == "__main__":
    main()
commit

# =============================================================================
# HOW TO RUN:
#   pip install cloudscraper pandas openpyxl
#   python extrair_cartoes_sofascore.py
#
# TO RESUME after interruption:
#   Just re-run — checkpoint_processed_matches.json tracks progress.
# =============================================================================
