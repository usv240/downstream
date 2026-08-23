"""Redaction gate tests.

The property under test: identifiers do not cross the model boundary, what the note actually says
about the site does, and the gate fails closed rather than proceeding unredacted.

This matters here because of one specific question the partner asks. "Who is the county emergency
manager, and which number works after hours?" is a request for a person's name and a person's
phone number, and the answer is the whole point of a notification flowchart. The owner keeps the
verbatim answer; what leaves for a model is the pseudonymised form.
"""

import pytest

from spine.redact import (
    NullReviewer,
    RedactionError,
    Redactor,
    ReplayReviewer,
)

OWNER_NOTE = """CEDAR HOLLOW DAM, OWNER FILE
Owner: Harold Jennings
Emergency Manager: Dana Whitfield
DOB: 04/12/1951               Phone: (406) 555-0173
Address: 118 Cedar Lane
Email: h.jennings51@example.com
SSN: 521-44-9083

The gravel lane washes out at the second bend in heavy rain.
The overflow channel was clear at the last walk-through.
"""


@pytest.fixture
def redactor():
    return Redactor(NullReviewer())


def test_all_identifier_kinds_are_removed(redactor):
    result = redactor.redact(OWNER_NOTE)
    for identifier in (
        "Harold Jennings", "Dana Whitfield", "04/12/1951", "(406) 555-0173",
        "118 Cedar Lane", "h.jennings51@example.com", "521-44-9083",
    ):
        assert identifier not in result.text, f"{identifier!r} leaked through the gate"


def test_what_the_owner_said_about_the_site_is_untouched(redactor):
    """The gate removes who the owner is, never what they told you about the dam."""
    result = redactor.redact(OWNER_NOTE)
    assert "The gravel lane washes out at the second bend in heavy rain." in result.text
    assert "The overflow channel was clear at the last walk-through." in result.text


def test_pseudonyms_are_stable_and_labeled(redactor):
    result = redactor.redact(OWNER_NOTE)
    for pseudonym in ("PERSON_1", "PHONE_1", "SSN_1", "DOB_1", "EMAIL_1", "ADDRESS_1"):
        assert pseudonym in result.text


def test_labels_survive_so_the_document_stays_readable(redactor):
    """A model still needs to know a field was a phone number; it must not know which."""
    result = redactor.redact(OWNER_NOTE)
    assert "Phone: PHONE_1" in result.text
    assert "Owner: PERSON_1" in result.text


def test_the_mapping_recovers_every_original(redactor):
    mapping = redactor.redact(OWNER_NOTE).mapping
    assert mapping["PERSON_1"] == "Harold Jennings"
    assert mapping["SSN_1"] == "521-44-9083"
    assert mapping["PHONE_1"] == "(406) 555-0173"


def test_repeated_identifiers_get_distinct_pseudonyms(redactor):
    text = "Owner: Ann Berg\nInspector: Joe Ruiz\nSSN: 111-22-3333\nSSN: 444-55-6666"
    result = redactor.redact(text)
    assert "PERSON_1" in result.text and "PERSON_2" in result.text
    assert result.mapping["SSN_1"] == "111-22-3333"
    assert result.mapping["SSN_2"] == "444-55-6666"


def test_all_caps_names_are_caught(redactor):
    """Regression. Official letters print names in caps; the pattern required Titlecase, so
    'Applicant: DEVON CARTER' matched nothing and the name reached the model endpoint."""
    result = redactor.redact("Applicant: DEVON CARTER\nStatus: ineligible")
    assert "DEVON CARTER" not in result.text
    assert result.mapping["PERSON_1"] == "DEVON CARTER"


def test_the_labels_this_product_actually_sees_are_recognised(redactor):
    """An owner file, an inspection note and a notification flowchart use these words."""
    for label in ("Owner", "Operator", "Emergency Manager", "Contact", "Inspector", "Engineer"):
        result = redactor.redact(f"{label}: Mara Rivera")
        assert "Mara Rivera" not in result.text, f"{label} label leaked the name"


def test_benefit_labels_are_still_recognised(redactor):
    """Regression. A FEMA determination letter is one of the documents an owner may hand over."""
    for label in ("Applicant", "Applicant Name", "Recipient", "Claimant"):
        result = redactor.redact(f"{label}: Mara Rivera")
        assert "Mara Rivera" not in result.text, f"{label} label leaked the name"


