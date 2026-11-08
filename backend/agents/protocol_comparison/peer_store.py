"""On-disk cache of peer trials fetched from ClinicalTrials.gov.

Layout under the store root:
    studies/<NCT ID>.json   one validated registry record per study
    queries/<query id>.json the query, when it ran, and the NCT IDs found
    lab_limits/<NCT ID>.json the LLM's reading of the study's lab limits

Records are stored as our validated subset of the registry JSON (same
keys and structure, unmodelled fields dropped). Caching keeps the demo
and tests independent of the registry, and records which version of each
record a value came from.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

from backend.agents.protocol_comparison.eligibility import StoredLabReading
from backend.clients.clinicaltrials_gov import (
    ClinicalTrialsGovClient,
    PeerSearchQuery,
    Phase,
    Population,
    StudyRecord,
)

logger = logging.getLogger(__name__)

# [TO REFACTOR:(theo)]: JSON files are enough for one disease area; move
# to a database if the corpus grows past a few thousand studies.
DEFAULT_PEER_STORE_DIR = Path("data/peers")
STUDIES_DIRNAME = "studies"
QUERIES_DIRNAME = "queries"
LAB_LIMITS_DIRNAME = "lab_limits"
QUERY_ID_LENGTH = 16  # hex characters of a SHA-256; collisions negligible
JSON_INDENT = 2
# Caps a live search: each new peer costs one Gemini lab-limit reading,
# and adult type 2 diabetes searches return hundreds of trials.
PEER_SEARCH_MAX_STUDIES = 50

type RegistrySearch = Callable[[PeerSearchQuery], Awaitable[list[StudyRecord]]]


class PeerStoreError(RuntimeError):
    """Raised when the cache on disk is incomplete or unreadable."""


class PeerSearcher(Protocol):
    """Anything that can search the registry, e.g. the real client."""

    async def search_studies(
        self, query: PeerSearchQuery
    ) -> list[StudyRecord]: ...


class StoredPeerQuery(BaseModel):
    """A cached search: its parameters, when it ran and what it found."""

    query_id: str
    condition: str
    phases: list[Phase]
    population: Population
    started_on_or_after: date
    started_before: date | None
    intervention: str | None
    exclude_nct_ids: list[str]
    fetched_at: datetime
    nct_ids: list[str]


def query_id_for(query: PeerSearchQuery) -> str:
    """Stable ID for a query: the same filters always map to the same ID."""
    canonical = json.dumps(
        {
            "condition": query.condition,
            "phases": sorted(query.phases),
            "population": query.population,
            "started_on_or_after": query.started_on_or_after.isoformat(),
            "started_before": (
                None
                if query.started_before is None
                else query.started_before.isoformat()
            ),
            "intervention": query.intervention,
            "exclude_nct_ids": sorted(query.exclude_nct_ids),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:QUERY_ID_LENGTH]


def _write_atomically(path: Path, text: str) -> None:
    """Write via a temp file so a crash never leaves half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)


