# MovieLens Web Application

User-based collaborative filtering recommender service built with FastAPI + vanilla JS.

---

## Quick start

```bash
# 1. Install dependencies
python3 -m pip install -r requirements.txt

# 2. Populate the database (creates movielens.db from the bundled zip)
python3 init_db.py

# 3. Start the backend server
python3 main.py
```

The API is now live at **http://localhost:3000**.
Interactive docs (Swagger UI): **http://localhost:3000/docs**

**In a second terminal**, serve the frontend:

```bash
cd ../frontend
python3 -m http.server 8081
```

Then open **http://localhost:8081** in your browser.

> Do not open `index.html` directly as a `file://` URL — browsers block `fetch` requests from file URLs to localhost. Always serve it through the HTTP server above.
> Port 8080 is reserved by VS Code; use 8081 (or any other free port).

---

## Project layout

```
backend/
  main.py          # App factory, CORS, router mount, Uvicorn entry point
  database.py      # SQLite connection helper
  models.py        # Pydantic request/response models
  routes.py        # 4 API endpoints (APIRouter)
  recommender.py   # Pearson collaborative filtering, fully isolated
  init_db.py       # One-time DB population script
  requirements.txt
  README.md        ← you are here
frontend/
  index.html       # Markup (no framework)
  index.js         # All JS by feature block (fetch + async/await)
  index.css        # Clean layout, no external libs
```

---

## curl examples

```bash
# Search movies
curl "http://localhost:3000/movielens/api/movies?search=matrix"

# Get ratings for a movie
curl "http://localhost:3000/movielens/api/ratings/2571"

# Add a movie
curl -X POST http://localhost:3000/movielens/api/movies \
  -H "Content-Type: application/json" \
  -d '{"title": "My Movie (2025)", "genres": "Drama|Thriller"}'

# Get recommendations (send your session ratings in the body)
curl -X POST http://localhost:3000/movielens/api/recommendations \
  -H "Content-Type: application/json" \
  -d '{"ratings": [{"movieId": 1, "rating": 5.0}, {"movieId": 2571, "rating": 4.5}]}'
```

---

## Viva prep — likely examiner questions

**Q1: Why Pearson correlation instead of cosine similarity?**

Pearson *centres* each user's ratings around their personal mean before computing similarity. This matters because users have different rating scales — one user's "4/5 = great" is another's "3/5 = pretty good". Pearson effectively measures whether two users rate movies *relatively* the same way (both liked it more than their average), not absolutely. Cosine similarity ignores this bias; Pearson corrects for it, which produces more accurate predictions in practice.

**Q2: What happens if two users have no co-rated movies?**

The `_pearson` function is never called for them — the neighbour loop checks `len(shared) < MIN_CO_RATED` (minimum 2) and `continue`s. If no neighbours survive this filter, `recommend()` detects an empty `similarities` list and falls back to `_global_fallback()`, which returns the globally highest-rated movies the user hasn't seen yet, so the response is always useful.

**Q3: What does MIN_CO_RATED = 2 guard against?**

With only one shared movie, both lists `xs` and `ys` have a single element. After centring around the mean (`xi − x̄`) every value becomes 0, so the denominator of Pearson is 0 → division by zero. Even with 2 items the correlation is ±1 with high variance, but it is at least mathematically defined. Raising MIN_CO_RATED (e.g. to 5 or 10) gives more reliable neighbours at the cost of fewer of them.

**Q4: What happens when a user gives the same rating to all their movies (zero variance)?**

Inside `_pearson`, `denom_x_sq = Σ(xi − x̄)² = 0`, so the denominator is 0. We check for this explicitly and return 0.0 (neutral similarity). This prevents a ZeroDivisionError and correctly discards that neighbour — a user who rated everything 3.0 tells us nothing about relative preference.

**Q5: How does the prediction formula work?**

`pred(u, i) = mean_u + Σ[sim(u,v) · (r_{v,i} − mean_v)] / Σ|sim(u,v)|`

Start from the active user's mean rating, then add a weighted average of how much each neighbour *deviated* from their own mean when rating movie `i`. Dividing by the sum of absolute similarities normalises the correction. The result is clamped to [0.5, 5.0] so it stays in a valid range.

**Q6: Why are the submitted ratings NOT stored in the database?**

The spec says so, but there is also a good design reason: storing transient user input would pollute the training data every time someone experiments with the app. Collaborative filtering quality depends on authentic historical ratings; mixing in session data would cause drift. The ratings are passed in memory from `routes.py` to `recommender.py` and discarded after the request.

**Q7: How would you add a /tags endpoint?**

Add a `GET /tags/{movieId}` handler in `routes.py` that queries `SELECT * FROM tags WHERE movieId = ?`. Add a `TagItem` Pydantic model in `models.py` mirroring the tags CSV columns. No other file needs to change — this is why routes and models are in separate files.

**Q8: How would you scale this if the ratings table had 100 million rows?**

The current approach loads all ratings into memory per request, which would be ≈ 4 GB at 100 M rows. Solutions: (1) pre-compute and cache a user–user similarity matrix on a schedule; (2) use a proper recommender library (Surprise, LightFM) with offline training; (3) store ratings in a column-oriented store (DuckDB, Parquet) for faster aggregation; (4) limit `db_users` to only users who share at least one movie with the active user using a subquery. For this assignment, loading ≈ 100 k rows is fast enough (< 0.5 s).
