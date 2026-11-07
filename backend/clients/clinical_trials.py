"""Client for interacting with the ClinicalTrials.gov REST API v2."""

import logging
import time
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

BASE_URL: Final[str] = "https://clinicaltrials.gov/api/v2"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
MAX_RETRIES: Final[int] = 3
RETRY_BACKOFF_SECONDS: Final[float] = 1.5
MIN_REQUEST_INTERVAL_SECONDS: Final[float] = 1.0

# Key fields needed for protocol analysis, clustering, and defect diagnosis
DEFAULT_PROTOCOL_FIELDS: Final[list[str]] = [
    "NCTId",
    "BriefTitle",
    "OfficialTitle",
    "OverallStatus",
    "WhyStopped",
    "StartDate",
    "CompletionDate",
    "LeadSponsorName",
    "OversightModule",
    "Phase",
    "DesignModule",
    "ArmsInterventionsModule",
    "OutcomesModule",
    "EligibilityModule",
    "ContactsLocationsModule",
    "DerivedSection",
]


ParamType = str | int | float | bool | None


class StudySearchResult(BaseModel):
    """Pydantic boundary model for paginated study search response."""

    model_config = ConfigDict(extra="ignore")

    studies: list[dict[str, object]] = Field(default_factory=list)
    next_page_token: str | None = Field(default=None, alias="nextPageToken")
    total_count: int | None = Field(default=None, alias="totalCount")


class ClinicalTrialsClient:
    """Synchronous client for ClinicalTrials.gov REST API v2 with retries and rate limiting."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        request_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.request_interval_seconds = request_interval_seconds
        self._last_request_timestamp: float = 0.0

    def _enforce_rate_limit(self) -> None:
        """Enforces polite rate limiting between consecutive network requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_timestamp
        if elapsed < self.request_interval_seconds:
            time.sleep(self.request_interval_seconds - elapsed)
        self._last_request_timestamp = time.monotonic()

    def _execute_get_request(
        self, endpoint: str, params: list[tuple[str, ParamType]]
    ) -> dict[str, object]:
        """Executes a GET request with exponential backoff retries and loud errors."""
        url = f"{self.base_url}{endpoint}"
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            self._enforce_rate_limit()
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise TypeError(
                            f"Expected JSON object from {url}, got {type(data).__name__}"
                        )
                    # Safe cast: JSON objects are string-keyed dictionaries
                    return dict(data)
            except (httpx.HTTPError, ValueError, TypeError) as error:
                last_exception = error
                logger.warning(
                    "ClinicalTrials.gov request failed: attempt=%d url=%s error=%s",
                    attempt,
                    url,
                    error,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        raise RuntimeError(
            f"Failed to fetch from {url} after {MAX_RETRIES} attempts"
        ) from last_exception

    def search_studies(
        self,
        condition: str | None = None,
        status: str | None = None,
        phase: str | None = None,
        page_size: int = 50,
        page_token: str | None = None,
        study_type: str | None = "INTERVENTIONAL",
        fields: list[str] | None = None,
        count_total: bool = True,
    ) -> StudySearchResult:
        """Searches studies matching condition and status filters."""
        params: list[tuple[str, ParamType]] = []

        if condition:
            params.append(("query.cond", condition))
        if status:
            params.append(("filter.overallStatus", status))
        if count_total:
            params.append(("countTotal", "true"))

        advanced_filters: list[str] = []
        if study_type:
            advanced_filters.append(f"AREA[StudyType]{study_type}")
        if phase:
            advanced_filters.append(f"AREA[Phase]{phase}")
        if advanced_filters:
            params.append(("filter.advanced", " AND ".join(advanced_filters)))

        selected_fields = fields if fields is not None else DEFAULT_PROTOCOL_FIELDS
        params.append(("fields", ",".join(selected_fields)))
        params.append(("pageSize", str(page_size)))

        if page_token:
            params.append(("pageToken", page_token))

        raw_response = self._execute_get_request("/studies", params)
        return StudySearchResult.model_validate(raw_response)

    def get_study(self, nct_id: str) -> dict[str, object]:
        """Fetches full study protocol by NCT ID."""
        cleaned_id = nct_id.strip().upper()
        if not cleaned_id.startswith("NCT"):
            raise ValueError(
                f"Invalid NCT ID format: expected NCT prefix, got {cleaned_id}"
            )
        return self._execute_get_request(f"/studies/{cleaned_id}", [])
