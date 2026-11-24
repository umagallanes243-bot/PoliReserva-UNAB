"""Crea un período académico en el catálogo V9."""

from datetime import date

from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL


class CrearPeriodoAcademico:
    def __init__(self, repositorio: RepositorioProgramacionesMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioProgramacionesMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, nombre: str, inicio: date | str, fin: date | str) -> None:
        self.repositorio.crear_periodo(actor=id_usuario_sesion, nombre=nombre, inicio=inicio, fin=fin)
