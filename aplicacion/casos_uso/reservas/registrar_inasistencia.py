# aplicacion/casos_uso/reservas/registrar_inasistencia.py
"""CU interno: Registrar inasistencia (PoliReserva UNAB V9)."""

from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


class RegistrarInasistencia:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(self, *, codigo_reserva: str) -> dict:
        """Marca una RESERVADA como INASISTENCIA tras 15 minutos.

        Uso exclusivo de un proceso interno confiable del servidor:
        no conectar directamente con una ruta o botón público.
        El repositorio comprueba el tiempo y audita el cambio.
        """
        return self.repositorio.marcar_inasistencia(codigo_reserva=codigo_reserva)
