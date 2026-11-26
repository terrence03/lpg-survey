"""Survey rules and row formatting, matching the original Streamlit app."""

import json
from pathlib import Path

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "public" / "questions.json"
QUESTIONS: dict = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]

CHECKIN_HEADERS = ["timestamp", "sid"]
SURVEY_HEADERS = [
    "timestamp", "sid", "q1", "q2", "q3", "gender", "age",
    "lpg_usage", "contract", "contract_no", "contract_no_other",
    "contract_aware", "contract_aware_no", "contract_aware_no_other",
    "contract_willing", "contract_willing_no", "contract_willing_no_other",
    "policy_info", "policy_info_network", "policy_info_network_other",
    "policy_info_advertising", "policy_info_advertising_other", "policy_info_other",
]
TEXT_KEYS = {q["other_key"]: k for k, q in QUESTIONS.items() if "other_key" in q}


class InvalidSurvey(ValueError):
    pass


def _visible(key: str, a: dict) -> bool:
    q = QUESTIONS[key]
    show = q.get("show")
    if not show:
        return True
    if q.get("parent") and not _visible(q["parent"], a):
        return False
    v = a.get(show["q"])
    if "eq" in show:
        return v == show["eq"]
    if "in" in show:
        return v in show["in"]
    if "has" in show:
        return isinstance(v, list) and show["has"] in v
    return True


def clean(answers: dict, texts: dict) -> dict:
    """Keep only known, visible answers with valid option codes."""
    out: dict = {}
    for key, q in QUESTIONS.items():
        v = answers.get(key)
        if v is None:
            continue
        opts = q["options"]
        if q["type"] == "multi":
            if not isinstance(v, list) or not all(isinstance(x, str) and x in opts for x in v):
                raise InvalidSurvey(f"bad value for {key}")
            v = [x for x in opts if x in v]
            if not v:
                continue
        elif not (isinstance(v, str) and v in opts):
            raise InvalidSurvey(f"bad value for {key}")
        out[key] = v
    out = {k: v for k, v in out.items() if _visible(k, out)}
    for tkey, qkey in TEXT_KEYS.items():
        t = texts.get(tkey)
        q = QUESTIONS[qkey]
        sel = out.get(qkey)
        chosen = sel == q["other"] or (isinstance(sel, list) and q["other"] in sel)
        if chosen and isinstance(t, str) and t.strip():
            out[tkey] = t.strip()[:500]
    return out


def is_complete(r: dict) -> bool:
    """Port of check_respone() in the original pages/survey.py."""
    overall = all(r.get(k) for k in ("q1", "q2", "q3", "gender", "age"))

    if r.get("lpg_usage") == "1":
        lpg = r.get("contract") == "1" or bool(r.get("contract") and r.get("contract_no"))
    else:
        lpg = r.get("lpg_usage") == "2"

    if r.get("contract_aware"):
        aware = r.get("contract_aware_no") is not None if r["contract_aware"] == "4" else True
    else:
        aware = False

    if r.get("contract_willing") == "1":
        willing = True
    elif r.get("contract_willing") == "2":
        willing = r.get("contract_willing_no") is not None
    else:
        willing = False

    pi = r.get("policy_info")
    if pi:
        if "7" in pi:
            policy = r.get("policy_info_network") is not None
        elif "8" in pi:
            policy = r.get("policy_info_advertising") is not None
        else:
            policy = True
    else:
        policy = False

    return all([overall, lpg, aware, willing, policy])


def to_row(r: dict, timestamp: str, sid: str) -> list:
    """Same output as format_response(..., to_list=True): option labels, multi joined by '/'."""
    row = {"timestamp": timestamp, "sid": sid}
    for k, v in r.items():
        if k in TEXT_KEYS:
            row[k] = v
        elif isinstance(v, list):
            row[k] = "/".join(QUESTIONS[k]["options"][x] for x in v)
        else:
            row[k] = QUESTIONS[k]["options"][v]
    return [row.get(c) for c in SURVEY_HEADERS]
