# aplicacion/casos_uso/reservas/finalizar_reserva.py
"""CU interno: Finalizar reserva (PoliReserva UNAB V9)."""

from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


class FinalizarReserva:
    def __init__(self, repositorio: RepositorioReservasMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioReservasMySQL()

    def ejecutar(self, *, codigo_reserva: str) -> dict:
        """Finaliza una CONFIRMADA al terminar su turno.

        Uso exclusivo de un proceso interno confiable del servidor:
        no conectar directamente con una ruta o botón público.
        El repositorio comprueba el tiempo y audita el cambio.
        """
        return self.repositorio.finalizar_reserva(codigo_reserva=codigo_reserva)
