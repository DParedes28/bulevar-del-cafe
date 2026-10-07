class ValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class FormClosedError(Exception):
    def __init__(self, message: str = "El periodo de observaciones está cerrado.") -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(Exception):
    def __init__(self, message: str = "No se encontró el registro.") -> None:
        self.message = message
        super().__init__(message)
