"""Confirma la entrega de las unidades de un préstamo pendiente."""

from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL


class EntregarPrestamo:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, operacion: int, unidades: tuple[int, ...],
                 detalle: str | None = None) -> None:
        self.repositorio.cambiar_estado(
            actor=id_usuario_sesion, operacion=operacion, destino='ENTREGADO',
            administrativo=True, detalle=detalle, unidades=unidades,
        )
