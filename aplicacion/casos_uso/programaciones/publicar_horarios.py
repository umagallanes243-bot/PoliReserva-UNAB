"""Publica una programación con sus horarios para el polideportivo."""

from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL


class PublicarHorarios:
    def __init__(self, repositorio: RepositorioProgramacionesMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioProgramacionesMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, tipo: str, id_periodo: int, nombre: str,
                 horarios, descripcion: str | None = None, responsable: str | None = None,
                 escuela: int | None = None) -> int:
        return self.repositorio.guardar_programacion(
            actor=id_usuario_sesion, tipo=tipo, id_periodo=id_periodo, nombre=nombre,
            descripcion=descripcion, responsable=responsable, escuela=escuela, horarios=horarios,
        )
