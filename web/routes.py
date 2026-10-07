import logging

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from core.database import get_session
from core.errors import FormClosedError, ValidationError
from core.services import (
    create_observation,
    get_manual,
    get_settings_row,
    is_form_open,
    manual_is_available,
)
from core.time import format_bogota

logger = logging.getLogger("bulevar")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter()

EMPTY_FORM = {
    "house_number": "",
    "owner_name": "",
    "owner_email": "",
    "article_or_page": "",
    "body": "",
}


def page_context(session: Session, **extra: object) -> dict[str, object]:
    try:
        settings_row = get_settings_row(session)
        context: dict[str, object] = {
            "form_open": is_form_open(settings_row),
            "manual_available": manual_is_available(session),
            "deadline_label": format_bogota(settings_row.deadline_at) if settings_row else None,
            "sent": False,
            "errors": [],
            "form": dict(EMPTY_FORM),
            "db_error": False,
        }
    except SQLAlchemyError:
        logger.exception("No se pudo leer el estado público")
        session.rollback()
        context = {
            "form_open": False,
            "manual_available": False,
            "deadline_label": None,
            "sent": False,
            "errors": [],
            "form": dict(EMPTY_FORM),
            "db_error": True,
        }
    context.update(extra)
    return context


def render(request: Request, context: dict[str, object], status_code: int = 200, reader: bool = False):
    return templates.TemplateResponse(
        request=request,
        name="leer.html" if reader else "index.html",
        context=context,
        status_code=status_code,
    )


def reader_requested(return_to: str) -> bool:
    return return_to.strip() == "/leer"


def after_send(return_to: str, page: str) -> str:
    if not reader_requested(return_to):
        return "/?enviada=1"
    page_number = int(page) if page.isdigit() and int(page) > 0 else 1
    return f"/leer?enviada=1&pagina={page_number}"


def pdf_response(session: Session, disposition: str) -> Response:
    try:
        document = get_manual(session)
    except SQLAlchemyError:
        logger.exception("No se pudo leer el manual")
        session.rollback()
        return Response(
            "El manual no está disponible en este momento.",
            status_code=503,
            media_type="text/plain; charset=utf-8",
        )
    if document is None:
        return Response(
            "El manual aún no está disponible.",
            status_code=404,
            media_type="text/plain; charset=utf-8",
        )
    filename = document.filename or "manual-convivencia.pdf"
    return Response(
        content=document.data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/")
def home(
    request: Request,
    enviada: int = Query(default=0),
    session: Session = Depends(get_session),
):
    return render(request, page_context(session, sent=enviada == 1))


@router.get("/leer")
def read_manual(
    request: Request,
    enviada: int = Query(default=0),
    pagina: int = Query(default=1),
    session: Session = Depends(get_session),
):
    context = page_context(session, sent=enviada == 1, start_page=max(pagina, 1))
    return render(request, context, reader=True)


@router.post("/observaciones")
def submit_observation(
    request: Request,
    house_number: str = Form(""),
    owner_name: str = Form(""),
    owner_email: str = Form(""),
    article_or_page: str = Form(""),
    body: str = Form(""),
    company_website: str = Form(""),
    return_to: str = Form("/"),
    page: str = Form("1"),
    session: Session = Depends(get_session),
):
    form = {
        "house_number": house_number,
        "owner_name": owner_name,
        "owner_email": owner_email,
        "article_or_page": article_or_page,
        "body": body,
    }
    reader = reader_requested(return_to)
    start_page = int(page) if page.isdigit() and int(page) > 0 else 1
    if company_website.strip():
        return RedirectResponse(after_send(return_to, page), status_code=303)
    try:
        create_observation(session, form)
    except FormClosedError as exc:
        return render(
            request,
            page_context(session, errors=[exc.message], form=form, start_page=start_page),
            status_code=403,
            reader=reader,
        )
    except ValidationError as exc:
        return render(
            request,
            page_context(session, errors=exc.errors, form=form, start_page=start_page),
            status_code=400,
            reader=reader,
        )
    except SQLAlchemyError:
        logger.exception("No se pudo guardar la observación")
        session.rollback()
        return render(
            request,
            page_context(
                session,
                errors=["No pudimos guardar la observación. Inténtalo de nuevo en unos minutos."],
                form=form,
                start_page=start_page,
            ),
            status_code=503,
            reader=reader,
        )
    return RedirectResponse(after_send(return_to, page), status_code=303)


@router.get("/manual")
def view_manual(session: Session = Depends(get_session)) -> Response:
    return pdf_response(session, "inline")


@router.get("/manual/descargar")
def download_manual(session: Session = Depends(get_session)) -> Response:
    return pdf_response(session, "attachment")
