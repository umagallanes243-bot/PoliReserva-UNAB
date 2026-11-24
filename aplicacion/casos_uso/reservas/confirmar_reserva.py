# aplicacion/casos_uso/reservas/confirmar_reserva.py
"""CU: Confirmar asistencia a una reserva (PoliReserva UNAB V9)."""

from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


class ConfirmarReserva:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, codigo_reserva: str) -> dict:
        """Confirma una reserva dentro de los primeros 15 minutos.

        El repositorio verifica los permisos del actor, el tiempo,
        la transición RESERVADA -> CONFIRMADA y registra auditoría.
        """
        return self.repositorio.confirmar_asistencia(
            codigo_reserva=codigo_reserva,
            id_usuario_actor=id_usuario_sesion,
        )
