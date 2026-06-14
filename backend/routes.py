"""
routes.py — ta tessera endpoints tou app, ola edo

o router importaretai sto main.py me prefix /movielens/api opote den
xreiazetai na to epanalamvanoume se kathe route. an theleis na prostheseis
p.x. /admin endpoints apla kaneis neo router sto main.py kai den aggizetai ayto
"""

import time

from fastapi import APIRouter, HTTPException, Response
from database import fetchall, fetchone, execute, get_db
from models import (
    NewMovie,
    RecommendationRequest,
    MovieItem,
    RatingItem,
    RecommendedMovie,
    NewTag,
    TagItem,
    MovieUpdate,
)
from recommender import recommend

router = APIRouter()


# ── shared helper ───────────────────────────────────────────────────────────
# WHY: pollá endpoints (tags, delete, patch) prepei na elegxoun an yparxei i
# tainía kai na petane to idio 404. Anti na to grafoume polles fores (DRY), to
# vazoume se mia synartisi. An den yparxei kanei raise — alliws gyrnaei tin grammi.
def _require_movie(movieId: int):
    movie = fetchone("SELECT movieId, title, genres FROM movies WHERE movieId = ?", (movieId,))
    if movie is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "message": f"Movie {movieId} not found"},
        )
    return movie


# ── 1. Search movies ──────────────────────────────────────────────────────────

@router.get("/movies")
def search_movies(search: str = ""):
    """
    GET /movielens/api/movies?search=<keyword>
    psaxnei me LIKE sto title, case-insensitive.
    an to search einai keno epistrefei oles tis tainies (careful me pagination lol)
    """
    # ta % kai stis duo meries = "contains" match, oxi "starts with"
    pattern = f"%{search}%"
    rows = fetchall(
        "SELECT movieId, title, genres FROM movies WHERE title LIKE ?",
        (pattern,),
    )
    movies = [MovieItem(movieId=r["movieId"], title=r["title"], genres=r["genres"])
              for r in rows]
    return {"status": "success", "movies": [m.model_dump() for m in movies]}


# ── 2. Get ratings for a movie ────────────────────────────────────────────────

@router.get("/ratings/{movieId}")
def get_ratings(movieId: int):
    """
    GET /movielens/api/ratings/{movieId}
    epistrefei ola ta ratings pou exei i tainía sti vasi.
    404 an to movieId den yparxei katholou
    """
    # elegxoume prwta an yparxei i tainía, alliws to 404 einai meaningless
    movie = fetchone("SELECT movieId FROM movies WHERE movieId = ?", (movieId,))
    if movie is None:
        raise HTTPException(status_code=404, detail={"status": "error", "message": f"Movie {movieId} not found"})

    rows = fetchall(
        "SELECT userId, movieId, rating, timestamp FROM ratings WHERE movieId = ?",
        (movieId,),
    )
    ratings = [RatingItem(userId=r["userId"], movieId=r["movieId"],
                          rating=r["rating"], timestamp=r["timestamp"])
               for r in rows]
    return {"status": "success", "ratings": [rt.model_dump() for rt in ratings]}


# ── 3. Add a movie ────────────────────────────────────────────────────────────

@router.post("/movies", status_code=201)
def add_movie(body: NewMovie):
    """
    POST /movielens/api/movies
    Body: {"title": "...", "genres": "Action|Drama"}
    prosthetei neo movie sti vasi me neo ID = MAX + 1
    ta MovieLens IDs den einai sequential opote den kanoume auto-increment,
    apla pairnoume to megalytero ID kai prosthetoume 1 — safe lol
    """
    # to kanoume mesa sto idio connection gia na min yparksei race condition
    # (SQLite write lock to prostateei enwn alla still good practice)
    conn = get_db()
    try:
        row = conn.execute("SELECT MAX(movieId) AS max_id FROM movies").fetchone()
        new_id = (row["max_id"] or 0) + 1
        conn.execute(
            "INSERT INTO movies (movieId, title, genres) VALUES (?, ?, ?)",
            (new_id, body.title, body.genres),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "success", "movieId": new_id}


# ── 4. Get recommendations ────────────────────────────────────────────────────

