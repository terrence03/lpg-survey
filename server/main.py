import json
import logging
import os
import re
from collections import OrderedDict
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import storage, survey

logging.basicConfig(level=logging.INFO)
SID = re.compile(r"^[0-9a-fA-F-]{8,64}$")
PUBLIC = Path(__file__).resolve().parent.parent / "public"

# Recently stored sids, so a phone retrying a send does not create duplicate rows.
_seen: "OrderedDict[tuple[str, str], None]" = OrderedDict()


def _first_time(kind: str, sid: str) -> bool:
    key = (kind, sid)
    if key in _seen:
        return False
    _seen[key] = None
    if len(_seen) > 20000:
        _seen.popitem(last=False)
    return True


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


async def _body(request: Request) -> dict | None:
    raw = await request.body()
    if len(raw) > 64_000:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    sid = data.get("sid")
    if not isinstance(sid, str) or not SID.match(sid):
        return None
    return data


async def health(request: Request):
    return JSONResponse({"ok": True})


def _store_checkin(sid: str) -> None:
    if _first_time("checkin", sid):
        storage.append("check_in", survey.CHECKIN_HEADERS, [[storage.get_timestamp(), sid]])


def _store_survey(sid: str, r: dict) -> None:
    if _first_time("survey", sid):
        storage.append("response", survey.SURVEY_HEADERS, [survey.to_row(r, storage.get_timestamp(), sid)])


async def checkin(request: Request):
    data = await _body(request)
    if data is None:
        return _error(400, "bad request")
    await run_in_threadpool(_store_checkin, data["sid"])
    return JSONResponse({"ok": True})


async def submit(request: Request):
    data = await _body(request)
    if data is None or not isinstance(data.get("answers"), dict):
        return _error(400, "bad request")
    texts = data.get("texts") if isinstance(data.get("texts"), dict) else {}
    try:
        r = survey.clean(data["answers"], texts)
    except survey.InvalidSurvey as e:
        return _error(400, str(e))
    if not survey.is_complete(r):
        return _error(422, "請檢查是否所有問題都已回答")
    await run_in_threadpool(_store_survey, data["sid"], r)
    return JSONResponse({"ok": True})


routes = [
    Route("/api/health", health, methods=["GET"]),
    Route("/api/checkin", checkin, methods=["POST"]),
    Route("/api/survey", submit, methods=["POST"]),
    Mount("/", StaticFiles(directory=PUBLIC, html=True), name="static"),
]

# When the web server forwards the full URL (e.g. IIS HttpPlatformHandler at
# /lpg-survey), set BASE_PATH so the app is served under that prefix.
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")
if BASE_PATH:
    async def _add_slash(request: Request):
        return RedirectResponse(BASE_PATH + "/", status_code=301)

    routes = [Route(BASE_PATH, _add_slash), Mount(BASE_PATH, routes=routes)]

app = Starlette(routes=routes)
