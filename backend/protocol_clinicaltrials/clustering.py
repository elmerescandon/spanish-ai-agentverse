"""Clustering and peer similarity engine for clinical trial protocols."""

import math
from typing import Final

import numpy as np
from sklearn.cluster import KMeans  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.neighbors import NearestNeighbors  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

from backend.protocol_clinicaltrials.models import (
    ClusterProfile,
    OverallStatus,
    ProtocolFeatures,
)

DEFAULT_NUM_CLUSTERS: Final[int] = 4
RANDOM_STATE: Final[int] = 42


class ProtocolClusteringEngine:
    """Hybrid clustering engine using semantic TF-IDF and normalized design features."""

    def __init__(self, num_clusters: int = DEFAULT_NUM_CLUSTERS) -> None:
        self.num_clusters = num_clusters
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z0-9_\-\.]{2,}\b",
        )
        self.scaler = StandardScaler()
        self.kmeans = KMeans(
            n_clusters=num_clusters, random_state=RANDOM_STATE, n_init=10
        )
        self.knn = NearestNeighbors(metric="cosine")
        self.protocols: list[ProtocolFeatures] = []
        self.feature_matrix: np.ndarray | None = None
        self.cluster_labels: np.ndarray | None = None
        self.is_fitted: bool = False

    def _extract_text(self, protocol: ProtocolFeatures) -> str:
        """Combines titles, conditions, and MeSH terms for semantic text representation."""
        terms = [protocol.title] + protocol.conditions + protocol.mesh_conditions
        return " ".join(terms)

    def _extract_numerical_vector(self, protocol: ProtocolFeatures) -> list[float]:
        """Extracts normalized numerical design and feasibility metrics."""
        return [
            math.log1p(max(0, protocol.target_enrollment)),
            float(protocol.num_inclusion_criteria),
            float(protocol.num_exclusion_criteria),
            float(protocol.exclusion_ratio),
            float(protocol.num_primary_outcomes),
            float(protocol.num_secondary_outcomes),
            float(protocol.arm_count),
            math.log1p(max(1, protocol.site_count)),
            math.log1p(max(0.0, protocol.patients_per_site)),
            1.0 if protocol.has_dmc else 0.0,
            1.0 if protocol.is_fda_regulated else 0.0,
            1.0 if protocol.healthy_volunteers else 0.0,
        ]

    def fit(self, protocols: list[ProtocolFeatures]) -> ProtocolClusteringEngine:
        """Fits TF-IDF, Scaler, KMeans, and NearestNeighbors on protocols."""
        if len(protocols) < self.num_clusters:
            raise ValueError(
                f"Need at least {self.num_clusters} protocols to cluster, got {len(protocols)}"
            )

        self.protocols = protocols
        corpus = [self._extract_text(p) for p in protocols]
        text_features = self.tfidf_vectorizer.fit_transform(corpus).toarray()

        num_vectors = np.array([self._extract_numerical_vector(p) for p in protocols])
        scaled_num_features = self.scaler.fit_transform(num_vectors)

        # Combine text and scaled numerical features into hybrid representation
        self.feature_matrix = np.hstack([text_features, scaled_num_features])

        self.kmeans.fit(self.feature_matrix)
        self.cluster_labels = self.kmeans.labels_

        self.knn.fit(self.feature_matrix)
        self.is_fitted = True
        return self

    def find_peer_cohort(
        self, candidate: ProtocolFeatures, top_k: int = 5
    ) -> list[tuple[ProtocolFeatures, float]]:
        """Finds the top-K most similar historical protocols with similarity scores."""
        if not self.is_fitted or self.feature_matrix is None:
            raise RuntimeError("Clustering engine must be fitted before finding peers")

        candidate_text = self._extract_text(candidate)
        text_vec = self.tfidf_vectorizer.transform([candidate_text]).toarray()

        num_vec = np.array([self._extract_numerical_vector(candidate)])
        scaled_num_vec = self.scaler.transform(num_vec)

        hybrid_vec = np.hstack([text_vec, scaled_num_vec])

        safe_k = min(top_k, len(self.protocols))
        distances, indices = self.knn.kneighbors(hybrid_vec, n_neighbors=safe_k)

        results: list[tuple[ProtocolFeatures, float]] = []
        for dist, idx in zip(distances[0], indices[0], strict=True):
            # Cosine distance to similarity: 1 - distance
            similarity = round(max(0.0, 1.0 - float(dist)), 4)
            results.append((self.protocols[idx], similarity))
        return results

    def predict_cluster(self, candidate: ProtocolFeatures) -> int:
        """Assigns a candidate protocol to the best matching cluster."""
        if not self.is_fitted:
            raise RuntimeError("Clustering engine must be fitted before prediction")

        candidate_text = self._extract_text(candidate)
        text_vec = self.tfidf_vectorizer.transform([candidate_text]).toarray()
        num_vec = np.array([self._extract_numerical_vector(candidate)])
        scaled_num_vec = self.scaler.transform(num_vec)
        hybrid_vec = np.hstack([text_vec, scaled_num_vec])

        label = int(self.kmeans.predict(hybrid_vec)[0])
        return label

    def compute_cluster_profiles(self) -> list[ClusterProfile]:
        """Calculates statistical distributions and failure rates for each cluster."""
        if not self.is_fitted or self.cluster_labels is None:
            raise RuntimeError("Clustering engine must be fitted to compute profiles")

        profiles: list[ClusterProfile] = []

        for cluster_id in range(self.num_clusters):
            cluster_protocols = [
                p
                for idx, p in enumerate(self.protocols)
                if self.cluster_labels[idx] == cluster_id
            ]
            if not cluster_protocols:
                continue

            completed_count = sum(
                1 for p in cluster_protocols if p.status == OverallStatus.COMPLETED
            )
            terminated_count = sum(
                1
                for p in cluster_protocols
                if p.status in (OverallStatus.TERMINATED, OverallStatus.WITHDRAWN)
            )
            term_rate = (
                round(terminated_count / len(cluster_protocols), 3)
                if cluster_protocols
                else 0.0
            )

            # Extract condition and phase distributions
            phase_counts: dict[str, int] = {}
            mesh_counts: dict[str, int] = {}
            for p in cluster_protocols:
                phase_counts[str(p.phase)] = phase_counts.get(str(p.phase), 0) + 1
                for m in p.mesh_conditions:
                    mesh_counts[m] = mesh_counts.get(m, 0) + 1

            top_phases = sorted(phase_counts, key=phase_counts.get, reverse=True)[:3]  # type: ignore[arg-type]
            top_mesh = sorted(mesh_counts, key=mesh_counts.get, reverse=True)[:3]  # type: ignore[arg-type]

            enrollments = [p.target_enrollment for p in cluster_protocols]
            exclusions = [p.num_exclusion_criteria for p in cluster_protocols]
            primaries = [p.num_primary_outcomes for p in cluster_protocols]
            secondaries = [p.num_secondary_outcomes for p in cluster_protocols]
            sites = [p.site_count for p in cluster_protocols]
            pts_per_site = [p.patients_per_site for p in cluster_protocols]

            profile = ClusterProfile(
                cluster_id=cluster_id,
                name=f"Cluster {cluster_id}: {', '.join(top_phases)} | {', '.join(top_mesh[:2])}",
                study_count=len(cluster_protocols),
                completed_count=completed_count,
                terminated_count=terminated_count,
                termination_rate=term_rate,
                top_mesh_conditions=top_mesh,
                top_phases=top_phases,
                median_enrollment=float(np.median(enrollments)),
                median_exclusion_count=float(np.median(exclusions)),
                p90_exclusion_count=float(np.percentile(exclusions, 90)),
                median_primary_outcomes=float(np.median(primaries)),
                median_secondary_outcomes=float(np.median(secondaries)),
                median_site_count=float(np.median(sites)),
                median_patients_per_site=float(np.median(pts_per_site)),
            )
            profiles.append(profile)

        return profiles
