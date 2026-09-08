import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    assistant, defects, ev_optimize, health, markov, ml, network, optimize, queueing, road_safety,
    vehicle_trust, warehouse,
)

app = FastAPI(
    title="Automotive Decision Intelligence Platform API",
    version="0.1.0",
)

# CORS_ORIGINS: comma-separated list, e.g. "https://app.example.com,https://staging.example.com".
# Defaults to the SvelteKit dev server so `npm run dev` + `uvicorn --reload`
# keeps working with zero config; set it explicitly for any real deployment.
_default_origins = "http://localhost:5173"
cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(warehouse.router)
app.include_router(ml.router)
app.include_router(defects.router)
app.include_router(network.router)
app.include_router(optimize.router)
app.include_router(assistant.router)
app.include_router(ev_optimize.router)
app.include_router(queueing.router)
app.include_router(markov.router)
app.include_router(road_safety.router)
app.include_router(vehicle_trust.router)
