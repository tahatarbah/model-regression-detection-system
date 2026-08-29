"""SQLite persistence for runs and per-example results."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def default_db_path() -> Path:
    env = os.environ.get("MRDS_DB")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / ".mrds" / "mrds.db").resolve()


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    suite_name: Mapped[str] = mapped_column(String(255), index=True)
    suite_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    model_label: Mapped[str] = mapped_column(String(255))
    tag: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    task_type: Mapped[str] = mapped_column(String(64))
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    examples: Mapped[list[ExampleRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ExampleRow(Base):
    __tablename__ = "examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    example_id: Mapped[str] = mapped_column(String(255))
    input_json: Mapped[str] = mapped_column(Text)
    expected_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    run: Mapped[RunRow] = relationship(back_populates="examples")


class SuiteRegistryRow(Base):
    __tablename__ = "suites"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    path: Mapped[str] = mapped_column(String(1024))
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String(64))
    config_json: Mapped[str] = mapped_column(Text, default="{}")


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _json_loads(s: str | None) -> Any:
    if s is None:
        return None
    return json.loads(s)


class Store:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{self.db_path.as_posix()}"
        self.engine = create_engine(url, echo=False)
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._Session()

    def register_suite(
        self,
        *,
        name: str,
        path: str,
        description: str,
        task_type: str,
        config: dict,
    ) -> None:
        with self.session() as s:
            row = s.get(SuiteRegistryRow, name)
            if row is None:
                row = SuiteRegistryRow(
                    name=name,
                    path=path,
                    description=description,
                    task_type=task_type,
                    config_json=_json_dumps(config),
                )
                s.add(row)
            else:
                row.path = path
                row.description = description
                row.task_type = task_type
                row.config_json = _json_dumps(config)
            s.commit()

    def list_suites(self) -> list[dict]:
        with self.session() as s:
            rows = s.scalars(select(SuiteRegistryRow).order_by(SuiteRegistryRow.name)).all()
            return [
                {
                    "name": r.name,
                    "path": r.path,
                    "description": r.description,
                    "task_type": r.task_type,
                    "config": _json_loads(r.config_json),
                }
                for r in rows
            ]

    def save_run(
        self,
        *,
        suite_name: str,
        suite_path: str | None,
        model_label: str,
        tag: str | None,
        task_type: str,
        metrics: dict[str, float],
        examples: list[dict],
        status: str = "completed",
        run_id: str | None = None,
    ) -> str:
        rid = run_id or str(uuid.uuid4())
        with self.session() as s:
            if tag:
                # keep tag uniqueness per suite: clear old tag owners
                existing = s.scalars(
                    select(RunRow).where(RunRow.suite_name == suite_name, RunRow.tag == tag)
                ).all()
                for e in existing:
                    e.tag = None
            run = RunRow(
                id=rid,
                suite_name=suite_name,
                suite_path=suite_path,
                model_label=model_label,
                tag=tag,
                status=status,
                task_type=task_type,
                metrics_json=_json_dumps(metrics),
            )
            s.add(run)
            for ex in examples:
                s.add(
                    ExampleRow(
                        run_id=rid,
                        example_id=str(ex["example_id"]),
                        input_json=_json_dumps(ex.get("input")),
                        expected_json=_json_dumps(ex.get("expected")),
                        output_json=_json_dumps(ex.get("output")),
                        score=ex.get("score"),
                        passed=ex.get("passed"),
                        latency_ms=ex.get("latency_ms"),
                        tokens_in=ex.get("tokens_in"),
                        tokens_out=ex.get("tokens_out"),
                        details_json=_json_dumps(ex.get("details") or {}),
                    )
                )
            s.commit()
        return rid

    def get_run(self, run_id: str) -> dict | None:
        with self.session() as s:
            row = s.get(RunRow, run_id)
            if row is None:
                return None
            return self._run_to_dict(s, row, include_examples=True)

    def get_run_by_tag(self, suite_name: str, tag: str) -> dict | None:
        tag = tag.lstrip("@")
        with self.session() as s:
            row = s.scalars(
                select(RunRow)
                .where(RunRow.suite_name == suite_name, RunRow.tag == tag)
                .order_by(RunRow.created_at.desc())
            ).first()
            if row is None:
                return None
            return self._run_to_dict(s, row, include_examples=True)

    def resolve_run_ref(self, ref: str, suite_name: str | None = None) -> dict | None:
        if ref.startswith("@"):
            if not suite_name:
                raise ValueError("suite_name required to resolve tag refs like @prod")
            return self.get_run_by_tag(suite_name, ref)
        return self.get_run(ref)

    def list_runs(self, suite_name: str | None = None, limit: int = 100) -> list[dict]:
        with self.session() as s:
            q = select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
            if suite_name:
                q = q.where(RunRow.suite_name == suite_name)
            rows = s.scalars(q).all()
            return [self._run_to_dict(s, r, include_examples=False) for r in rows]

    def _run_to_dict(self, s: Session, row: RunRow, *, include_examples: bool) -> dict:
        data = {
            "id": row.id,
            "suite_name": row.suite_name,
            "suite_path": row.suite_path,
            "model_label": row.model_label,
            "tag": row.tag,
            "status": row.status,
            "task_type": row.task_type,
            "metrics": _json_loads(row.metrics_json) or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        if include_examples:
            ex_rows = s.scalars(
                select(ExampleRow).where(ExampleRow.run_id == row.id)
            ).all()
            data["examples"] = [
                {
                    "example_id": e.example_id,
                    "input": _json_loads(e.input_json),
                    "expected": _json_loads(e.expected_json),
                    "output": _json_loads(e.output_json),
                    "score": e.score,
                    "passed": e.passed,
                    "latency_ms": e.latency_ms,
                    "tokens_in": e.tokens_in,
                    "tokens_out": e.tokens_out,
                    "details": _json_loads(e.details_json) or {},
                }
                for e in ex_rows
            ]
        return data
