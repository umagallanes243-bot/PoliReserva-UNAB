# Presentacion/estudiante/mis_prestamos.py
"""Solicitudes e historial de préstamos del usuario (interfaz NiceGUI)."""

import asyncio
from datetime import date, datetime

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui
from aplicacion.casos_uso.implementos.cancelar_solicitud import CancelarSolicitud
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from Presentacion.sesion import obtener_actor
from Presentacion.estudiante.layout_usuario import crear_marco_usuario
from dominio.reglas.implementos import agrupar_unidades, nombre_tipo_implemento
from Presentacion.componentes.dialogos import filas_detalle
from Presentacion.componentes.reserva_prestamo import SelectorReservaPrestamo
from Presentacion.componentes.exportaciones import descargar_comprobante_prestamo
from Presentacion.componentes.filtros import filtros_historial
from Presentacion.componentes.tablas import COLORES_PRESTAMO, slot_badge_mapa, tabla_datos
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina

AZUL = '#09234B'
VIGENTES = {'PENDIENTE', 'ENTREGADO'}
ESTADOS = ['PENDIENTE', 'ENTREGADO', 'DEVUELTO', 'CANCELADO']


def texto_fecha(valor):
    if isinstance(valor, (date, datetime)):
        return valor.strftime('%d/%m/%Y %H:%M') if isinstance(valor, datetime) else valor.strftime('%d/%m/%Y')
    if not valor:
        return '—'
    return str(valor).replace('T', ' ')[:16]


def adaptar_prestamo(registro):
    estado = str(registro.get('nombre_estado') or registro.get('estado_prestamo') or '').upper().strip()
    cantidad = registro.get('total_implementos')
    return {
        'id_operacion': registro.get('id_operacion'),
        'numero': str(registro.get('id_operacion') or '—'),
        'fecha_solicitud': texto_fecha(registro.get('fecha_solicitud')),
        'recojo': texto_fecha(registro.get('fecha_inicio_prevista')),
        'entrega': texto_fecha(registro.get('fecha_entrega')),
        'devolucion': texto_fecha(registro.get('fecha_devolucion_prevista')),
        'cantidad': str(cantidad) if cantidad is not None else '—',
        'vinculo': registro.get('vinculo') or 'Sin reserva',
        'estado': estado,
    }


