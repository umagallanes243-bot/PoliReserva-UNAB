"""Supervisión del polideportivo y acceso a la gestión operativa."""

from collections import Counter
from datetime import date, datetime, timedelta

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from aplicacion.reportes import datos_dashboard, datos_operativos_dashboard, tendencia_reservas
from dominio.reglas.agenda import TIPOS_ACTIVIDAD, intervalo_jornada
from dominio.reglas.periodos import PERIODOS, PERIODOS_REFERENCIA, fechas_de_consulta
from dominio.reglas.reservas import ESTADOS_RESERVA, ZONA_PERU
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from Presentacion.admin.layout_admin import crear_marco_admin
from Presentacion.componentes.agenda import COLORES, TIPOS, pintar_miniagenda, tramos_agenda
from Presentacion.componentes.estilos import AZUL_MEDIO
from Presentacion.componentes.filtros import campo_texto, fila_filtros
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina
from Presentacion.sesion import exigir_administrador


ESTILOS_ESTADO = {
    'RESERVADA': ('Reservadas', '#C26115'),
    'CONFIRMADA': ('Confirmadas', '#15803D'),
    'FINALIZADA': ('Finalizadas', '#2563EB'),
    'CANCELADA': ('Canceladas', '#64748B'),
    'INASISTENCIA': ('Inasistencias', '#B91C1C'),
}
NOMBRES_ACTIVIDADES = ('Talleres deportivos', 'Eventos institucionales', 'Mantenimientos')


def _horas(minutos):
    horas, resto = divmod(minutos, 60)
    return f'{horas} h {resto} min' if horas and resto else f'{resto} min' if resto else f'{horas} h'


def _metrica(titulo, icono, *, destacado=False):
    with tarjeta_seccion(padding='p-3', extra='min-w-0 items-start', gap='gap-1'):
        with ui.row().classes('items-center gap-1.5 no-wrap'):
            ui.icon(icono, size='18px').classes('text-[#164875]')
            ui.label(titulo).classes('text-sm font-semibold text-[#09234B]')
        color = 'text-[#164875]' if destacado else 'text-[#09234B]'
        valor = ui.label('—').classes(f'text-[30px] leading-none font-bold tabular-nums {color} py-1')
        subtitulo = ui.label().classes('text-xs font-medium text-slate-700')
        nota = ui.label().classes('text-xs text-slate-600')
        return valor, subtitulo, nota


def _conteos_estados(conteos):
    return {
        'aria': {'enabled': True},
        'tooltip': {'trigger': 'item', 'formatter': '{b}: {c} ({d}%)'},
        'series': [{
            'type': 'pie', 'radius': ['56%', '81%'], 'center': ['50%', '50%'],
            'label': {'show': False}, 'labelLine': {'show': False},
            'itemStyle': {'borderColor': '#FFFFFF', 'borderWidth': 2},
            'data': [{'name': ESTILOS_ESTADO[e][0], 'value': conteos[e],
                      'itemStyle': {'color': ESTILOS_ESTADO[e][1]}} for e in ESTADOS_RESERVA],
        }],
    }


def _opciones_tendencia(etiquetas, valores):
    return {
        'aria': {'enabled': True},
        'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
        'grid': {'left': 32, 'right': 16, 'top': 8, 'bottom': 26},
        'xAxis': {'type': 'category', 'data': etiquetas,
                  'axisLabel': {'hideOverlap': True, 'fontSize': 11, 'color': '#475569'},
                  'axisTick': {'show': False}, 'axisLine': {'lineStyle': {'color': '#CBD5E1'}}},
        'yAxis': {'type': 'value', 'minInterval': 1, 'axisLabel': {'color': '#475569'},
                  'splitLine': {'lineStyle': {'color': '#E2E8F0'}}},
        'series': [{'name': 'Reservas', 'type': 'bar', 'barMaxWidth': 28, 'data': valores,
                    'itemStyle': {'color': AZUL_MEDIO, 'borderRadius': [4, 4, 0, 0]}}],
    }


def _sin_reservas(error):
    mensaje = 'Indicador no disponible.' if error else 'No hay reservas en este período.'
    ui.label(mensaje).classes(
        'w-full min-h-[128px] flex items-center justify-center rounded-lg bg-slate-50 text-sm text-slate-600'
    )


