# Extension Notes & Viva Prep

This copy of the project adds four feature groups on top of the original four
endpoints. Each section below gives a **one-line summary** of what was built,
then the **examiner questions** you are most likely to get with model answers.
Every answer is tagged with the underlying **concept** so you can speak to the
theory, not just the code.

All new code keeps the original conventions:
- responses shaped `{"status": "success", ...}`, errors `{"status": "error", "message": ...}`
- parameterised SQL (`?` placeholders) everywhere — never f-strings in queries
- DB access through `database.py` helpers (`fetchall`, `fetchone`, `execute`, `get_db`)
- frontend stays vanilla JS / one `index.html` / `index.js` / `index.css`

Files touched: `models.py`, `routes.py`, `recommender.py`, `frontend/index.{html,js,css}`.

---

## Extension 1 — Tags

**Summary:** Added `GET /tags/{movieId}` (list tags), `POST /tags` (add a tag,
movie-existence validated first), and `GET /movies/by-tag?tag=` (find movies by
tag via a SQL JOIN).

### Q: Why check the movie exists before inserting a tag?
A tag row carries a `movieId` that *references* a movie. If we let someone tag a
non-existent movie we'd create an **orphan row** — data pointing at nothing —
which breaks **referential integrity**. So `POST /tags` calls `_require_movie()`
first and returns **404** if the movie is missing, instead of silently corrupting
the table. *(Concept: referential integrity / foreign keys.)*

### Q: `GET /tags/{movieId}` for a movie with no tags returns 200 with `[]`, but a missing movie returns 404. Why the difference?
They mean different things. `404` = "this resource does not exist." `200 []` =
"the resource exists but currently has nothing." Collapsing both into an empty
list would hide errors — the client couldn't tell a typo'd ID from a genuinely
un-tagged movie. *(Concept: HTTP status code semantics.)*

### Q: Why a JOIN in `/movies/by-tag` instead of two queries?
Tags and movies live in **separate tables** (normalised design). To return a
movie's title + genres alongside the matched tag, I join `tags` to `movies` on
`movieId` in **one** query. The alternative — query tags, then loop and query
each movie — is the classic **N+1 query problem**: 1 + N round-trips instead of 1.
I also use `DISTINCT` because the same tag can be applied by many users, which
would otherwise duplicate the movie in the result. *(Concept: SQL JOINs, N+1.)*

### Q: How is SQL injection prevented here?
The tag keyword goes into the query as a bound parameter: `WHERE t.tag LIKE ?`
with the value passed separately as `(pattern,)`. The driver sends the SQL and
the data on different channels, so user input can never be parsed as SQL. If I'd
written `f"... LIKE '%{tag}%'"`, a tag of `'; DROP TABLE movies; --` could run.
*(Concept: SQL injection / parameterised queries.)*

### Q: Where does the tag's timestamp come from?
The **server** sets it (`int(time.time())`), not the client. A client clock can
be wrong or spoofed; "when did this happen" is a fact the server owns.
*(Concept: trust boundaries / server-authoritative data.)*

---

## Extension 2 — Movie CRUD (delete + partial update)

**Summary:** Added `DELETE /movies/{movieId}` (cascades to ratings + tags,
returns **204**) and `PATCH /movies/{movieId}` (partial update, **404** if absent).
Together with the existing `GET`/`POST` this completes CRUD on movies.

### Q: Which REST verb maps to which operation, and why PATCH not PUT?
`POST` = create, `GET` = read, `DELETE` = delete. For update there are two verbs:
**PUT** replaces the whole resource (client must send *every* field), **PATCH**
applies a *partial* change (send only what changes). I chose PATCH so you can
edit just the genres without re-sending the title. *(Concept: REST verbs.)*

### Q: Why does DELETE return 204 and not 200 with a body?
**204 No Content** means "succeeded, and there's deliberately nothing to return."
The movie is gone, so echoing it back would be odd. 204 responses must have an
empty body — that's why the handler returns FastAPI's `Response(status_code=204)`
rather than a dict. *(Concept: HTTP status codes.)*

### Q: What happens to ratings and tags when you delete a movie?
They'd become **orphans** (rows referencing a movie that no longer exists). The
schema declares `FOREIGN KEY (movieId) REFERENCES movies(movieId)` but SQLite
doesn't enforce it unless `PRAGMA foreign_keys=ON` *and* you declared
`ON DELETE CASCADE` — this DB does neither. So I delete the children manually,
in order (ratings, tags, then the movie), inside **one transaction** so it's
**atomic**: either everything is removed or nothing is. *(Concept: referential
integrity, cascading delete, transaction atomicity.)*

### Q: A PATCH with an empty body `{}` is rejected with 422. Why?
The `MovieUpdate` model has a validator requiring at least one of `title`/`genres`.
An empty patch is a no-op and almost always a client mistake, so I fail fast with
**422 Unprocessable Entity** (the body is well-formed JSON but semantically
invalid) rather than running an `UPDATE ... SET` with nothing to set.
*(Concept: input validation, 422 vs 400.)*

### Q: How is the partial UPDATE built safely?
I build the `SET` clause dynamically from only the fields that were sent
(`title = ?`, `genres = ?`), collecting values into a params list, and append the
`movieId` last for the `WHERE`. Column names are hard-coded (never user input);
only values are parameterised — so the dynamic SQL is still injection-safe.
*(Concept: parameterised queries with dynamic columns.)*

---

## Extension 3 — Genre filter

**Summary:** Added `GET /movies/by-genre?genre=` (LIKE match, because genres are
pipe-delimited) and `GET /genres` (distinct genre list for a dropdown).

