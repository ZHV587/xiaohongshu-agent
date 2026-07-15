from data_foundation.repositories.resource import ResourceRepository
from data_foundation.repositories.feedback import FeedbackRepository
from data_foundation.repositories.performance import PerformanceRepository
from data_foundation.repositories.telemetry import TelemetryRepository
from data_foundation.repositories.user_skill import UserSkillRepository
from data_foundation.repositories.generated_copy import GeneratedCopyRepository
from data_foundation.repositories.preference import PreferenceRepository
from data_foundation.repositories.retrieval_metrics import RetrievalMetricsRepository
from data_foundation.repositories.reranker_shadow import RerankerShadowRepository

resource_repo = ResourceRepository()
feedback_repo = FeedbackRepository()
performance_repo = PerformanceRepository()
telemetry_repo = TelemetryRepository()
user_skill_repo = UserSkillRepository()

__all__ = [
    "resource_repo",
    "feedback_repo",
    "performance_repo",
    "telemetry_repo",
    "user_skill_repo",
    "ResourceRepository",
    "FeedbackRepository",
    "PerformanceRepository",
    "TelemetryRepository",
    "UserSkillRepository",
    "GeneratedCopyRepository",
    "PreferenceRepository",
    "RetrievalMetricsRepository",
    "RerankerShadowRepository",
]
