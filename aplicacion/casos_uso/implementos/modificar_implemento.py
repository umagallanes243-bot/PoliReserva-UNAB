"""Actualiza los datos permitidos de una unidad patrimonial."""

from infraestructura.persistencia.implementos_mysql import ErrorImplemento, RepositorioImplementosMySQL


class ModificarImplemento:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, id_implemento: int, codigo: str, nombre: str,
                 categoria: int | str, apto: bool, descripcion: str | None = None) -> None:
        if id_implemento is None:
            raise ErrorImplemento('Selecciona un implemento para modificar.')
        self.repositorio.guardar_implemento(
            actor=id_usuario_sesion, id_implemento=id_implemento, codigo=codigo, nombre=nombre,
            categoria=categoria, descripcion=descripcion, apto=apto,
        )
