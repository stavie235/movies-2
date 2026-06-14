"""
recommender.py — user-based collaborative filtering me Pearson similarity, to heart tou app

einai xwristo apo to FastAPI epistrofe na to unit-testaris mono tou an theleis
(apla kales recommend(user_ratings) kai voila)

pos doulevei se apla:
1. fortwnei ola ta ratings apo ti vasi sti mnimi (100k grammes, acceptable gia ptixiako)
2. vrisketai poioi xristes exoun vathmologisei toulaxiston MIN_CO_RATED kines tainies me ton active user
3. ypologizei Pearson correlation metaksy tou active user kai kathe neighbor
4. kratai tous TOP_K pio similar (mono positive similarity — negative tha antistrefe tis provlepseis)
5. gia kathe tainía pou den exei dei o active user, provlepei rating:

       pred(u, i) = mean_u
                    + Σ_v [ sim(u,v) · (r_{v,i} − mean_v) ]
                      ──────────────────────────────────────
                            Σ_v |sim(u,v)|

   oi summations einai mono gia neighbors pou exoun vathmologisei auti ti tainía
6. epistrefei ta TOP_N movies me to ipsylotero predicted rating, me titlo kai genres
"""

import sqlite3
from database import get_db

# ── numbers pou mporeis na allakseis an theleis na kaneis tweaking ──────────

# posous neighbors kratame — megalytero K = pio smooth provlepseis alla pio argo
# mikrotero K = pio grigoro alla pio "noisy". 30 einai classic sweet spot
TOP_K = 30

# posa recommendations na epistrefoume ston user
TOP_N = 10

# postes kines tainies preepei na exoun vathmologisei dyo xristes mazi
# gia na tous sygkrinoume me Pearson. me 1 mono tainía i formula xalaei (division by zero)
# to kratame sto 2 giati an to auksissoume riskiroume na min vriskoume katholou neighbors
# kai na paei panta sto fallback — which would be awkward in the exam ngl
MIN_CO_RATED = 2


# ── ta maths ─────────────────────────────────────────────────────────────────

def _pearson(xs: list[float], ys: list[float]) -> float:
    """
    ypologizei Pearson correlation metaksy dyo liston vathmologiwn.

    typos:
        r = Σ(xi − x̄)(yi − ȳ)
            ───────────────────────────────────
            sqrt( Σ(xi − x̄)² · Σ(yi − ȳ)² )

    epistrefei 0.0 se edge cases:
    - ligoteres apo MIN_CO_RATED kines tainies (o caller filtrarei prin, alla gia asfaleia)
    - an kapoios exei dwsei to idio rating se ola (zero variance = denominator = 0 = undefined)
    """
    n = len(xs)
    if n < MIN_CO_RATED:
        return 0.0

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    # afairoume to mean apo kathe rating — etsi sygkrineta "style" oxi "absolute scores"
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]

    numerator   = sum(a * b for a, b in zip(dx, dy))
    denom_x_sq  = sum(a * a for a in dx)
    denom_y_sq  = sum(b * b for b in dy)

    # an kapoios exei dwsei to idio score se ola, i formula den orizetai — epistrefoume 0
    if denom_x_sq == 0 or denom_y_sq == 0:
        return 0.0

    return numerator / (denom_x_sq ** 0.5 * denom_y_sq ** 0.5)