@ui.page('/usuario/mis-prestamos', response_timeout=15)
def pagina_mis_prestamos(request: Request):
    actor = obtener_actor(request)
    if actor is None:
        ui.navigate.to('/')
        return
    if not crear_marco_usuario('MIS PRÉSTAMOS'):
        return

    repo = RepositorioImplementosMySQL()
    try:
        prestamos = [adaptar_prestamo(p) for p in repo.listar_prestamos(actor.id_usuario)]
    except ErrorMySQL:
        prestamos = []
        ui.notify('No se pudieron consultar tus préstamos.', type='warning')
    seleccionado = {'fila': None}

    with ui.column().classes('w-full max-w-[1400px] mx-auto px-4 md:px-6 py-4 gap-3'):
        with ui.row().classes('w-full items-center justify-between gap-2 flex-wrap'):
            titulo_pagina('MIS PRÉSTAMOS', 'assignment_return', icono_px='24px')
            ui.button('Solicitar implementos', icon='add',
                      on_click=lambda: ui.navigate.to('/usuario/solicitar-prestamo')) \
                .props('no-caps').classes('bg-[#164875] text-white')

        with tarjeta_seccion(padding='p-4'):
            vista, buscar, estado = filtros_historial('Buscar préstamo o reserva', ESTADOS)

            columnas = [
                {'name': 'numero', 'label': 'N.º PRÉSTAMO', 'field': 'numero', 'align': 'left'},
                {'name': 'fecha_solicitud', 'label': 'SOLICITUD', 'field': 'fecha_solicitud', 'align': 'center'},
                {'name': 'cantidad', 'label': 'IMPLEMENTOS', 'field': 'cantidad', 'align': 'center'},
                {'name': 'recojo', 'label': 'RECOJO PREVISTO', 'field': 'recojo', 'align': 'center'},
                {'name': 'devolucion', 'label': 'DEVOLUCIÓN PREVISTA', 'field': 'devolucion', 'align': 'center'},
                {'name': 'vinculo', 'label': 'MODALIDAD / RESERVA', 'field': 'vinculo', 'align': 'center'},
                {'name': 'estado', 'label': 'ESTADO', 'field': 'estado', 'align': 'center'},
            ]
            tabla = tabla_datos(
                columnas, [], 'id_operacion', paginacion=8,
                sin_datos='No hay préstamos para mostrar',
                clases='w-full rounded-lg text-[#09234B]',
            )
            slot_badge_mapa(
                tabla, 'estado', COLORES_PRESTAMO,
                defecto='grey-7', clases='text-white px-3 py-1',
            )

            with ui.row().classes('w-full justify-end gap-2 flex-wrap'):
                btn_ver = ui.button('Ver detalle', icon='visibility') \
                    .props('outline no-caps').classes('text-[#164875]')
                btn_cancelar = ui.button('Cancelar solicitud', icon='cancel') \
                    .props('outline no-caps').classes('text-red-700')
                btn_pdf = ui.button('Descargar comprobante', icon='picture_as_pdf') \
                    .props('outline no-caps').classes('text-[#164875]')

    def actualizar_acciones():
        operacion = tabla.selected[0].get('id_operacion') if tabla.selected else None
        visible = any(p['id_operacion'] == operacion for p in tabla.rows)
        fila = seleccionado['fila'] = next((p for p in prestamos if visible and p['id_operacion'] == operacion), None)
        btn_ver.set_enabled(fila is not None)
        btn_pdf.set_enabled(fila is not None)
        btn_cancelar.set_visibility(vista.value == 'Vigentes')
        btn_cancelar.set_enabled(bool(fila and fila['estado'] == 'PENDIENTE' and vista.value == 'Vigentes'))

    def filtrar():
        texto = str(buscar.value or '').strip().casefold()
        es_vigente = vista.value == 'Vigentes'
        tabla.rows = [p for p in prestamos
                      if (p['estado'] in VIGENTES) == es_vigente
                      and (estado.value == 'Todos' or p['estado'] == estado.value)
                      and (texto in p['numero'].casefold() or texto in p['vinculo'].casefold())]
        tabla.selected.clear()
        tabla.update()
        actualizar_acciones()

    def consulta_seleccion():
        p = seleccionado['fila']
        if p is None or obtener_actor(request) != actor:
            return None
        try:
            registro = repo.obtener_prestamo(p['id_operacion'], id_usuario=actor.id_usuario)
            detalles = repo.detalle_prestamo(p['id_operacion'], id_usuario=actor.id_usuario) if registro else []
        except (ErrorMySQL, ValueError):
            ui.notify('No se pudo consultar el préstamo.', type='warning')
            return None
        if registro is None:
            ui.notify('El préstamo ya no está disponible.', type='warning')
            return None
        return registro, detalles

    def ver_detalle():
        consulta = consulta_seleccion()
        if consulta is None:
            return
        registro, detalles = consulta
        p = adaptar_prestamo(registro)
        with ui.dialog() as dlg, ui.card().classes('w-full max-w-xl p-5 gap-3 rounded-xl'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(f"PRÉSTAMO N.º {p['numero']}") \
                    .classes('text-lg font-bold text-[#09234B]')
                ui.button(icon='close', on_click=dlg.close).props('round flat dense')
            ui.separator()
            filas_detalle((
                ('Estado', p['estado']),
                ('Modalidad / reserva', SelectorReservaPrestamo.descripcion(registro)),
                ('Fecha de solicitud', p['fecha_solicitud']),
                ('Recojo previsto', p['recojo']),
                ('Entrega realizada', p['entrega']),
                ('Devolución prevista', p['devolucion']),
            ))
            ui.separator()
            ui.label('IMPLEMENTOS SOLICITADOS').classes('text-sm font-bold text-[#09234B]')
            for (categoria, nombre), cantidad in sorted(agrupar_unidades(detalles).items()):
                with ui.row().classes('w-full justify-between gap-2'):
                    ui.label(f'{nombre} · {categoria}').classes('text-sm')
                    ui.label(f'× {cantidad}').classes('text-sm font-semibold')
            if not detalles:
                ui.label('No hay implementos para mostrar.').classes('text-sm text-slate-500')
            efectivas = [d for d in detalles if d.get('movimiento') in ('ENTRADA', 'SALIDA')]
            if efectivas:
                ui.separator()
                ui.label('UNIDADES ENTREGADAS').classes('text-sm font-bold text-[#09234B]')
                for d in efectivas:
                    ui.label(f"{d['codigo_patrimonial']} · {nombre_tipo_implemento(d['nombre_implemento'])}") \
                        .classes('text-sm')
            ui.button('Cerrar', on_click=dlg.close).props('no-caps') \
                .classes('bg-[#164875] text-white self-end')
        dlg.open()

    def descargar():
        consulta = consulta_seleccion()
        if consulta is not None:
            descargar_comprobante_prestamo(*consulta)

    def cancelar_solicitud():
        p = seleccionado['fila']
        if not p or p['estado'] != 'PENDIENTE' or vista.value != 'Vigentes':
            return
        async def cancelar():
            if not boton.enabled:
                return
            if obtener_actor(request) != actor:
                ui.navigate.to('/')
                return
            boton.disable()
            try:
                await asyncio.to_thread(
                    CancelarSolicitud(repo).ejecutar, id_usuario_sesion=actor.id_usuario, operacion=p['id_operacion'],
                )
            except (ErrorMySQL, ValueError) as exc:
                if not boton.is_deleted:
                    ui.notify(str(exc) if isinstance(exc, ValueError) else
                              'No se pudo cancelar la solicitud.', type='warning')
                    boton.enable()
            else:
                if not boton.is_deleted and obtener_actor(request) == actor:
                    p['estado'] = 'CANCELADO'
                    dlg.close()
                    filtrar()
                    ui.notify('Solicitud cancelada.', type='positive')

        with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-5 gap-3 rounded-xl'):
            ui.label('CANCELAR SOLICITUD').classes('text-lg font-bold text-[#09234B]')
            ui.label(f"Préstamo N.º {p['numero']}").classes('text-sm')
            ui.label('¿Deseas cancelar esta solicitud pendiente?') \
                .classes('text-sm text-slate-600')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Volver', on_click=dlg.close).props('flat no-caps')
                boton = ui.button('Confirmar cancelación', on_click=cancelar).props('no-caps color=negative')
        dlg.open()

    def recargar():
        if obtener_actor(request) != actor:
            return
        try:
            actuales = [adaptar_prestamo(p) for p in repo.listar_prestamos(actor.id_usuario)]
        except ErrorMySQL:
            return
        if actuales != prestamos:
            prestamos[:] = actuales
            filtrar()

    ui.timer(60, recargar, immediate=False)
    btn_pdf.on('click', descargar)
    btn_ver.on('click', lambda _: ver_detalle())
    btn_cancelar.on('click', lambda _: cancelar_solicitud())
    tabla.on_select(actualizar_acciones)
    for control in (vista, buscar, estado):
        control.on_value_change(filtrar)
    filtrar()
