"""Crea una categoría del inventario patrimonial."""

from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL


class CrearCategoriaImplemento:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, nombre: str) -> None:
        self.repositorio.crear_categoria(actor=id_usuario_sesion, nombre=nombre)
