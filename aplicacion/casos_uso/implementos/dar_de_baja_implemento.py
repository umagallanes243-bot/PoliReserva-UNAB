"""Da de baja una unidad patrimonial y registra su salida."""

from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL


class DarDeBajaImplemento:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, unidad: int, motivo: str | None = None) -> None:
        self.repositorio.dar_de_baja(actor=id_usuario_sesion, unidad=unidad, motivo=motivo)
