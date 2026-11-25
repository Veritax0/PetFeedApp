class ErrorDeDominio(Exception):
    pass


class RecursoNoEncontrado(ErrorDeDominio):
    pass


class ConflictoDeDatos(ErrorDeDominio):
    pass


class DatosInvalidos(ErrorDeDominio):
    pass
