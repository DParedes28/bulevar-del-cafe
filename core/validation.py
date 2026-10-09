import re
from pathlib import Path

from core.errors import ValidationError
from core.models import MAX_PDF_BYTES

DOCUMENT_RE = re.compile(r"^[0-9]{5,12}$")
PDF_MAGIC = b"%PDF"
FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean(value: str) -> str:
    return value.replace("\x00", "").strip()


def validate_observation_fields(
    etapa: str,
    manzana: str,
    house_number: str,
    owner_name: str,
    owner_document: str,
    page_number: str,
    article: str,
    body: str,
) -> dict[str, str | int]:
    stage = _clean(etapa)
    block = _clean(manzana)
    house = _clean(house_number)
    name = _clean(owner_name)
    document = re.sub(r"[\s.\-]", "", _clean(owner_document))
    article_label = _clean(article)
    observation = _clean(body)
    errors: list[str] = []
    parsed_page = int(page_number) if str(page_number).isdigit() else 0

    if stage not in {"1", "2"}:
        errors.append("Elige la etapa 1 o 2.")
    if not 1 <= len(block) <= 20:
        errors.append("La manzana debe tener entre 1 y 20 caracteres.")
    if not 1 <= len(house) <= 20:
        errors.append("La casa debe tener entre 1 y 20 caracteres.")
    if not 2 <= len(name) <= 120:
        errors.append("El nombre debe tener entre 2 y 120 caracteres.")
    if DOCUMENT_RE.fullmatch(document) is None:
        errors.append("Escribe la cédula solo con números, entre 5 y 12 dígitos.")
    if not 1 <= parsed_page <= 9999:
        errors.append("Elige la página del manual.")
    if len(article_label) > 80:
        errors.append("El artículo debe tener como máximo 80 caracteres.")
    if not 10 <= len(observation) <= 4000:
        errors.append("La observación debe tener entre 10 y 4000 caracteres.")

    if errors:
        raise ValidationError(errors)

    return {
        "etapa": stage,
        "manzana": block,
        "house_number": house,
        "owner_name": name,
        "owner_document": document,
        "page_number": parsed_page,
        "article": article_label,
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
