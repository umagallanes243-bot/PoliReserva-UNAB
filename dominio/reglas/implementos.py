"""Identidad visible de los tipos de material y recuento de unidades."""

import re
from collections import Counter
from datetime import date, datetime, time, timedelta

from unicodedata import combining, normalize

from dominio.reglas.reservas import ZONA_PERU, acciones_reserva


_NUMERO_UNIDAD = re.compile(r'\s+(?:(?:n(?:ro|o|[.°º])(?:[.°º])?)\s*|#\s*)\d+$', re.IGNORECASE)
_ACENTOS = {'balon': 'balón', 'futbol': 'fútbol', 'voley': 'vóley', 'basquet': 'básquet',
            'cronometro': 'cronómetro'}


MAX_OBSERVACION_PRESTAMO = 200


def validar_motivo_sin_reserva(valor):
    motivo = valor.strip() if isinstance(valor, str) else ''
    if not motivo:
        raise ValueError('Indica el motivo de la solicitud sin reserva.')
    if len(motivo) > MAX_OBSERVACION_PRESTAMO:
        raise ValueError(f'El motivo debe tener como máximo {MAX_OBSERVACION_PRESTAMO} caracteres.')
    return motivo


def intervalo_reserva(reserva):
    dia = date.fromisoformat(str(reserva['fecha_uso']))
    return tuple(datetime.combine(dia, time.fromisoformat(str(reserva[campo])))
                 for campo in ('hora_inicio', 'hora_fin'))


def reserva_admite_prestamo(reserva, ahora):
    inicio, fin = intervalo_reserva(reserva)
    return ahora < fin and acciones_reserva(
        reserva['estado_reserva'], inicio.date(), inicio.time(), fin.time(),
        ahora.replace(tzinfo=ZONA_PERU),
    ).vigente


def fechas_sugeridas_prestamo(reserva, ahora):
    inicio, fin = intervalo_reserva(reserva)
    siguiente_minuto = ahora.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return max(inicio, siguiente_minuto), fin


def devolucion_vencida(fecha_prevista, ahora):
    return bool(fecha_prevista and datetime.fromisoformat(str(fecha_prevista)) < ahora.replace(tzinfo=None))


def texto_buscable(valor):
    return ''.join(c for c in normalize('NFD', str(valor or '').casefold()) if not combining(c))


def nombre_tipo_implemento(valor):
    nombre = _NUMERO_UNIDAD.sub('', ' '.join(str(valor or '').split()))
    return re.sub(r'\w+', lambda m: _ACENTOS.get(m[0].lower(), m[0]), nombre).capitalize()


def agrupar_unidades(filas):
    """Cuenta por categoría y tipo, conservando variantes y excluyendo repetidos."""
    unicas = {r['id_implemento']: r for r in filas}
    return Counter(
        (r['nombre_categoria'], nombre_tipo_implemento(r['nombre_implemento']))
        for r in unicas.values()
    )
