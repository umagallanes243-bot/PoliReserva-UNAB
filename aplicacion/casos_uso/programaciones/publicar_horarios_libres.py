"""Calcula y publica los huecos del cronograma como una sola programación."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import NamedTuple

from dominio.reglas.agenda import a_minutos, hhmm, restar_intervalos
from dominio.reglas.reservas import APERTURA, CIERRE, ZONA_PERU
from infraestructura.persistencia.programaciones_mysql import ErrorProgramacion, RepositorioProgramacionesMySQL


class PropuestaHorariosLibres(NamedTuple):
    id_periodo: int
    horarios: tuple[tuple[date, str, str], ...]


class PublicarHorariosLibres:
    def __init__(self, repositorio=None):
        self.repositorio = repositorio if repositorio is not None else RepositorioProgramacionesMySQL()

    def previsualizar(self, *, id_periodo, desde, hasta, inicio, fin, fines_de_semana=False):
        periodo = next((p for p in self.repositorio.listar_periodos() if p['id_periodo'] == id_periodo), None)
        if periodo is None:
            raise ErrorProgramacion('Selecciona un período académico activo.')
        try:
            desde, hasta = (date.fromisoformat(str(valor)) for valor in (desde, hasta))
        except ValueError as exc:
            raise ErrorProgramacion('Indica las fechas inicial y final.') from exc
        if not (date.fromisoformat(periodo['fecha_inicio']) <= desde <= hasta <=
                date.fromisoformat(periodo['fecha_fin'])):
            raise ErrorProgramacion('El rango debe estar dentro del período académico seleccionado.')

        apertura, cierre = a_minutos(inicio), a_minutos(fin)
        if apertura is None or cierre is None or not APERTURA <= apertura < cierre <= CIERRE:
            raise ErrorProgramacion('Indica una jornada válida entre las 07:00 y las 22:00.')

        ahora = datetime.now(ZONA_PERU)
        desde = max(desde, ahora.date())
        if desde > hasta:
            return PropuestaHorariosLibres(id_periodo, ())
        bloqueos = defaultdict(list)
        for dia, inicio, fin in self.repositorio.intervalos_para_publicacion(desde, hasta):
            bloqueos[dia].append((a_minutos(inicio), a_minutos(fin)))

        horarios = []
        for i in range((hasta - desde).days + 1):
            dia = desde + timedelta(days=i)
            if dia.weekday() >= 5 and not fines_de_semana:
                continue
            primera = apertura
            if dia == ahora.date():
                primera = max(apertura, ahora.hour * 60 + ahora.minute + 1)
            horarios.extend((dia, hhmm(a), hhmm(b))
                            for a, b in restar_intervalos(primera, cierre, bloqueos[dia]))
        return PropuestaHorariosLibres(id_periodo, tuple(horarios))

    def ejecutar(self, *, id_usuario_sesion, propuesta: PropuestaHorariosLibres):
        if not propuesta.horarios:
            raise ErrorProgramacion('No hay franjas pendientes de publicación.')
        return self.repositorio.guardar_programacion(
            actor=id_usuario_sesion, tipo='LIBRE', id_periodo=propuesta.id_periodo,
            nombre='Horarios libres del cronograma', descripcion=None, responsable=None, escuela=None,
            horarios=propuesta.horarios, solo_futuros=True,
        )
