# aplicacion/casos_uso/reservas/cancelar_reserva.py
"""CU: Cancelar una reserva del polideportivo (PoliReserva UNAB V9)."""

from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


class CancelarReserva:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, codigo_reserva: str) -> dict:
        """Cancela antes del inicio si el actor es titular o administrador.

        id_usuario_sesion debe proceder de la sesión validada del servidor.
        El repositorio valida permisos, cambia estado y registra auditoría.
        """
        return self.repositorio.cancelar_reserva(
            codigo_reserva=codigo_reserva,
            id_usuario_actor=id_usuario_sesion,
        )
