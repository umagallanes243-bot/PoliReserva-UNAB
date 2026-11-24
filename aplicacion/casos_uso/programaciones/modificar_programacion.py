"""Actualiza una programación existente y sus horarios."""

from infraestructura.persistencia.programaciones_mysql import ErrorProgramacion, RepositorioProgramacionesMySQL


class ModificarProgramacion:
    def __init__(self, repositorio: RepositorioProgramacionesMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioProgramacionesMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, id_programacion: int, tipo: str,
                 id_periodo: int, nombre: str, horarios, descripcion: str | None = None,
                 responsable: str | None = None, escuela: int | None = None) -> int:
        if id_programacion is None:
            raise ErrorProgramacion('Selecciona una programación para modificar.')
        return self.repositorio.guardar_programacion(
            actor=id_usuario_sesion, id_programacion=id_programacion, tipo=tipo, id_periodo=id_periodo,
            nombre=nombre, descripcion=descripcion, responsable=responsable, escuela=escuela,
            horarios=horarios,
        )
