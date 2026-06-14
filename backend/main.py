"""
main.py — edo startarei olo to app, CORS kai error handling

gia na trekseis ton server:
    python main.py
        i
    uvicorn main:app --port 3000 --reload
"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from routes import router

app = FastAPI(
    title="MovieLens API",
    description="Collaborative-filtering recommendation service backed by MovieLens latest-small.",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# allow_origins=["*"] lei sto browser "ok na kaneis request apo opoudipote"
# gia production tha balaname mono to domain tou frontend mas, alla gia to ptixiako
# den mas noiazei, it's giving "works on my machine" energy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Error handlers ────────────────────────────────────────────────────────────
# to FastAPI by default stelnei errors san {"detail": ...} alla emeis theloume
# panta {"status": "error", "message": "..."} — etsi to JS frontend xerei
# exactly ti na perimeinei kai den kanoume extra checks

@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # an to routes.py ekane raise me dict (dikia mas morfh), to pernoume as exei
    # alliws (p.x. FastAPI 404 gia agnosto path) to kanome string
    if isinstance(exc.detail, dict) and "message" in exc.detail:
        content = exc.detail
    else:
        content = {"status": "error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # to Pydantic piasei kalo request prin ftasei sto diko mas kwdika
    # pairnoume to proto lathos kai to kanome ena readable minima
    first = exc.errors()[0]
    # vazei "body ->" mpros, to afairoume giati einai useless info gia ton user
    loc   = " -> ".join(str(p) for p in first["loc"] if p != "body")
    # to Pydantic vazei "Value error, " mpros sta dika mas errors — strip it
    raw   = first["msg"].removeprefix("Value error, ")
    msg   = f"{loc}: {raw}" if loc else raw
    return JSONResponse(status_code=422, content={"status": "error", "message": msg})


# ── Router ────────────────────────────────────────────────────────────────────
# ola ta endpoints tou routes.py einai proseggisima me prefix /movielens/api
# to vazei edo oste to routes.py na mhn epianalambani to prefix se kathe route
app.include_router(router, prefix="/movielens/api")


@app.get("/")
def root():
    """aplo health check — an to http://localhost:3000/ epistrefei ok, o server treksei"""
    return {"status": "ok", "message": "MovieLens API is running. See /docs for the interactive spec."}


if __name__ == "__main__":
    # python main.py ksekinae ton server apeftheias
    # an theleis auto-restart otan allazeis arxeia: uvicorn main:app --port 3000 --reload
    uvicorn.run("main:app", host="0.0.0.0", port=3000)
