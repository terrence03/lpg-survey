import logging
import re
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage, survey

logging.basicConfig(level=logging.INFO)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
SID = re.compile(r"^[0-9a-fA-F-]{8,64}$")

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


class CheckIn(BaseModel):
    sid: str = Field(max_length=64)


class Survey(BaseModel):
    sid: str = Field(max_length=64)
    answers: dict
    texts: dict = {}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/checkin")
def checkin(body: CheckIn):
    if not SID.match(body.sid):
        raise HTTPException(400, "bad sid")
    if _first_time("checkin", body.sid):
        storage.append("check_in", survey.CHECKIN_HEADERS, [[storage.get_timestamp(), body.sid]])
    return {"ok": True}


@app.post("/api/survey")
def submit(body: Survey):
    if not SID.match(body.sid):
        raise HTTPException(400, "bad sid")
    try:
        r = survey.clean(body.answers, body.texts)
    except survey.InvalidSurvey as e:
        raise HTTPException(400, str(e)) from e
    if not survey.is_complete(r):
        raise HTTPException(422, "請檢查是否所有問題都已回答")
    if _first_time("survey", body.sid):
        storage.append("response", survey.SURVEY_HEADERS, [survey.to_row(r, storage.get_timestamp(), body.sid)])
    return {"ok": True}


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "public", html=True), name="static")
