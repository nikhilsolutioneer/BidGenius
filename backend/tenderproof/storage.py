"""Local transactional persistence. Sources and estimate snapshots are immutable."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import Any, Callable

from sqlalchemy import JSON, Integer, String, UniqueConstraint, create_engine, event, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainError(Exception):
    def __init__(self, message: str, status: int = 422, detail: Any = None):
        self.message, self.status, self.detail = message, status, detail
        super().__init__(message)


class InstanceLock:
    """Keep separate server processes from recovering each other's active runs."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.handle = (directory / "application.lock").open("a+b")

    def acquire(self):
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError("Another TenderProof server is already using this data directory. Use the existing app, or configure a separate TENDERPROOF_DATA_DIR.") from None

    def release(self):
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class DocumentRow(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    path: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)


class PageRow(Base):
    __tablename__ = "pages"
    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    page: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class SpanRow(Base):
    __tablename__ = "source_spans"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    page: Mapped[int] = mapped_column(Integer, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class RevisionRow(Base):
    __tablename__ = "estimate_revisions"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)


class Repository:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.directory / 'tenderproof.sqlite'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    def create_project(self, data: dict, pdf_path: Path):
        with Session(self.engine) as session, session.begin():
            session.add(ProjectRow(id=data["id"], data=deepcopy(data)))
            doc = data["document"]
            session.add(DocumentRow(id=doc["id"], project_id=data["id"], path=str(pdf_path.resolve()), data=doc))

    def duplicate_project(self, data: dict, pdf_path: Path):
        self.create_project(data, pdf_path)

    def projects(self) -> list[dict]:
        with Session(self.engine) as session:
            result = [deepcopy(row.data) for row in session.scalars(select(ProjectRow))]
        return sorted(result, key=lambda p: p["updated_at"], reverse=True)

    def project(self, project_id: str) -> dict:
        with Session(self.engine) as session:
            row = session.get(ProjectRow, project_id)
            if row is None:
                raise DomainError("Project not found.", 404)
            return deepcopy(row.data)

    def update_project(self, project_id: str, fn: Callable[[dict], Any], expected_revision: int | None = None, snapshot: bool = False) -> tuple[dict, Any]:
        with Session(self.engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.get(ProjectRow, project_id)
            if row is None:
                raise DomainError("Project not found.", 404)
            data = deepcopy(row.data)
            if expected_revision is not None and data["revision"] != expected_revision:
                raise DomainError("This estimate changed. Refresh and review the latest revision.", 409)
            result = fn(data)
            data["updated_at"] = now()
            row.data = data
            if snapshot:
                session.add(RevisionRow(project_id=project_id, revision=data["revision"], created_at=now(), data=deepcopy(data)))
            session.commit()
            return deepcopy(data), result

    def revision(self, project_id: str, revision: int) -> dict:
        with Session(self.engine) as session:
            row = session.get(RevisionRow, (project_id, revision))
            if row is None:
                raise DomainError("Estimate revision not found. Finish a processing run first.", 404)
            return deepcopy(row.data)

    def revisions(self, project_id: str) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.scalars(select(RevisionRow).where(RevisionRow.project_id == project_id).order_by(RevisionRow.revision.desc()))
            return [{"revision": row.revision, "created_at": row.created_at, "selling_price_chf": row.data.get("estimate", {}).get("totals", {}).get("selling_price_chf")} for row in rows]

    def create_run(self, data: dict):
        with Session(self.engine) as session, session.begin():
            session.add(RunRow(id=data["id"], project_id=data["project_id"], data=data))

    def run(self, run_id: str) -> dict:
        with Session(self.engine) as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise DomainError("Processing run not found.", 404)
            return deepcopy(row.data)

    def update_run(self, run_id: str, **changes) -> dict:
        with Session(self.engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.get(RunRow, run_id)
            if row is None:
                raise DomainError("Processing run not found.", 404)
            row.data = {**row.data, **changes, "updated_at": now()}
            result = deepcopy(row.data)
            session.commit()
            return result

    def recover_runs(self):
        with Session(self.engine) as session, session.begin():
            for row in session.scalars(select(RunRow)):
                if row.data["status"] in ("running", "queued"):
                    row.data = {**row.data, "status": "resumable", "updated_at": now(), "stage": "interrupted — resume available"}

    def document(self, document_id: str) -> dict:
        with Session(self.engine) as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                raise DomainError("Document not found.", 404)
            return {**deepcopy(row.data), "project_id": row.project_id, "path": row.path}

    def save_parsed(self, document_id: str, pages: list[dict], spans: list[dict]):
        with Session(self.engine) as session, session.begin():
            for page in pages:
                session.merge(PageRow(document_id=document_id, page=page["page"], data=page))
            for span in spans:
                # Immutable evidence is inserted once. A parser version change uses a new document.
                existing = session.get(SpanRow, span["id"])
                if existing is None:
                    session.add(SpanRow(id=span["id"], document_id=document_id, page=span["page"], data=span))
            document = session.get(DocumentRow, document_id)
            document.data = {**document.data, "page_count": len(pages)}

    def pages(self, document_id: str) -> list[dict]:
        with Session(self.engine) as session:
            return [deepcopy(r.data) for r in session.scalars(select(PageRow).where(PageRow.document_id == document_id).order_by(PageRow.page))]

    def update_pages(self, document_id: str, pages: list[int], status: str, dispositions: dict[str, str] | None = None):
        with Session(self.engine) as session, session.begin():
            for number in pages:
                row = session.get(PageRow, (document_id, number))
                if row is not None:
                    original = row.data["status"]
                    row.data = {**row.data, "extraction_status": status,
                                "status": original if original in ("partial", "failed", "needs_ocr") else status}
            if dispositions:
                for row in session.scalars(select(SpanRow).where(SpanRow.document_id == document_id, SpanRow.page.in_(pages))):
                    if row.id in dispositions:
                        row.data = {**row.data, "disposition": dispositions[row.id]}

    def spans(self, document_id: str, pages: list[int] | None = None) -> list[dict]:
        stmt = select(SpanRow).where(SpanRow.document_id == document_id)
        if pages is not None:
            stmt = stmt.where(SpanRow.page.in_(pages))
        with Session(self.engine) as session:
            return [deepcopy(row.data) for row in session.scalars(stmt.order_by(SpanRow.page))]

    def source(self, source_id: str) -> dict:
        with Session(self.engine) as session:
            row = session.get(SpanRow, source_id)
            if row is None:
                raise DomainError("Source evidence not found.", 404)
            return deepcopy(row.data)

    def sources_for_project(self, project: dict, source_ids: list[str]) -> list[dict]:
        sources = [self.source(source_id) for source_id in source_ids]
        if any(s["document_id"] != project["document"]["id"] for s in sources):
            raise DomainError("Evidence must belong to this project's document.")
        return sources
