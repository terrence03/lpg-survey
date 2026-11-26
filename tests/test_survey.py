from server import survey

BASE = {"q1": "1", "q2": "4", "q3": "4", "gender": "1", "age": "2",
        "lpg_usage": "2", "contract_aware": "1", "contract_willing": "1", "policy_info": ["1"]}


def test_minimal_complete():
    assert survey.is_complete(survey.clean(BASE, {}))


def test_hidden_answers_dropped():
    r = survey.clean({**BASE, "contract": "2", "contract_no": ["1"]}, {"contract_no_other": "x"})
    assert "contract" not in r and "contract_no" not in r and "contract_no_other" not in r


def test_contract_no_required_when_not_signed():
    r = survey.clean({**BASE, "lpg_usage": "1", "contract": "2"}, {})
    assert not survey.is_complete(r)
    r = survey.clean({**BASE, "lpg_usage": "1", "contract": "2", "contract_no": ["6"]}, {"contract_no_other": "x"})
    assert survey.is_complete(r) and r["contract_no_other"] == "x"


def test_original_quirks_kept():
    # 5.1 only required for "完全不瞭解"
    assert survey.is_complete(survey.clean({**BASE, "contract_aware": "3"}, {}))
    assert not survey.is_complete(survey.clean({**BASE, "contract_aware": "4"}, {}))
    # with both 7 and 8 ticked only 7.1 is checked
    r = survey.clean({**BASE, "policy_info": ["7", "8"], "policy_info_network": ["1"]}, {})
    assert survey.is_complete(r)


def test_row_format():
    r = survey.clean({**BASE, "policy_info": ["7", "1"], "policy_info_network": ["2", "1"]}, {})
    row = survey.to_row(r, "2026-01-01 00:00:00", "sid")
    d = dict(zip(survey.SURVEY_HEADERS, row))
    assert d["policy_info"] == "地方或特色活動攤位/網路社群"
    assert d["policy_info_network"] == "Facebook/Line"
    assert d["q1"].startswith("A.") and d["contract"] is None
    assert len(row) == 23


def test_bad_code_rejected():
    import pytest
    with pytest.raises(survey.InvalidSurvey):
        survey.clean({**BASE, "age": "9"}, {})
