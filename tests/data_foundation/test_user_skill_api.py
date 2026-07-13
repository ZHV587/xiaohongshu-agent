from contextlib import contextmanager
from datetime import datetime, timezone

from data_foundation.models import UserSkill, UserSkillRegistryEntry, UserSkillVersion
from tests.data_foundation.asgi_client import ASGIClient


def _client(monkeypatch):
    monkeypatch.setenv("XHS_INTERNAL_SECRET", "internal-secret")
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "")
    import data_foundation.http_app as http_app

    return ASGIClient(http_app.app)


def _headers(open_id="ou-user"):
    return {"X-XHS-Internal-Key": "internal-secret", "X-XHS-Open-Id": open_id}


def _definition():
    return {
        "displayName": "结构压缩",
        "description": "用户要求压缩内容结构时使用",
        "instructions": "删除重复信息，保留事实和结论。",
        "triggerExamples": ["再短一点"],
        "nonTriggerExamples": ["扩写案例"],
        "tags": ["结构"],
    }


def _skill(status="draft", published_version=None):
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    version = UserSkillVersion(
        id="11111111-1111-1111-1111-111111111111",
        tenant_id="default",
        owner_open_id="ou-user",
        skill_id="22222222-2222-2222-2222-222222222222",
        version=1,
        display_name="结构压缩",
        description="用户要求压缩内容结构时使用",
        instructions_markdown="删除重复信息，保留事实和结论。",
        trigger_examples=["再短一点"],
        non_trigger_examples=["扩写案例"],
        tags=["结构"],
        content_hash="hash",
        created_by_open_id="ou-user",
        created_at=now,
    )
    return UserSkill(
        id=version.skill_id,
        tenant_id="default",
        owner_open_id="ou-user",
        runtime_name="usr-owner-123",
        latest_version=1,
        status=status,
        published_version=published_version,
        created_at=now,
        updated_at=now,
        latest_definition=version,
    )


class FakeRepository:
    def __init__(self):
        self.skill = _skill()
        self.calls = []

    def create_skill(self, **kwargs):
        self.calls.append(("create", kwargs))
        return self.skill

    def list_skills(self, **kwargs):
        self.calls.append(("list", kwargs))
        return [self.skill]

    def get_skill(self, **kwargs):
        self.calls.append(("get", kwargs))
        return self.skill

    def list_versions(self, **kwargs):
        return [self.skill.latest_definition]

    def append_version(self, **kwargs):
        self.calls.append(("append", kwargs))
        return self.skill

    def publish_version(self, **kwargs):
        self.calls.append(("publish", kwargs))
        return self.skill

    def disable_skill(self, **kwargs):
        self.calls.append(("disable", kwargs))
        return self.skill

    def rollback_version(self, **kwargs):
        self.calls.append(("rollback", kwargs))
        return self.skill

    def archive_skill(self, **kwargs):
        self.calls.append(("archive", kwargs))
        return self.skill

    def get_catalog_revision(self, **kwargs):
        return 3

    def list_published_registry_entries(self, **kwargs):
        self.calls.append(("registry", kwargs))
        return [
            UserSkillRegistryEntry(
                skill_id=self.skill.id,
                version_id=self.skill.latest_definition.id,
                runtime_name=self.skill.runtime_name,
                display_name=self.skill.latest_definition.display_name,
                description=self.skill.latest_definition.description,
                tags=self.skill.latest_definition.tags,
            )
        ]


def _patch_repo(monkeypatch, repo):
    import data_foundation.user_skill_api as api

    @contextmanager
    def provider():
        yield repo

    monkeypatch.setattr(api, "_repository", provider)


