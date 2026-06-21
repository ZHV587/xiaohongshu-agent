from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
import math
from pathlib import Path

import psycopg
import pytest

from data_foundation.embedding_repository import EmbeddingRepository, VectorChunk
from data_foundation.repository import ResourceRepository


def _vector(first: float = 0.1) -> list[float]:
    return [first] + [0.0] * 1535


def _resource(conn, *, tenant_id: str = "tenant-a", title: str = "文档"):
    return ResourceRepository(conn).upsert_resource(
        tenant_id=tenant_id,
        actor_open_id="ou_owner",
        resource_type="doc",
        title=title,
        content_text="正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "test", "external_type": "doc", "external_id": f"{tenant_id}:{title}"},
    )


def _update_resource(conn, resource):
    return ResourceRepository(conn).upsert_resource(
        tenant_id=resource.tenant_id,
        actor_open_id="ou_owner",
        resource_type=resource.type,
        title=f"{resource.title} 新版",
        content_text="新正文",
        content_json={},
        visibility=resource.visibility,
        owner_open_id=resource.owner_open_id,
        mapping={
            "system": "test",
            "external_type": "doc",
            "external_id": f"{resource.tenant_id}:{resource.title}",
        },
    )


def test_embedding_repository_uses_schema_qualified_vector_cast_for_custom_search_paths():
    source = Path("data_foundation/embedding_repository.py").read_text(encoding="utf-8").lower()

    assert "::public.vector" in source
    assert "::vector" not in source


def test_building_index_does_not_replace_active_until_complete(migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    active = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="old-model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )
    repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=active.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "正文", _vector())],
    )
    assert repo.activate_if_complete(active.id, tenant_id="tenant-a") is True

    building = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="new-model",
        config_version="v2",
        chunker_version="text-v1",
        expected_resources=2,
    )

    assert repo.active_index("tenant-a").id == active.id
    assert repo.activate_if_complete(building.id, tenant_id="tenant-a") is False
    assert repo.active_index("tenant-a").id == active.id


def test_store_batch_rejects_stale_resource_version(migrated_conn):
    resource = _resource(migrated_conn)
    updated = _update_resource(migrated_conn, resource)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )

    assert repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "旧正文", _vector())],
    ) == "superseded"
    assert migrated_conn.execute("select count(*) as count from resource_embeddings").fetchone()["count"] == 0

    assert repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=updated.id,
        resource_version=updated.version,
        chunks=[VectorChunk(0, "新正文", _vector())],
    ) == "stored"


def test_store_batch_validates_vectors_before_writing(migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )

    with pytest.raises(ValueError, match="1536 finite"):
        repo.store_batch(
            tenant_id="tenant-a",
            embedding_index_id=index.id,
            resource_id=resource.id,
            resource_version=resource.version,
            chunks=[VectorChunk(0, "正文", [math.nan] * 1536)],
        )

    assert migrated_conn.execute("select count(*) as count from resource_embeddings").fetchone()["count"] == 0


def test_store_batch_is_idempotent_for_completed_resource(migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )

    first = repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "正文", _vector(0.1))],
    )
    second = repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "正文更新", _vector(0.2))],
    )

    assert first == "stored"
    assert second == "stored"
    row = migrated_conn.execute(
        "select completed_resources from embedding_indexes where id = %s",
        (index.id,),
    ).fetchone()
    assert row["completed_resources"] == 1
    assert migrated_conn.execute("select count(*) as count from resource_embeddings").fetchone()["count"] == 1


def test_storing_revised_resource_keeps_index_completion_equal_to_current_resources(migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )
    assert repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "正文", _vector(0.1))],
    ) == "stored"

    revised = _update_resource(migrated_conn, resource)
    assert repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=revised.id,
        resource_version=revised.version,
        chunks=[VectorChunk(0, "新正文", _vector(0.2))],
    ) == "stored"

    row = migrated_conn.execute(
        "select expected_resources, completed_resources from embedding_indexes where id = %s",
        (index.id,),
    ).fetchone()
    assert row["expected_resources"] == 1
    assert row["completed_resources"] == 1


def test_store_batch_waits_for_resource_revision_lock(database_url, migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )
    schema = migrated_conn.execute("select current_schema() as schema").fetchone()["schema"]

    def store() -> str:
        with psycopg.connect(database_url) as conn:
            conn.execute(f'set search_path to "{schema}", public')
            return EmbeddingRepository(conn).store_batch(
                tenant_id="tenant-a",
                embedding_index_id=index.id,
                resource_id=resource.id,
                resource_version=resource.version,
                chunks=[VectorChunk(0, "正文", _vector())],
            )

    with psycopg.connect(database_url) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(f'set search_path to "{schema}", public')
        blocker.execute(
            "select id from resources where tenant_id = %s and id = %s for update",
            ("tenant-a", resource.id),
        )
        future = pool.submit(store)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.25)
        blocker.commit()
        assert future.result(timeout=5) == "stored"


def test_activation_recomputes_counts_after_resource_becomes_blank(migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )
    repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "正文", _vector())],
    )
    ResourceRepository(migrated_conn).upsert_resource(
        tenant_id=resource.tenant_id,
        actor_open_id="ou_owner",
        resource_type=resource.type,
        title=f"{resource.title} 空白版",
        content_text=" ",
        content_json={},
        visibility=resource.visibility,
        owner_open_id=resource.owner_open_id,
        mapping={
            "system": "test",
            "external_type": "doc",
            "external_id": f"{resource.tenant_id}:{resource.title}",
        },
    )

    assert repo.activate_if_complete(index.id, tenant_id="tenant-a") is True
    row = migrated_conn.execute(
        "select status, expected_resources, completed_resources from embedding_indexes where id = %s",
        (index.id,),
    ).fetchone()
    assert row == {"status": "active", "expected_resources": 0, "completed_resources": 0}


def test_store_batch_with_no_chunks_does_not_overcount_completion(migrated_conn):
    resource = _resource(migrated_conn)
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )

    assert repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[],
    ) == "stored"
    assert repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=index.id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[],
    ) == "stored"

    row = migrated_conn.execute(
        "select completed_resources from embedding_indexes where id = %s",
        (index.id,),
    ).fetchone()
    assert row["completed_resources"] == 0


def test_activate_requires_exact_completion_count(migrated_conn):
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )
    migrated_conn.execute(
        "update embedding_indexes set completed_resources = 2 where id = %s",
        (index.id,),
    )

    assert repo.activate_if_complete(index.id, tenant_id="tenant-a") is False


def test_create_index_refreshes_expected_resources_for_existing_profile(migrated_conn):
    repo = EmbeddingRepository(migrated_conn)
    first = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=1,
    )
    second = repo.create_index(
        tenant_id="tenant-a",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=3,
    )

    assert second.id == first.id
    assert second.expected_resources == 3


def test_zero_resource_index_activates_immediately(migrated_conn):
    repo = EmbeddingRepository(migrated_conn)
    index = repo.create_index(
        tenant_id="empty-tenant",
        embedding_model="model",
        config_version="v1",
        chunker_version="text-v1",
        expected_resources=0,
    )

    assert repo.activate_if_complete(index.id, tenant_id="empty-tenant") is True
    assert repo.active_index("empty-tenant").id == index.id
