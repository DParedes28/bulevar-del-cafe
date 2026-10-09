from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlmodel import Field, SQLModel


class ObservationStatus(str, Enum):
    nueva = "nueva"
    revisada = "revisada"
    incorporada = "incorporada"


STATUS_LABELS: dict[str, str] = {
    ObservationStatus.nueva.value: "Nueva",
    ObservationStatus.revisada.value: "Revisada",
    ObservationStatus.incorporada.value: "Incorporada",
}

MAX_PDF_BYTES = 15 * 1024 * 1024


class AppSettings(SQLModel, table=True):
    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("id = 1", name="app_settings_singleton"),)

    id: int = Field(sa_column=Column(SmallInteger, primary_key=True, autoincrement=False))
    deadline_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class Observation(SQLModel, table=True):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('nueva', 'revisada', 'incorporada')",
            name="observations_status_chk",
        ),
        CheckConstraint(
            "etapa IS NULL OR etapa IN ('1', '2')",
            name="observations_etapa_chk",
        ),
        CheckConstraint(
            "manzana IS NULL OR char_length(btrim(manzana)) BETWEEN 1 AND 20",
            name="observations_manzana_chk",
        ),
        CheckConstraint(
            "char_length(btrim(house_number)) BETWEEN 1 AND 20",
            name="observations_house_chk",
        ),
        CheckConstraint(
            "char_length(btrim(owner_name)) BETWEEN 2 AND 120",
            name="observations_name_chk",
        ),
        CheckConstraint(
            "char_length(btrim(owner_document)) BETWEEN 1 AND 20",
            name="observations_document_chk",
        ),
        CheckConstraint(
            "page_number BETWEEN 1 AND 9999",
            name="observations_page_chk",
        ),
        CheckConstraint(
            "char_length(article) <= 80",
            name="observations_article_chk",
        ),
        CheckConstraint(
            "char_length(btrim(body)) BETWEEN 10 AND 4000",
            name="observations_body_chk",
        ),
        Index(
            "ix_observations_house_active",
            "house_number",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_observations_created_active",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    etapa: str | None = Field(default=None, sa_column=Column(String(1), nullable=True))
    manzana: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    house_number: str = Field(sa_column=Column(String(20), nullable=False))
    owner_name: str = Field(sa_column=Column(String(120), nullable=False))
    owner_document: str = Field(sa_column=Column(String(20), nullable=False))
    page_number: int = Field(sa_column=Column(Integer, nullable=False))
    article: str = Field(default="", sa_column=Column(String(80), nullable=False, server_default=""))
    body: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(
        default=ObservationStatus.nueva.value,
        sa_column=Column(String(20), nullable=False, server_default="nueva"),
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class ManualDocument(SQLModel, table=True):
    __tablename__ = "manual_documents"
    __table_args__ = (
        CheckConstraint("id = 1", name="manual_documents_singleton"),
        CheckConstraint("content_type = 'application/pdf'", name="manual_documents_pdf_chk"),
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 15728640",
            name="manual_documents_size_chk",
        ),
    )

    id: int = Field(sa_column=Column(SmallInteger, primary_key=True, autoincrement=False))
    filename: str = Field(sa_column=Column(String(255), nullable=False))
    content_type: str = Field(
        default="application/pdf",
        sa_column=Column(String(100), nullable=False, server_default="application/pdf"),
    )
    size_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    uploaded_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
