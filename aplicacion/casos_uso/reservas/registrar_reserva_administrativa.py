"""Registra una reserva por cuenta de un titular con gestión administrativa."""

from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


class RegistrarReservaAdministrativa:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, id_usuario: int, fecha_uso, hora_inicio, hora_fin) -> dict:
        return self.repositorio.registrar_reserva(
            id_usuario=id_usuario, id_admin_gestor=id_usuario_sesion,
            fecha_uso=fecha_uso, hora_inicio=hora_inicio, hora_fin=hora_fin,
        )
