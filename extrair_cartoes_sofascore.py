"""
=============================================================================
BRASILEIRÃO SÉRIE A — CARD EVENTS EXTRACTOR (2018–2023)
Source  : SofaScore unofficial API  (tournament ID = 325)
Output  : cartoes_brasileirao_2018_2023.csv

Columns in output:
    season, match_date, match_id, round,
    home_team, home_team_id, away_team, away_team_id,
    player_id, player_name, player_slug, position,
    club, club_id, home_away,
    card_type,   ← yellow | red | yellow_red
    minute, minute_extra,
    score_home_at_card, score_away_at_card,
    player_photo_url     ← ready to feed straight into Claude Vision

Key advantage over FBref approach:
    player_id is the NATIVE SofaScore ID — photo URL is simply
    https://api.sofascore.com/api/v1/player/{player_id}/image
    No name-matching, no search calls, zero ambiguity.

Runtime : ~45–90 min for ~2280 matches (polite 1.5s delay between calls)
=============================================================================
"""

import requests
import time
import json
import csv
import os
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
TOURNAMENT_ID   = 325          # Brasileirão Série A
TARGET_YEARS    = [2018, 2019, 2020, 2021, 2022, 2023]
DELAY_MATCH     = 1.5          # seconds between match calls (Cloudflare limit)
DELAY_ROUND     = 0.8          # seconds between round calls
OUTPUT_FILE     = "cartoes_brasileirao_2018_2023.csv"
CHECKPOINT_FILE = "checkpoint_processed_matches.json"

BASE  = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "en-US,en;q=0.9",
    "Referer"         : "https://www.sofascore.com/",
    "Origin"          : "https://www.sofascore.com",
}