### Q: Why `LIKE` instead of `genres = ?`?
The `genres` column stores a **pipe-delimited string** like
`"Action|Adventure|Sci-Fi"`. Equality would only match a movie whose entire genre
field is exactly the search term. `LIKE '%Sci-Fi%'` finds the substring inside the
list. *(Concept: denormalised storage / string matching.)*

### Q: That `genres` column violates a normal form — which, and what's the cost?
It violates **first normal form (1NF)**, which requires atomic (single-valued)
columns; here one cell holds many genres. The costs: you can't index a single
genre, you must use `LIKE` (slower, and `%Drama%` could false-match a genre named
e.g. `Melodrama`), and aggregation per-genre is awkward. The clean design is a
join table `movie_genres(movieId, genre)`. I kept the CSV's shape to honour the
assignment's "mirror the CSV" rule, but I can explain the trade-off.
*(Concept: normalization / 1NF / denormalization.)*

### Q: Why compute the genre list in Python instead of SQL?
Because the genres are packed into one column, SQLite can't easily split them into
rows (no built-in `split`/`unnest`). So `/genres` reads every `genres` string,
splits on `|`, and collects uniques in a `set`. I also drop the literal
`"(no genres listed)"` placeholder MovieLens uses. *(Concept: set dedup, data
cleaning.)*

### Q: How does the frontend dropdown stay in sync with the data?
It isn't hard-coded. On page load `loadGenres()` calls `GET /genres` and builds
the `<option>` elements from the response, so adding a movie with a new genre
makes it appear after refresh. *(Concept: data-driven UI.)*

---

## Extension 4 — Cosine similarity (swappable with Pearson)

**Summary:** Added `_cosine()` next to the existing `_pearson()` and a single
module-level switch `SIMILARITY_FN` so the metric changes in **one line**; the
prediction logic calls `SIMILARITY_FN(xs, ys)` without knowing which it is.

### Q: What's the actual difference between Pearson and cosine here?
Both measure how similarly two users rate co-rated movies, but **Pearson
mean-centres first** (subtracts each user's average rating, `xᵢ − x̄`) and cosine
does **not**. So cosine compares the raw rating vectors' angle (absolute scores),
while Pearson compares deviations from each user's own mean (relative taste).
Practically: a generous rater (all 4–5s) and a harsh rater (all 2–3s) who agree
on *ranking* look **similar to Pearson** but **less similar to cosine**, because
cosine still "sees" the magnitude gap. *(Concept: Pearson vs cosine = mean-centering.)*

### Q: Why does mean-centering matter for recommendations?
Users have different rating **scales/biases** — one person's 3 is another's 5.
Centering removes that personal bias so you compare *preferences*, not *habits*.
That's usually why Pearson is the default for user-based collaborative filtering.
Cosine is simpler and common for **item-based** CF or sparse implicit data.
*(Concept: collaborative filtering, rating bias.)*

### Q: How is the swap "one line", and what design pattern is that?
`SIMILARITY_FN = _pearson` (flip to `_cosine`). Everything downstream calls
`SIMILARITY_FN(xs, ys)`. This is the **strategy pattern**: the algorithm
(predict ratings from neighbours) is fixed; the interchangeable *strategy* is the
similarity function injected into it. *(Concept: strategy pattern / dependency
injection.)*

### Q: Both functions return 0.0 in edge cases — when, and why does it matter?
Two guards: (1) fewer than `MIN_CO_RATED` co-rated items, and (2) a zero
denominator. For Pearson a zero denominator happens when a user has **zero
variance** (rated everything the same) — `Σ(xᵢ−x̄)² = 0`. For cosine it's a zero
vector. Returning 0 (neutral, "no information") avoids a `ZeroDivisionError` and
correctly discards an uninformative neighbour. *(Concept: numerical edge cases.)*

### Q: What is the cold-start problem and where does it show up?
**Cold start** = you can't make good CF predictions for a user/item with little or
no rating history, because similarity needs overlap. In this app a brand-new
session user who has rated only one or two movies may share too few co-rated items
with anyone (`MIN_CO_RATED`), so no neighbours survive — `recommend()` then falls
back to `_global_fallback()` (globally top-rated movies) so the response is still
useful. Newly *added* movies have the same issue: nobody has rated them yet, so
they can never be recommended until they accumulate ratings. *(Concept: cold-start.)*

---

## Cross-cutting: CORS (you'll likely be asked regardless of feature)

### Q: What does enabling CORS do, and why is it needed here?
The frontend is served from `localhost:8081` and calls the API on
`localhost:3000` — different **origins** (port counts). Browsers block
cross-origin `fetch` by default (**same-origin policy**). The
`CORSMiddleware` with `allow_origins=["*"]` makes the server send
`Access-Control-Allow-Origin`, telling the browser the call is permitted. In
production you'd restrict `*` to your real frontend domain. *(Concept: CORS /
same-origin policy.)* Note CORS is a **browser** guard — `curl` ignores it, which
is why the API works in a terminal even without CORS.

---

## Quick manual test commands (server on :3000)

```bash
B=http://localhost:3000/movielens/api
curl "$B/tags/1"
curl -X POST "$B/tags" -H "Content-Type: application/json" -d '{"movieId":1,"tag":"sci-fi"}'
curl "$B/movies/by-tag?tag=pixar"
curl -X PATCH "$B/movies/1" -H "Content-Type: application/json" -d '{"genres":"Drama"}'
curl -i -X DELETE "$B/movies/1"          # expect HTTP 204
curl "$B/movies/by-genre?genre=Film-Noir"
curl "$B/genres"
```

To switch the recommender metric: in `recommender.py` change
`SIMILARITY_FN = _pearson` to `SIMILARITY_FN = _cosine` (one line) and restart.
