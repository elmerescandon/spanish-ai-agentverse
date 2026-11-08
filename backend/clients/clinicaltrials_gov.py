"""ClinicalTrials.gov API v2 client: peer trial search and study fetch.

Responses are validated into typed models that mirror the registry's own
JSON structure, so a value's field path (for provenance) is the same as in
the registry. Only the fields the comparison agent uses are modelled.
"""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

logger = logging.getLogger(__name__)

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"
STUDY_PAGE_URL_TEMPLATE = "https://clinicaltrials.gov/study/{nct_id}"
# Whole sections rather than single fields: field names are easy to get
# wrong, and a record is only ~35 KB.
REQUESTED_SECTIONS = "protocolSection,derivedSection,documentSection"
USER_AGENT = "protocol-gap-agent/0.1 (UCL AgentVerse hackathon)"

REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2.0  # delay is RETRY_BASE_DELAY_SECONDS * 2**n
MIN_SECONDS_BETWEEN_REQUESTS = 1.0  # stays well under the API rate limit
SEARCH_PAGE_SIZE = 100  # API maximum is 1,000; 100 keeps pages small
MAX_SEARCH_PAGES = 10  # caps a runaway search at 1,000 studies
DEFAULT_MAX_STUDIES = 200
ERROR_BODY_PREVIEW_CHARACTERS = 200

HTTP_NOT_FOUND = 404
HTTP_RATE_LIMITED = 429
HTTP_SERVER_ERROR_MIN = 500

NCT_ID_PATTERN = re.compile(r"NCT\d{8}")
UNBOUNDED_RANGE_END = "MAX"


class ClinicalTrialsGovError(RuntimeError):
    """Raised when the registry fails or returns an unexpected payload."""


class StudyNotFoundError(ClinicalTrialsGovError):
    """Raised when the registry has no study with the requested NCT ID."""


class Phase(StrEnum):
    """Trial phase values used by the registry."""

    NOT_APPLICABLE = "NA"
    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1 = "PHASE1"
    PHASE2 = "PHASE2"
    PHASE3 = "PHASE3"
    PHASE4 = "PHASE4"


class OverallStatus(StrEnum):
    """Recruitment status values used by the registry."""

    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    COMPLETED = "COMPLETED"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    RECRUITING = "RECRUITING"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    AVAILABLE = "AVAILABLE"
    NO_LONGER_AVAILABLE = "NO_LONGER_AVAILABLE"
    TEMPORARILY_NOT_AVAILABLE = "TEMPORARILY_NOT_AVAILABLE"
    APPROVED_FOR_MARKETING = "APPROVED_FOR_MARKETING"
    WITHHELD = "WITHHELD"
    UNKNOWN = "UNKNOWN"


class AgeGroup(StrEnum):
    """Standard age groups the registry derives from a trial's age limits."""

    CHILD = "CHILD"
    ADULT = "ADULT"
    OLDER_ADULT = "OLDER_ADULT"


class Masking(StrEnum):
    """Blinding levels used by the registry."""

    NONE = "NONE"
    SINGLE = "SINGLE"
    DOUBLE = "DOUBLE"
    TRIPLE = "TRIPLE"
    QUADRUPLE = "QUADRUPLE"


class Population(StrEnum):
    """Which patients a peer trial is mainly for, used to filter peers."""

    PEDIATRIC = "PEDIATRIC"
    ADULT = "ADULT"


# Registry search syntax for each population: pediatric trials enrol
# children but not older adults; adult trials enrol adults but no children.
POPULATION_FILTERS: dict[Population, str] = {
    Population.PEDIATRIC: (
        "AREA[StdAge]CHILD AND NOT AREA[StdAge]OLDER_ADULT"
    ),
    Population.ADULT: "AREA[StdAge]ADULT AND NOT AREA[StdAge]CHILD",
}


