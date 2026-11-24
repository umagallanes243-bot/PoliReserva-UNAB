"""Rangos de consulta de los indicadores y reportes."""

from calendar import monthrange
from datetime import date, timedelta

from dominio.reglas.reservas import inicio_semana


MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
         'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def sumar_meses(dia, meses):
    anio, mes = divmod(dia.year * 12 + dia.month - 1 + meses, 12)
    ultimo = monthrange(anio, mes + 1)[1]
    return date(anio, mes + 1, min(dia.day, ultimo))


def limites_mes(dia):
    return dia.replace(day=1), dia.replace(day=monthrange(dia.year, dia.month)[1])


PERIODOS_REFERENCIA = ('Día', 'Semana', 'Mes', 'Año')
PERIODOS = (*PERIODOS_REFERENCIA, 'Período académico', 'Personalizado', 'Todo el historial')


def fechas_de_consulta(periodo, referencia, desde, hasta, ciclo, catalogo):
    """Devuelve inicio y fin inclusivos, con ambos nulos para todo el historial."""
    if periodo == 'Todo el historial':
        return None, None
    if periodo == 'Período académico':
        elegido = next((p for p in catalogo if str(p['id_periodo']) == str(ciclo)), None)
        if elegido is None:
            raise ValueError('Selecciona un período académico.')
        inicio = date.fromisoformat(str(elegido['fecha_inicio']))
        fin = date.fromisoformat(str(elegido['fecha_fin']))
    elif periodo == 'Personalizado':
        inicio, fin = (date.fromisoformat(str(valor)) for valor in (desde, hasta))
    else:
        dia = date.fromisoformat(str(referencia))
        if periodo in ('Día', 'Hoy'):
            inicio = fin = dia
        elif periodo == 'Semana':
            inicio = inicio_semana(dia)
            fin = inicio + timedelta(days=6)
        elif periodo == 'Mes':
            inicio, fin = limites_mes(dia)
        elif periodo == 'Año':
            inicio, fin = date(dia.year, 1, 1), date(dia.year, 12, 31)
        else:
            raise ValueError('Selecciona un período válido.')
    if inicio > fin:
        raise ValueError('La fecha final debe ser igual o posterior a la inicial.')
    return inicio, fin
