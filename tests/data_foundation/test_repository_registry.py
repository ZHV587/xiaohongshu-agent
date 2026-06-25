import pytest
from data_foundation.repositories import resource_repo, feedback_repo, performance_repo, telemetry_repo
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.repositories.feedback import FeedbackRepository
from data_foundation.repositories.performance import PerformanceRepository
from data_foundation.repositories.telemetry import TelemetryRepository

def test_singleton_instances_are_cached():
    assert resource_repo is not None
    assert feedback_repo is not None
    assert performance_repo is not None
    assert telemetry_repo is not None
    
    assert isinstance(resource_repo, ResourceRepository)
    assert isinstance(feedback_repo, FeedbackRepository)
    assert isinstance(performance_repo, PerformanceRepository)
    assert isinstance(telemetry_repo, TelemetryRepository)
