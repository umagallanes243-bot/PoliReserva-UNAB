# Presentacion/estudiante/inicio_usuario.py
"""Inicio del portal para estudiantes y docentes. Solo presentación."""

from datetime import date, datetime
from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import app, ui
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL
from Presentacion.sesion import obtener_actor
from dominio.reglas.reservas import ZONA_PERU, acciones_reserva
from Presentacion.componentes.agenda import leyenda_agenda, pintar_miniagenda, tramos_agenda
from Presentacion.componentes.filtros import campo_texto
from Presentacion.estudiante.layout_usuario import crear_marco_usuario

AZUL = '#09234B'
AZUL_MEDIO = '#164875'


def boton_acceso(texto: str, icono: str, descripcion: str, ruta: str):
    with ui.card().classes(
        'w-full min-w-0 p-3 rounded-xl border border-slate-200 '
        'shadow-none gap-1 hover:border-blue-300 min-h-[90px] '
    ):
        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.icon(icono, size='24px').style(f'color:{AZUL_MEDIO}')
            ui.label(texto).classes('font-semibold text-sm text-[#09234B]')
        ui.label(descripcion).classes('text-xs text-slate-500 leading-snug')
        ui.button('Abrir', icon='arrow_forward',
                  on_click=lambda: ui.navigate.to(ruta)) \
            .props('flat dense no-caps').classes('self-end text-[#164875]')


def panel_personal(titulo: str, icono: str, campos: dict, boton: str, ruta: str):
    with ui.card().classes(
        'w-full min-w-0 p-4 rounded-xl border border-slate-200 shadow-none gap-3'
    ):
        with ui.row().classes('items-center gap-2'):
            ui.icon(icono, size='22px').style(f'color:{AZUL_MEDIO}')
            ui.label(titulo).classes('text-sm font-bold text-[#09234B]')
        with ui.element('div').classes('grid grid-cols-2 gap-2 w-full'):
            for campo, valor in campos.items():
                with ui.element('div').classes('rounded-lg bg-[#F3F5F8] p-3'):
                    ui.label(campo).classes('text-xs text-slate-500')
                    ui.label(str(valor) if valor is not None else '—').classes('text-lg font-semibold text-[#09234B]')
        ui.button(boton, icon='arrow_forward',
                  on_click=lambda: ui.navigate.to(ruta)) \
            .props('outline dense no-caps').classes('self-end text-[#164875]')


