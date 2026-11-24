"""Cancela una solicitud pendiente por su titular o desde administración."""

from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL


class CancelarSolicitud:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, operacion: int) -> None:
        self.repositorio.cambiar_estado(actor=id_usuario_sesion, operacion=operacion, destino='CANCELADO')

    def ejecutar_como_admin(self, *, id_usuario_sesion: int, operacion: int, motivo: str | None = None) -> None:
        self.repositorio.cambiar_estado(
            actor=id_usuario_sesion, operacion=operacion, destino='CANCELADO',
            administrativo=True, detalle=motivo,
        )
