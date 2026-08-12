import urllib.parse

import pytest

from downstream.registry import build_query, fallback_records


def test_query_uses_literal_official_field_names():
    parsed = urllib.parse.urlparse(build_query())
    params = urllib.parse.parse_qs(parsed.query)
    assert params["where"] == ["HAZARD_POTENTIAL='High' AND EAP_PREPARED IS NULL"]
    assert "NIDID" in params["outFields"][0]
    assert params["returnGeometry"] == ["false"]


def test_state_filter_rejects_a_value_that_is_not_a_state():
    """Stronger than the previous escaping contract: the value never reaches the query at all."""
    with pytest.raises(ValueError, match="not a state"):
        build_query(state="Owner's State")


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


def _where(url: str) -> str:
    """build_query returns a percent-encoded URL; assertions belong on the decoded clause."""
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["where"][0]


# --- State filtering --------------------------------------------------------------
#
# Regression: NID spells the state out in full, so STATE='IA' matched nothing and the query
# returned zero rows with live=True and no error. A caller reads that as "no high-hazard dam in
# Iowa is missing an EAP", which is a false statement produced by this system. Returning nothing
# is not a safe default when the question was answerable.


def test_a_two_letter_state_is_translated_to_the_spelling_nid_actually_uses():
    from downstream.registry import build_query, resolve_state

    assert resolve_state("IA") == "Iowa"
    assert resolve_state("ia") == "Iowa"
    where = _where(build_query(state="IA"))
    assert "STATE='Iowa'" in where
    assert "STATE='IA'" not in where


def test_a_full_state_name_is_accepted_as_written():
    from downstream.registry import build_query, resolve_state

    assert resolve_state("Iowa") == "Iowa"
    assert resolve_state("north carolina") == "North Carolina"
    assert "STATE='North Carolina'" in _where(build_query(state="north carolina"))


def test_an_unrecognised_state_raises_instead_of_answering_wrongly():
    import pytest

    from downstream.registry import build_query

    with pytest.raises(ValueError, match="not a state"):
        build_query(state="Iowaa")


def test_a_quote_in_the_state_cannot_break_out_of_the_where_clause():
    import pytest

    from downstream.registry import build_query

    with pytest.raises(ValueError):
        build_query(state="' OR 1=1 --")