# ── EXTENSION 4: cosine similarity (enallaktiki tou Pearson) ─────────────────
def _cosine(xs: list[float], ys: list[float]) -> float:
    """
    ypologizei cosine similarity metaksy dyo liston vathmologiwn.

    typos:
        cos = Σ(xi · yi)
              ───────────────────────────
              sqrt(Σxi²) · sqrt(Σyi²)

    I VASIKI DIAFORA APO TO PEARSON: to cosine DEN afairei to mean prin.
    To Pearson kanei "mean-centering" (xi − x̄) wste na sygkrinei *sxetiko* gousto
    (an kapoios vathmologise pano apo to diko tou meso oro). To cosine vlepei tis
    vathmologies san dianysmata kai metraei ti gwnia tous — sygkrinei *apolyta*
    scores. Apotelesma: an dyo xristes simfwnoun sti seira alla o enas vathmologei
    panta psila ki o allos xamila, to Pearson tous vlepei "idious", to cosine oxi.

    epistrefei 0.0 sta idia edge cases me to Pearson (ligotera apo MIN_CO_RATED,
    i miden dianysma — kapoios pou edwse panta 0, pou den symvainei edw afou
    ta ratings einai >= 0.5, alla to elegxoume gia asfaleia).
    """
    n = len(xs)
    if n < MIN_CO_RATED:
        return 0.0

    dot     = sum(a * b for a, b in zip(xs, ys))
    norm_x  = sum(a * a for a in xs) ** 0.5
    norm_y  = sum(b * b for b in ys) ** 0.5

    if norm_x == 0 or norm_y == 0:
        return 0.0

    return dot / (norm_x * norm_y)


# ── METRIC SWITCH ────────────────────────────────────────────────────────────
# ENA SHMEIO ALLAGHS: gyrna ayti ti grammi se _cosine gia na allakseis metric.
# Olos o ypoloipos kwdikas kalei SIMILARITY_FN(xs, ys) xwris na kserei poio einai.
# (auto einai to "strategy pattern" — i logiki tis provlepsis den allazei, mono
# i synartisi omoiotitas pou tis dinoume.)
SIMILARITY_FN = _pearson
# SIMILARITY_FN = _cosine


# ── Main entry point ──────────────────────────────────────────────────────────

def recommend(user_ratings: list[dict]) -> list[dict]:
    """
    paragei recommendations gia ton active user.
    pairnei lista me ta session ratings tou user, epistrefei lista me tainies + predicted ratings.
    epistrefei kai True/False gia to an xrhsimopoihthike to fallback.
    """

    # kanome dict gia na psaxnoume ratings me movieId quickly: {movieId: rating}
    user_map: dict[int, float] = {r["movieId"]: r["rating"] for r in user_ratings}
    # den mporei na einai empty — to models.py (min_length=1) to elegxei prin ftasei edo
    user_mean = sum(user_map.values()) / len(user_map)

    # ── vima 1: fortwnoume ola ta ratings apo ti vasi ────────────────────────
    conn = get_db()
    rows = conn.execute("SELECT userId, movieId, rating FROM ratings").fetchall()
    conn.close()

    # organosnoume ana user: {userId: {movieId: rating}}
    db_users: dict[int, dict[int, float]] = {}
    for row in rows:
        db_users.setdefault(row["userId"], {})[row["movieId"]] = row["rating"]

    # ── vima 2 & 3: vriskome neighbors kai ypologizoume similarity ───────────
    similarities: list[tuple[float, int]] = []  # (sim, userId)

    for v_id, v_map in db_users.items():
        # kines tainies pou exoun vathmologisei kai oi dyo (intersection)
        shared = [mid for mid in user_map if mid in v_map]

        # an exoun vathmologisei poly liges kines mazi, i Pearson den axizei
        if len(shared) < MIN_CO_RATED:
            continue

        xs = [user_map[mid] for mid in shared]
        ys = [v_map[mid]    for mid in shared]

        # xrhsimopoiei oti metric einai energo sto SIMILARITY_FN (Pearson i cosine)
        sim = SIMILARITY_FN(xs, ys)

        # negative similarity simainei "antithetwn gematon" — an tous kratousame
        # tha antistrefe tis provlepseis kai tha proeinai things they hated, not it
        if sim > 0:
            similarities.append((sim, v_id))

    # ── edge case: den vrikame katholou neighbors ─────────────────────────────
    if not similarities:
        # fallback: epistrefoume ta globally popular movies
        # to isFallback=True pigenei sto frontend kai deixnei different message
        return _global_fallback(user_map), True

    # kratame tous TOP_K pio similar neighbors
    similarities.sort(key=lambda t: t[0], reverse=True)
    top_neighbours = similarities[:TOP_K]

    # ── vima 4 & 5: problepoume ratings gia tainies pou den exei dei o user ──
    # mazi oles tis tainies pou exoun dei oi neighbors alla oxi o user
    candidate_movies: set[int] = set()
    for _, v_id in top_neighbours:
        for mid in db_users[v_id]:
            if mid not in user_map:
                candidate_movies.add(mid)

    predictions: list[tuple[float, int]] = []

    for movie_id in candidate_movies:
        numerator   = 0.0
        denom       = 0.0

        for sim, v_id in top_neighbours:
            v_map = db_users[v_id]
            if movie_id not in v_map:
                # aytos o neighbor den exei vathmologisei ayti tin tainía — skip
                continue

            v_mean  = sum(v_map.values()) / len(v_map)
            # provlepoume vasi tis apostasis tou neighbor rating apo to diko tou mean
            numerator += sim * (v_map[movie_id] - v_mean)
            denom     += abs(sim)

        # den tin exei vathmologisei kaneis apo tous neighbors — skip
        if denom == 0:
            continue

        predicted = user_mean + numerator / denom
        # clamp sto [0.5, 5.0] giati mathematika mporei na vgei ektos range
        predicted = max(0.5, min(5.0, predicted))
        predictions.append((predicted, movie_id))

    # sort by predicted rating, kratame ta top N
    predictions.sort(key=lambda t: t[0], reverse=True)
    top_predictions = predictions[:TOP_N]

    # ── vima 6: prosthetoume titlo kai genres apo ti vasi ───────────────────
    return _attach_metadata(top_predictions), False


