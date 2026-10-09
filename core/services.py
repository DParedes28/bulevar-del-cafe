import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from core.errors import FormClosedError, NotFoundError, ValidationError
from core.models import (
    STATUS_LABELS,
    AppSettings,
    ManualDocument,
    Observation,
    ObservationStatus,
)
from core.time import utcnow
from core.validation import validate_observation_fields, validate_pdf


def get_settings_row(session: Session) -> AppSettings | None:
    return session.get(AppSettings, 1)


def is_form_open(row: object | None, moment: datetime | None = None) -> bool:
    if row is None:
        return True
    deadline = row.deadline_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    current = moment or utcnow()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current < deadline


def save_deadline(session: Session, deadline_at: datetime) -> AppSettings:
    if deadline_at.tzinfo is None:
        raise ValidationError(["La fecha límite debe incluir zona horaria."])
    deadline_at = deadline_at.astimezone(timezone.utc)
    now = utcnow()
    row = get_settings_row(session)
    if row is None:
        row = AppSettings(id=1, deadline_at=deadline_at, updated_at=now)
        session.add(row)
    else:
        row.deadline_at = deadline_at
        row.updated_at = now
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        row = get_settings_row(session)
        if row is None:
            raise
        row.deadline_at = deadline_at
        row.updated_at = now
        session.commit()
    session.refresh(row)
    return row


def manual_is_available(session: Session) -> bool:
    statement = select(ManualDocument.id).where(ManualDocument.id == 1)
    return session.exec(statement).first() is not None


def get_manual_metadata(session: Session) -> tuple[str, int, datetime] | None:
    statement = select(
        ManualDocument.filename,
        ManualDocument.size_bytes,
        ManualDocument.uploaded_at,
    ).where(ManualDocument.id == 1)
    row = session.exec(statement).first()
    if row is None:
        return None
    return row[0], row[1], row[2]


def get_manual(session: Session) -> ManualDocument | None:
    return session.get(ManualDocument, 1)


_manual_lock = threading.Lock()
_manual_cache: tuple[str, datetime, bytes] | None = None
_manual_checked_at = 0.0
MANUAL_CACHE_SECONDS = 30


def clear_manual_cache() -> None:
    global _manual_cache, _manual_checked_at
    with _manual_lock:
        _manual_cache = None
        _manual_checked_at = 0.0


def get_cached_manual(session: Session) -> tuple[str, datetime, bytes] | None:
    global _manual_cache, _manual_checked_at
    now = time.monotonic()
    with _manual_lock:
        if _manual_cache is not None and now - _manual_checked_at < MANUAL_CACHE_SECONDS:
            return _manual_cache
        meta = get_manual_metadata(session)
        if meta is None:
            _manual_cache = None
            _manual_checked_at = time.monotonic()
            return None
        filename, _size_bytes, uploaded_at = meta
        if (
            _manual_cache is not None
            and _manual_cache[0] == filename
            and _manual_cache[1] == uploaded_at
        ):
            _manual_checked_at = time.monotonic()
            return _manual_cache
        document = get_manual(session)
        if document is None or not document.data:
            _manual_cache = None
            _manual_checked_at = time.monotonic()
            return None
        _manual_cache = (document.filename, document.uploaded_at, bytes(document.data))
        _manual_checked_at = time.monotonic()
        return _manual_cache


def save_manual(session: Session, filename: str, data: bytes) -> None:
    stored_name = validate_pdf(filename, data)
    now = utcnow()
    exists = session.exec(select(ManualDocument.id).where(ManualDocument.id == 1)).first()
    if exists is None:
        session.add(
            ManualDocument(
                id=1,
                filename=stored_name,
                content_type="application/pdf",
                size_bytes=len(data),
                data=data,
                uploaded_at=now,
            )
        )
    else:
        session.exec(
            update(ManualDocument)
            .where(ManualDocument.id == 1)
            .values(
                filename=stored_name,
                content_type="application/pdf",
                size_bytes=len(data),
                data=data,
                uploaded_at=now,
            )
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ValidationError(["No se pudo guardar el PDF. Revisa que sea un archivo válido de hasta 15 MB."]) from None
    clear_manual_cache()


def create_observation(session: Session, payload: dict[str, str]) -> Observation:
    if not is_form_open(get_settings_row(session)):
        raise FormClosedError()
    clean = validate_observation_fields(**payload)
    now = utcnow()
    observation = Observation(
        house_number=clean["house_number"],
        owner_name=clean["owner_name"],
        owner_document=str(clean["owner_document"]),
        page_number=int(clean["page_number"]),
        article=str(clean["article"]),
        body=clean["body"],
        status=ObservationStatus.nueva.value,
        created_at=now,
        updated_at=now,
    )
    session.add(observation)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ValidationError(
            ["No pudimos guardar la observación. Revisa los campos e inténtalo de nuevo."]
        ) from None
    session.refresh(observation)
    return observation


@dataclass(frozen=True)
class ObservationRecord:
    id: int
    house_number: str
    owner_name: str
    owner_document: str
    page_number: int
    article: str
    body: str
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


def snapshot_observation(row: Observation) -> ObservationRecord:
    if row.id is None:
        raise NotFoundError("La observación todavía no tiene identificador.")
    return ObservationRecord(
        id=row.id,
        house_number=row.house_number,
        owner_name=row.owner_name,
        owner_document=row.owner_document,
        page_number=row.page_number,
        article=row.article,
        body=row.body,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def count_active_observations(session: Session) -> int:
    statement = select(func.count(Observation.id)).where(Observation.deleted_at.is_(None))
    return int(session.exec(statement).one())


def list_observations(
    session: Session,
    house: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
) -> list[Observation]:
    statement = select(Observation)
    if not include_deleted:
        statement = statement.where(Observation.deleted_at.is_(None))
    if house and house.strip():
        term = house.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Observation.house_number.ilike(f"%{term}%", escape="\\"))
    if status:
        statement = statement.where(Observation.status == status)
    statement = statement.order_by(Observation.created_at.desc())
    return list(session.exec(statement).all())


def _active_observation(session: Session, observation_id: int) -> Observation:
    observation = session.get(Observation, observation_id)
    if observation is None or observation.deleted_at is not None:
        raise NotFoundError("No se encontró la observación.")
    return observation


def set_observation_status(session: Session, observation_id: int, status: str) -> Observation:
    if status not in STATUS_LABELS:
        raise ValidationError(["El estado no es válido."])
    observation = _active_observation(session, observation_id)
    observation.status = status
    observation.updated_at = utcnow()
    session.commit()
    session.refresh(observation)
    return observation


def soft_delete_observation(session: Session, observation_id: int) -> Observation:
    observation = session.get(Observation, observation_id)
    if observation is None:
        raise NotFoundError("No se encontró la observación.")
    now = utcnow()
    observation.deleted_at = now
    observation.updated_at = now
    session.commit()
    session.refresh(observation)
    return observation


def restore_observation(session: Session, observation_id: int) -> Observation:
    observation = session.get(Observation, observation_id)
    if observation is None:
        raise NotFoundError("No se encontró la observación.")
    observation.deleted_at = None
    observation.updated_at = utcnow()
    session.commit()
    session.refresh(observation)
    return observation
