import secrets
import sys
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
from pydantic import ValidationError as SettingsError
from sqlalchemy.exc import SQLAlchemyError

from core.config import get_settings
from core.database import init_db, open_session
from core.errors import NotFoundError, ValidationError
from core.models import STATUS_LABELS
from core.services import (
    count_active_observations,
    get_manual_metadata,
    get_settings_row,
    is_form_open,
    list_observations,
    restore_observation,
    save_deadline,
    save_manual,
    set_observation_status,
    snapshot_observation,
    soft_delete_observation,
)
from core.time import BOGOTA, combine_bogota, format_bogota, to_bogota

st.set_page_config(page_title="Administración · Bulevar del Café", layout="wide")


def password_ok(provided: str, expected: str) -> bool:
    if not expected:
        return False
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_password(expected: str) -> None:
    if st.session_state.get("authenticated"):
        return
    st.title("Administración")
    st.caption("Bulevar del Café")
    password = st.text_input("Contraseña", type="password")
    if st.button("Entrar", type="primary"):
        if password_ok(password, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Contraseña incorrecta.")
    st.stop()


def flash(message: str) -> None:
    st.session_state["flash"] = message
    st.rerun()


def format_size(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def observations_frame(rows: list) -> pd.DataFrame:
    show_deleted = any(row.deleted_at is not None for row in rows)
    records = []
    for row in rows:
        record = {
            "Id": row.id,
            "Casa": row.house_number,
            "Nombre": row.owner_name,
            "Cédula": row.owner_document,
            "Página": row.page_number,
            "Artículo": row.article,
            "Observación": row.body,
            "Estado": STATUS_LABELS.get(row.status, row.status),
            "Creada": format_bogota(row.created_at),
            "Actualizada": format_bogota(row.updated_at),
        }
        if show_deleted:
            record["Eliminada"] = format_bogota(row.deleted_at) if row.deleted_at else ""
        records.append(record)
    return pd.DataFrame(records)


def excel_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_excel(buffer, index=False, sheet_name="Observaciones")
    return buffer.getvalue()


try:
    settings = get_settings()
except SettingsError:
    st.error("Falta DATABASE_URL. Agrégala en el entorno o en el archivo .env del proyecto.")
    st.stop()

if not settings.admin_password:
    st.error("Falta ADMIN_PASSWORD. Sin esa variable el panel permanece cerrado.")
    st.stop()

require_password(settings.admin_password)

if not st.session_state.get("db_ready"):
    try:
        init_db()
    except Exception as exc:
        st.error("No se pudo conectar a la base de datos.")
        st.caption(str(exc).split("\n")[0])
        st.stop()
    st.session_state["db_ready"] = True

notice = st.session_state.pop("flash", None)
if notice:
    st.success(notice)

st.title("Bulevar del Café")
st.caption("Las fechas se guardan y se muestran en hora de Colombia.")

with open_session() as session:
    settings_row = get_settings_row(session)
    deadline_at = None if settings_row is None else settings_row.deadline_at
    manual = get_manual_metadata(session)
    active_count = count_active_observations(session)

if deadline_at is None:
    form_label = "Sin fecha"
elif is_form_open(SimpleNamespace(deadline_at=deadline_at)):
    form_label = "Abierto"
else:
    form_label = "Cerrado"

metric_form, metric_manual, metric_count = st.columns(3)
metric_form.metric("Formulario", form_label)
metric_manual.metric("Manual", "Publicado" if manual else "Sin archivo")
metric_count.metric("Observaciones activas", active_count)

period_tab, manual_tab, observations_tab = st.tabs(["Periodo", "Manual", "Observaciones"])

with period_tab:
    if deadline_at is None:
        initial = datetime.now(BOGOTA) + timedelta(days=15)
        st.info("Todavía no hay una fecha límite. Los copropietarios pueden comentar hasta que guardes una fecha de cierre.")
    else:
        initial = to_bogota(deadline_at)
        st.write(f"Cierre actual: **{format_bogota(deadline_at)}**")
    deadline_day = st.date_input("Fecha límite", value=initial.date(), key="deadline_day")
    deadline_time = st.time_input(
        "Hora límite (Colombia)",
        value=initial.time().replace(microsecond=0),
        key="deadline_time",
    )
    chosen = datetime.combine(deadline_day, deadline_time, tzinfo=BOGOTA)
    if chosen <= datetime.now(BOGOTA):
        st.info("Esa fecha ya pasó. Al guardarla, el formulario queda cerrado.")
    if st.button("Guardar fecha", type="primary"):
        try:
            with open_session() as session:
                save_deadline(session, combine_bogota(deadline_day, deadline_time))
        except ValidationError as exc:
            for message in exc.errors:
                st.error(message)
        except SQLAlchemyError as exc:
            st.error("No se pudo guardar la fecha.")
            st.caption(str(exc).split("\n")[0])
        else:
            flash("Fecha límite actualizada.")

with manual_tab:
    if manual is None:
        st.info("Todavía no hay un PDF publicado. La página pública no muestra la descarga.")
    else:
        filename, size_bytes, uploaded_at = manual
        st.write(f"Archivo actual: **{filename}**")
        st.write(f"Tamaño: {format_size(size_bytes)} · Publicado: {format_bogota(uploaded_at)}")
    upload = st.file_uploader("PDF del manual", type=["pdf"], accept_multiple_files=False)
    if st.button("Publicar PDF", type="primary"):
        if upload is None:
            st.warning("Selecciona un PDF antes de publicarlo.")
        else:
            try:
                with open_session() as session:
                    save_manual(session, upload.name, upload.getvalue())
            except ValidationError as exc:
                for message in exc.errors:
                    st.error(message)
            except SQLAlchemyError as exc:
                st.error("No se pudo guardar el PDF.")
                st.caption(str(exc).split("\n")[0])
            else:
                flash("Manual publicado.")

with observations_tab:
    filter_house, filter_status, filter_deleted = st.columns([2, 1, 1])
    house = filter_house.text_input("Número de casa", placeholder="Contiene…")
    status_options = ["Todas", *STATUS_LABELS.keys()]
    status_choice = filter_status.selectbox(
        "Estado",
        status_options,
        format_func=lambda value: "Todas" if value == "Todas" else STATUS_LABELS[value],
    )
    include_deleted = filter_deleted.checkbox("Mostrar eliminadas")
    selected_status = None if status_choice == "Todas" else status_choice

    with open_session() as session:
        rows = [
            snapshot_observation(row)
            for row in list_observations(
                session,
                house=house,
                status=selected_status,
                include_deleted=include_deleted,
            )
        ]
    frame = observations_frame(rows)

    if frame.empty:
        st.info("No hay observaciones con ese filtro.")
    else:
        st.dataframe(frame, hide_index=True)
        csv_data = frame.to_csv(index=False).encode("utf-8-sig")
        download_csv, download_excel = st.columns(2)
        download_csv.download_button(
            "Descargar CSV",
            data=csv_data,
            file_name="observaciones-bulevar-del-cafe.csv",
            mime="text/csv",
        )
        download_excel.download_button(
            "Descargar Excel",
            data=excel_bytes(frame),
            file_name="observaciones-bulevar-del-cafe.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        labels = {
            row.id: f"#{row.id} · casa {row.house_number} · {STATUS_LABELS.get(row.status, row.status)}"
            for row in rows
        }
        selected_id = st.selectbox("Observación", options=list(labels), format_func=lambda item: labels[item])
        selected = next(row for row in rows if row.id == selected_id)
        if selected.deleted_at is not None:
            st.caption(f"Eliminada el {format_bogota(selected.deleted_at)}.")
            if st.button("Restaurar observación"):
                try:
                    with open_session() as session:
                        restore_observation(session, selected_id)
                except NotFoundError as exc:
                    st.error(exc.message)
                except SQLAlchemyError as exc:
                    st.error("No se pudo restaurar la observación.")
                    st.caption(str(exc).split("\n")[0])
                else:
                    flash("Observación restaurada.")
        else:
            new_status = st.selectbox(
                "Nuevo estado",
                list(STATUS_LABELS),
                index=list(STATUS_LABELS).index(selected.status),
                format_func=lambda value: STATUS_LABELS[value],
            )
            action_update, action_delete = st.columns(2)
            if action_update.button("Actualizar estado", type="primary"):
                try:
                    with open_session() as session:
                        set_observation_status(session, selected_id, new_status)
                except (ValidationError, NotFoundError) as exc:
                    message = exc.errors[0] if isinstance(exc, ValidationError) else exc.message
                    st.error(message)
                except SQLAlchemyError as exc:
                    st.error("No se pudo actualizar el estado.")
                    st.caption(str(exc).split("\n")[0])
                else:
                    flash("Estado actualizado.")
            confirm_delete = action_delete.checkbox("Confirmo la eliminación")
            if action_delete.button("Marcar como eliminada"):
                if not confirm_delete:
                    st.warning("Marca la confirmación antes de eliminar.")
                else:
                    try:
                        with open_session() as session:
                            soft_delete_observation(session, selected_id)
                    except NotFoundError as exc:
                        st.error(exc.message)
                    except SQLAlchemyError as exc:
                        st.error("No se pudo eliminar la observación.")
                        st.caption(str(exc).split("\n")[0])
                    else:
                        flash("Observación marcada como eliminada. Puedes restaurarla desde este mismo filtro.")
