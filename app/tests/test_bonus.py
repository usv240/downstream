from downstream.bonus import SYNTHETIC_NOTE, gemma_redaction_proof


def test_recorded_gemma_proof_removes_every_returned_name():
    proof = gemma_redaction_proof()
    assert proof["identifiers_leaked_in_replay"] == []
    assert all(name not in proof["redacted_text"] for name in proof["recorded_spans"])


def test_gemma_has_a_real_safety_job_and_narrow_boundary():
    proof = gemma_redaction_proof()
    assert "owner notes" in proof["job"]
    assert "spans only" in proof["boundary"]
    assert proof["input_is_synthetic"] is True


def test_bonus_evidence_names_actual_maas_model():
    assert gemma_redaction_proof()["model"] == "gemma-4-26b-a4b-it-maas"


def test_synthetic_note_contains_no_real_contact_claim():
    assert "Taylor McNeil" in SYNTHETIC_NOTE
    assert "synthetic" not in SYNTHETIC_NOTE.lower()
