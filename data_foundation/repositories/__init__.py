from data_foundation.repositories.resource import ResourceRepository
from data_foundation.repositories.feedback import FeedbackRepository
from data_foundation.repositories.performance import PerformanceRepository
from data_foundation.repositories.telemetry import TelemetryRepository

resource_repo = ResourceRepository()
feedback_repo = FeedbackRepository()
performance_repo = PerformanceRepository()
telemetry_repo = TelemetryRepository()

__all__ = [
    "resource_repo",
    "feedback_repo",
    "performance_repo",
    "telemetry_repo",
    "ResourceRepository",
    "FeedbackRepository",
    "PerformanceRepository",
    "TelemetryRepository",
]
