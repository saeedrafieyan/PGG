"""Local HTTP API: Describe -> Review -> Download over ``DesignSession``.

Endpoints (JSON):

    GET  /api/printers                      printer / process profiles
    POST /api/sessions {text, process?, printer?}  -> proposal card (nothing generated)
    POST /api/sessions/{id}/approve         start generation (checkpoint 1), returns immediately
    GET  /api/sessions/{id}                 state, progress stage, proposal and result cards
    GET  /api/sessions/{id}/files/{kind}    stl | 3mf | step | report | trace

``GET /`` serves a one-page front end using these endpoints. Generation runs in
one background worker at a time (it can need several GB of memory). The
server binds to localhost by default; it has no authentication and is meant
for a single user on their own machine until deployment (deferred).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Route

from porous_designer.services.design_session import DesignSession

STATIC = Path(__file__).resolve().parent / "static"
MEDIA = {"stl": "model/stl", "3mf": "model/3mf", "step": "model/step", "report": "text/html", "trace": "application/json"}


class SessionStore:
    def __init__(self, *, output_dir: Path | None = None, generate=None, provider=None, settings=None) -> None:
        self.sessions: dict[str, DesignSession] = {}
        self.output_dir, self.generate, self.provider, self.settings = output_dir, generate, provider, settings
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="age-generation")
        self.lock = threading.Lock()

    def new(self) -> DesignSession:
        s = DesignSession(output_dir=self.output_dir, generate=self.generate, provider=self.provider, settings=self.settings)
        with self.lock:
            self.sessions[s.session_id] = s
        return s

    def get(self, sid: str) -> DesignSession | None:
        return self.sessions.get(sid)


def create_app(store: SessionStore | None = None) -> Starlette:
    store = store or SessionStore()

    async def index(request: Request):
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    async def printers(request: Request):
        from porous_designer.printability.profiles import all_profiles

        return JSONResponse(
            [
                {"id": p.id, "process": p.process, "name": p.display_name or p.id, "min_wall_mm": p.min_wall_mm, "min_hole_mm": p.min_hole_mm, "calibrated": p.calibrated}
                for p in sorted(all_profiles().values(), key=lambda p: (p.process, p.id))
            ]
        )

    async def create(request: Request):
        body = await request.json()
        text = str(body.get("text", "")).strip()
        if not text:
            return JSONResponse({"error": "empty request"}, status_code=400)
        session = store.new()
        try:
            card = session.propose(text, process=body.get("process") or None, printer=body.get("printer") or None)
        except Exception as exc:
            return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)
        return JSONResponse({"session_id": session.session_id, "state": session.state, "proposal": card})

    async def status(request: Request):
        session = store.get(request.path_params["sid"])
        if session is None:
            return JSONResponse({"error": "unknown session"}, status_code=404)
        return JSONResponse(session.to_dict())

    async def approve(request: Request):
        session = store.get(request.path_params["sid"])
        if session is None:
            return JSONResponse({"error": "unknown session"}, status_code=404)
        if session.state != "proposed":
            return JSONResponse({"error": f"cannot approve in state {session.state}"}, status_code=409)
        session.state, session.stage, session.message = "queued", "queued", "Waiting for the generator"

        def job():
            try:
                session.approve()
            except Exception:
                pass  # recorded in session.error

        store.executor.submit(job)
        return JSONResponse(session.to_dict(), status_code=202)

    async def download(request: Request):
        session = store.get(request.path_params["sid"])
        if session is None:
            return JSONResponse({"error": "unknown session"}, status_code=404)
        kind = request.path_params["kind"]
        path = session.files().get(kind)
        if path is None:
            return JSONResponse({"error": f"no {kind} file"}, status_code=404)
        return FileResponse(path, media_type=MEDIA.get(kind, "application/octet-stream"), filename=path.name)

    return Starlette(
        routes=[
            Route("/", index),
            Route("/api/printers", printers),
            Route("/api/sessions", create, methods=["POST"]),
            Route("/api/sessions/{sid}", status),
            Route("/api/sessions/{sid}/approve", approve, methods=["POST"]),
            Route("/api/sessions/{sid}/files/{kind}", download),
        ]
    )


def serve(host: str = "127.0.0.1", port: int = 8765, **store_kwargs) -> None:
    import uvicorn

    uvicorn.run(create_app(SessionStore(**store_kwargs)), host=host, port=port, log_level="info")