def test_validate_rejects_capability_fields_and_never_calls_a_model(monkeypatch):
    response = _client(monkeypatch).post(
        "/internal/user-skills/validate",
        headers=_headers(),
        json={**_definition(), "allowedTools": ["shell"]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "SKILL_FIELD_NOT_ALLOWED"
    assert response.headers["Cache-Control"] == "no-store"


def test_validate_distinguishes_json_shape_semantics_and_payload_size(monkeypatch):
    client = _client(monkeypatch)
    malformed = client.post(
        "/internal/user-skills/validate", headers=_headers(), content="{"
    )
    wrong_shape = client.post(
        "/internal/user-skills/validate", headers=_headers(), json=[]
    )
    invalid_definition = client.post(
        "/internal/user-skills/validate", headers=_headers(), json={"displayName": "only"}
    )
    oversized = client.post(
        "/internal/user-skills/validate",
        headers=_headers(),
        content="{" + (" " * (64 * 1024)) + "}",
    )

    assert (malformed.status_code, malformed.json()["code"]) == (400, "SKILL_INVALID_JSON")
    assert (wrong_shape.status_code, wrong_shape.json()["code"]) == (400, "SKILL_INVALID_BODY")
    assert (invalid_definition.status_code, invalid_definition.json()["code"]) == (
        422,
        "SKILL_INVALID_INPUT",
    )
    assert (oversized.status_code, oversized.json()["code"]) == (413, "SKILL_PAYLOAD_TOO_LARGE")


def test_create_binds_owner_to_authenticated_user_and_returns_compiled_skill(monkeypatch):
    repo = FakeRepository()
    _patch_repo(monkeypatch, repo)

    response = _client(monkeypatch).post(
        "/internal/user-skills/create", headers=_headers(), json=_definition()
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["skill"]["latest"]["skillMd"].startswith("---\nname:")
    call = repo.calls[0][1]
    assert call["owner_open_id"] == "ou-user"
    assert call["actor_open_id"] == "ou-user"
    assert call["trigger_examples"] == ["再短一点"]


def test_registry_authenticates_scopes_owner_and_never_returns_skill_body(monkeypatch):
    repo = FakeRepository()
    _patch_repo(monkeypatch, repo)
    import data_foundation.user_skill_api as api

    monkeypatch.setattr(
        api,
        "build_skill_registry",
        lambda entries: [
            {
                "skillId": entries[0].skill_id,
                "versionId": entries[0].version_id,
                "runtimeName": entries[0].runtime_name,
                "displayName": entries[0].display_name,
                "description": entries[0].description,
                "tags": entries[0].tags,
                "source": "user",
                "readonly": False,
            }
        ],
    )
    client = _client(monkeypatch)
    denied = client.get("/internal/user-skills/registry")
    response = client.get("/internal/user-skills/registry", headers=_headers("ou-owner"))

    assert denied.status_code == 401
    assert denied.headers["Cache-Control"] == "no-store"
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert payload["items"][0]["versionId"] == repo.skill.latest_definition.id
    assert "instructions" not in payload["items"][0]
    assert "skillMd" not in payload["items"][0]
    assert repo.calls[-1][1]["owner_open_id"] == "ou-owner"


def test_list_detail_and_append_use_authenticated_owner_scope(monkeypatch):
    repo = FakeRepository()
    _patch_repo(monkeypatch, repo)
    client = _client(monkeypatch)

    listed = client.get("/internal/user-skills", headers=_headers())
    detailed = client.get(
        f"/internal/user-skills/detail?skillId={repo.skill.id}", headers=_headers()
    )
    appended = client.post(
        "/internal/user-skills/version",
        headers=_headers(),
        json={"skillId": repo.skill.id, "expectedLatestVersion": 1, **_definition()},
    )

    assert listed.status_code == detailed.status_code == appended.status_code == 200
    assert listed.json()["revision"] == 3
    assert "instructions" not in listed.json()["skills"][0]
    assert "skillMd" not in listed.json()["skills"][0]
    assert len(detailed.json()["skill"]["versions"]) == 1
    assert detailed.json()["skill"]["versions"][0]["versionId"] == repo.skill.latest_definition.id
    append_call = next(value for name, value in repo.calls if name == "append")
    assert append_call["owner_open_id"] == "ou-user"
    assert append_call["expected_latest_version"] == 1


def test_cross_owner_lookup_is_uniform_404(monkeypatch):
    class MissingRepository(FakeRepository):
        def get_skill(self, **kwargs):
            raise KeyError("Skill not found")

    _patch_repo(monkeypatch, MissingRepository())
    response = _client(monkeypatch).get(
        "/internal/user-skills/detail?skillId=22222222-2222-2222-2222-222222222222",
        headers=_headers("ou-other"),
    )

    assert response.status_code == 404
    assert response.json() == {
        "ok": False,
        "error": "Skill not found",
        "code": "SKILL_NOT_FOUND",
    }


def test_publication_actions_delegate_without_accepting_extra_fields(monkeypatch):
    repo = FakeRepository()
    _patch_repo(monkeypatch, repo)
    client = _client(monkeypatch)
    skill_id = repo.skill.id

    assert client.post(
        "/internal/user-skills/publish", headers=_headers(), json={"skillId": skill_id}
    ).status_code == 200
    assert client.post(
        "/internal/user-skills/rollback",
        headers=_headers(),
        json={"skillId": skill_id, "version": 1},
    ).status_code == 200
    assert client.post(
        "/internal/user-skills/disable", headers=_headers(), json={"skillId": skill_id}
    ).status_code == 200
    assert client.post(
        "/internal/user-skills/archive", headers=_headers(), json={"skillId": skill_id}
    ).status_code == 200
    rejected = client.post(
        "/internal/user-skills/publish",
        headers=_headers(),
        json={"skillId": skill_id, "tools": ["shell"]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "SKILL_UNKNOWN_FIELD"


def test_enable_requires_disabled_skill(monkeypatch):
    repo = FakeRepository()
    _patch_repo(monkeypatch, repo)
    response = _client(monkeypatch).post(
        "/internal/user-skills/enable", headers=_headers(), json={"skillId": repo.skill.id}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SKILL_CONFLICT"
