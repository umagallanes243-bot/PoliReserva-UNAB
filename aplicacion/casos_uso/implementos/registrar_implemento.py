"""Registra una unidad patrimonial con su movimiento de alta."""

from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL


class RegistrarImplemento:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, codigo: str, nombre: str, categoria: int | str,
                 apto: bool, descripcion: str | None = None) -> None:
        self.repositorio.guardar_implemento(
            actor=id_usuario_sesion, codigo=codigo, nombre=nombre, categoria=categoria,
            descripcion=descripcion, apto=apto,
        )