def _alerta(texto, icono, destino, *, vencimiento=False):
    with ui.element('a').props(f'href="{destino}"').classes(
        'w-full flex items-center gap-2 px-1.5 py-2 min-h-10 rounded-md '
        'hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 text-[#09234B]'
    ):
        ui.icon(icono, size='16px').classes('text-red-700' if vencimiento else 'text-[#164875]')
        ui.label(texto).classes('flex-1 text-xs sm:text-sm font-medium leading-snug cursor-pointer')
        valor = ui.label('—').classes('text-sm font-bold tabular-nums cursor-pointer')
        ui.icon('chevron_right', size='16px').classes('text-slate-400')
        return valor


def _actividades_restantes(agenda, ahora):
    return sum(
        1 for bloque in (agenda or {}).get('ocupados', ())
        if bloque['tipo'] in TIPOS_ACTIVIDAD and (intervalo := intervalo_jornada(bloque['inicio'], bloque['fin']))
        and intervalo[1] > ahora.hour * 60 + ahora.minute
    )


@ui.page('/admin/dashboard')
def pagina_dashboard(request: Request):
    if not crear_marco_admin('INICIO'):
        return
    ui.query('.nicegui-content').style('min-height:0')
    programaciones = RepositorioProgramacionesMySQL()
    hoy = datetime.now(ZONA_PERU).date()
    try:
        catalogo = programaciones.listar_periodos()
    except ErrorMySQL:
        catalogo = []
        ui.notify('No se pudieron consultar los períodos académicos.', type='warning')

    consulta = {'filas': [], 'desde': None, 'hasta': None, 'error': False}
    agenda_actual = {'fecha': None, 'agenda': None, 'error': False}

    with ui.column().classes('dashboard-polideportivo w-full max-w-[1600px] mx-auto px-3 sm:px-5 py-3 gap-3'):
        with ui.row().classes('w-full justify-between items-center gap-x-4 gap-y-2 flex-wrap'):
            with ui.column().classes('gap-0'):
                titulo_pagina('Dashboard', 'space_dashboard', icono_px='22px')
                rango = ui.label().classes('text-xs text-slate-600')
            with fila_filtros(gap='gap-2').classes('max-w-full', remove='w-full'):
                periodo = ui.select(list(PERIODOS), value='Semana', label='Período estadístico') \
                    .props('outlined dense options-dense').classes('w-40 sm:w-44')
                referencia = campo_texto('Fecha de referencia', hoy.isoformat(), tipo='date', clases='w-36 sm:w-40')
                ciclos = {p['id_periodo']: p['nombre_periodo'] for p in catalogo}
                academico = ui.select(ciclos, value=next(iter(ciclos), None), label='Período académico') \
                    .props('outlined dense options-dense').classes('w-44')
                if not ciclos:
                    academico.disable()
                desde = campo_texto('Desde', (hoy - timedelta(days=6)).isoformat(), tipo='date', clases='w-36')
                hasta = campo_texto('Hasta', hoy.isoformat(), tipo='date', clases='w-36')
                ui.button(icon='refresh', on_click=lambda: actualizar_todo()).props(
                    'outline round aria-label="Actualizar dashboard"'
                ).tooltip('Actualizar dashboard')

        with ui.element('div').classes('indicadores-dashboard grid grid-cols-1 min-[380px]:grid-cols-2 xl:grid-cols-4 gap-3 w-full'):
            reservas = _metrica('Reservas del período', 'event_note', destacado=True)
            uso = _metrica('Utilización del polideportivo', 'timelapse')
            prestamos = _metrica('Préstamos de implementos', 'assignment')
            inventario = _metrica('Inventario actual', 'inventory_2')

        with ui.element('div').classes('graficos-dashboard grid grid-cols-1 lg:grid-cols-2 gap-3 w-full'):
            with tarjeta_seccion(extra='min-w-0', gap='gap-1'):
                ui.label('Reservas por estado').classes('text-sm font-semibold text-[#09234B]')

                @ui.refreshable
                def estados():
                    if not consulta['filas']:
                        _sin_reservas(consulta['error'])
                        return
                    conteos = Counter(f['estado_reserva'] for f in consulta['filas'])
                    with ui.element('div').classes('w-full grid grid-cols-[minmax(96px,1fr)_minmax(125px,1fr)] items-center'):
                        ui.echart(_conteos_estados(conteos)).classes('w-full min-w-0 h-[136px]')
                        with ui.column().classes('w-full gap-1 px-2 md:px-5'):
                            for estado in ESTADOS_RESERVA:
                                nombre, color = ESTILOS_ESTADO[estado]
                                with ui.row().classes('w-full items-center gap-2 no-wrap'):
                                    ui.icon('circle', size='10px').style(f'color:{color}')
                                    ui.label(nombre).classes('text-xs text-slate-700 flex-1')
                                    ui.label(str(conteos[estado])).classes('text-xs font-semibold tabular-nums')

                estados()

            with tarjeta_seccion(extra='min-w-0', gap='gap-1'):
                with ui.row().classes('w-full items-baseline justify-between gap-x-2 gap-y-0 flex-wrap'):
                    ui.label('Tendencia de reservas').classes('text-sm font-semibold text-[#09234B]')
                    ui.label('Todos los estados por fecha de uso').classes('text-xs text-slate-600')

                @ui.refreshable
                def tendencia():
                    if not consulta['filas']:
                        _sin_reservas(consulta['error'])
                        return
                    etiquetas, valores = tendencia_reservas(
                        consulta['filas'], consulta['desde'], consulta['hasta'], periodo.value,
                    )
                    ui.echart(_opciones_tendencia(etiquetas, valores)).classes('w-full min-w-0 h-[136px]')

                tendencia()

        with ui.element('div').classes(
            'operacion-dashboard grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-[1fr_0.78fr_1.24fr] gap-3 w-full'
        ):
            with tarjeta_seccion(extra='min-w-0', gap='gap-1'):
                ui.label('Pendientes de atención').classes('text-sm font-semibold text-[#09234B]')
                alertas = {
                    'pendientes': _alerta('Solicitudes de préstamo', 'pending_actions', '/admin/prestamos?estado=PENDIENTE'),
                    'por_devolver': _alerta('Unidades por devolver', 'assignment_return', '/admin/prestamos?estado=ENTREGADO'),
                    'vencidos': _alerta('Devoluciones vencidas', 'warning_amber', '/admin/prestamos?estado=VENCIDOS',
                                        vencimiento=True),
                    'por_confirmar': _alerta('Reservas por confirmar', 'fact_check', '/admin/reservas?filtro=asistencia'),
                    'actividades': _alerta('Actividades que quedan hoy', 'event', '/admin/actividades'),
                }

            with tarjeta_seccion(extra='min-w-0', gap='gap-1'):
                ui.label('Actividades del período').classes('text-sm font-semibold text-[#09234B]')
                conteos_actividades = {}
                for tipo, nombre in zip(TIPOS_ACTIVIDAD, NOMBRES_ACTIVIDADES):
                    with ui.row().classes('w-full items-center gap-2 min-h-10 no-wrap'):
                        ui.icon('circle', size='10px').style(f'color:{COLORES[TIPOS[tipo]][1]}')
                        ui.label(nombre).classes('flex-1 text-sm text-slate-700')
                        conteos_actividades[tipo] = ui.label('—').classes('text-sm font-bold tabular-nums text-[#09234B]')
                ui.link('Ver reportes de actividades', '/admin/reportes?modulo=Programaciones') \
                    .classes('text-xs font-medium text-[#164875] mt-1')

            with tarjeta_seccion(extra='min-w-0', gap='gap-2'):
                with ui.row().classes('w-full items-center justify-between gap-1 flex-wrap'):
                    ui.label('Agenda diaria').classes('text-sm font-semibold text-[#09234B]')
                    fecha_agenda = campo_texto('Fecha de la agenda', hoy.isoformat(), tipo='date', clases='w-36')
                    ui.button('Hoy', on_click=lambda: fecha_agenda.set_value(
                        datetime.now(ZONA_PERU).date().isoformat(),
                    )).props('flat dense no-caps').classes('text-[#164875]')
                espacio_agenda = ui.column().classes('w-full gap-1')
                ui.button('Ver calendario completo', icon='open_in_new', on_click=lambda: ui.navigate.to(
                    f'/admin/actividades?dia={fecha_agenda.value or hoy.isoformat()}',
                )).props('flat dense no-caps').classes('text-[#164875] self-start')

        def actualizar_estadisticas():
            try:
                inicio, fin = fechas_de_consulta(periodo.value, referencia.value, desde.value, hasta.value,
                                                academico.value, catalogo)
                exigir_administrador(request)
                filas, estadisticas, actividades, solicitudes = datos_dashboard(inicio, fin, datetime.now(ZONA_PERU))
            except (ErrorMySQL, ValueError) as exc:
                rango.set_text('No se pudieron consultar las estadísticas.' if isinstance(exc, ErrorMySQL)
                               else 'Revisa las fechas del período seleccionado.')
                consulta.update(filas=[], desde=None, hasta=None, error=True)
                for valor, subtitulo, nota in (reservas, uso, prestamos):
                    valor.set_text('—')
                    subtitulo.set_text('')
                    nota.set_text('')
                for etiqueta in conteos_actividades.values():
                    etiqueta.set_text('—')
            else:
                rango.set_text(f'{inicio:%d/%m/%Y} – {fin:%d/%m/%Y}' if inicio and fin else 'Todo el historial')
                consulta.update(filas=filas, desde=inicio, hasta=fin, error=False)
                reservas[0].set_text(str(estadisticas['total']))
                reservas[1].set_text(f"{estadisticas['vigentes']} vigentes · {estadisticas['usuarios']} titulares")
                ocupacion = estadisticas['ocupacion']
                uso[0].set_text('—' if ocupacion is None else f'{ocupacion:g} %')
                uso[1].set_text(f"{_horas(estadisticas['minutos_utilizados'])} utilizadas · "
                                f"{_horas(estadisticas['minutos_habilitados'])} habilitadas")
                uso[2].set_text(f"{_horas(estadisticas['minutos_futuros'])} reservadas a futuro")
                prestamos[0].set_text(str(solicitudes['total']))
                prestamos[1].set_text(f"{solicitudes['pendientes']} pendientes del período")
                prestamos[2].set_text(f"{solicitudes['con_reserva']} con reserva · {solicitudes['sin_reserva']} sin reserva · "
                                      f"{solicitudes['reservas_con_prestamo']} reservas vinculadas")
                for tipo, etiqueta in conteos_actividades.items():
                    etiqueta.set_text(str(actividades.get(tipo, 0)))
            estados.refresh()
            tendencia.refresh()

        def dibujar_agenda():
            espacio_agenda.clear()
            with espacio_agenda:
                try:
                    dia = date.fromisoformat(str(fecha_agenda.value))
                    if dia == agenda_actual['fecha']:
                        if agenda_actual['error']:
                            pintar_miniagenda([], 'No se pudo consultar la agenda diaria.', compacto=True)
                            return
                        agenda = agenda_actual['agenda']
                    else:
                        exigir_administrador(request)
                        agenda = programaciones.obtener_agenda(dia)
                except (ErrorMySQL, ValueError):
                    pintar_miniagenda([], 'No se pudo consultar la agenda diaria.', compacto=True)
                    return
                ahora = datetime.now(ZONA_PERU)
                tramos = tramos_agenda(agenda, dia, ahora, portal=False, mostrar_huecos=True) if agenda else []
                pintar_miniagenda(tramos, 'Sin horarios publicados para esta fecha.',
                                  alto_visible=142, px_hora=25, compacto=True)
                if not agenda:
                    ui.link('Publicar desde Actividades', f'/admin/actividades?dia={dia.isoformat()}') \
                        .classes('text-xs text-[#164875]')

        def actualizar_operacion():
            ahora = datetime.now(ZONA_PERU)
            try:
                exigir_administrador(request)
                unidades, pendientes = datos_operativos_dashboard(ahora)
            except (ErrorMySQL, ValueError):
                unidades, pendientes = None, {}
            if unidades is None:
                inventario[0].set_text('—')
                inventario[1].set_text('No se pudo consultar el inventario.')
                inventario[2].set_text('')
            else:
                inventario[0].set_text(f"{unidades['disponibles']} / {unidades['total']}")
                inventario[1].set_text('Unidades disponibles del total activo')
                detalle = f"{unidades['prestadas']} prestadas"
                if unidades['no_habilitadas']:
                    detalle += f" · {unidades['no_habilitadas']} no habilitadas"
                inventario[2].set_text(detalle)
            try:
                exigir_administrador(request)
                agenda = programaciones.obtener_agenda(ahora.date())
            except (ErrorMySQL, ValueError):
                agenda_actual.update(fecha=ahora.date(), agenda=None, error=True)
            else:
                agenda_actual.update(fecha=ahora.date(), agenda=agenda, error=False)
                pendientes['actividades'] = _actividades_restantes(agenda, ahora)
            for clave, etiqueta in alertas.items():
                etiqueta.set_text(str(pendientes.get(clave, '—')))

        def ajustar_periodo():
            referencia.set_visibility(periodo.value in PERIODOS_REFERENCIA)
            academico.set_visibility(periodo.value == 'Período académico')
            desde.set_visibility(periodo.value == 'Personalizado')
            hasta.set_visibility(periodo.value == 'Personalizado')
            actualizar_estadisticas()

        def actualizar_todo():
            actualizar_operacion()
            dibujar_agenda()
            ajustar_periodo()

        periodo.on_value_change(ajustar_periodo)
        for control in (referencia, academico, desde, hasta):
            control.on_value_change(actualizar_estadisticas)
        fecha_agenda.on_value_change(dibujar_agenda)
        actualizar_todo()