def _attach_metadata(predictions: list[tuple[float, int]]) -> list[dict]:
    """pairnei (predicted_rating, movieId) kai epistrefei full movie info me ena mono query"""
    if not predictions:
        return []

    # ena query me IN anti gia N queries — poly pio grigoro
    ids = [mid for _, mid in predictions]
    placeholders = ",".join("?" * len(ids))
    conn = get_db()
    rows = conn.execute(
        f"SELECT movieId, title, genres FROM movies WHERE movieId IN ({placeholders})",
        tuple(ids),
    ).fetchall()
    conn.close()

    meta = {row["movieId"]: row for row in rows}

    result = []
    for pred, mid in predictions:
        if mid not in meta:
            continue   # den tha suvei, alla an yparxei rating xwris movie sto db to skip
        m = meta[mid]
        result.append({
            "movieId":         m["movieId"],
            "title":           m["title"],
            "genres":          m["genres"],
            "predictedRating": round(pred, 4),
        })
    return result


def _global_fallback(user_map: dict[int, float]) -> list[dict]:
    """
    den vrikame arketa similar users — epistrefoume ta globally top-rated movies
    san backup opote o user pairnei toulaxiston kati useful.
    HAVING COUNT(*) >= 5 giati den theloume tainies me mia mona vathmologia na
    dominoun tin lista (statistical reliability basically)
    to frontend deixnei different message otan ayto kaleitai (isFallback=True)
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT m.movieId, m.title, m.genres, AVG(r.rating) AS avg_rating
        FROM ratings r
        JOIN movies  m ON m.movieId = r.movieId
        GROUP BY r.movieId
        HAVING COUNT(*) >= 5
        ORDER BY avg_rating DESC
        LIMIT ?
        """,
        (TOP_N,),
    ).fetchall()
    conn.close()

    return [
        {
            "movieId":         row["movieId"],
            "title":           row["title"],
            "genres":          row["genres"],
            "predictedRating": round(row["avg_rating"], 4),
        }
        for row in rows
        if row["movieId"] not in user_map  # min proeinai tainies pou exei hdh dei
    ][:TOP_N]