class RegistryModel(BaseModel):
    """Base for registry JSON: camelCase keys, unknown fields ignored."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        frozen=True,
    )


class IdentificationModule(RegistryModel):
    nct_id: str
    brief_title: str
    official_title: str | None = None


class DateStruct(RegistryModel):
    # Kept as text: the registry often gives month precision ("2017-07").
    date: str


class StatusModule(RegistryModel):
    overall_status: OverallStatus
    why_stopped: str | None = None
    start_date_struct: DateStruct | None = None
    completion_date_struct: DateStruct | None = None
    last_update_post_date_struct: DateStruct | None = None


class LeadSponsor(RegistryModel):
    name: str
    sponsor_class: str | None = Field(default=None, alias="class")


class SponsorCollaboratorsModule(RegistryModel):
    lead_sponsor: LeadSponsor | None = None


class OversightModule(RegistryModel):
    oversight_has_dmc: bool | None = None


class ConditionsModule(RegistryModel):
    conditions: list[str] = Field(default_factory=list)


class MaskingInfo(RegistryModel):
    masking: Masking | None = None


class DesignInfo(RegistryModel):
    allocation: str | None = None
    intervention_model: str | None = None
    primary_purpose: str | None = None
    masking_info: MaskingInfo | None = None


class EnrollmentInfo(RegistryModel):
    count: int | None = None
    type: str | None = None


class DesignModule(RegistryModel):
    study_type: str | None = None
    phases: list[Phase] = Field(default_factory=list)
    design_info: DesignInfo | None = None
    enrollment_info: EnrollmentInfo | None = None


class ArmGroup(RegistryModel):
    label: str


class Intervention(RegistryModel):
    type: str | None = None
    name: str


class ArmsInterventionsModule(RegistryModel):
    arm_groups: list[ArmGroup] = Field(default_factory=list)
    interventions: list[Intervention] = Field(default_factory=list)


class Outcome(RegistryModel):
    measure: str
    time_frame: str | None = None


class OutcomesModule(RegistryModel):
    primary_outcomes: list[Outcome] = Field(default_factory=list)
    secondary_outcomes: list[Outcome] = Field(default_factory=list)


class EligibilityModule(RegistryModel):
    eligibility_criteria: str | None = None
    healthy_volunteers: bool | None = None
    sex: str | None = None
    minimum_age: str | None = None
    maximum_age: str | None = None
    std_ages: list[AgeGroup] = Field(default_factory=list)


class Location(RegistryModel):
    facility: str | None = None
    city: str | None = None
    country: str | None = None


class ContactsLocationsModule(RegistryModel):
    locations: list[Location] = Field(default_factory=list)


class ProtocolSection(RegistryModel):
    identification_module: IdentificationModule
    status_module: StatusModule
    sponsor_collaborators_module: SponsorCollaboratorsModule | None = None
    oversight_module: OversightModule | None = None
    conditions_module: ConditionsModule | None = None
    design_module: DesignModule | None = None
    arms_interventions_module: ArmsInterventionsModule | None = None
    outcomes_module: OutcomesModule | None = None
    eligibility_module: EligibilityModule | None = None
    contacts_locations_module: ContactsLocationsModule | None = None


class MeshTerm(RegistryModel):
    term: str


class BrowseModule(RegistryModel):
    meshes: list[MeshTerm] = Field(default_factory=list)


class DerivedSection(RegistryModel):
    condition_browse_module: BrowseModule | None = None
    intervention_browse_module: BrowseModule | None = None


class LargeDocument(RegistryModel):
    type_abbrev: str | None = None
    has_protocol: bool = False
    has_sap: bool = False
    label: str | None = None
    date: str | None = None
    filename: str


class LargeDocumentModule(RegistryModel):
    large_docs: list[LargeDocument] = Field(default_factory=list)


class DocumentSection(RegistryModel):
    large_document_module: LargeDocumentModule = Field(
        default_factory=LargeDocumentModule
    )


class StudyRecord(RegistryModel):
    """One registry study, limited to the sections we request."""

    protocol_section: ProtocolSection
    derived_section: DerivedSection | None = None
    document_section: DocumentSection | None = None

    @property
    def nct_id(self) -> str:
        return self.protocol_section.identification_module.nct_id

    @property
    def url(self) -> str:
        """Public study page, shown to reviewers as the value's source."""
        return STUDY_PAGE_URL_TEMPLATE.format(nct_id=self.nct_id)

    @property
    def last_updated(self) -> str | None:
        """Registry version date, so a value can be traced to a version."""
        last_update = self.protocol_section.status_module
        if last_update.last_update_post_date_struct is None:
            return None
        return last_update.last_update_post_date_struct.date


class SearchPage(RegistryModel):
    studies: list[StudyRecord] = Field(default_factory=list)
    next_page_token: str | None = None
    total_count: int | None = None


@dataclass(frozen=True)
class PeerSearchQuery:
    """Filters that define which registry trials count as peers."""

    condition: str
    phases: tuple[Phase, ...]
    population: Population
    started_on_or_after: date
    started_before: date | None = None
    intervention: str | None = None
    exclude_nct_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.phases:
            raise ValueError("expected at least one phase, got none")
        if (
            self.started_before is not None
            and self.started_before <= self.started_on_or_after
        ):
            raise ValueError(
                "expected started_before after started_on_or_after, got "
                f"started_on_or_after={self.started_on_or_after} "
                f"started_before={self.started_before}"
            )


def build_search_params(
    query: PeerSearchQuery, page_token: str | None
) -> dict[str, str]:
    """Translate a peer query into registry search parameters."""
    phase_filter = " OR ".join(f"AREA[Phase]{phase}" for phase in query.phases)
    # The registry's RANGE is inclusive, so stop the day before the draft.
    range_end = (
        UNBOUNDED_RANGE_END
        if query.started_before is None
        else (query.started_before - timedelta(days=1)).isoformat()
    )
    range_start = query.started_on_or_after.isoformat()
    filters = [
        "AREA[StudyType]INTERVENTIONAL",
        f"({phase_filter})",
        POPULATION_FILTERS[query.population],
        f"AREA[StartDate]RANGE[{range_start},{range_end}]",
    ]
    params = {
        "query.cond": query.condition,
        "filter.advanced": " AND ".join(filters),
        "fields": REQUESTED_SECTIONS,
        "pageSize": str(SEARCH_PAGE_SIZE),
        "countTotal": "true",
    }
    if query.intervention is not None:
        params["query.intr"] = query.intervention
    if page_token is not None:
        params["pageToken"] = page_token
    return params


