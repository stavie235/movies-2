# Ultimate Master Guide — MovieLens Web App

Everything from scratch. Read this once end-to-end, then use the section headers
to jump back to whatever the examiner is pointing at.

---

## Table of Contents

1. [What We Built and Why](#1-what-we-built-and-why)
2. [Tech Stack — Each Choice Explained](#2-tech-stack--each-choice-explained)
3. [Project Layout — Why Each File Exists](#3-project-layout--why-each-file-exists)
4. [The Database Layer](#4-the-database-layer)
5. [Pydantic Models — The Contract Layer](#5-pydantic-models--the-contract-layer)
6. [The Four API Endpoints](#6-the-four-api-endpoints)
7. [The Recommendation Algorithm — From Scratch](#7-the-recommendation-algorithm--from-scratch)
8. [The Frontend — HTML, CSS, JavaScript](#8-the-frontend--html-css-javascript)
9. [A Request From Click to Response](#9-a-request-from-click-to-response)
10. [Error Handling — The Whole Chain](#10-error-handling--the-whole-chain)
11. [Security Notes](#11-security-notes)
12. [Viva Q&A — 20 Questions You Must Be Able to Answer](#12-viva-qa--20-questions-you-must-be-able-to-answer)

---

## 1. What We Built and Why

### The product

A web application where a user can:
- Search for movies from the MovieLens dataset
- Add new movies to the database
- Rate movies in their browser session
- Get personalised movie recommendations based on those ratings

### What MovieLens is

MovieLens is a public research dataset published by GroupLens at the University of
Minnesota. The "latest-small" version has:
- **9 742 movies** with titles and genre tags
- **100 836 ratings** from **610 users** on a 0.5–5.0 scale
- **3 683 free-text tags** users applied to movies

We use this real data as the training base for our recommendation engine.

### Why it's split into two separate processes

The **backend** (Python/FastAPI) handles data and logic. The **frontend** (HTML/JS)
handles the user interface. They communicate over HTTP using JSON. This is called
a **client–server architecture**.

Why not just serve HTML from Python? Because separating them means:
- You can change the UI without touching the database logic
- You can test the API independently (curl, Swagger, scripts)
- It matches how real production systems are built

---

## 2. Tech Stack — Each Choice Explained

### Python

The standard language for data-heavy university courses. The standard library
includes `sqlite3`, `csv`, `urllib`, `zipfile` — we need all of these and import
none from pip.

### FastAPI

A modern Python web framework. Key properties for this assignment:

| Property | What it means |
|---|---|
| **Async-capable** | Can handle many requests without blocking |
| **Pydantic integration** | Annotate a function parameter with a model class → automatic JSON parsing + validation |
| **Auto docs** | Visit `/docs` and you get a live Swagger UI — every endpoint is clickable |
| **Type hints** | Python type annotations tell FastAPI the expected shape of inputs/outputs |

We chose FastAPI over Flask because the course taught it, and because Pydantic
validation saves us from writing manual `if "field" not in body` checks.

### Uvicorn

An **ASGI server** — the process that actually listens on a TCP port and hands
HTTP requests to FastAPI. Think of it like this:

```
Browser → [network] → Uvicorn (port 3000) → FastAPI app → your Python code
```

You never write the TCP socket code yourself; Uvicorn handles that layer.

### SQLite (via standard-library `sqlite3`)

SQLite is a **file-based relational database**. The entire database lives in
`movielens.db`, a single file. No separate database server process to install
or run.

Why not PostgreSQL or MySQL? For a single-user university demo, SQLite is
perfectly adequate and has zero setup cost. The `sqlite3` module is in Python's
standard library — no extra pip install.

### Pydantic v2

A Python library for data validation using type annotations. When you define:

```python
class SessionRating(BaseModel):
    movieId: int   = Field(..., gt=0)
    rating:  float = Field(..., ge=0.5, le=5.0)
```

Pydantic will:
1. Check that `movieId` is an integer greater than 0
2. Check that `rating` is a float between 0.5 and 5.0
3. Raise a `RequestValidationError` (→ 422 HTTP response) if either fails

You get all this validation for free just by writing the type annotation.

### Vanilla JS with `fetch`

The spec says **no frameworks** — no React, Vue, jQuery, or CDN imports.
This is intentional: a second-year course tests whether you understand the raw
browser APIs before abstracting them away.

`fetch` is the modern browser-native way to make HTTP requests. It returns a
**Promise**, which we handle with `async/await`.

---

## 3. Project Layout — Why Each File Exists

```
backend/
  init_db.py      ← one-time setup script, not part of the running app
  database.py     ← the ONLY place that knows the DB file path
  models.py       ← the ONLY place that defines data shapes
  routes.py       ← the ONLY place that defines endpoints
  recommender.py  ← the ONLY place that contains ML logic
  main.py         ← glues everything together, starts the server
  requirements.txt
  README.md
frontend/
  index.html      ← markup structure
  index.css       ← visual styling
  index.js        ← all behaviour / API calls
```

**The rule behind this layout**: each file has exactly one job. If the examiner
asks "where do I change the database path?" — `database.py`. "Where do I add
a new endpoint?" — `routes.py`. "Where is the Pearson formula?" — `recommender.py`.

If everything were in one file, a change to the recommendation algorithm would
put you at risk of accidentally breaking an endpoint. Separation prevents that.

---

## 4. The Database Layer

### 4.1 The schema (three tables)

```sql
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

CREATE TABLE tags (
    userId    INTEGER NOT NULL,
    movieId   INTEGER NOT NULL,
    tag       TEXT    NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (movieId) REFERENCES movies(movieId)
);
```

Column names match the CSV headers **exactly**. This means our CSV loading code
needs no column-name mapping — it reads the header row and uses those names directly.

**FOREIGN KEY** says: every `movieId` in `ratings` must exist in `movies`. This
is referential integrity — you can't have a rating for a movie that doesn't exist.

**REAL** is SQLite's floating-point type. Ratings like 4.5 need decimal places.

**INTEGER PRIMARY KEY** in SQLite is special: it aliases the rowid, giving you
an auto-increment column for free.

### 4.2 Indexes

```sql
CREATE INDEX idx_ratings_movieId ON ratings(movieId);
CREATE INDEX idx_ratings_userId  ON ratings(userId);
```

Without an index, a query like `SELECT * FROM ratings WHERE movieId = 2571`
forces SQLite to **scan all 100 836 rows** one by one to find matches.

With an index, SQLite builds a sorted B-tree on `movieId`. Finding all rows for
movieId 2571 takes O(log n) for the lookup, then a fast sequential read of the
matching rows. On 100 k rows this is the difference between ~5 ms and <1 ms.

The `userId` index speeds up the recommender, which needs to load all ratings
grouped by user.

### 4.3 `init_db.py` — how it loads the data

```
1. Download zip from GroupLens (cached locally after first run)
2. Open zip in memory (zipfile + io.BytesIO — no temp files on disk)
3. Wrap the raw bytes in io.TextIOWrapper so csv.DictReader can read it as text
4. DictReader uses the header row as dict keys → rows are [{movieId: "1", title: "Toy Story..."}]
5. executemany() bulk-inserts all rows in one transaction → much faster than one INSERT per row
6. Commit → close → reopen → print COUNT(*) for each table to confirm
```

**Why `executescript` for the schema but `executemany` for the data?**

`executescript` runs a multi-statement string (the full DDL with DROP/CREATE).
`executemany` runs one parameterised statement repeated for a list of tuples.
You can't use `executemany` for DDL because it expects a single repeatable statement.

**Why is it idempotent?**

The schema starts with `DROP TABLE IF EXISTS`. So re-running the script always
starts from a clean state. The data is always re-loaded from the zip. This means
if the script crashes halfway, you just run it again.

### 4.4 `database.py` — the connection helper

```python
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
```

**`row_factory = sqlite3.Row`** is the key line. Without it, query results are
plain tuples: `row[0]`, `row[1]` — fragile if you change the SELECT order.
With it, results are `sqlite3.Row` objects that support both index and name access:
`row["title"]` — readable and order-independent.

**Why open a new connection per query?**

For a low-concurrency university demo this is fine. Each `fetchall` / `fetchone`
/ `execute` call opens a connection, uses it, and closes it in a `finally` block.
The `finally` guarantees the connection is closed even if an exception is raised.

In production you would use a connection pool. For this assignment, the simplicity
is worth more than the micro-optimisation.

---

## 5. Pydantic Models — The Contract Layer

Every API endpoint has a **request shape** (what it expects from the caller) and
a **response shape** (what it sends back). `models.py` defines all of these.

### Request models

```python
class NewMovie(BaseModel):
    title:  str = Field(..., min_length=1)
    genres: str = Field(..., min_length=1)
```

`Field(...)` means the field is required (the `...` is Python's Ellipsis, a
conventional way to say "no default"). `min_length=1` means an empty string fails.

```python
class SessionRating(BaseModel):
    movieId: int   = Field(..., gt=0)       # greater than 0
    rating:  float = Field(..., ge=0.5, le=5.0)  # 0.5 ≤ rating ≤ 5.0
```

```python
class RecommendationRequest(BaseModel):
    ratings: list[SessionRating] = Field(..., min_length=1)

    @model_validator(mode="after")
    def no_duplicate_movie_ids(self):
        ids = [r.movieId for r in self.ratings]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate movieIds in ratings list")
        return self
```

The `@model_validator` runs after Pydantic has already validated each individual
`SessionRating`. It then applies a cross-field rule: no two entries may share the
same `movieId`. A set removes duplicates; if the lengths differ, there were duplicates.

### Response models

```python
class RecommendedMovie(BaseModel):
    movieId:         int
    title:           str
    genres:          str
    predictedRating: float
```

Response models give us `.model_dump()` — a method that converts the Pydantic
object to a plain Python dict, which FastAPI serialises to JSON.

**Why use response models at all?**

You could just return a plain dict. But with a model:
- The Swagger UI at `/docs` shows the exact shape of every response
- `model_dump()` means the field names are defined in one place, not scattered
  across string literals in your route handlers
- If you rename a field, the type-checker catches every place it's used

---

## 6. The Four API Endpoints

All four live in `routes.py` and are mounted at `/movielens/api` in `main.py`.

### 6.1 GET /movies?search={keyword}

```python
@router.get("/movies")
def search_movies(search: str = ""):
    pattern = f"%{search}%"
    rows = fetchall(
        "SELECT movieId, title, genres FROM movies WHERE title LIKE ?",
        (pattern,),
    )
```

**LIKE with % wildcards**: In SQL, `%` matches any sequence of characters.
So `%matrix%` matches "The Matrix", "Matrix Reloaded", "Animatrix", etc.
LIKE is case-insensitive for ASCII in SQLite by default.

**Empty search** (`search=""`): the pattern becomes `%%`, which matches every
row — so you get all 9 742 movies. This is intentional: "leave blank to browse all".

**The `?` placeholder**: Never write `f"... WHERE title LIKE '%{search}%'"`.
If `search` were `'; DROP TABLE movies;--`, that would execute the DROP.
The `?` placeholder passes the value as data, never as SQL code.

### 6.2 GET /ratings/{movieId}

```python
@router.get("/ratings/{movieId}")
def get_ratings(movieId: int):
    movie = fetchone("SELECT movieId FROM movies WHERE movieId = ?", (movieId,))
    if movie is None:
        raise HTTPException(status_code=404, detail={...})
```

**Path parameter**: `{movieId}` in the URL path is extracted by FastAPI and
passed as the `movieId` parameter. Because the annotation says `int`, FastAPI
automatically tries to parse it as an integer. If you visit `/ratings/banana`,
FastAPI returns a 422 before your code even runs.

**Two-step lookup**: First confirm the movie exists (404 if not), then fetch its
ratings. Without the first step, a missing movie and a movie with zero ratings
would both return an empty list — indistinguishable to the caller.

### 6.3 POST /movies

```python
@router.post("/movies", status_code=201)
def add_movie(body: NewMovie):
    conn = get_db()
    row = conn.execute("SELECT MAX(movieId) AS max_id FROM movies").fetchone()
    new_id = (row["max_id"] or 0) + 1
    conn.execute(
        "INSERT INTO movies (movieId, title, genres) VALUES (?, ?, ?)",
        (new_id, body.title, body.genres),
    )
    conn.commit()
```

**`status_code=201`**: HTTP 201 Created is the correct status for a successful
resource creation. 200 OK is for reads or updates. The distinction matters in REST.

**`MAX(movieId) + 1`**: This is simpler and safer than relying on SQLite's
AUTOINCREMENT for a dataset where we loaded specific IDs from a CSV. Using
AUTOINCREMENT would start at 1 and potentially collide with existing IDs.
`MAX + 1` guarantees uniqueness.

**`(row["max_id"] or 0) + 1`**: If the table were empty, `MAX(movieId)` returns
NULL, which Python receives as `None`. `None or 0` evaluates to `0`, so the
first movie gets ID 1.

**Same transaction**: The MAX and INSERT use the same `conn` object, so no other
write can slip in between them and steal the same ID. SQLite's write lock makes
this safe.

### 6.4 POST /recommendations

```python
@router.post("/recommendations")
def get_recommendations(body: RecommendationRequest):
    user_ratings = [{"movieId": r.movieId, "rating": r.rating}
                    for r in body.ratings]
    results = recommend(user_ratings)
```

This endpoint is deliberately thin. It converts the Pydantic objects to plain
dicts (so `recommender.py` has no FastAPI dependency) and delegates everything
to `recommend()`. The endpoint is responsible for HTTP; the recommender is
responsible for maths.

**The ratings are NOT stored**: `recommend()` takes them as an argument. It
never calls `execute()` with an INSERT. After the request ends, the data is
garbage-collected. This is an explicit design decision stated in the spec.

---

## 7. The Recommendation Algorithm — From Scratch

This section explains the maths step by step. Read it until you can derive
every line without looking.

### 7.1 The problem

You (user u) have rated some movies. There are 610 other users in the database
who have also rated movies. The question is: **what movies should we show you
next?**

The insight behind collaborative filtering: if two users rated the same movies
similarly in the past, they probably have similar taste, so movies one liked but
the other hasn't seen are good recommendations.

### 7.2 Co-rated movies

For you and user v, the **co-rated set** is:

```
shared = {movieId : movieId in u's ratings AND movieId in v's ratings}
```

We need at least 2 co-rated movies (`MIN_CO_RATED = 2`) because:
- With 1 item, each user's "list" has one element. After centring around the mean,
  that one element becomes 0. The denominator of Pearson is 0. Division by zero.
- With 2 items you get a number (though a noisy one).
- In production you'd use 5–10 for reliability.

### 7.3 Pearson correlation — the formula

Given two equal-length lists of ratings for the co-rated movies:
- `xs` = your ratings (user u) for the shared movies
- `ys` = user v's ratings for the same shared movies

```
         Σ (xi − x̄)(yi − ȳ)
r = ───────────────────────────────────
    √(Σ(xi − x̄)²) · √(Σ(yi − ȳ)²)
```

Where:
- `x̄` = mean of xs (your average over the co-rated set)
- `ȳ` = mean of ys (user v's average over the co-rated set)
- `xi − x̄` = how much you deviated from your average for movie i
- `yi − ȳ` = how much user v deviated from their average for movie i

**Result**: a number in [-1, +1]:
- `+1` = perfect positive correlation (same relative taste)
- `0`  = no relationship
- `-1` = perfect inverse correlation (opposite taste)

**Why subtract the mean first?**

Imagine you always rate 1–2 stars and I always rate 4–5 stars. On any given
co-rated movie, you gave it 2.0 and I gave it 5.0 — but we both loved it
relative to our own scales. Cosine similarity would say we're dissimilar.
Pearson says: your deviation from your mean was +0.5 (you liked it more than
usual), my deviation was +0.5 — that's a match. Pearson corrects for personal
rating scale bias.

**Zero variance**:

If user v gave every co-rated movie exactly 3.0, then `yi − ȳ = 0` for all i.
`Σ(yi − ȳ)² = 0`. Denominator = 0. We cannot compute Pearson. We return 0.0
(no similarity) and skip this user.

This is handled by:

```python
if denom_x_sq == 0 or denom_y_sq == 0:
    return 0.0
```

### 7.4 Selecting TOP_K neighbours

After computing similarity with every user who shares enough movies, we:
1. Keep only **positive** similarities (negative similarity would invert predictions)
2. Sort by similarity descending
3. Take the top `K = 30`

Why K=30? It's a standard default in CF literature. More neighbours → smoother
predictions, slower computation. Fewer → faster, noisier. 30 is the sweet spot
for a dataset of this size.

### 7.5 Predicting a rating

For a movie `i` that you haven't rated, but some of your top-K neighbours have:

```
                Σ_v [ sim(u,v) · (r_{v,i} − mean_v) ]
pred(u,i) = x̄u + ──────────────────────────────────────
                          Σ_v |sim(u,v)|
```

Where the sum runs only over neighbours who actually rated movie `i`.

**Unpacking this formula**:

- Start from your own mean rating `x̄u`. This anchors the prediction to your
  personal scale — a neutral prediction for you is "your average".
- For each neighbour v who rated movie i:
  - `r_{v,i} − mean_v` = how much v deviated from their mean for this movie.
    Positive = they liked it more than usual; negative = less than usual.
  - Multiply by `sim(u,v)` = weight by how similar v is to you. A very similar
    user's opinion counts more.
- Sum these weighted deviations, then normalise by `Σ|sim(u,v)|` so the result
  is an average, not a sum that grows with the number of neighbours.

**Empty denominator guard**:

If none of the top-K neighbours rated movie `i`, the denominator `Σ|sim|` is 0.
We skip this movie entirely rather than dividing by zero.

```python
if denom == 0:
    continue
```

**Clamping**:

The formula can theoretically produce values outside [0.5, 5.0] (e.g. if
everyone who rated a film gave it 5.0 and they're all highly similar to you).
We clamp:

```python
predicted = max(0.5, min(5.0, predicted))
```

### 7.6 The global fallback

If no neighbours pass the MIN_CO_RATED filter (e.g. you only rated one obscure
movie nobody else has seen), `similarities` is empty and the main algorithm
produces nothing.

Instead of returning an empty list, we return the globally highest-rated movies
you haven't seen yet (requiring ≥5 ratings for statistical stability). This is
clearly labelled as a fallback in the code — not an algorithmic result.

### 7.7 Time complexity note

For each request we load all 100 836 rating rows into a Python dict — O(n) in the
number of ratings. Then for each of 610 users we compute Pearson over their shared
movies — O(K·m) where K is number of neighbours and m is average co-rated count.

For this dataset, the whole thing runs in ~100 ms. If the dataset were 100×
larger, we would pre-compute similarities offline, but for 100 k rows this is fine.

---

## 8. The Frontend — HTML, CSS, JavaScript

### 8.1 index.html — markup structure

The page is five `<section class="card">` blocks, one per feature. Each section
is self-contained: it has its inputs, its button, and its `<div class="msg">`
for feedback. There's also a results table where needed.

Key decisions:
- **No `<form>` elements**: using `<div>` + `<button>` avoids the browser's
  default form-submit behaviour (page reload on Enter), which would clear the
  session ratings.
- **`<script src="index.js">` at the end of `<body>`**: this ensures the DOM
  is fully parsed before the JS runs, so `getElementById()` always finds its
  target. If you put the script in `<head>`, the elements don't exist yet.
- **No CDN imports**: the `<head>` has exactly one `<link>` (the CSS) and
  nothing else. This is a hard requirement from the spec.

### 8.2 index.css — styling philosophy

Simple card layout using CSS grid. Nothing clever. Key rules:

```css
main {
  max-width: 900px;
  margin: 2rem auto;      /* centred horizontally */
  display: grid;
  gap: 1.5rem;            /* space between cards */
}
```

**`.msg` states**: the same div gets different background colours based on the
class applied by `setMsg()`:
- `.msg.ok`   → green background (success)
- `.msg.err`  → red background (error)
- `.msg.info` → blue background (neutral info)

This avoids having three separate divs per section; one div changes class.

### 8.3 index.js — feature by feature

#### The session store

```javascript
const sessionRatings = {};
```

A plain JS object. Keys are movieId (number), values are rating (float).

**Why not localStorage?** The spec says ratings are session-only. `localStorage`
persists across browser sessions. A plain object disappears on page refresh.
A `Map` would also work, but a plain object is simpler and the examiner
won't find anything to complain about.

#### `setMsg(id, text, type)` — the feedback helper

```javascript
function setMsg(id, text, type = "info") {
  const el = document.getElementById(id);
  el.textContent = text;    // textContent, not innerHTML — XSS safe
  el.className = `msg ${type}`;
}
```

Used by every section. `textContent` (not `innerHTML`) means no HTML parsing,
so no XSS risk even if `text` somehow contained `<script>`.

#### `apiErr(data)` — unified error extraction

```javascript
function apiErr(data) {
  return data.message ?? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) ?? "Unknown error";
}
```

After the backend error-shape fix, all our errors come as `{"status":"error","message":"..."}`.
`data.message` handles those. The `data.detail` fallback handles unexpected
FastAPI 500s that still use the default format. `??` is the nullish coalescing
operator — it returns the right side only if the left is `null` or `undefined`
(not for `""` or `0`, unlike `||`).

#### Section 1 — Add a movie (async fetch with error feedback)

```javascript
const res  = await fetch(`${BASE_URL}/movies`, {
  method:  "POST",
  headers: { "Content-Type": "application/json" },
  body:    JSON.stringify({ title, genres }),
});
const data = await res.json();

if (!res.ok) {
  setMsg("msg-add", `Error: ${apiErr(data)}`, "err");
  return;
}
```

**`res.ok`** is `true` for status codes 200–299. For 4xx/5xx it's `false`.
We always parse `res.json()` before the `res.ok` check because even error
responses have a JSON body (our `{"status":"error","message":"..."}` shape).

**`async/await`**: `fetch()` returns a Promise. `await` pauses execution until
the Promise resolves. Without `await`, `res` would be a Promise object, not
the actual response — calling `res.json()` would fail.

**`try/catch`**: wraps the entire async block. If the network is down, `fetch()`
throws a `TypeError: Failed to fetch`. Without `try/catch`, this would be an
unhandled rejection — no visible feedback to the user. The `catch` block shows
`"Network error: ..."` in the UI.

#### Section 2 — Search with Enter-key support

```javascript
document.getElementById("search-kw").addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchMovies();
});
```

`addEventListener("keydown", handler)` is the spec-required way to attach
event handlers. The alternative (`element.onkeydown = fn`) overwrites any
existing handler; `addEventListener` stacks them.

#### Section 3 — "Use ID" button (dynamic event listener)

```javascript
tbody.querySelectorAll(".btn-use-id").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.getElementById("rate-id").value = btn.dataset.id;
    document.getElementById("avg-id").value  = btn.dataset.id;
  });
});
```

These buttons are created dynamically inside `innerHTML`, so they don't exist
when the page loads — you can't attach handlers at startup. Instead we attach
them immediately after building the table rows.

`btn.dataset.id` reads the `data-id="..."` attribute from the HTML. This is
the standard way to pass data from markup to JS event handlers.

#### `escHtml(str)` — XSS guard

```javascript
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
```

We use `innerHTML` to build table rows (convenient for templating). If a movie
title contained `<script>alert(1)</script>`, injecting it directly into `innerHTML`
would execute the script — that is an XSS attack.

`escHtml` converts `<` to `&lt;` etc., so the browser renders it as literal
text rather than HTML. Every user-controlled string goes through `escHtml`
before entering `innerHTML`.

---

## 9. A Request From Click to Response

Trace a full recommendation request end-to-end.

```
User clicks "Get Recommendations"
  │
  ▼
index.js: btn-recs click handler
  - reads sessionRatings object
  - builds payload: {ratings: [{movieId:1,rating:5.0}, ...]}
  - calls fetch(BASE_URL + "/recommendations", {method:"POST", body: JSON.stringify(payload)})
  │
  ▼
Network: HTTP POST to http://localhost:3000/movielens/api/recommendations
  │
  ▼
Uvicorn: receives TCP connection, parses HTTP request, passes to FastAPI
  │
  ▼
FastAPI middleware stack:
  1. CORSMiddleware: adds Access-Control-Allow-Origin: * header
  2. Routes the request to the matching handler in routes.py
  3. Pydantic parses the JSON body into RecommendationRequest
     - Validates each SessionRating (types, ranges)
     - Runs no_duplicate_movie_ids validator
     - If any check fails → RequestValidationError → 422 response (no Python code runs)
  │
  ▼
routes.py: get_recommendations(body: RecommendationRequest)
  - converts Pydantic objects to plain dicts
  - calls recommend(user_ratings)
  │
  ▼
recommender.py: recommend(user_ratings)
  - opens DB, loads all 100 836 ratings into db_users dict
  - for each of 610 DB users: find shared movies, compute Pearson
  - keep top-30 neighbours with positive similarity
  - for each unseen candidate movie: apply prediction formula
  - sort by predicted rating, take top 10
  - JOIN with movies table to get title/genres
  - return list of dicts
  │
  ▼
routes.py: wraps results in RecommendedMovie Pydantic objects
  - calls .model_dump() on each
  - returns {"status":"success","recommendations":[...]}
  │
  ▼
FastAPI serialises the return value to JSON
Uvicorn sends HTTP 200 response with Content-Type: application/json
  │
  ▼
Network: response bytes arrive in browser
  │
  ▼
index.js: await res.json() parses the response
  - res.ok is true (status 200)
  - loops through data.recommendations
  - builds table rows with escHtml(title), escHtml(genres)
  - inserts into DOM
  - calls setMsg("msg-recs", "10 recommendation(s) returned.", "ok")
  │
  ▼
User sees the results table
```

---

## 10. Error Handling — The Whole Chain

### Backend side (main.py)

Two custom exception handlers override FastAPI's defaults:

**Handler 1 — Pydantic validation (422)**:

```python
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    first = exc.errors()[0]
    loc   = " → ".join(str(p) for p in first["loc"] if p != "body")
    raw   = first["msg"].removeprefix("Value error, ")
    msg   = f"{loc}: {raw}" if loc else raw
    return JSONResponse(status_code=422, content={"status":"error","message":msg})
```

Without this, FastAPI returns `{"detail": [{...complex Pydantic object...}]}`.
With it, the frontend gets `{"status":"error","message":"ratings → 0 → rating: Input should be less than or equal to 5"}`.

**Handler 2 — HTTP exceptions (404, 405, etc.)**:

```python
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request, exc):
    if isinstance(exc.detail, dict) and "message" in exc.detail:
        content = exc.detail
    else:
        content = {"status": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=content)
```

In `routes.py` we `raise HTTPException(status_code=404, detail={"status":"error","message":"..."})`.
FastAPI's default handler would wrap that as `{"detail": {"status":"error","message":"..."}}`.
Our handler unwraps it, returning the dict directly.

### Frontend side (index.js)

Every `fetch` call follows the same three-level error handling:

```
Level 1 — try/catch: catches network failure (server down, DNS error)
  → shows "Network error: Failed to fetch"

Level 2 — !res.ok: catches 4xx/5xx HTTP status codes
  → parses JSON body, calls apiErr(data), shows the message

Level 3 — input guards before fetch: catches bad user input locally
  → shows inline validation message without even hitting the server
```

The user always sees a human-readable message. There are no silent failures
and no raw stack traces in the UI.

---

## 11. Security Notes

### SQL injection — why it can't happen here

Every SQL statement uses `?` or named placeholders:

```python
# SAFE: the value is passed as a parameter, never concatenated
fetchall("SELECT * FROM movies WHERE title LIKE ?", (pattern,))

# UNSAFE (we never do this):
fetchall(f"SELECT * FROM movies WHERE title LIKE '%{search}%'")
```

When you use `?`, the SQLite driver sends the query template and the data
value separately. The database engine treats the value as a literal string —
it can never be interpreted as SQL code. So `'; DROP TABLE movies;--` becomes
a harmless search string that returns zero results.

We tested this: the search endpoint returns 0 results for the injection string
and the movies table has all 9 742 rows intact afterward.

### XSS (Cross-Site Scripting) — why it can't happen here

Movie titles come from an external database and could contain `<script>` or
`<img onerror="...">`. We use `escHtml()` on every value injected into
`innerHTML`. The browser sees `&lt;script&gt;` and renders it as text,
never executes it.

We also use `el.textContent = text` (not `innerHTML`) in `setMsg()`, which
is inherently safe — `textContent` never triggers HTML parsing.

### CORS — why we allow all origins

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```

CORS (Cross-Origin Resource Sharing) is a browser security mechanism. By
default, a browser won't let JavaScript on `http://localhost:5500` call an
API on `http://localhost:3000` — different ports = different "origins".

We allow `*` (all origins) for development. In production you would set:
```python
allow_origins=["https://yourdomain.com"]
```

For the university demo this is fine — add a comment saying you know it should
be restricted.

---

## 12. Viva Q&A — 20 Questions You Must Be Able to Answer

---

**Q1: Walk me through what happens when I click "Get Recommendations".**

See Section 9 — you should be able to narrate the whole chain from click to
DOM update without looking.

---

**Q2: Why Pearson correlation? Why not cosine similarity or Euclidean distance?**

Pearson subtracts each user's personal mean before measuring similarity. This
corrects for **rating scale bias** — one user may consistently rate everything
higher than another. Cosine similarity does not correct for this. Euclidean
distance measures absolute rating differences, which is also distorted by bias.
Pearson measures whether users rate things *relatively* the same way, which is
the right question for a recommender.

---

**Q3: What happens if two users have no co-rated movies?**

The `shared` list is empty, `len(shared) < MIN_CO_RATED` is True, and we
`continue` — this user is skipped entirely and contributes zero to the
similarity list.

---

**Q4: What if a user rated everything identically (e.g. all 3.0)?**

After centring: every `xi − x̄ = 0`. So `denom_x_sq = Σ(xi−x̄)² = 0`.
`_pearson` detects `denom_x_sq == 0` and returns 0.0. This user is later
filtered out (we keep only positive similarity), so they contribute nothing
to predictions. No division by zero occurs.

---

**Q5: What if none of the neighbours rated the candidate movie?**

The inner loop over `top_neighbours` finds no one who rated movie `i`, so
`denom` stays 0.0. We check `if denom == 0: continue` — this movie is skipped.
No prediction, no division by zero.

---

**Q6: If I submit a movieId that doesn't exist in the DB for recommendations,
what happens?**

The `user_map` for that movie has no matching row in any DB user's rating set,
so `shared` is empty for every neighbour. No neighbours qualify. The algorithm
falls back to `_global_fallback()` which returns the globally highest-rated
movies the user hasn't seen.

---

**Q7: Why are the session ratings not stored in the database?**

Two reasons. First, the spec says so. Second, polluting the training data with
experimental ratings would corrupt the recommender for all future users — if
you rate 50 random movies at 5.0 just to try the feature, every similar user
would start getting your experiment as recommendations.

---

**Q8: How does adding a new movie guarantee a unique ID?**

`SELECT MAX(movieId) + 1 FROM movies` — both the MAX query and the INSERT happen
on the same SQLite connection object, so SQLite's write lock prevents any other
write from intervening. The new ID is always one more than the highest existing ID.

---

**Q9: What are the `?` placeholders in the SQL queries?**

Parameterised query placeholders. The value is passed separately from the SQL
template, so the database driver never interprets user input as SQL. This prevents
SQL injection. The `?` is a positional placeholder; SQLite also supports
`:name` named placeholders.

---

**Q10: What does `row_factory = sqlite3.Row` do?**

It changes query result rows from plain tuples (access by index only: `row[0]`)
to `sqlite3.Row` objects that support access by column name (`row["title"]`).
This makes the code more readable and less fragile — if you change the column
order in a SELECT, named access still works.

---

**Q11: What is Uvicorn? How is it different from FastAPI?**

FastAPI is the **web framework** — it defines routes, parses requests, validates
data, and returns responses. Uvicorn is the **ASGI server** — it opens a TCP
socket on port 3000, receives raw HTTP bytes, and hands them to FastAPI. FastAPI
itself has no networking code; it just processes the request object Uvicorn provides.

---

**Q12: What is ASGI?**

Asynchronous Server Gateway Interface. The Python standard for how async web
servers (Uvicorn, Hypercorn) communicate with async web frameworks (FastAPI,
Starlette). The synchronous predecessor is WSGI (used by Flask, Django's dev server).

---

**Q13: Why does the frontend use `async/await` instead of `.then()/.catch()`?**

Both work. `async/await` is syntactic sugar over Promises introduced in ES2017.
It makes asynchronous code read like synchronous code — no nested callbacks.
`try/catch` with `async/await` is equivalent to `.catch()` on a Promise chain,
but is easier to read and reason about, especially with multiple sequential awaits.

---

**Q14: What does `escHtml` protect against?**

Cross-site scripting (XSS). If a movie title contains `<script>alert(1)</script>`
and we inject it directly into `innerHTML`, the browser executes the script.
`escHtml` converts `<` to `&lt;`, `>` to `&gt;`, etc. — the browser then
renders them as literal characters, never as HTML tags.

---

**Q15: What is `MIN_CO_RATED` and what happens if you raise it?**

`MIN_CO_RATED = 2` is the minimum number of movies two users must both have rated
for us to compute Pearson between them. Raising it to 5 or 10 gives more reliable
similarity estimates (correlation from 2 data points is noisy) but means fewer
neighbours qualify — you need users with broader overlapping taste. For this
dataset's density, 2 is acceptable.

---

**Q16: How would you add a `/tags` endpoint?**

1. In `models.py`: add `class TagItem(BaseModel)` with fields `userId`, `movieId`,
   `tag`, `timestamp`.
2. In `routes.py`: add `@router.get("/tags/{movieId}")`, query the `tags` table,
   return `{"status":"success","tags":[...]}`.
3. No other file needs to change.

---

**Q17: Why `status_code=201` on the POST /movies endpoint?**

HTTP 201 Created is the semantically correct status for "a new resource was
created". 200 OK means "the request succeeded and here is the result", which
is appropriate for reads. Using the right status code lets HTTP clients (and
humans reading logs) understand what happened without reading the body.

---

**Q18: What would you change to make this production-ready?**

- CORS: restrict `allow_origins` to the actual frontend domain
- Auth: add JWT or session tokens so not everyone can add movies
- Recommender: pre-compute user similarities on a schedule instead of per-request
- Database: use PostgreSQL with a connection pool (SQLAlchemy + asyncpg) for
  concurrent writes
- Input: rate-limit the recommendation endpoint to prevent abuse
- Indexes: add a covering index on `ratings(userId, movieId, rating)` to avoid
  table lookups in the recommender query

---

**Q19: The recommender loads all ratings on every request. How would you fix that?**

For this dataset (100 k rows, ~1 MB) it's fast enough (~100 ms). To scale:
1. Pre-compute the user–user similarity matrix nightly and cache it in the DB
2. On request, look up the pre-computed top-K neighbours directly
3. Only recompute the prediction step (much cheaper) per request
4. Alternatively, add an in-process LRU cache (`functools.lru_cache` or
   `cachetools`) so repeated identical requests skip the DB round-trip

---

**Q20: What is the difference between `fetchall`, `fetchone`, and `execute`
in `database.py`? Why split them?**

- `fetchall` — SELECT that returns every matching row as a list
- `fetchone` — SELECT that returns the first row (or None)
- `execute` — INSERT/UPDATE/DELETE; commits and returns `lastrowid`

They are split because the caller's intent differs: checking existence vs.
fetching all results vs. writing. Having three named helpers means `routes.py`
reads like a sentence: "fetchone to check existence, fetchall to get all ratings".
Sharing one generic function would require the caller to pass flags or inspect
the SQL string to know whether to commit.

---

*End of guide. Good luck with the viva.*
