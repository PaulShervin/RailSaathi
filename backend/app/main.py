"""FastAPI application factory. Run with: uv run uvicorn app.main:app --reload"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware import AccessLogMiddleware, BodySizeLimitMiddleware, RateLimitMiddleware
from app.api.routes import router
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.harness.errors import PlannerError
from app.navigation.routers import disruptions as nav_disruptions
from app.navigation.routers import navigation as nav_routing
from app.navigation.routers import stations as nav_stations
from app.navigation.services.station_store import InvalidStationId

log = logging.getLogger("railsaathi")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        title="RailSaathi AI — Smart Passenger Planner API",
        version=settings.api_version,
        description="Prototype planner API. Uses clearly labelled DEMO railway data. Does not book tickets.",
    )
    app.state.container = container or build_container(settings)

    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes,
                       large_prefixes={"/api/stations/": 1_048_576})  # station-editor graph uploads (admin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-Id", "X-Admin-Token"],
    )
    _register_errors(app)
    app.include_router(router)
    # Station navigation (indoor routing on floor plans), merged from Navigation_exp.
    app.include_router(nav_stations.router, tags=["station-navigation"])
    app.include_router(nav_routing.router, tags=["station-navigation"])
    app.include_router(nav_disruptions.router, tags=["station-navigation"])
    return app


def _register_errors(app: FastAPI) -> None:
    @app.exception_handler(PlannerError)
    async def planner_error(_: Request, exc: PlannerError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status,
                            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    @app.exception_handler(InvalidStationId)
    async def invalid_station(_: Request, exc: InvalidStationId) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"Unknown station '{exc}'"})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "code": "invalid_request", "message": "The request is invalid.", "details": {"errors": details}}})

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": {
            "code": "internal_error", "message": "Something went wrong. Please try again.", "details": {}}})


app = create_app()
