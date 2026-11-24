"""Cambia el turno de una reserva futura conservando su código."""

from infraestructura.persistencia.reservas_mysql import ErrorReserva, RepositorioReservasMySQL


class ReprogramarReserva:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, id_usuario: int, codigo_reserva: str,
                 fecha_uso, hora_inicio, hora_fin) -> dict:
        if not codigo_reserva:
            raise ErrorReserva('Selecciona una reserva para modificar.')
        return self.repositorio.registrar_reserva(
            id_usuario=id_usuario, id_admin_gestor=id_usuario_sesion, codigo_a_reprogramar=codigo_reserva,
            fecha_uso=fecha_uso, hora_inicio=hora_inicio, hora_fin=hora_fin,
        )
