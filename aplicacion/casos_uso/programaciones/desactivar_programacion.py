"""Desactiva una programación sin eliminar su historial."""

from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL


class DesactivarProgramacion:
    def __init__(self, repositorio: RepositorioProgramacionesMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioProgramacionesMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, id_programacion: int) -> None:
        self.repositorio.desactivar_programacion(actor=id_usuario_sesion, id_programacion=id_programacion)
