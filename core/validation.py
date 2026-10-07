import re
from pathlib import Path

from core.errors import ValidationError
from core.models import MAX_PDF_BYTES

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PDF_MAGIC = b"%PDF"
FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean(value: str) -> str:
    return value.replace("\x00", "").strip()


def validate_observation_fields(
    house_number: str,
    owner_name: str,
    owner_email: str,
    article_or_page: str,
    body: str,
) -> dict[str, str]:
    house = _clean(house_number)
    name = _clean(owner_name)
    email = _clean(owner_email).lower()
    article = _clean(article_or_page)
    observation = _clean(body)
    errors: list[str] = []

    if not 1 <= len(house) <= 20:
        errors.append("El número de casa debe tener entre 1 y 20 caracteres.")
    if not 2 <= len(name) <= 120:
        errors.append("El nombre debe tener entre 2 y 120 caracteres.")
    if len(email) > 254 or EMAIL_RE.fullmatch(email) is None:
        errors.append("Escribe un correo electrónico válido.")
    if not 1 <= len(article) <= 120:
        errors.append("El artículo o la página debe tener entre 1 y 120 caracteres.")
    if not 10 <= len(observation) <= 4000:
        errors.append("La observación debe tener entre 10 y 4000 caracteres.")

    if errors:
        raise ValidationError(errors)

    return {
        "house_number": house,
        "owner_name": name,
        "owner_email": email,
        "article_or_page": article,
        "body": observation,
    }


def safe_pdf_filename(filename: str) -> str:
    base = Path(filename).name
    cleaned = FILENAME_RE.sub("-", base).strip(".-")
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned or 'manual'}.pdf"
    return cleaned[:255] or "manual.pdf"


def validate_pdf(filename: str, data: bytes) -> str:
    errors: list[str] = []
    if not data.startswith(PDF_MAGIC):
        errors.append("El archivo debe ser un PDF.")
    if not 0 < len(data) <= MAX_PDF_BYTES:
        errors.append("El PDF debe pesar como máximo 15 MB.")
    if errors:
        raise ValidationError(errors)
    return safe_pdf_filename(filename)
