# Presentacion/estudiante/resumen_reserva.py
"""Resumen de una reserva efectivamente registrada. No crea reservas."""

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import app, ui
from infraestructura.persistencia.reservas_mysql import ErrorReserva, RepositorioReservasMySQL
from Presentacion.sesion import obtener_actor
from Presentacion.estudiante.layout_usuario import crear_marco_usuario
from Presentacion.componentes.exportaciones import descargar_comprobante
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina


def texto(valor):
    return str(valor).strip() if valor not in (None, '') else '—'


@ui.page('/usuario/resumen-reserva', response_timeout=15)
def pagina_resumen_reserva(request: Request):
    actor = obtener_actor(request)
    if actor is None:
        ui.navigate.to('/')
        return
    if not crear_marco_usuario(''):
        return

    # Solo debe establecerse desde el servidor, DESPUÉS del guardado exitoso.
    reserva = app.storage.user.get('ultima_reserva')
    reserva = reserva if isinstance(reserva, dict) else {}
    codigo = reserva.get('codigo_reserva')
    try:
        reserva = (RepositorioReservasMySQL().obtener_por_codigo(codigo, id_usuario=actor.id_usuario)
                   if codigo else None) or {}
    except (ErrorMySQL, ErrorReserva):
        ui.notify('No se pudo cargar el resumen de la reserva.', type='warning')
        reserva = {}
    codigo = reserva.get('codigo_reserva')

    def dato(etiqueta, valor):
        with ui.row().classes('w-full items-center justify-between gap-3 py-1'):
            ui.label(etiqueta).classes('text-xs text-slate-500')
            ui.label(texto(valor)).classes('text-sm font-semibold text-[#09234B] text-right')

    with ui.column().classes('w-full max-w-[850px] mx-auto px-4 py-5 gap-3'):
        titulo_pagina('RESUMEN DE RESERVA', 'receipt_long', icono_px='25px')

        with tarjeta_seccion(padding='p-5'):
            with ui.row().classes('w-full items-center justify-between gap-2'):
                ui.label('CÓDIGO DE RESERVA').classes('text-xs font-bold text-slate-500')
                if codigo:
                    ui.badge(reserva['estado_reserva'], color='orange-7').classes('font-bold')
            ui.label(codigo or '—').classes('text-2xl font-bold text-[#164875]')
            ui.separator()

            with ui.element('div').classes('grid grid-cols-1 sm:grid-cols-2 gap-4 w-full'):
                with ui.column().classes('w-full gap-1'):
                    ui.label('SOLICITANTE').classes('text-xs font-bold text-[#164875]')
                    dato('Nombre', reserva.get('solicitante') or app.storage.user.get('nombre'))
                    dato('Código institucional', reserva.get('codigo_institucional') or app.storage.user.get('codigo_institucional'))
                    dato('Escuela', reserva.get('escuela') or app.storage.user.get('escuela'))

                with ui.column().classes('w-full gap-1'):
                    ui.label('HORARIO RESERVADO').classes('text-xs font-bold text-[#164875]')
                    dato('Fecha de uso', reserva.get('fecha_uso'))
                    dato('Hora inicial', reserva.get('hora_inicio'))
                    dato('Hora final', reserva.get('hora_fin'))

            ui.separator()
            if reserva.get('estado_reserva') == 'RESERVADA':
                ui.label('Confirma tu asistencia durante los primeros 15 minutos del turno desde Mis reservas.') \
                    .classes('text-xs text-slate-600')

            with ui.row().classes('w-full justify-end gap-2 flex-wrap'):
                ui.button('Volver al calendario', icon='calendar_month',
                          on_click=lambda: ui.navigate.to('/usuario/calendario')).props(
                    'outline no-caps').classes('text-[#164875]')

                def comprobar_y_descargar():
                    if not codigo or obtener_actor(request) != actor:
                        return
                    try:
                        vigente = RepositorioReservasMySQL().obtener_por_codigo(codigo, id_usuario=actor.id_usuario)
                    except (ErrorMySQL, ErrorReserva):
                        ui.notify('No se pudo obtener el comprobante.', type='warning')
                        return
                    if vigente:
                        descargar_comprobante(vigente)

                ui.button('Descargar comprobante', icon='picture_as_pdf', on_click=comprobar_y_descargar).props(
                    'outline no-caps').classes('text-[#164875]').set_enabled(bool(codigo))

                ui.button('Ir a mis reservas', icon='arrow_forward',
                          on_click=lambda: ui.navigate.to('/usuario/mis-reservas')).props(
                    'no-caps').classes('bg-[#164875] text-white')
