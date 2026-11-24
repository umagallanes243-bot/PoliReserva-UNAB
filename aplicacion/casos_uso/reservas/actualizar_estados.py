"""Procesa las transiciones vencidas del polideportivo sin intervención de una página."""

import logging

from mysql.connector import Error as ErrorMySQL

from aplicacion.casos_uso.reservas.finalizar_reserva import FinalizarReserva
from aplicacion.casos_uso.reservas.registrar_inasistencia import RegistrarInasistencia
from infraestructura.persistencia.conexion_mysql import obtener_conexion
from infraestructura.persistencia.reservas_mysql import ErrorReserva, RepositorioReservasMySQL

logger = logging.getLogger(__name__)


def actualizar_estados():
    """El candado de la BD impide ciclos simultáneos entre procesos NiceGUI."""
    try:
        with obtener_conexion() as conexion, conexion.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(CONCAT(DATABASE(), '.estados-reserva'), 0)")
            adquirido, = cursor.fetchone()
            if adquirido != 1:
                return
            try:
                repo = RepositorioReservasMySQL()
                casos = {'RESERVADA': RegistrarInasistencia(repo), 'CONFIRMADA': FinalizarReserva(repo)}
                for reserva in repo.listar_transiciones_vencidas():
                    try:
                        casos[reserva['nombre_estado']].ejecutar(codigo_reserva=reserva['codigo_reserva'])
                    except (ErrorReserva, ErrorMySQL) as exc:
                        logger.warning('No se pudo avanzar una reserva vencida (%s)', type(exc).__name__)
            finally:
                cursor.execute("SELECT RELEASE_LOCK(CONCAT(DATABASE(), '.estados-reserva'))")
                cursor.fetchone()
    except ErrorMySQL as exc:
        logger.warning('No se pudo ejecutar el cierre de reservas (%s)', exc.errno)