def test_case_reference_numbers_are_removed(redactor):
    """A FEMA registration number identifies the applicant as directly as their name."""
    result = redactor.redact("Registration: DEMO-7319\nDisaster: DR-4999")
    assert "DEMO-7319" not in result.text
    assert result.mapping["CASE_REF_1"] == "DEMO-7319"


def test_a_letter_with_no_street_address_still_redacts(redactor):
    """The audit that started this: one fixture reported zero redactions purely because it had
    no street address, which masked the fact that names and case numbers were leaking in all
    four letters."""
    letter = (
        "FEDERAL DISASTER ASSISTANCE\n"
        "Applicant: DEVON CARTER\n"
        "Registration: DEMO-7319\n"
        "We could not confirm that you lived at the damaged address.\n"
    )
    result = redactor.redact(letter)
    assert len(result.replacements) >= 2
    assert "DEVON CARTER" not in result.text
    assert "DEMO-7319" not in result.text
    # The reason for denial must survive: it is the whole product.
    assert "could not confirm that you lived" in result.text


@pytest.mark.parametrize(
    "text,identifier",
    [
        ("Applicant: MARY-JANE OKONKWO", "MARY-JANE OKONKWO"),
        ("Applicant: SEAN O'BRIEN", "SEAN O'BRIEN"),
        ("Applicant: SEAN O’BRIEN", "SEAN O’BRIEN"),
        ("owner: Devon Carter", "Devon Carter"),
        ("Mailing: P.O. Box 4417", "P.O. Box 4417"),
        ("Mailing: PO Box 22", "PO Box 22"),
    ],
)
def test_ordinary_real_world_spellings_are_not_missed(redactor, text, identifier):
    """Regression from boundary probing. Every one of these leaked: the name class excluded
    hyphens and apostrophes, the label was case-sensitive, and a PO box has no street suffix
    for the address pattern to anchor on."""
    assert identifier not in redactor.redact(text).text


@pytest.mark.parametrize(
    "text",
    [
        "The spillway was clear and the access road was passable.",
        "Name of disaster: SEVERE STORMS AND FLOODING",
        "MAX. EMBANKMENT HT. 31 FT",
        "The county road crosses the outlet channel below the dam.",
    ],
)
def test_the_gate_does_not_over_redact(redactor, text):
    """Over-redaction is safer than under-redaction but still destroys the product: the reason
    for a denial and the owner's description of the site are the whole output."""
    assert redactor.redact(text).text == text


def test_a_document_with_no_identifiers_passes_through_unchanged(redactor):
    text = "TOP OF DAM EL. 742.6\nCONC. O.F. SPILLWAY 18 FT"
    result = redactor.redact(text)
    assert result.text == text
    assert result.replacements == []


def test_the_reviewer_catches_unlabeled_names():
    """Layer 2: a name in running text has no shape a regex can trust.

    This is the gap the recorded Gemma evidence covers. The pattern layer cannot find
    'Taylor McNeil' in a sentence, because nothing about it looks different from a place.
    """
    text = "The gravel lane was checked yesterday with Taylor McNeil. The spillway was clear."
    result = Redactor(ReplayReviewer(["Taylor McNeil"])).redact(text)
    assert "Taylor McNeil" not in result.text
    assert "PERSON_1" in result.text
    assert "The spillway was clear." in result.text


def test_reviewer_names_not_present_are_ignored():
    result = Redactor(ReplayReviewer(["Nobody Here"])).redact("The spillway was clear.")
    assert result.replacements == []


def test_replay_reviewer_costs_are_visible():
    reviewer = ReplayReviewer([])
    redactor = Redactor(reviewer)
    for _ in range(5):
        redactor.redact("some text")
    assert reviewer.calls == 5


def test_a_failing_reviewer_fails_the_gate_closed():
    """If the gate errors, the step fails. Unredacted text never proceeds as a fallback."""

    class Broken(NullReviewer):
        def find_names(self, text):
            raise RedactionError("model unavailable")

    with pytest.raises(RedactionError):
        Redactor(Broken()).redact(OWNER_NOTE)
