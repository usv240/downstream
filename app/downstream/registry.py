"""Read-only access to the public USACE National Inventory of Dams service."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

NID_LAYER = (
    "https://geospatial.sec.usace.army.mil/dls/rest/services/NID/"
    "National_Inventory_of_Dams_Public_Service/FeatureServer/0"
)

PUBLIC_FIELDS = (
    "NIDID,NAME,STATE,COUNTYSTATE,LATITUDE,LONGITUDE,DAM_HEIGHT,"
    "YEAR_COMPLETED,HAZARD_POTENTIAL,EAP_PREPARED,PRIMARY_OWNER_TYPE"
)


@dataclass(frozen=True)
class NIDResult:
    records: list[dict[str, Any]]
    source_url: str
    live: bool
    interpretation: str


def build_query(limit: int = 5, state: str | None = None) -> str:
    """Build the literal, reviewable ArcGIS query used by the public demo."""
    if not 1 <= limit <= 25:
        raise ValueError("limit must be between 1 and 25")
    where = "HAZARD_POTENTIAL='High' AND EAP_PREPARED IS NULL"
    if state:
        safe_state = state.replace("'", "''")
        where += f" AND STATE='{safe_state}'"
    params = {
        "where": where,
        "outFields": PUBLIC_FIELDS,
        "returnGeometry": "false",
        "resultRecordCount": str(limit),
        "orderByFields": "STATE,NAME",
        "f": "json",
    }
    return f"{NID_LAYER}/query?{urllib.parse.urlencode(params)}"


def search_high_hazard_unreported(
    limit: int = 5, state: str | None = None, timeout: float = 8.0
) -> NIDResult:
    """Return records whose public EAP status is null.

    Null means unreported in this field. It does not prove that an EAP does not exist.
    """
    url = build_query(limit, state)
    request = urllib.request.Request(url, headers={"User-Agent": "Downstream/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(payload["error"].get("message", "NID query failed"))
    rows = [feature.get("attributes", {}) for feature in payload.get("features", [])]
    return NIDResult(
        records=rows,
        source_url=url,
        live=True,
        interpretation=(
            "These are high-hazard records with no EAP status reported in the selected public "
            "field. This is not evidence that an Emergency Action Plan does not exist."
        ),
    )


def fallback_records() -> NIDResult:
    """A labelled fallback keeps the demo understandable during a federal endpoint outage."""
    return NIDResult(
        records=[],
        source_url=NID_LAYER,
        live=False,
        interpretation=(
            "The live NID service was unavailable. No cached record is represented as current, "
            "and the synthetic authoring preset remains available."
        ),
    )
