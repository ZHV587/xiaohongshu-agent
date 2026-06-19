from data_foundation.outbox_worker import process_outbox_batch


class RecordingRepo:
    def __init__(self, rows):
        self.rows = rows
        self.leases = []
        self.completed = []

    def lease_outbox(self, *, tenant_id, batch_size):
        self.leases.append({"tenant_id": tenant_id, "batch_size": batch_size})
        return self.rows[:batch_size]

    def complete_outbox(self, outbox_id, *, status="succeeded", error=None):
        self.completed.append((outbox_id, status, error))


def test_process_outbox_batch_returns_empty_stats_when_nothing_leased():
    repo = RecordingRepo([])

    result = process_outbox_batch(repo, tenant_id="default")

    assert result == {"leased": 0, "processed": 0, "succeeded": 0, "failed": 0, "errors": []}
    assert repo.leases == [{"tenant_id": "default", "batch_size": 20}]
    assert repo.completed == []


def test_process_outbox_batch_marks_known_topics_succeeded():
    repo = RecordingRepo(
        [
            {"id": "1", "topic": "meili_index", "resource_id": "res1", "payload": {}},
            {"id": "2", "topic": "embedding_generate", "resource_id": "res1", "payload": {}},
            {"id": "3", "topic": "graph_ingest", "resource_id": "res1", "payload": {}},
        ]
    )

    result = process_outbox_batch(repo, tenant_id="default", batch_size=3)

    assert result == {"leased": 3, "processed": 3, "succeeded": 3, "failed": 0, "errors": []}
    assert repo.completed == [
        ("1", "succeeded", None),
        ("2", "succeeded", None),
        ("3", "succeeded", None),
    ]


def test_process_outbox_batch_marks_failed_item_and_continues():
    repo = RecordingRepo(
        [
            {"id": "1", "topic": "meili_index", "resource_id": "res1", "payload": {}},
            {"id": "2", "topic": "unknown_topic", "resource_id": "res2", "payload": {}},
            {"id": "3", "topic": "graph_ingest", "resource_id": "res3", "payload": {}},
        ]
    )

    result = process_outbox_batch(repo, tenant_id="default", batch_size=3)

    assert result["leased"] == 3
    assert result["processed"] == 3
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["errors"] == [
        {"id": "2", "topic": "unknown_topic", "error": "ValueError: Unsupported outbox topic: unknown_topic"}
    ]
    assert repo.completed[0] == ("1", "succeeded", None)
    assert repo.completed[1] == ("2", "failed", "ValueError: Unsupported outbox topic: unknown_topic")
    assert repo.completed[2] == ("3", "succeeded", None)
