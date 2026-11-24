# aplicacion/casos_uso/reservas/registrar_reserva.py
"""CU: Registrar reserva del polideportivo (PoliReserva UNAB V9)."""

from datetime import date, time

from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


class RegistrarReserva:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(
        self,
        *,
        id_usuario_sesion: int,
        fecha_uso: date | str,
        hora_inicio: time | str,
        hora_fin: time | str,
    ) -> dict:
        """Crea una reserva para el usuario de la sesión autenticada.

        El repositorio comprueba perfil, fecha futura, duración máxima de
        2 horas, disponibilidad, solapamientos y reserva activa previa.
        No se recibe ningún rol ni ID de administrador desde el formulario.
        """
        return self.repositorio.registrar_reserva(
            id_usuario=id_usuario_sesion,
            fecha_uso=fecha_uso,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
        )
