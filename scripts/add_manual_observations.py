#!/usr/bin/env python3
"""
Utility script to manually insert verified Board Diversity Matrix observations
into the database.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime

import config as C

# Get current UTC timestamp in ISO-8601
NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_observation(cur, *, cik, accession_or_url, source_type, form_type,
                       publication_date, observed_text, matched_query,
                       fetch_timestamp, confidence, source_url=None):
    # Check if already exists
    cur.execute(
        "SELECT observation_id FROM disclosure_observations WHERE cik=? AND accession_or_url=?",
        (cik, accession_or_url)
    )
    existing = cur.fetchone()
    if existing:
        print(f"Observation for CIK {cik} at {accession_or_url} already exists. Skipping.")
        return existing[0]

    cur.execute("""INSERT INTO disclosure_observations
        (cik,accession_or_url,source_type,form_type,publication_date,
         observed_text,matched_query,fetch_timestamp,confidence)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (cik, accession_or_url, source_type, form_type, publication_date,
         observed_text, matched_query, fetch_timestamp, confidence))
    obs_id = cur.lastrowid

    cols = ("accession_or_url", "source_type", "form_type", "publication_date",
            "observed_text", "matched_query", "fetch_timestamp", "confidence")
    values = {
        "accession_or_url": accession_or_url,
        "source_type": source_type,
        "form_type": form_type,
        "publication_date": publication_date,
        "observed_text": observed_text,
        "matched_query": matched_query,
        "fetch_timestamp": fetch_timestamp,
        "confidence": confidence,
    }

    # Determine source_id based on source_type
    src_id = "SRC_WAYBACK_CDX" if source_type == "website_archive" else "SRC_EDGAR_SUBMISSIONS"

    for col in cols:
        cur.execute("""INSERT INTO field_provenance
            (target_table,row_key,column_name,is_derived,source_id,source_url,
             source_location,observed_text,raw_value,normalized_value,formula,
             rule_source_id,extraction_method,extracted_utc,confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("disclosure_observations", str(obs_id), col, 0, src_id, source_url or accession_or_url,
             f"disclosure_observations.{col}; CIK {cik}", observed_text,
             str(values[col]) if values[col] is not None else None,
             str(values[col]) if values[col] is not None else None,
             None, None, source_type, fetch_timestamp, confidence))

    print(f"Successfully inserted manual observation ID {obs_id} for CIK {cik}")
    return obs_id


def main():
    parser = argparse.ArgumentParser(description="Insert manual disclosure observations.")
    parser.add_argument("--json-file", required=True, help="Path to JSON file containing observations list.")
    args = parser.parse_args()

    if not os.path.exists(args.json_file):
        print(f"Error: file not found: {args.json_file}")
        return

    with open(args.json_file, encoding="utf-8") as f:
        observations = json.load(f)

    print(f"Loaded {len(observations)} observations from {args.json_file}")

    conn = sqlite3.connect(C.SQLITE_PATH)
    cur = conn.cursor()

    count = 0
    for obs in observations:
        cik = obs.get("cik")
        url = obs.get("accession_or_url")
        source_type = obs.get("source_type", "website_archive")
        form_type = obs.get("form_type")
        pub_date = obs.get("publication_date")
        observed_text = obs.get("observed_text")
        matched_query = obs.get("matched_query", "Board Diversity Matrix")
        confidence = obs.get("confidence", 0.9)

        if not cik or not url or not pub_date or not observed_text:
            print(f"Warning: Missing required fields in observation: {obs}. Skipping.")
            continue

        insert_observation(
            cur,
            cik=str(cik),
            accession_or_url=url,
            source_type=source_type,
            form_type=form_type,
            publication_date=pub_date,
            observed_text=observed_text,
            matched_query=matched_query,
            fetch_timestamp=NOW,
            confidence=confidence,
            source_url=url
        )
        count += 1

    conn.commit()
    conn.close()
    print(f"Done. Processed {count} manual observations.")


if __name__ == "__main__":
    main()
