"""
models.py — ta shapes twn requests kai responses, basically i "morfh" twn dedomenwn

to Pydantic elegxei automata ta incoming JSONs kai an kati den stamparei
epistrefei 422 prin ftasei sto diko mas kwdika — super convenient ngl
"""

from pydantic import BaseModel, Field, model_validator


# ── Request bodies ────────────────────────────────────────────────────────────

class NewMovie(BaseModel):
    """ayto stelnei o user otan thelei na prostethei neo tainía sti vasi"""
    title:  str = Field(..., min_length=1, description="Movie title")
    genres: str = Field(..., min_length=1, description="Pipe-separated genre list, e.g. Action|Drama")


class SessionRating(BaseModel):
    """ena zeugaraki (tainía, vathmologia) apo ton user gia ayti ti session"""
    movieId: int   = Field(..., gt=0)
    rating:  float = Field(..., ge=0.5, le=5.0)


class RecommendationRequest(BaseModel):
    """ayto stelnei o user otan thelei recommendations — lista me ta ratings tou"""
    ratings: list[SessionRating] = Field(..., min_length=1)

    @model_validator(mode="after")
    def no_duplicate_movie_ids(self) -> "RecommendationRequest":
        # an o user steilei to idio movieId dis, sto recommender to deutero
        # tha overwritarei to proto kai tha xasoume data silently — better to crash early
        ids = [r.movieId for r in self.ratings]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate movieIds in ratings list — each movie may appear only once")
        return self


# ── Response shapes ───────────────────────────────────────────────────────────

class MovieItem(BaseModel):
    """mia tainía opos epistrefetai apo to search"""
    movieId: int
    title:   str
    genres:  str


class RatingItem(BaseModel):
    """mia grammi rating apo ti vasi opos epistrefetai apo to /ratings/{movieId}"""
    userId:    int
    movieId:   int
    rating:    float
    timestamp: int


class RecommendedMovie(BaseModel):
    """mia provlepomeni tainia me to predicted rating tis
    isFallback = True simainei oti den vrikame arketa similar users kai
    epistrefoume ta globally popular movies anti gia personalized"""
    movieId:         int
    title:           str
    genres:          str
    predictedRating: float
    isFallback:      bool = False


# ── EXTENSION 1: Tags ───────────────────────────────────────────────────────
# WHY xwristo model gia to POST /tags: theloume to Pydantic na epivalei oti
# yparxei kai movieId kai tag PRIN ftasoume sto endpoint (validation-as-contract).
# To userId einai optional me default 0 giati o web-app user den exei pragmatiko
# MovieLens account — to 0 leitourgei san "anonymous session user" sentinel.

class NewTag(BaseModel):
    """ayto stelnei o user otan thelei na prosthesei tag se mia tainía"""
    movieId: int = Field(..., gt=0)
    tag:     str = Field(..., min_length=1, description="Free-text tag, e.g. 'sci-fi'")
    userId:  int = Field(0, ge=0, description="Optional — defaults to 0 (anonymous)")


class TagItem(BaseModel):
    """mia grammi tag apo ti vasi opos epistrefetai apo to /tags/{movieId}"""
    userId:    int
    movieId:   int
    tag:       str
    timestamp: int


# ── EXTENSION 2: Partial movie update ───────────────────────────────────────
# WHY ola ta pedia einai Optional: ayto einai to shape gia PATCH (merkiki
# enimerwsi). O user mporei na steilei mono {"genres": "..."} xwris na ksanagrapsei
# to title. An itan PUT (oliki antikatastasi) tha ta kaname kai ta dyo required.
# To model_validator frontizei na min erthei keno body (kanena pedio) — ayto tha
# itan no-op kai pithanos lathos tou client.

class MovieUpdate(BaseModel):
    """partial update gia mia tainía — mono ta pedia pou stelnontai allazoun"""
    title:  str | None = Field(None, min_length=1)
    genres: str | None = Field(None, min_length=1)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MovieUpdate":
        if self.title is None and self.genres is None:
            raise ValueError("Provide at least one field to update (title and/or genres)")
        return self
