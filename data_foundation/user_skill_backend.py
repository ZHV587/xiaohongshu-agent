from __future__ import annotations

import asyncio
import fnmatch as fnmatch_module
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath

from deepagents.backends.protocol import (
    ASYNC_GREP_TIMEOUT,
    FILE_NOT_FOUND,
    INVALID_PATH,
    PERMISSION_DENIED,
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

from data_foundation.db import connect
from data_foundation.models import PublishedUserSkillDocument
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repositories.user_skill import UserSkillRepository
from data_foundation.user_skill_service import SkillDefinition, UserSkillCompiler


DocumentLoader = Callable[[str, str], Sequence[PublishedUserSkillDocument]]
ActorResolver = Callable[[], str]


def _load_published_documents(tenant_id: str, owner_open_id: str) -> list[PublishedUserSkillDocument]:
    with connect(connect_timeout=3, options="-c statement_timeout=5000") as conn:
        return UserSkillRepository(conn).list_published_documents(
            tenant_id=tenant_id,
            owner_open_id=owner_open_id,
        )


def _current_actor() -> str:
    return actor_from_config(None)


class PostgresUserSkillsBackend(BackendProtocol):
    """把本人已发布 Skill 映射成 DeepAgents 可读、不可写的虚拟文件树。"""

    def __init__(
        self,
        *,
        document_loader: DocumentLoader = _load_published_documents,
        actor_resolver: ActorResolver = _current_actor,
        tenant_resolver: Callable[[], str] = default_tenant_id,
        io_timeout_seconds: float = 6.0,
    ) -> None:
        self._document_loader = document_loader
        self._actor_resolver = actor_resolver
        self._tenant_resolver = tenant_resolver
        self._io_timeout_seconds = io_timeout_seconds

    async def _run_async(self, function, *args):
        return await asyncio.wait_for(
            asyncio.to_thread(function, *args),
            timeout=self._io_timeout_seconds,
        )

    def _documents(self) -> list[PublishedUserSkillDocument]:
        return self._documents_for_actor(self._actor_resolver())

    def _documents_for_actor(self, actor_open_id: str) -> list[PublishedUserSkillDocument]:
        return list(self._document_loader(self._tenant_resolver(), actor_open_id))

    @staticmethod
    def _content(document: PublishedUserSkillDocument) -> str:
        definition = SkillDefinition(
            display_name=document.display_name,
            description=document.description,
            instructions=document.instructions_markdown,
            trigger_examples=tuple(document.trigger_examples),
            non_trigger_examples=tuple(document.non_trigger_examples),
            tags=tuple(document.tags),
        )
        return UserSkillCompiler.compile(document.runtime_name, definition)

    @staticmethod
    def _safe_parts(path: str) -> tuple[str, ...] | None:
        if not isinstance(path, str) or not path.startswith("/") or "\\" in path:
            return None
        pure = PurePosixPath(path)
        if ".." in pure.parts:
            return None
        return tuple(part for part in pure.parts if part != "/")

    @classmethod
    def _document_for_path(
        cls,
        path: str,
        documents: Sequence[PublishedUserSkillDocument],
    ) -> PublishedUserSkillDocument | None:
        parts = cls._safe_parts(path)
        if parts is None or len(parts) != 2 or parts[1] != "SKILL.md":
            return None
        return next((item for item in documents if item.runtime_name == parts[0]), None)

    @staticmethod
    def _directory_info(document: PublishedUserSkillDocument) -> FileInfo:
        return {
            "path": f"/{document.runtime_name}/",
            "is_dir": True,
            "size": 0,
            "modified_at": document.updated_at.isoformat(),
        }

    @classmethod
    def _file_info(cls, document: PublishedUserSkillDocument) -> FileInfo:
        content = cls._content(document)
        return {
            "path": f"/{document.runtime_name}/SKILL.md",
            "is_dir": False,
            "size": len(content.encode("utf-8")),
            "modified_at": document.updated_at.isoformat(),
        }

    def _ls_for_actor(self, path: str, actor_open_id: str) -> LsResult:
        parts = self._safe_parts(path)
        if parts is None:
            return LsResult(error=INVALID_PATH)
        documents = self._documents_for_actor(actor_open_id)
        if not parts:
            return LsResult(entries=[self._directory_info(item) for item in documents])
        if len(parts) == 1:
            document = next((item for item in documents if item.runtime_name == parts[0]), None)
            if document is None:
                return LsResult(error=FILE_NOT_FOUND)
            return LsResult(entries=[self._file_info(document)])
        return LsResult(error=FILE_NOT_FOUND)

    def ls(self, path: str) -> LsResult:
        return self._ls_for_actor(path, self._actor_resolver())

    async def als(self, path: str) -> LsResult:
        actor = self._actor_resolver()
        try:
            return await self._run_async(self._ls_for_actor, path, actor)
        except TimeoutError:
            return LsResult(error="User Skill catalog timed out")

    def _read_for_actor(self, file_path: str, offset: int, limit: int, actor_open_id: str) -> ReadResult:
        if offset < 0 or limit < 1:
            return ReadResult(error="Invalid line range")
        document = self._document_for_path(file_path, self._documents_for_actor(actor_open_id))
        if document is None:
            return ReadResult(error=f"File '{file_path}' not found")
        lines = self._content(document).splitlines(keepends=True)
        if offset >= len(lines):
            return ReadResult(error=f"Line offset {offset} exceeds file length ({len(lines)} lines)")
        return ReadResult(
            file_data={
                "content": "".join(lines[offset : offset + limit]),
                "encoding": "utf-8",
                "modified_at": document.updated_at.isoformat(),
            }
        )

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._read_for_actor(file_path, offset, limit, self._actor_resolver())

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        actor = self._actor_resolver()
        try:
            return await self._run_async(self._read_for_actor, file_path, offset, limit, actor)
        except TimeoutError:
            return ReadResult(error="User Skill catalog timed out")

    def _download_for_actor(
        self,
        paths: list[str],
        actor_open_id: str,
    ) -> list[FileDownloadResponse]:
        documents = self._documents_for_actor(actor_open_id)
        responses: list[FileDownloadResponse] = []
        for path in paths:
            if self._safe_parts(path) is None:
                responses.append(FileDownloadResponse(path=path, error=INVALID_PATH))
                continue
            document = self._document_for_path(path, documents)
            if document is None:
                responses.append(FileDownloadResponse(path=path, error=FILE_NOT_FOUND))
                continue
            responses.append(
                FileDownloadResponse(path=path, content=self._content(document).encode("utf-8"))
            )
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._download_for_actor(paths, self._actor_resolver())

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        actor = self._actor_resolver()
        try:
            return await self._run_async(self._download_for_actor, paths, actor)
        except TimeoutError:
            return [
                FileDownloadResponse(path=path, error="User Skill catalog timed out")
                for path in paths
            ]

    @staticmethod
    def _matches(candidate: str, pattern: str) -> bool:
        normalized = pattern.lstrip("/")
        relative = candidate.lstrip("/")
        return PurePosixPath(relative).match(normalized) or fnmatch_module.fnmatch(relative, normalized)

    def _glob_for_actor(self, pattern: str, path: str | None, actor_open_id: str) -> GlobResult:
        documents = self._documents_for_actor(actor_open_id)
        base = (path or "/").rstrip("/")
        entries = [entry for item in documents for entry in (self._directory_info(item), self._file_info(item))]
        matches = [
            entry
            for entry in entries
            if (not base or base == "/" or entry["path"].startswith(f"{base}/"))
            and self._matches(entry["path"], pattern)
        ]
        return GlobResult(matches=matches)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return self._glob_for_actor(pattern, path, self._actor_resolver())

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        actor = self._actor_resolver()
        try:
            return await self._run_async(self._glob_for_actor, pattern, path, actor)
        except TimeoutError:
            return GlobResult(error="User Skill catalog timed out")

    def _grep_for_actor(
        self,
        pattern: str,
        path: str | None,
        glob: str | None,
        actor_open_id: str,
    ) -> GrepResult:
        base = (path or "/").rstrip("/")
        matches: list[GrepMatch] = []
        for document in self._documents_for_actor(actor_open_id):
            file_path = f"/{document.runtime_name}/SKILL.md"
            if base and base != "/" and not file_path.startswith(f"{base}/"):
                continue
            if glob and not self._matches(file_path, glob):
                continue
            for line_number, line in enumerate(self._content(document).splitlines(), start=1):
                if pattern in line:
                    matches.append({"path": file_path, "line": line_number, "text": line})
        return GrepResult(matches=matches)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        return self._grep_for_actor(pattern, path, glob, self._actor_resolver())

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        actor = self._actor_resolver()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._grep_for_actor, pattern, path, glob, actor),
                timeout=min(self._io_timeout_seconds, ASYNC_GREP_TIMEOUT),
            )
        except TimeoutError:
            return GrepResult(error="Error: grep timed out; try a narrower path")

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=PERMISSION_DENIED)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return self.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=PERMISSION_DENIED)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self.edit(file_path, old_string, new_string, replace_all)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error=PERMISSION_DENIED) for path, _ in files]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return self.upload_files(files)


__all__ = ["PostgresUserSkillsBackend"]
