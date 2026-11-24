"""Horario local y ventanas de vigencia del polideportivo."""

from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple


ZONA_PERU = timezone(timedelta(hours=-5))
APERTURA, CIERRE = 7 * 60, 22 * 60
MAXIMO_RESERVA_MINUTOS = 120
LIMITE_SEMANAL_MINUTOS = 180
ESTADOS_RESERVA = ('RESERVADA', 'CONFIRMADA', 'FINALIZADA', 'CANCELADA', 'INASISTENCIA')
ESTADOS_CONSUMEN_CUPO = ('RESERVADA', 'CONFIRMADA', 'FINALIZADA', 'INASISTENCIA')
TOLERANCIA_MINUTOS = 15
TOLERANCIA_ASISTENCIA = timedelta(minutes=TOLERANCIA_MINUTOS)


def inicio_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


def minutos_disponibles(segundos_utilizados: int) -> int:
    return max(0, (LIMITE_SEMANAL_MINUTOS * 60 - segundos_utilizados) // 60)


def aviso_cupo_semanal(segundos_utilizados: int) -> str:
    minutos = minutos_disponibles(segundos_utilizados)
    if not minutos:
        return 'Has utilizado las 3 horas de reserva disponibles para esta semana.'
    saldo = 'Te queda 1 minuto disponible' if minutos == 1 else f'Te quedan {minutos} minutos disponibles'
    return f'{saldo} para esta semana. Selecciona un horario de menor duración.'


class AccionesReserva(NamedTuple):
    vigente: bool = False
    cancelar: bool = False
    confirmar: bool = False


def acciones_reserva(estado, fecha, hora_inicio, hora_fin, ahora: datetime) -> AccionesReserva:
    """Espejo de las reglas temporales para consultas y botones."""
    if estado not in ('RESERVADA', 'CONFIRMADA'):
        return AccionesReserva()
    try:
        dia = date.fromisoformat(str(fecha))
        inicio = datetime.combine(dia, time.fromisoformat(str(hora_inicio)), ZONA_PERU)
        fin = datetime.combine(dia, time.fromisoformat(str(hora_fin)), ZONA_PERU)
    except (TypeError, ValueError):
        return AccionesReserva()
    if estado == 'CONFIRMADA':
        return AccionesReserva(vigente=ahora < fin)
    limite = inicio + TOLERANCIA_ASISTENCIA
    return AccionesReserva(ahora < limite, ahora < inicio, inicio <= ahora < limite)