@router.post("/recommendations")
def get_recommendations(body: RecommendationRequest):
    """
    POST /movielens/api/recommendations
    Body: {"ratings": [{"movieId": 1, "rating": 4.5}, ...]}
    trexei ton recommender me ta session ratings tou user.
    ta ratings DEN grafontwi sti vasi, xrhsimopoiountai mono gia tin provlepsi
    """
    # elegxoume an ola ta movieIds yparxoun sti vasi — an oxi 422 me lista twn missing
    submitted_ids = [r.movieId for r in body.ratings]
    placeholders = ",".join("?" * len(submitted_ids))
    found = fetchall(
        f"SELECT movieId FROM movies WHERE movieId IN ({placeholders})",
        tuple(submitted_ids),
    )
    found_ids = {row["movieId"] for row in found}
    missing = [mid for mid in submitted_ids if mid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": f"Unknown movieId(s): {missing}"},
        )

    # ta Pydantic objects ta kanome plain dicts giati o recommender den xerei Pydantic
    user_ratings = [{"movieId": r.movieId, "rating": r.rating}
                    for r in body.ratings]

    results, is_fallback = recommend(user_ratings)
    recs = [
        RecommendedMovie(
            movieId=r["movieId"],
            title=r["title"],
            genres=r["genres"],
            predictedRating=r["predictedRating"],
            isFallback=is_fallback,
        )
        for r in results
    ]
    return {"status": "success", "recommendations": [r.model_dump() for r in recs]}


# ════════════════════════════════════════════════════════════════════════════
# EXTENSION 1 — TAGS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/tags/{movieId}")
def get_tags(movieId: int):
    """
    GET /movielens/api/tags/{movieId}
    epistrefei ola ta tags pou exei mia tainía.
    WHY elegxoume prwta an yparxei i tainía: theloume na ksexorisoume to "i tainía
    den yparxei" (404) apo to "yparxei alla den exei tags" (200 me adeia lista).
    Xwris ayto, kai ta dyo tha edinan adeia lista kai o client den tha ksere giati.
    """
    _require_movie(movieId)
    rows = fetchall(
        "SELECT userId, movieId, tag, timestamp FROM tags WHERE movieId = ?",
        (movieId,),
    )
    tags = [TagItem(userId=r["userId"], movieId=r["movieId"],
                    tag=r["tag"], timestamp=r["timestamp"])
            for r in rows]
    return {"status": "success", "tags": [t.model_dump() for t in tags]}


@router.post("/tags", status_code=201)
def add_tag(body: NewTag):
    """
    POST /movielens/api/tags
    Body: {"movieId": 1, "tag": "sci-fi", "userId": 0}
    WHY validate-movie-first: an o user kanei tag se anyparkti tainía, tha
    dimiourgousame "orphan" tag pou den deixnei pouthena (referential integrity).
    Kalytera 404 amesos para silent corruption tis vasis.
    """
    _require_movie(body.movieId)

    # to timestamp to vazoume emeis (Unix seconds) — to CSV format to thelei int.
    # WHY server-side timestamp: o client den prepei na orizei "pote" eginei kati,
    # giati to roloi tou client mporei na einai lathos i na to spoofarei.
    now = int(time.time())
    execute(
        "INSERT INTO tags (userId, movieId, tag, timestamp) VALUES (?, ?, ?, ?)",
        (body.userId, body.movieId, body.tag, now),
    )
    return {"status": "success", "movieId": body.movieId, "tag": body.tag}


@router.get("/movies/by-tag")
def movies_by_tag(tag: str = ""):
    """
    GET /movielens/api/movies/by-tag?tag=<keyword>
    epistrefei oles tis tainies pou exoun ena tag pou taireiazi (case-insensitive).
    WHY JOIN: ta tags kai ta movies einai se ksexwristoers pinakes (normalised).
    Kanoume JOIN sto movieId gia na paroume titlo+genres mazi me to tag se ena query
    anti gia N+1 queries (prwta vres tag movieIds, meta query gia kathe movie).
    DISTINCT giati mia tainía mporei na exei to idio tag apo pollous users.
    """
    pattern = f"%{tag}%"
    rows = fetchall(
        """
        SELECT DISTINCT m.movieId, m.title, m.genres
        FROM movies m
        JOIN tags   t ON t.movieId = m.movieId
        WHERE t.tag LIKE ?
        """,
        (pattern,),
    )
    movies = [MovieItem(movieId=r["movieId"], title=r["title"], genres=r["genres"])
              for r in rows]
    return {"status": "success", "movies": [m.model_dump() for m in movies]}


# ════════════════════════════════════════════════════════════════════════════
# EXTENSION 2 — MOVIE CRUD (delete + partial update)
# ════════════════════════════════════════════════════════════════════════════

