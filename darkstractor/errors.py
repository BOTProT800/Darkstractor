class DarkstractorError(Exception):
    """Error esperado que puede mostrarse directamente al usuario."""


class FormatError(DarkstractorError):
    """El archivo no coincide con el formato esperado o está truncado."""


class CancelledError(DarkstractorError):
    """La operación fue cancelada por el usuario."""

