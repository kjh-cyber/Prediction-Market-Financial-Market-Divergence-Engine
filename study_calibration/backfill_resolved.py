"""Backfill already-RESOLVED Polymarket markets for a calibration study.

Fetches closed binary (Yes/No) markets that settled cleanly (one outcome → 1,
the other → 0), pulls each market's full YES-probability history from the CLOB,
and stores probability trajectory + official resolution label.

PM-only (no financial data). Writes to its OWN db (data/calibration.db) so the
frozen divergence.db is never touched. Idempotent + resumable: markets already
stored are skipped, so it can be re-run to grow the sample.

Usage:
  .venv/bin/python study_calibration/backfill_resolved.py [target_count]
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "calibration.db"

END_MIN = "2024-06-01"        # only markets ending after this (CLOB history exists)
END_MAX = "2026-07-15"        # settled before collection stopped
VOL_MIN = 30000               # liquidity floor
PAGE = 100
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
SLEEP = 0.06                  # polite pause between CLOB calls

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def init_db(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS resolved_markets (
        condition_id TEXT PRIMARY KEY,
        question TEXT, slug TEXT, category TEXT,
        yes_token TEXT, outcome INTEGER,          -- 1 = YES settled true, 0 = NO
        end_date TEXT, end_ts INTEGER, volume REAL,
        n_points INTEGER, collected_at TEXT
    );
    CREATE TABLE IF NOT EXISTS resolved_prices (
        yes_token TEXT, ts INTEGER, p REAL,       -- p = P(YES) over time
        PRIMARY KEY (yes_token, ts)
    );
    """)
    con.commit()


def parse_binary(m):
    """Return (yes_token, outcome 0/1) if a clean Yes/No settlement, else None."""
    try:
        outcomes = json.loads(m.get("outcomes", "[]"))
        op = [str(x) for x in json.loads(m.get("outcomePrices", "[]"))]
        tk = json.loads(m.get("clobTokenIds", "[]"))
    except (json.JSONDecodeError, TypeError):
        return None
    if len(outcomes) != 2 or len(op) != 2 or len(tk) != 2:
        return None
    low = [o.lower() for o in outcomes]
    if "yes" not in low or "no" not in low:
        return None
    if sorted(op) != ["0", "1"]:            # must be a clean binary settlement
        return None
    yi = low.index("yes")
    return tk[yi], (1 if op[yi] == "1" else 0)


def fetch_history(clob, token):
    """YES-probability history via CLOB. interval=max with coarse fidelity fallback."""
    for params in ({"market": token, "interval": "max", "fidelity": "720"},
                   {"market": token, "interval": "1w"},
                   {"market": token, "interval": "1d"}):
        try:
            h = clob.get("/prices-history", params=params)
            if h.status_code == 200:
                pts = h.json().get("history", [])
                if pts:
                    return [(int(p["t"]), float(p["p"])) for p in pts]
        except httpx.HTTPError:
            continue
    return []


def main():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    init_db(con)
    have = {r[0] for r in con.execute("SELECT condition_id FROM resolved_markets")}
    print(f"이미 보유: {len(have)}개 · 목표: {TARGET}개")

    g = httpx.Client(base_url=GAMMA, timeout=30)
    c = httpx.Client(base_url=CLOB, timeout=30)
    stored = len(have)
    offset = 0
    empty_pages = 0

    try:
        while stored < TARGET:
            r = g.get("/markets", params={
                "closed": "true", "end_date_min": END_MIN, "end_date_max": END_MAX,
                "volume_num_min": VOL_MIN, "order": "volumeNum", "ascending": "false",
                "limit": PAGE, "offset": offset})
            offset += PAGE
            if r.status_code != 200:
                print(f"gamma {r.status_code} at offset {offset}; stop"); break
            data = r.json()
            if not data:
                empty_pages += 1
                if empty_pages >= 2:
                    print("no more markets; stop"); break
                continue
            empty_pages = 0

            for m in data:
                cid = str(m.get("conditionId") or m.get("id"))
                if not cid or cid in have:
                    continue
                pb = parse_binary(m)
                if pb is None:
                    continue
                yes_token, outcome = pb
                pts = fetch_history(c, yes_token)
                time.sleep(SLEEP)
                if len(pts) < 5:                 # need a usable trajectory
                    continue
                end_iso = m.get("endDate", "") or ""
                try:
                    end_ts = int(dt.datetime.fromisoformat(
                        end_iso.replace("Z", "+00:00")).timestamp())
                except ValueError:
                    end_ts = pts[-1][0]
                con.execute(
                    "INSERT OR REPLACE INTO resolved_markets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, m.get("question", ""), m.get("slug", ""),
                     m.get("category", ""), yes_token, outcome, end_iso[:10], end_ts,
                     float(m.get("volumeNum", 0) or 0), len(pts),
                     dt.datetime.fromtimestamp(pts[-1][0], dt.UTC).isoformat()))
                con.executemany(
                    "INSERT OR REPLACE INTO resolved_prices VALUES (?,?,?)",
                    [(yes_token, t, p) for t, p in pts])
                have.add(cid)
                stored += 1
                if stored % 25 == 0:
                    con.commit()
                    print(f"  저장 {stored}개 (offset {offset}) 최근: {m.get('question','')[:45]}")
                if stored >= TARGET:
                    break
        con.commit()
    finally:
        g.close(); c.close()

    n_mk = con.execute("SELECT COUNT(*) FROM resolved_markets").fetchone()[0]
    n_yes = con.execute("SELECT COUNT(*) FROM resolved_markets WHERE outcome=1").fetchone()[0]
    n_px = con.execute("SELECT COUNT(*) FROM resolved_prices").fetchone()[0]
    con.close()
    print(f"\n완료: 마켓 {n_mk}개 (YES {n_yes}/NO {n_mk-n_yes}) · 가격포인트 {n_px:,} → {DB}")


if __name__ == "__main__":
    main()