class PeerStore:
    """Reads and writes cached peer searches under a root directory."""

    def __init__(self, root: Path = DEFAULT_PEER_STORE_DIR) -> None:
        self._root = root

    def _study_path(self, nct_id: str) -> Path:
        return self._root / STUDIES_DIRNAME / f"{nct_id}.json"

    def _query_path(self, query_id: str) -> Path:
        return self._root / QUERIES_DIRNAME / f"{query_id}.json"

    def _lab_limits_path(self, trial_id: str) -> Path:
        return self._root / LAB_LIMITS_DIRNAME / f"{trial_id}.json"

    def load_lab_reading(self, trial_id: str) -> StoredLabReading | None:
        """Return the cached LLM reading for a trial, or None."""
        path = self._lab_limits_path(trial_id)
        if not path.exists():
            return None
        try:
            return StoredLabReading.model_validate_json(path.read_bytes())
        except ValidationError as error:
            raise PeerStoreError(
                f"expected a valid cached lab reading at {path}, got "
                f"{error.error_count()} validation error(s)"
            ) from error

    def save_lab_reading(self, stored: StoredLabReading) -> None:
        """Cache an LLM reading, replacing any older one for the trial."""
        _write_atomically(
            self._lab_limits_path(stored.trial_id),
            stored.model_dump_json(indent=JSON_INDENT),
        )

    def load_study(self, nct_id: str) -> StudyRecord:
        """Load one cached study; raises PeerStoreError if missing."""
        path = self._study_path(nct_id)
        try:
            return StudyRecord.model_validate_json(path.read_bytes())
        except FileNotFoundError as error:
            raise PeerStoreError(
                f"expected cached study at {path}, found no file"
            ) from error
        except ValidationError as error:
            raise PeerStoreError(
                f"expected a valid study record at {path}, got "
                f"{error.error_count()} validation error(s)"
            ) from error

    def save_study(self, study: StudyRecord) -> None:
        """Cache one study record, overwriting any older version."""
        _write_atomically(
            self._study_path(study.nct_id),
            study.model_dump_json(
                by_alias=True, exclude_none=True, indent=JSON_INDENT
            ),
        )

    def load_query(self, query: PeerSearchQuery) -> StoredPeerQuery | None:
        """Return the cached search for query, or None if never run."""
        path = self._query_path(query_id_for(query))
        if not path.exists():
            return None
        try:
            return StoredPeerQuery.model_validate_json(path.read_bytes())
        except ValidationError as error:
            raise PeerStoreError(
                f"expected a valid cached query at {path}, got "
                f"{error.error_count()} validation error(s)"
            ) from error

    def load_studies(self, query: PeerSearchQuery) -> list[StudyRecord] | None:
        """Return the cached studies for query, in search order."""
        stored = self.load_query(query)
        if stored is None:
            return None
        return [self.load_study(nct_id) for nct_id in stored.nct_ids]

    def save(
        self,
        query: PeerSearchQuery,
        studies: list[StudyRecord],
        fetched_at: datetime,
    ) -> StoredPeerQuery:
        """Cache studies and the query that found them.

        Studies are written before the query file, so a query on disk
        always points at studies that exist. Saving twice overwrites.
        """
        for study in studies:
            self.save_study(study)
        stored = StoredPeerQuery(
            query_id=query_id_for(query),
            condition=query.condition,
            phases=list(query.phases),
            population=query.population,
            started_on_or_after=query.started_on_or_after,
            started_before=query.started_before,
            intervention=query.intervention,
            exclude_nct_ids=sorted(query.exclude_nct_ids),
            fetched_at=fetched_at,
            nct_ids=[study.nct_id for study in studies],
        )
        _write_atomically(
            self._query_path(stored.query_id),
            stored.model_dump_json(indent=JSON_INDENT),
        )
        return stored


async def load_or_fetch_peers(
    query: PeerSearchQuery,
    searcher: PeerSearcher,
    store: PeerStore,
    refresh: bool = False,
) -> list[StudyRecord]:
    """Return cached search results, fetching and caching them if needed.

    With refresh=True the registry is always searched and the cache
    overwritten.
    """
    if not refresh:
        cached = store.load_studies(query)
        if cached is not None:
            logger.info(
                "peer cache hit: query_id=%s studies=%d",
                query_id_for(query),
                len(cached),
            )
            return cached
    studies = await searcher.search_studies(query)
    stored = store.save(query, studies, fetched_at=datetime.now(UTC))
    logger.info(
        "peer cache written: query_id=%s studies=%d",
        stored.query_id,
        len(studies),
    )
    return studies


async def search_registry(query: PeerSearchQuery) -> list[StudyRecord]:
    """Search ClinicalTrials.gov live, keeping the first results.

    Raises:
        ClinicalTrialsGovError: the registry failed after its retries.
    """
    async with ClinicalTrialsGovClient() as client:
        return await client.search_studies(
            query, max_studies=PEER_SEARCH_MAX_STUDIES
        )


class PeerSource:
    """Finds the peers for a search without writing to disk.

    Looks in memory, then in the committed snapshot (data/peers), and
    only then searches the registry live; a live result is kept in
    memory for the rest of the process, since the deployed filesystem is
    read-only.
    """

    def __init__(
        self, store: PeerStore, search: RegistrySearch = search_registry
    ) -> None:
        self._store = store
        self._search = search
        self._searches: dict[str, list[StudyRecord]] = {}

    async def studies_for(self, query: PeerSearchQuery) -> list[StudyRecord]:
        """Return the studies the search finds.

        Raises:
            ClinicalTrialsGovError: a live search failed.
            PeerStoreError: the committed snapshot is unreadable.
        """
        query_id = query_id_for(query)
        studies = self._searches.get(query_id)
        if studies is None:
            studies = self._store.load_studies(query)
        if studies is None:
            studies = await self._search(query)
            logger.info(
                "peer search run live: query_id=%s studies=%d",
                query_id,
                len(studies),
            )
        self._searches[query_id] = studies
        return studies
