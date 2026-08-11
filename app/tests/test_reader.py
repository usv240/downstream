from downstream.reader import DrawingReader, DrawingReplayClient


def response(**changes):
    base = {
        "transcription": "TOP OF DAM EL. 742.6\nMAX. EMBANKMENT HT. 31 FT",
        "facts": [
            {"key": "crest_elevation", "value": "742.6 ft", "quoted_text": "TOP OF DAM EL. 742.6", "confidence": 0.95},
            {"key": "dam_height_ft", "value": "31", "quoted_text": "MAX. EMBANKMENT HT. 31 FT", "confidence": 0.9},
        ],
    }
    base.update(changes)
    return base


def test_valid_recorded_facts_keep_provenance():
    result = DrawingReader(DrawingReplayClient(response())).read(b"png")
    assert len(result.facts) == 2
    assert all(fact["provenance"] == "recorded_gemini_3_5_flash" for fact in result.facts)


def test_empty_quote_cannot_launder_a_fact():
    raw = response(facts=[{"key": "dam_height_ft", "value": "999", "quoted_text": "", "confidence": 1}])
    result = DrawingReader(DrawingReplayClient(raw)).read(b"png")
    assert result.facts == []
    assert "empty quote" in result.dropped[0]


def test_quote_must_appear_in_transcription():
    raw = response(facts=[{"key": "dam_height_ft", "value": "999", "quoted_text": "NOT PRESENT", "confidence": 1}])
    result = DrawingReader(DrawingReplayClient(raw)).read(b"png")
    assert result.facts == []
    assert "not in transcription" in result.dropped[0]


def test_invalid_confidence_is_dropped():
    raw = response(facts=[{"key": "dam_height_ft", "value": "31", "quoted_text": "MAX. EMBANKMENT HT. 31 FT", "confidence": 2}])
    assert DrawingReader(DrawingReplayClient(raw)).read(b"png").facts == []


def test_transcription_is_required():
    try:
        DrawingReader(DrawingReplayClient(response(transcription=""))).read(b"png")
    except ValueError as exc:
        assert "transcription" in str(exc)
    else:
        raise AssertionError("empty transcription accepted")


def test_image_is_required():
    try:
        DrawingReader(DrawingReplayClient(response())).read(b"")
    except ValueError as exc:
        assert "image" in str(exc)
    else:
        raise AssertionError("empty image accepted")
