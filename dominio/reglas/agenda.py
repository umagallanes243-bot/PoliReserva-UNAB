"""Intervalos de la jornada del único polideportivo."""

from dominio.reglas.reservas import APERTURA, CIERRE


TIPOS_ACTIVIDAD = ('TALLER DEPORTIVO', 'EVENTO INSTITUCIONAL', 'MANTENIMIENTO')


def a_minutos(valor):
    try:
        horas, minutos = map(int, str(valor).split(':')[:2])
    except (TypeError, ValueError):
        return None
    if 0 <= horas <= 24 and 0 <= minutos < 60 and (horas < 24 or minutos == 0):
        return horas * 60 + minutos
    return None


def hhmm(valor):
    return f'{valor // 60:02d}:{valor % 60:02d}'


def intervalo_jornada(inicio, fin):
    inicio, fin = a_minutos(inicio), a_minutos(fin)
    if inicio is not None and fin is not None:
        inicio, fin = max(APERTURA, inicio), min(CIERRE, fin)
        if inicio < fin:
            return inicio, fin
    return None


def unir_intervalos(intervalos):
    unidos = []
    for inicio, fin in sorted(intervalos):
        if unidos and inicio <= unidos[-1][1]:
            anterior, corte = unidos[-1]
            unidos[-1] = anterior, max(corte, fin)
        else:
            unidos.append((inicio, fin))
    return unidos


def restar_intervalos(inicio, fin, cortes):
    """Tramos restantes tras quitar todos los intervalos ocupados."""
    for desde, hasta in sorted(cortes):
        if desde >= fin:
            break
        if hasta <= inicio:
            continue
        if inicio < desde:
            yield inicio, desde
        inicio = max(inicio, hasta)
    if inicio < fin:
        yield inicio, fin
