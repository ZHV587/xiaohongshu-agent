from contextlib import nullcontext
from dataclasses import dataclass, field

from data_foundation.feishu_sync import SyncResult, sync_base_rows, sync_wiki_documents
from data_foundation.models import Resource
from data_foundation.repository import ResourceRepository


@dataclass
class RecordingRepository:
    resource: Resource
    mappings: list[dict] = field(default_factory=list)
    upserts: list[dict] = field(default_factory=list)

    def unit_of_work(self):
        return nullcontext()

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        return self.resource

    def upsert_mapping(self, **mapping):
        self.mappings.append(mapping)

    def mark_mapping_failed(self, **_kwargs):
        return None


def _resource(resource_id: str = "resource-1") -> Resource:
    return Resource(
        id=resource_id,
        tenant_id="default",
        type="feishu_doc",
        title="选题方法",
        summary=None,
        content_text="",
        content_json={},
        status="active",
        visibility="team",
        owner_open_id="ou_sync",
        created_at=None,
        updated_at=None,
        version=1,
    )


def test_sync_wiki_documents_upserts_resource_and_wiki_mapping():
    repo = RecordingRepository(_resource())

    result = sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[
            {
                "obj_token": "doc1",
                "node_token": "wik1",
                "title": "选题方法",
                "content": "第一段\n\n第二段",
            }
        ],
    )

    assert result == SyncResult(imported=1, errors=[])
    assert [request.topic for request in repo.upserts[0]["outbox_requests"]] == ["meili_index", "graph_ingest"]
    assert repo.mappings[0]["external_type"] == "wiki_node"
    assert repo.mappings[0]["external_id"] == "sp1:wik1"


def test_feishu_sync_preserves_external_source_updated_at():
    repo = RecordingRepository(_resource())

    sync_base_rows(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        app_token="base1",
        rows=[
            {
                "record_id": "rec1",
                "table_id": "tbl1",
                "external_updated_at": "2026-05-01T08:00:00Z",
                "fields": {"标题": "旧资料"},
            }
        ],
    )
    sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[
            {
                "obj_token": "doc1",
                "node_token": "wik1",
                "title": "旧文档",
                "content": "正文",
                "external_updated_at": "2026-04-01T08:00:00Z",
            }
        ],
    )

    assert repo.upserts[0]["mapping"]["external_updated_at"] == "2026-05-01T08:00:00Z"
    assert repo.upserts[1]["mapping"]["external_updated_at"] == "2026-04-01T08:00:00Z"


def test_sync_wiki_documents_reports_document_identity_on_invalid_input():
    repo = RecordingRepository(_resource())

    result = sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[{"obj_token": "doc1", "title": "缺少节点", "content": "正文"}],
    )

    assert result.imported == 0
    assert len(result.errors) == 1
    assert "doc1" in result.errors[0]
    assert "node_token" in result.errors[0]


def test_sync_base_rows_reports_record_identity_on_invalid_input():
    repo = RecordingRepository(_resource())

    result = sync_base_rows(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        app_token="base1",
        rows=[{"table_id": "tbl1", "fields": {"标题": "缺少记录 ID"}}],
    )

    assert result.imported == 0
    assert "base1:tbl1:<missing>" in result.errors[0]
    assert "record_id" in result.errors[0]


def test_sync_base_rows_upserts_records(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    result = sync_base_rows(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        app_token="base1",
        rows=[
            {"record_id": "rec1", "table_id": "tbl1", "fields": {"标题": "露营标题", "正文": "露营正文", "点赞": 88}},
            {"record_id": "rec2", "table_id": "tbl1", "fields": {"标题": "收纳标题", "正文": "收纳正文"}},
        ],
    )

    assert result == SyncResult(imported=2, errors=[])
    assert repo.debug_counts()["resources"] == 2
    assert repo.debug_counts()["resource_mappings"] == 2
    assert repo.debug_counts()["resource_outbox"] == 4

    resource_id = migrated_conn.execute(
        """
        select resource_id
        from resource_mappings
        where tenant_id = 'default' and external_id = 'base1:tbl1:rec1'
        """
    ).fetchone()["resource_id"]
    resource = repo.get_resource("default", "ou_sync", str(resource_id))
    assert resource is not None
    assert resource.type == "feishu_base_record"
    assert resource.content_text == "露营正文"
    assert resource.content_json == {
        "fields": {"标题": "露营标题", "正文": "露营正文", "点赞": 88},
        "identity_kind": "feishu_record_id",
    }

    mapping = migrated_conn.execute(
        """
        select external_id, sync_status
        from resource_mappings
        where resource_id = %s
        """,
        (resource.id,),
    ).fetchone()
    assert mapping["external_id"] == "base1:tbl1:rec1"
    assert mapping["sync_status"] == "synced"


def test_sync_wiki_documents_upserts_docs_without_direct_embedding_writes(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    result = sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[
            {
                "obj_token": "doc1",
                "node_token": "wik1",
                "title": "选题方法",
                "content": "第一段\n\n第二段",
            },
        ],
    )

    assert result == SyncResult(imported=1, errors=[])
    resource_id = migrated_conn.execute(
        """
        select resource_id
        from resource_mappings
        where tenant_id = 'default' and external_id = 'doc1'
        """
    ).fetchone()["resource_id"]
    resource = repo.get_resource("default", "ou_sync", str(resource_id))
    assert resource is not None
    assert resource.type == "feishu_doc"
    assert resource.content_json == {"space_id": "sp1", "obj_token": "doc1", "node_token": "wik1"}

    assert migrated_conn.execute("select count(*) as count from resource_embeddings").fetchone()["count"] == 0
    assert migrated_conn.execute("select count(*) as count from resource_outbox").fetchone()["count"] == 2

    sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[
            {
                "obj_token": "doc1",
                "node_token": "wik1",
                "title": "选题方法",
                "content": "新的一段",
            }
        ],
    )
    assert migrated_conn.execute("select count(*) as count from resource_embeddings").fetchone()["count"] == 0

    mappings = migrated_conn.execute(
        """
        select external_type, external_id, sync_status
        from resource_mappings
        where resource_id = %s
        order by external_type
        """,
        (resource.id,),
    ).fetchall()
    assert [(row["external_type"], row["external_id"], row["sync_status"]) for row in mappings] == [
        ("docx", "doc1", "synced"),
        ("wiki_node", "sp1:wik1", "synced"),
    ]

    counts_after_change = repo.debug_counts()
    replay = sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[
            {
                "obj_token": "doc1",
                "node_token": "wik1",
                "title": "选题方法",
                "content": "新的一段",
            }
        ],
    )
    assert replay == SyncResult(imported=1, errors=[])
    assert repo.debug_counts() == counts_after_change