def get(url, retries=3):
    """GET with retry logic."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                print(f"    Rate limited — waiting 30s...")
                time.sleep(30)
            elif r.status_code == 403:
                print(f"    403 Cloudflare block — waiting 60s...")
                time.sleep(60)
            else:
                print(f"    HTTP {r.status_code} for {url}")
                time.sleep(5)
        except Exception as e:
            print(f"    Request error: {e} — retry {attempt+1}/{retries}")
            time.sleep(5)
    return None

# ── STEP 1: GET ALL SEASON IDs ────────────────────────────────────────────────
def get_seasons():
    print("\n[1/4] Fetching season IDs for tournament 325 (Brasileirão Série A)...")
    data = get(f"{BASE}/unique-tournament/{TOURNAMENT_ID}/seasons")
    if not data:
        raise RuntimeError("Could not fetch seasons")

    seasons = {}
    for s in data.get("seasons", []):
        year = s.get("year")
        sid  = s.get("id")
        # SofaScore stores year as "2018" or "18/19" — filter by target years
        try:
            if int(str(year)[:4]) in TARGET_YEARS:
                seasons[int(str(year)[:4])] = sid
                print(f"  Season {year} → ID {sid}")
        except Exception:
            pass

    if not seasons:
        raise RuntimeError("No matching seasons found. Check TARGET_YEARS or tournament ID.")
    return seasons

# ── STEP 2: GET ALL MATCH IDs PER SEASON (via rounds) ────────────────────────
def get_match_ids_for_season(season_id, year):
    print(f"\n[2/4] Collecting match IDs for season {year} (season_id={season_id})...")
    matches = []
    round_n = 1

    while True:
        url  = f"{BASE}/unique-tournament/{TOURNAMENT_ID}/season/{season_id}/events/round/{round_n}"
        data = get(url)
        if not data or not data.get("events"):
            # No more rounds
            break

        for event in data["events"]:
            matches.append({
                "season"      : year,
                "match_id"    : event["id"],
                "round"       : round_n,
                "match_date"  : datetime.fromtimestamp(event.get("startTimestamp", 0)).strftime("%Y-%m-%d"),
                "home_team"   : event.get("homeTeam", {}).get("name", ""),
                "home_team_id": event.get("homeTeam", {}).get("id", ""),
                "away_team"   : event.get("awayTeam", {}).get("name", ""),
                "away_team_id": event.get("awayTeam", {}).get("id", ""),
            })

        print(f"  Round {round_n:2d}: {len(data['events'])} matches")
        round_n += 1
        time.sleep(DELAY_ROUND)

        # Safety cap — Série A has 38 rounds
        if round_n > 40:
            break

    print(f"  → {len(matches)} matches found for {year}")
    return matches

# ── STEP 3: EXTRACT CARD INCIDENTS FROM EACH MATCH ───────────────────────────
CARD_TYPE_MAP = {
    "yellow"    : "yellow",
    "red"       : "red",
    "yellowRed" : "yellow_red",   # second yellow → red
}

def extract_cards_from_match(match):
    url  = f"{BASE}/event/{match['match_id']}/incidents"
    data = get(url)
    if not data:
        return []

    cards = []
    for inc in data.get("incidents", []):
        inc_type  = inc.get("incidentType", "")
        inc_class = inc.get("incidentClass", "")

        # Only card incidents
        if inc_type != "card":
            continue

        card_type = CARD_TYPE_MAP.get(inc_class)
        if not card_type:
            continue

        player = inc.get("player", {})
        if not player or not player.get("id"):
            continue   # skip if no player data

        player_id = player["id"]

        # Determine home/away from isHome flag
        home_away = "home" if inc.get("isHome", False) else "away"
        club      = match["home_team"] if home_away == "home" else match["away_team"]
        club_id   = match["home_team_id"] if home_away == "home" else match["away_team_id"]

        # Score at time of card
        score = inc.get("score", {})

        cards.append({
            "season"              : match["season"],
            "match_date"          : match["match_date"],
            "match_id"            : match["match_id"],
            "round"               : match["round"],
            "home_team"           : match["home_team"],
            "home_team_id"        : match["home_team_id"],
            "away_team"           : match["away_team"],
            "away_team_id"        : match["away_team_id"],
            # ── Player info — native SofaScore IDs ──
            "player_id"           : player_id,
            "player_name"         : player.get("name", ""),
            "player_slug"         : player.get("slug", ""),
            "position"            : player.get("position", ""),
            "club"                : club,
            "club_id"             : club_id,
            "home_away"           : home_away,
            # ── Card details ──
            "card_type"           : card_type,
            "minute"              : inc.get("time", ""),
            "minute_extra"        : inc.get("addedTime", ""),
            "score_home_at_card"  : score.get("current", {}).get("home", "") if isinstance(score.get("current"), dict) else "",
            "score_away_at_card"  : score.get("current", {}).get("away", "") if isinstance(score.get("current"), dict) else "",
            # ── Pre-built photo URL — no extra API call needed ──
            "player_photo_url"    : f"{BASE}/player/{player_id}/image",
        })

    return cards

# ── STEP 4: MAIN LOOP ─────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("BRASILEIRÃO SÉRIE A — CARD EVENTS EXTRACTOR")
    print("SofaScore tournament ID: 325")
    print("=" * 65)

    # Load checkpoint (resume support)
    processed_match_ids = set()
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            processed_match_ids = set(json.load(f))
        print(f"\nResuming — {len(processed_match_ids)} matches already processed.")

    # Open output CSV (append mode for resume)
    file_exists  = os.path.exists(OUTPUT_FILE)
    csv_columns  = [
        "season","match_date","match_id","round",
        "home_team","home_team_id","away_team","away_team_id",
        "player_id","player_name","player_slug","position",
        "club","club_id","home_away",
        "card_type","minute","minute_extra",
        "score_home_at_card","score_away_at_card",
        "player_photo_url",
    ]

    out_f  = open(OUTPUT_FILE, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=csv_columns)
    if not file_exists:
        writer.writeheader()

    total_cards = 0
    seasons     = get_seasons()

    for year, season_id in sorted(seasons.items()):
        all_matches = get_match_ids_for_season(season_id, year)
        pending     = [m for m in all_matches if m["match_id"] not in processed_match_ids]

        print(f"\n[3/4] Extracting cards — {year}: {len(pending)} matches to process...")

        for i, match in enumerate(pending):
            cards = extract_cards_from_match(match)
            for c in cards:
                writer.writerow(c)
            out_f.flush()

            total_cards += len(cards)
            processed_match_ids.add(match["match_id"])

            # Save checkpoint every 50 matches
            if (i + 1) % 50 == 0:
                with open(CHECKPOINT_FILE, "w") as f:
                    json.dump(list(processed_match_ids), f)
                print(f"  Checkpoint saved — {i+1}/{len(pending)} done ({total_cards} cards so far)")

            time.sleep(DELAY_MATCH)

        # Season done — save checkpoint
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(list(processed_match_ids), f)
        print(f"  ✓ Season {year} complete")

    out_f.close()

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"EXTRACTION COMPLETE")
    print(f"Output file : {OUTPUT_FILE}")
    print(f"Total cards : {total_cards}")
    print("=" * 65)

    # Quick breakdown
    import pandas as pd
    df = pd.read_csv(OUTPUT_FILE)
    print(f"\nRows in file      : {len(df)}")
    print(f"Unique players    : {df['player_id'].nunique()}")
    print(f"Unique player IDs : confirmed — no name-matching needed\n")
    print("Cards by type:")
    print(df["card_type"].value_counts().to_string())
    print("\nCards by season:")
    print(df.groupby("season")["card_type"].count().to_string())

    # Save unique player list with photo URLs ready for classifier
    player_list = (
        df[["player_id","player_name","player_slug","position","player_photo_url"]]
        .drop_duplicates(subset="player_id")
        .sort_values("player_name")
    )
    player_list.to_csv("jogadores_unicos_com_foto.csv", index=False)
    print(f"\nUnique player list saved: jogadores_unicos_com_foto.csv")
    print(f"  → {len(player_list)} unique players")
    print(f"  → photo URLs pre-built, ready for Claude Vision classifier")
    print("\nNext step: open the classifier app and upload jogadores_unicos_com_foto.csv")

if __name__ == "__main__":
    main()

# =============================================================================
# HOW TO RUN:
#
#   pip install requests pandas
#   python extrair_cartoes_sofascore.py
#
# TO RESUME after interruption:
#   Just re-run the script — checkpoint_processed_matches.json tracks progress
#
# RATE LIMITING:
#   Default: 1.5s between match calls (~45–90 min total)
#   If you get repeated 429 errors, increase DELAY_MATCH to 2.5
#
# OUTPUT FILES:
#   cartoes_brasileirao_2018_2023.csv   ← full dataset, one row per card
#   jogadores_unicos_com_foto.csv       ← deduplicated players + photo URLs
#   checkpoint_processed_matches.json  ← resume state (safe to delete after)
# =============================================================================
