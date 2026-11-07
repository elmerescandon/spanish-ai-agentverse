"""Unit tests for ClinicalTrialsClient."""

import httpx
import pytest

from backend.clients.clinical_trials import ClinicalTrialsClient, StudySearchResult


def test_search_studies_parses_response_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ClinicalTrialsClient(request_interval_seconds=0.0)

    mock_payload = {
        "totalCount": 2,
        "nextPageToken": "cursor_123",
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT01234567",
                        "briefTitle": "Test Study 1",
                    }
                }
            },
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT07654321",
                        "briefTitle": "Test Study 2",
                    }
                }
            },
        ],
    }

    def mock_get(self: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=mock_payload, request=request)

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    result = client.search_studies(
        condition="diabetes", status="COMPLETED", page_size=10
    )

    assert isinstance(result, StudySearchResult)
    assert result.total_count == 2
    assert result.next_page_token == "cursor_123"
    assert len(result.studies) == 2


def test_get_study_invalid_id_raises_value_error() -> None:
    client = ClinicalTrialsClient(request_interval_seconds=0.0)
    with pytest.raises(ValueError, match="Invalid NCT ID format"):
        client.get_study("INVALID123")


def test_retry_mechanism_fails_loudly_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ClinicalTrialsClient(request_interval_seconds=0.0)

    def mock_get_fail(self: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(500, request=request)

    monkeypatch.setattr(httpx.Client, "get", mock_get_fail)

    with pytest.raises(RuntimeError, match="Failed to fetch"):
        client.search_studies(condition="diabetes")
