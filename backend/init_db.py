"""
init_db.py — Download the MovieLens latest-small dataset and populate movielens.db.

Run once before starting the server:
    python init_db.py

The script is idempotent: it drops and recreates the three tables every time,
so you can safely re-run it after a partial failure or a dataset update.
"""

import csv
import io
import os
import sqlite3
import urllib.request
import zipfile

# ── Dataset source ────────────────────────────────────────────────────────────
DATASET_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
ZIP_PATH    = "ml-latest-small.zip"        # cached locally to avoid re-downloading
DB_PATH     = "movielens.db"

# ── Schema ────────────────────────────────────────────────────────────────────
# Column names mirror the CSV headers exactly so the load loop needs no mapping.
SCHEMA = """
DROP TABLE IF EXISTS ratings;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS movies;

CREATE TABLE movies (
    movieId  INTEGER PRIMARY KEY,
    title    TEXT    NOT NULL,
    genres   TEXT    NOT NULL
);

CREATE TABLE ratings (
    userId    INTEGER NOT NULL,
    movieId   INTEGER NOT NULL,
    rating    REAL    NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (movieId) REFERENCES movies(movieId)
);

-- Index on movieId speeds up "get all ratings for a movie" (used by /ratings/{id}).
CREATE INDEX idx_ratings_movieId ON ratings(movieId);

-- Index on userId speeds up the recommender's neighbour lookup (scan per user).
CREATE INDEX idx_ratings_userId  ON ratings(userId);

CREATE TABLE tags (
    userId    INTEGER NOT NULL,
    movieId   INTEGER NOT NULL,
    tag       TEXT    NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (movieId) REFERENCES movies(movieId)
);
"""


def download_zip() -> bytes:
    """Download the dataset zip if not already cached; return its raw bytes."""
    if os.path.exists(ZIP_PATH):
        print(f"[init_db] Using cached {ZIP_PATH}")
        with open(ZIP_PATH, "rb") as f:
            return f.read()

    print(f"[init_db] Downloading {DATASET_URL} …")
    with urllib.request.urlopen(DATASET_URL) as resp:
        data = resp.read()
    with open(ZIP_PATH, "wb") as f:
        f.write(data)
    print(f"[init_db] Saved to {ZIP_PATH}")
    return data


def csv_rows(zip_data: bytes, filename: str) -> list[dict]:
    """
    Extract a CSV file from the zip bytes and return its rows as a list of dicts.
    DictReader uses the header row as keys, so names match the CSV exactly.
    """
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        # The zip contains a single top-level folder (ml-latest-small/).
        inner_path = f"ml-latest-small/{filename}"
        with zf.open(inner_path) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8")
            return list(csv.DictReader(text))


def load_table(cur: sqlite3.Cursor, table: str, rows: list[dict], columns: list[str]):
    """
    Bulk-insert `rows` into `table`, reading only the given `columns`.
    Uses parameterised queries (? placeholders) — never string-interpolation —
    to prevent SQL injection.
    """
    placeholders = ", ".join("?" * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    # Extract values in column order from each dict row.
    data = [tuple(row[c] for c in columns) for row in rows]
    cur.executemany(sql, data)


def main():
    zip_data = download_zip()

    print("[init_db] Extracting CSVs …")
    movie_rows  = csv_rows(zip_data, "movies.csv")
    rating_rows = csv_rows(zip_data, "ratings.csv")
    tag_rows    = csv_rows(zip_data, "tags.csv")

    print(f"[init_db] Rows read — movies: {len(movie_rows)}, "
          f"ratings: {len(rating_rows)}, tags: {len(tag_rows)}")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    print("[init_db] Applying schema …")
    # executescript runs the multi-statement DDL in one call.
    cur.executescript(SCHEMA)

    print("[init_db] Loading movies …")
    load_table(cur, "movies",  movie_rows,  ["movieId", "title", "genres"])

    print("[init_db] Loading ratings …")
    load_table(cur, "ratings", rating_rows, ["userId", "movieId", "rating", "timestamp"])

    print("[init_db] Loading tags …")
    load_table(cur, "tags",    tag_rows,    ["userId", "movieId", "tag", "timestamp"])

    conn.commit()
    conn.close()

    # Confirmation counts so you can visually verify the load was complete.
    conn = sqlite3.connect(DB_PATH)
    for table in ("movies", "ratings", "tags"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"[init_db] ✓ {table}: {count} rows")
    conn.close()
    print("[init_db] Done. Database written to", DB_PATH)


if __name__ == "__main__":
    main()
