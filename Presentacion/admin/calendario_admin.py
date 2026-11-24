"""Calendario de la programación y los turnos del polideportivo."""

from calendar import Calendar
from collections import Counter
from datetime import date, datetime, timedelta

from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from dominio.reglas.periodos import MESES, limites_mes, sumar_meses
from dominio.reglas.reservas import ZONA_PERU, inicio_semana
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from Presentacion.componentes.agenda import (
    COLORES, DIAS_CORTOS, ETIQUETAS, LEYENDA_ADMIN, leyenda_agenda, pintar_semana, tramos_agenda,
)
from Presentacion.componentes.estilos import BOTON_PRIMARIO
from Presentacion.componentes.filtros import campo_texto
from Presentacion.componentes.tarjetas import tarjeta_seccion
from Presentacion.sesion import exigir_administrador


TIPOS_VISIBLES = {
    'todos': 'Todos los tipos', 'libre': 'Horarios libres', 'taller': 'Taller deportivo',
    'evento': 'Evento institucional', 'mantenimiento': 'Mantenimiento',
}
ICONOS_MES = {'reservado': 'event_available', 'taller': 'sports_basketball',
             'evento': 'event', 'mantenimiento': 'build'}


def filtrar_tramos(tramos, *, tipo, periodo, mostrar_reservas):
    """Filtra solo franjas ya calculadas con la ocupación completa."""
    visibles = []
    for tramo in tramos:
        if tramo.tipo == 'sin_programacion':
            visibles.append(tramo)
            continue
        if periodo is not None and tramo.id_periodo != periodo:
            continue
        if tramo.tipo == 'reservado':
            if mostrar_reservas:
                visibles.append(tramo)
        elif tipo in ('todos', tramo.tipo) or (tipo == 'libre' and tramo.tipo == 'no_disponible'):
            visibles.append(tramo)
    return visibles


def pintar_mes(mes, tramos, elegido, al_dia):
    filas = Calendar().monthdayscalendar(mes.year, mes.month)
    with ui.element('div').classes('w-full grid grid-cols-7 overflow-hidden rounded-lg border border-slate-200'):
        for rotulo in DIAS_CORTOS:
            ui.label(rotulo).classes('bg-slate-50 py-2 text-center text-xs font-semibold text-slate-600')
        for fila in filas:
            for numero in fila:
                if not numero:
                    ui.element('div').classes('min-h-[60px] border-t border-slate-100 bg-slate-50')
                    continue
                dia = mes.replace(day=numero)
                bloques = tramos[dia]
                conteos = Counter(t.tipo for t in bloques)
                resumen = [f'{ETIQUETAS[tipo]} ({conteos[tipo]})' for tipo in ICONOS_MES if conteos[tipo]]
                if conteos['libre']:
                    resumen.append('Horario disponible')
                if bloques and all(t.tipo == 'sin_programacion' for t in bloques):
                    resumen.append('Sin programación')
                etiqueta = f"{dia:%d/%m/%Y} · " + (' · '.join(resumen) or 'Sin bloques visibles')
                fondo = 'bg-blue-50' if dia == elegido else 'bg-white'
                celda = ui.element('button').props('type=button')
                celda.props['aria-label'] = etiqueta
                with celda.classes(
                    f'{fondo} min-h-[60px] border-t border-r border-slate-100 '
                    'hover:bg-blue-50 text-left px-1 sm:px-2 py-1 focus-visible:outline focus-visible:outline-2'
                ).on('click', lambda _, d=dia: al_dia(d)):
                    ui.label(str(numero)).classes('block font-semibold text-xs text-[#09234B] tabular-nums')
                    with ui.row().classes('gap-x-1 sm:gap-x-2 gap-y-0 leading-none'):
                        for tipo, icono in ICONOS_MES.items():
                            if conteos[tipo]:
                                with ui.row().classes('items-center no-wrap gap-0.5').style(f'color:{COLORES[tipo][2]}'):
                                    ui.icon(icono, size='14px')
                                    ui.label(str(conteos[tipo])).classes('text-[11px] font-semibold tabular-nums')
                        if not any(conteos[tipo] for tipo in ICONOS_MES) and conteos['libre']:
                            ui.icon('check', size='14px').style(f"color:{COLORES['libre'][2]}")
                    ui.tooltip(etiqueta)