@ui.page('/usuario/inicio', response_timeout=15)
def pagina_inicio_usuario(request: Request):
    actor = obtener_actor(request)
    if actor is None:
        ui.navigate.to('/')
        return
    if not crear_marco_usuario('INICIO'):
        return

    nombre = str(app.storage.user.get('nombre') or 'Usuario').strip()
    hoy = datetime.now(ZONA_PERU).date()
    fecha_actual = hoy.strftime('%d/%m/%Y')
    resumen = dict.fromkeys(('Fecha de uso', 'Horario', 'Código', 'Estado'))
    prestamos = dict.fromkeys(('Solicitudes pendientes', 'Préstamos activos'))
    try:
        filas = RepositorioReservasMySQL().listar_por_usuario(actor.id_usuario, solo_activas=True)
        ahora = datetime.now(ZONA_PERU)
        vigentes = [r for r in filas if acciones_reserva(
            r['estado_reserva'], r['fecha_uso'], r['hora_inicio'], r['hora_fin'], ahora,
        ).vigente]
        resumen['Turnos vigentes'] = len(vigentes)
        if vigentes:
            r = min(vigentes, key=lambda fila: (fila['fecha_uso'], fila['hora_inicio']))
            resumen.update({'Fecha de uso': r['fecha_uso'],
                            'Horario': f"{r['hora_inicio']} – {r['hora_fin']}",
                            'Código': r['codigo_reserva'], 'Estado': r['estado_reserva']})
        estados = [p['nombre_estado'] for p in RepositorioImplementosMySQL().listar_prestamos(actor.id_usuario)]
        prestamos.update({'Solicitudes pendientes': estados.count('PENDIENTE'),
                          'Préstamos activos': estados.count('ENTREGADO')})
    except (ErrorMySQL, ValueError):
        ui.notify('Algunos datos del portal no se pudieron consultar.', type='warning')

    with ui.column().classes(
        'w-full max-w-[1440px] mx-auto px-4 sm:px-6 py-4 gap-4'
    ):
        with ui.row().classes('w-full justify-between items-center gap-2 flex-wrap'):
            with ui.column().classes('gap-0'):
                ui.label('INICIO').classes('text-xl font-bold text-[#09234B]')
                ui.label(f'Bienvenido, {nombre}').classes('text-sm text-slate-600')
            ui.label(fecha_actual).classes('text-xs text-slate-500')

        with ui.element('div').classes('w-full grid grid-cols-1 lg:grid-cols-2 gap-3'):
            panel_personal(
                'PRÓXIMO TURNO VIGENTE', 'event_available',
                resumen,
                'Ver mis reservas', '/usuario/mis-reservas',
            )
            panel_personal(
                'MIS PRÉSTAMOS', 'inventory_2',
                prestamos,
                'Ver mis préstamos', '/usuario/mis-prestamos',
            )

        # Parte inferior compacta: accesos a la izquierda, agenda diaria a la derecha.
        # Las columnas se apilan solo en pantallas estrechas.
        with ui.element('div').classes(
            'w-full grid grid-cols-1 lg:grid-cols-5 gap-3 items-stretch'
        ):
            # 40 %: accesos rápidos en sentido vertical.
            with ui.column().classes('w-full min-w-0 lg:col-span-2 gap-2'):
                with ui.row().classes('items-center gap-2 min-h-[26px]'):
                    ui.icon('bolt', size='20px').classes('text-blue-800')
                    ui.label('ACCESOS RÁPIDOS').classes(
                        'text-sm font-bold text-[#09234B]'
                    )

                boton_acceso(
                    'Ver calendario', 'calendar_month',
                    'Consultar la programación del polideportivo.',
                    '/usuario/calendario',
                )
                boton_acceso(
                    'Mis reservas', 'event_note',
                    'Consultar reservas y confirmar asistencia.',
                    '/usuario/mis-reservas',
                )
                boton_acceso(
                    'Solicitar implementos', 'sports_soccer',
                    'Consultar materiales y solicitar un préstamo.',
                    '/usuario/solicitar-prestamo',
                )

            # 60 %: miniagenda diaria; no es una barra única ni franjas prefijadas.
            with ui.card().classes(
                'w-full min-w-0 lg:col-span-3 p-3 rounded-xl '
                'border border-slate-200 shadow-none gap-2'
            ):
                with ui.row().classes(
                    'w-full items-center justify-between gap-2 flex-wrap'
                ):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('schedule', size='20px').style(
                            f'color:{AZUL_MEDIO}'
                        )
                        ui.label('DISPONIBILIDAD DIARIA').classes(
                            'text-sm font-bold text-[#09234B]'
                        )
                    ui.button(
                        'Ver calendario completo', icon='open_in_new',
                        on_click=lambda: ui.navigate.to(f'/usuario/calendario?dia={fecha_agenda.value or hoy.isoformat()}'),
                    ).props('flat dense no-caps').classes('text-[#164875]')

                with ui.row().classes('w-full items-center gap-2 flex-wrap'):
                    fecha_agenda = campo_texto('Fecha de disponibilidad', hoy.isoformat(), tipo='date',
                                               clases='w-56 max-w-full')
                    refrescar = ui.button(icon='refresh').props('flat round').tooltip('Actualizar disponibilidad')
                leyenda_agenda('libre', 'reservado', 'taller', 'evento', 'mantenimiento', 'no_disponible')

                @ui.refreshable
                def agenda_diaria():
                    try:
                        dia = date.fromisoformat(str(fecha_agenda.value))
                    except ValueError:
                        pintar_miniagenda([], 'Selecciona una fecha válida.')
                        return
                    try:
                        agenda = RepositorioProgramacionesMySQL().obtener_agenda(dia)
                    except (ErrorMySQL, ValueError):
                        pintar_miniagenda([], 'No se pudo consultar la programación.')
                        return
                    tramos = tramos_agenda(agenda, dia, datetime.now(ZONA_PERU))
                    pintar_miniagenda(tramos, 'No hay horarios publicados para esta fecha.')

                fecha_agenda.on_value_change(lambda: agenda_diaria.refresh())
                refrescar.on('click', lambda: agenda_diaria.refresh())

                def actualizar_agenda():
                    if obtener_actor(request) == actor:
                        agenda_diaria.refresh()

                agenda_diaria()
                ui.timer(60, actualizar_agenda, immediate=False)