def _is_retryable_status(status_code: int) -> bool:
    return (
        status_code == HTTP_RATE_LIMITED
        or status_code >= HTTP_SERVER_ERROR_MIN
    )


class ClinicalTrialsGovClient:
    """Async registry client with throttling, retries and validation.

    Use as an async context manager so the HTTP connection pool is closed.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        self._sleep = sleep
        self._clock = clock
        self._last_request_at = float("-inf")
        self._throttle_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def fetch_study(self, nct_id: str) -> StudyRecord:
        """Fetch one study by NCT ID.

        Raises ValueError for a malformed ID, StudyNotFoundError when the
        registry has no such study, and ClinicalTrialsGovError otherwise.
        """
        if NCT_ID_PATTERN.fullmatch(nct_id) is None:
            raise ValueError(
                f"expected an NCT ID like NCT01234567, got {nct_id!r}"
            )
        body = await self._get(
            f"{STUDIES_URL}/{nct_id}",
            {"fields": REQUESTED_SECTIONS},
            description=f"study {nct_id}",
        )
        return _parse(StudyRecord, body, description=f"study {nct_id}")

    async def search_studies(
        self,
        query: PeerSearchQuery,
        max_studies: int = DEFAULT_MAX_STUDIES,
    ) -> list[StudyRecord]:
        """Return studies matching query, minus query.exclude_nct_ids."""
        studies: list[StudyRecord] = []
        page_token: str | None = None
        for page_number in range(1, MAX_SEARCH_PAGES + 1):
            description = f"search page {page_number} for {query.condition!r}"
            body = await self._get(
                STUDIES_URL,
                build_search_params(query, page_token),
                description=description,
            )
            page = _parse(SearchPage, body, description=description)
            studies.extend(
                study
                for study in page.studies
                if study.nct_id not in query.exclude_nct_ids
            )
            if len(studies) >= max_studies or page.next_page_token is None:
                break
            page_token = page.next_page_token
        else:
            logger.warning(
                "peer search truncated at page cap: condition=%s pages=%d "
                "studies=%d",
                query.condition,
                MAX_SEARCH_PAGES,
                len(studies),
            )
        logger.info(
            "peer search done: condition=%s population=%s studies=%d",
            query.condition,
            query.population,
            min(len(studies), max_studies),
        )
        return studies[:max_studies]

    async def _wait_for_rate_limit(self) -> None:
        async with self._throttle_lock:
            elapsed_seconds = self._clock() - self._last_request_at
            if elapsed_seconds < MIN_SECONDS_BETWEEN_REQUESTS:
                await self._sleep(
                    MIN_SECONDS_BETWEEN_REQUESTS - elapsed_seconds
                )
            self._last_request_at = self._clock()

    async def _get(
        self, url: str, params: dict[str, str], description: str
    ) -> bytes:
        """GET with retries on rate limits, server errors and timeouts."""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            await self._wait_for_rate_limit()
            try:
                response = await self._http.get(url, params=params)
            except httpx.TransportError as error:
                last_error = error
                logger.warning(
                    "registry request failed, retrying: target=%s "
                    "attempt=%d/%d error=%s",
                    description,
                    attempt + 1,
                    MAX_RETRIES,
                    type(error).__name__,
                )
            else:
                if response.status_code == HTTP_NOT_FOUND:
                    raise StudyNotFoundError(
                        f"registry has no {description} (status 404)"
                    )
                if not response.is_error:
                    return response.content
                status_error = ClinicalTrialsGovError(
                    f"registry returned status {response.status_code} for "
                    f"{description}: "
                    f"{response.text[:ERROR_BODY_PREVIEW_CHARACTERS]}"
                )
                if not _is_retryable_status(response.status_code):
                    raise status_error
                last_error = status_error
                logger.warning(
                    "registry returned retryable status: target=%s "
                    "attempt=%d/%d status=%d",
                    description,
                    attempt + 1,
                    MAX_RETRIES,
                    response.status_code,
                )
            if attempt < MAX_RETRIES - 1:
                await self._sleep(RETRY_BASE_DELAY_SECONDS * 2**attempt)
        raise ClinicalTrialsGovError(
            f"registry request for {description} failed after "
            f"{MAX_RETRIES} attempts: {last_error}"
        ) from last_error


def _parse[ModelT: BaseModel](
    model: type[ModelT], body: bytes, description: str
) -> ModelT:
    try:
        return model.model_validate_json(body)
    except ValidationError as error:
        raise ClinicalTrialsGovError(
            f"unexpected payload for {description}: expected "
            f"{model.__name__}, got {error.error_count()} validation "
            f"error(s): {error}"
        ) from error