def panel_calendario_admin(request, dia_inicial, catalogo, abrir_bloque, publicar, publicar_libres):
    repo = RepositorioProgramacionesMySQL()
    estado = {'rango': None, 'agendas': {}, 'error': ''}

    with tarjeta_seccion(padding='p-3', extra='min-w-0', gap='gap-2'):
        with ui.row().classes('w-full justify-between items-center gap-2 flex-wrap'):
            with ui.row().classes('items-center gap-1 flex-wrap'):
                modo = ui.toggle(['Semana', 'Mes'], value='Semana').props('unelevated no-caps')
                ui.button(icon='chevron_left', on_click=lambda: desplazar(-1)).props(
                    'flat round aria-label="Período anterior"'
                ).tooltip('Período anterior')
                intervalo = ui.label().classes('text-sm font-semibold text-[#09234B] text-center')
                ui.button(icon='chevron_right', on_click=lambda: desplazar(1)).props(
                    'flat round aria-label="Período siguiente"'
                ).tooltip('Período siguiente')
                ui.button('Hoy', on_click=lambda: elegir_dia(datetime.now(ZONA_PERU).date())).props('flat no-caps')
            with ui.row().classes('items-center gap-1 flex-wrap'):
                fecha = campo_texto('Fecha del calendario', dia_inicial.isoformat(), tipo='date', clases='w-40')
                ui.button(icon='refresh', on_click=lambda: cargar(forzar=True)).props(
                    'flat round aria-label="Actualizar calendario"'
                ).tooltip('Actualizar calendario')
                ui.button('Publicar', icon='add', on_click=lambda: publicar_fecha()) \
                    .props('unelevated no-caps').classes(BOTON_PRIMARIO)
        with ui.row().classes('w-full items-center gap-2 flex-wrap'):
            tipo = ui.select(TIPOS_VISIBLES, value='todos', label='Tipo de programación') \
                .props('outlined dense options-dense').classes('w-48 max-w-full')
            periodo = ui.select({p['id_periodo']: p['nombre_periodo'] for p in catalogo},
                                label='Período académico') \
                .props('outlined dense clearable').classes('w-52 max-w-full')
            reservas = ui.switch('Mostrar reservas', value=True).classes('text-sm')
            ui.button('Completar horarios libres', icon='event_available', on_click=lambda: abrir_lote()) \
                .props('outline no-caps').classes('text-[#164875] ml-auto')
        leyenda_agenda(*LEYENDA_ADMIN)

        @ui.refreshable
        def dibujar():
            if estado['error']:
                ui.label(estado['error']).classes('w-full bg-slate-50 rounded-lg py-6 text-center text-slate-700')
                return
            inicio, fin = estado['rango']
            dias = [inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)]
            ahora = datetime.now(ZONA_PERU)
            tramos = {
                dia: filtrar_tramos(tramos_agenda(
                    estado['agendas'].get(dia.isoformat()), dia, ahora, portal=False, mostrar_huecos=True,
                ), tipo=tipo.value, periodo=periodo.value, mostrar_reservas=reservas.value)
                for dia in dias
            }
            if modo.value == 'Mes':
                pintar_mes(inicio, tramos, fecha_elegida(), abrir_semana)
            else:
                pintar_semana(dias, tramos, fecha_elegida(), al_dia=elegir_dia,
                              al_tramo=lambda d, t: abrir_bloque(d, t, cargar_despues, periodo.value),
                              alto_visible='clamp(320px,55dvh,500px)')

        def fecha_elegida():
            return date.fromisoformat(fecha.value or '')

        def cargar(*, forzar=False):
            try:
                elegido = fecha_elegida()
                if modo.value == 'Semana':
                    inicio = inicio_semana(elegido)
                    fin = inicio + timedelta(days=6)
                    intervalo.set_text(f'{inicio:%d/%m} – {fin:%d/%m/%Y}')
                else:
                    inicio, fin = limites_mes(elegido)
                    intervalo.set_text(f'{MESES[elegido.month - 1].capitalize()} {elegido.year}')
            except (ValueError, OverflowError):
                estado['error'] = 'Selecciona una fecha válida.'
                dibujar.refresh()
                return
            if forzar or (inicio, fin) != estado['rango']:
                try:
                    exigir_administrador(request)
                    agendas = repo.obtener_agendas(inicio, fin)
                except (ErrorMySQL, ValueError):
                    estado.update(rango=None, agendas={}, error='No se pudo consultar el calendario.')
                else:
                    estado.update(rango=(inicio, fin), agendas=agendas, error='')
            elif estado['error']:
                estado['error'] = ''
            dibujar.refresh()

        def cargar_despues():
            cargar(forzar=True)

        def publicar_fecha():
            try:
                dia = fecha_elegida()
            except ValueError:
                ui.notify('Selecciona una fecha de publicación.', type='warning')
                return
            publicar(dia, cargar_despues, id_periodo=periodo.value)

        def abrir_lote():
            try:
                dia = fecha_elegida()
            except ValueError:
                ui.notify('Selecciona una fecha del calendario.', type='warning')
                return
            desde, hasta = estado['rango'] or (dia, dia)
            publicar_libres(desde, hasta, cargar_despues, id_periodo=periodo.value)

        def elegir_dia(dia):
            fecha.set_value(dia.isoformat())

        def desplazar(paso):
            try:
                dia = fecha_elegida()
                destino = dia + timedelta(weeks=paso) if modo.value == 'Semana' else sumar_meses(dia, paso)
            except (ValueError, OverflowError):
                ui.notify('Selecciona una fecha válida.', type='warning')
                return
            elegir_dia(destino)

        def abrir_semana(dia):
            elegir_dia(dia)
            modo.set_value('Semana')

        def refrescar_filtros():
            dibujar.refresh()

        for control in (fecha, modo):
            control.on_value_change(lambda _: cargar())
        for control in (tipo, periodo, reservas):
            control.on_value_change(refrescar_filtros)

        # Carga las filas una vez antes de dibujar. Los filtros de vista solo repintan.
        estado['error'] = 'Cargando calendario…'
        dibujar()
        cargar()

    return cargar_despues
