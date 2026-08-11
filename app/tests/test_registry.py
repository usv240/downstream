import urllib.parse

import pytest

from downstream.registry import build_query, fallback_records


def test_query_uses_literal_official_field_names():
    parsed = urllib.parse.urlparse(build_query())
    params = urllib.parse.parse_qs(parsed.query)
    assert params["where"] == ["HAZARD_POTENTIAL='High' AND EAP_PREPARED IS NULL"]
    assert "NIDID" in params["outFields"][0]
    assert params["returnGeometry"] == ["false"]


def test_state_filter_escapes_quotes():
    params = urllib.parse.parse_qs(urllib.parse.urlparse(build_query(state="Owner's State")).query)
    assert "Owner''s State" in params["where"][0]


@pytest.mark.parametrize("limit", [0, 26, -1, 1000])
def test_query_limit_is_bounded(limit):
    with pytest.raises(ValueError):
        build_query(limit=limit)


def test_fallback_never_represents_cache_as_live():
    result = fallback_records()
    assert result.live is False
    assert result.records == []
    assert "unavailable" in result.interpretation


def test_interpretation_says_unreported_not_missing_plan():
    result = fallback_records()
    assert "No cached record" in result.interpretation