@router.delete("/movies/{movieId}", status_code=204)
def delete_movie(movieId: int):
    """
    DELETE /movielens/api/movies/{movieId}
    svinei mia tainía KAI ta ratings/tags tis.
    WHY 204 No Content: i diagrafi petyxe alla den exoume tipota na epistrepsoume.
    To 204 leei sto client "ok, teleiwse, min perimeneis body".
    WHY svinoume kai ratings+tags: ta movieId tous einai foreign keys pros movies.
    An afhname mono ta movies na fygoun, tha menane "orphan" ratings/tags pou
    deixnoun se anyparkti tainía — break tin referential integrity kai tha xalouse
    o recommender (tha prospathouse na kanei JOIN se movie pou den yparxei).
    """
    _require_movie(movieId)

    # ola sto idio connection/transaction — an kati apotyxei, kanena den grafetai
    # (atomicity). Svinoume prwta ta children (ratings, tags) kai meta to parent.
    conn = get_db()
    try:
        conn.execute("DELETE FROM ratings WHERE movieId = ?", (movieId,))
        conn.execute("DELETE FROM tags    WHERE movieId = ?", (movieId,))
        conn.execute("DELETE FROM movies  WHERE movieId = ?", (movieId,))
        conn.commit()
    finally:
        conn.close()

    # 204 prepei na exei adeio body — gia ayto Response xwris content
    return Response(status_code=204)


@router.patch("/movies/{movieId}")
def update_movie(movieId: int, body: MovieUpdate):
    """
    PATCH /movielens/api/movies/{movieId}
    Body: {"title": "..."} i {"genres": "..."} i kai ta dyo.
    WHY PATCH kai oxi PUT: PATCH = merkiki enimerwsi (allazeis mono osa stelneis).
    PUT tha apaitouse oliki antikatastasi (na ksanasteileis OLA ta pedia). Edo
    theloume na mporei kapoios na allaksei mono ta genres xwris na ksero to title.
    """
    _require_movie(movieId)

    # xtizoume to UPDATE dynamika me mono ta pedia pou estile o user.
    # WHY: an o user den estile title, den theloume na to kanoume NULL/keno —
    # theloume na to afhsoume opos einai. Ftiaxnoume "col = ?" mono gia osa irthan.
    fields = []
    params = []
    if body.title is not None:
        fields.append("title = ?")
        params.append(body.title)
    if body.genres is not None:
        fields.append("genres = ?")
        params.append(body.genres)
    # to model_validator sto MovieUpdate egguatai oti fields den einai pote keno

    params.append(movieId)  # gia to WHERE sto telos
    execute(f"UPDATE movies SET {', '.join(fields)} WHERE movieId = ?", tuple(params))

    updated = fetchone("SELECT movieId, title, genres FROM movies WHERE movieId = ?", (movieId,))
    return {
        "status": "success",
        "movie": MovieItem(movieId=updated["movieId"], title=updated["title"],
                           genres=updated["genres"]).model_dump(),
    }


# ════════════════════════════════════════════════════════════════════════════
# EXTENSION 3 — GENRE FILTER
# ════════════════════════════════════════════════════════════════════════════

@router.get("/movies/by-genre")
def movies_by_genre(genre: str = ""):
    """
    GET /movielens/api/movies/by-genre?genre=<genre>
    epistrefei oles tis tainies pou periexoun to genre.
    WHY LIKE kai oxi genres = ?: to genres pedio einai pipe-delimited string,
    p.x. "Action|Adventure|Sci-Fi". Isotita (=) tha taireiaze mono an i tainía exei
    AKRIVOS ena genre. Me LIKE %genre% vriskoume to genre mesa sto string.
    (Trade-off: ayto einai denormalised — se ena katharo schema ta genres tha itan
    se ksexwristo pinaka movie_genres. Alla to MovieLens CSV ta dinei etsi.)
    """
    pattern = f"%{genre}%"
    rows = fetchall(
        "SELECT movieId, title, genres FROM movies WHERE genres LIKE ?",
        (pattern,),
    )
    movies = [MovieItem(movieId=r["movieId"], title=r["title"], genres=r["genres"])
              for r in rows]
    return {"status": "success", "movies": [m.model_dump() for m in movies]}


@router.get("/genres")
def list_genres():
    """
    GET /movielens/api/genres
    epistrefei ola ta monadika genres — gia na gemizi to dropdown sto frontend.
    WHY se Python kai oxi se SQL: epeidi ta genres einai pipe-delimited mesa se
    ena pedio, i SQLite den mporei eukola na ta kanei split se ksexwristes grammes.
    Ta diavazoume ola, ta spame sto "|", kai kratame ta monadika me ena set.
    """
    rows = fetchall("SELECT genres FROM movies", ())
    genres: set[str] = set()
    for r in rows:
        for g in r["genres"].split("|"):
            g = g.strip()
            # to MovieLens exei to literal "(no genres listed)" — to petame
            if g and g != "(no genres listed)":
                genres.add(g)
    return {"status": "success", "genres": sorted(genres)}
