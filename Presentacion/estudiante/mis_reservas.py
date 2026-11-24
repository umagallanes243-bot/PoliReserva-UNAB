# Presentacion/estudiante/mis_reservas.py
"""Consulta y gestión de las reservas propias."""

import asyncio
from datetime import datetime

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from aplicacion.casos_uso.reservas.cancelar_reserva import CancelarReserva
from aplicacion.casos_uso.reservas.confirmar_reserva import ConfirmarReserva
from dominio.reglas.implementos import fechas_sugeridas_prestamo, reserva_admite_prestamo
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from infraestructura.persistencia.reservas_mysql import ErrorReserva, RepositorioReservasMySQL
from Presentacion.sesion import obtener_actor
from dominio.reglas.reservas import TOLERANCIA_ASISTENCIA, ZONA_PERU, acciones_reserva
from Presentacion.estudiante.layout_usuario import crear_marco_usuario
from Presentacion.componentes.dialogos import filas_detalle
from Presentacion.componentes.filtros import filtros_historial
from Presentacion.componentes.tablas import COLORES_RESERVA, slot_badge_mapa, tabla_datos
from Presentacion.componentes.exportaciones import descargar_comprobante
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina


ESTADOS = {'RESERVADA', 'CONFIRMADA', 'FINALIZADA', 'CANCELADA', 'INASISTENCIA'}


def vista_reserva(registro):
    """Adapta los nombres de BD a columnas de la tabla."""
    estado = str(registro.get('nombre_estado') or registro.get('estado_reserva') or '').upper()
    inicio = str(registro.get('hora_inicio') or '')[:5]
    fin = str(registro.get('hora_fin') or '')[:5]
    fecha = registro.get('fecha_uso')
    return {
        'id_reserva': registro.get('id_reserva'),
        'codigo': str(registro.get('codigo_reserva') or ''),
        'fecha': str(fecha or '')[:10],
        'horario': f'{inicio} – {fin}' if inicio and fin else '—',
        'inicio': inicio,
        'fin': fin,
        'estado': estado,
    }


def acciones_fila(fila, ahora):
    return acciones_reserva(fila['estado'], fila['fecha'], fila['inicio'], fila['fin'], ahora)


@ui.page('/usuario/mis-reservas', response_timeout=15)
def pagina_mis_reservas(request: Request):
    actor = obtener_actor(request)
    if actor is None:
        ui.navigate.to('/')
        return
    if not crear_marco_usuario('MIS RESERVAS'):
        return

    repo = RepositorioReservasMySQL()
    try:
        filas = [vista_reserva(r) for r in repo.listar_por_usuario(actor.id_usuario)]
    except (ErrorMySQL, ErrorReserva):
        ui.notify('No se pudieron consultar tus reservas.', type='warning')
        filas = []
    guardando = False
    seleccion = {'fila': None}

    with ui.column().classes('w-full max-w-[1500px] mx-auto px-3 sm:px-5 py-4 gap-3'):
        with ui.row().classes('w-full items-center justify-between gap-2 flex-wrap'):
            titulo_pagina('MIS RESERVAS', 'event_note', icono_px='23px')
            ui.button('Consultar disponibilidad', icon='calendar_month',
                      on_click=lambda: ui.navigate.to('/usuario/calendario')) \
                .props('no-caps').classes('bg-[#164875] text-white')

        with tarjeta_seccion(padding='p-3 sm:p-4'):
            vista, buscar, estado_filtro = filtros_historial(
                'Buscar por código de reserva', sorted(ESTADOS)
            )

            columnas = [
                {'name': 'codigo', 'label': 'CÓDIGO', 'field': 'codigo', 'align': 'left'},
                {'name': 'fecha', 'label': 'FECHA DE USO', 'field': 'fecha', 'align': 'center'},
                {'name': 'horario', 'label': 'HORARIO', 'field': 'horario', 'align': 'center'},
                {'name': 'estado', 'label': 'ESTADO', 'field': 'estado', 'align': 'center'},
            ]
            tabla = tabla_datos(columnas, [], 'id_reserva', paginacion=8,
                                clases='w-full rounded-lg text-[#09234B]')

            slot_badge_mapa(
                tabla, 'estado', COLORES_RESERVA,
                defecto='grey-7', clases='px-3 py-1 text-white',
            )

            with ui.row().classes('w-full items-center justify-end gap-2 flex-wrap'):
                btn_consultar = ui.button('Ver detalle', icon='visibility') \
                    .props('outline no-caps').classes('text-[#164875]')
                btn_confirmar = ui.button('Confirmar asistencia', icon='check_circle') \
                    .props('no-caps').classes('bg-[#16A34A] text-white')
                btn_cancelar = ui.button('Cancelar reserva', icon='cancel') \
                    .props('outline no-caps').classes('text-red-700')
                btn_implementos = ui.button('Solicitar implementos', icon='sports_soccer',
                                             on_click=lambda: solicitar_implementos()) \
                    .props('outline no-caps').classes('text-[#164875]')
                btn_pdf = ui.button('Descargar comprobante', icon='picture_as_pdf') \
                    .props('outline no-caps').classes('text-[#164875]')
            aviso_asistencia = ui.label().classes('text-xs text-slate-600 self-end')

        def admite_prestamo(fila):
            if not fila or not fila['id_reserva'] or not fila['inicio'] or not fila['fin']:
                return False
            ahora = datetime.now(ZONA_PERU).replace(tzinfo=None)
            reserva = {'fecha_uso': fila['fecha'], 'hora_inicio': fila['inicio'],
                       'hora_fin': fila['fin'], 'estado_reserva': fila['estado']}
            if not reserva_admite_prestamo(reserva, ahora):
                return False
            inicio, fin = fechas_sugeridas_prestamo(reserva, ahora)
            return inicio < fin

        def solicitar_implementos():
            fila = seleccion['fila']
            if obtener_actor(request) == actor and admite_prestamo(fila):
                ui.navigate.to(f"/usuario/solicitar-prestamo?reserva={fila['id_reserva']}")

        def mostrar_detalle():
            r = seleccion['fila']
            if r is None or obtener_actor(request) != actor:
                return
            try:
                prestamos = RepositorioImplementosMySQL().listar_prestamos(
                    actor.id_usuario, id_reserva=r['id_reserva'],
                )
            except (ErrorMySQL, ValueError):
                prestamos = None
            with ui.dialog() as dialogo, ui.card().classes('w-full max-w-md p-5 gap-3'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('receipt_long', size='22px').classes('text-[#164875]')
                    ui.label('DETALLE DE RESERVA').classes('text-base font-bold text-[#09234B]')
                ui.separator()
                filas_detalle((
                    ('Código', r['codigo']), ('Fecha de uso', r['fecha']),
                    ('Horario', r['horario']), ('Estado', r['estado']),
                ))
                ui.label('Préstamos asociados').classes('text-sm font-semibold text-[#09234B]')
                if prestamos is None:
                    ui.label('No se pudieron consultar los préstamos.').classes('text-sm text-slate-600')
                elif not prestamos:
                    ui.label('Sin préstamos asociados.').classes('text-sm text-slate-600')
                else:
                    for p in prestamos:
                        ui.label(f"N.º {p['id_operacion']} · {p['nombre_estado']} · {p['implementos']} unidades")
                ui.button('Cerrar', on_click=dialogo.close).props('no-caps') \
                    .classes('bg-[#164875] text-white self-end')
            dialogo.open()

        def actualizar_acciones():
            elegida = tabla.selected[0].get('id_reserva') if tabla.selected else None
            fila = seleccion['fila'] = next((r for r in tabla.rows if r['id_reserva'] == elegida), None)
            vigente = vista.value == 'Vigentes'
            btn_consultar.set_enabled(fila is not None)
            btn_pdf.set_enabled(fila is not None)
            btn_implementos.set_visibility(admite_prestamo(fila))
            btn_confirmar.set_visibility(vigente)
            btn_cancelar.set_visibility(vigente)
            acciones = acciones_fila(fila, datetime.now(ZONA_PERU)) if fila else None
            btn_confirmar.set_enabled(bool(vigente and acciones and acciones.confirmar and not guardando))
            btn_cancelar.set_enabled(bool(vigente and acciones and acciones.cancelar and not guardando))
            texto = ''
            if vigente and acciones and (acciones.cancelar or acciones.confirmar):
                inicio = datetime.fromisoformat(f"{fila['fecha']}T{fila['inicio']}")
                limite = (inicio + TOLERANCIA_ASISTENCIA).strftime('%H:%M')
                texto = (f'Puedes confirmar la asistencia hasta las {limite}.' if acciones.confirmar
                         else f'Podrás confirmar de {inicio:%H:%M} a {limite} el día del turno.')
            aviso_asistencia.set_text(texto)
            aviso_asistencia.set_visibility(bool(texto))

        def confirmar_accion(caso, titulo, accion):
            fila = seleccion['fila']
            if fila is None or vista.value != 'Vigentes' or not getattr(
                acciones_fila(fila, datetime.now(ZONA_PERU)), accion
            ):
                actualizar_acciones()
                return

            async def aplicar():
                nonlocal filas, guardando
                dialogo.close()
                if guardando:
                    return
                if obtener_actor(request) != actor:
                    ui.navigate.to('/')
                    return
                guardando = True
                actualizar_acciones()
                try:
                    reserva = await asyncio.to_thread(
                        caso.ejecutar, id_usuario_sesion=actor.id_usuario, codigo_reserva=fila['codigo'],
                    )
                except (ErrorReserva, ErrorMySQL) as exc:
                    if not tabla.is_deleted:
                        ui.notify(str(exc) if isinstance(exc, ErrorReserva) else
                                  'No se pudo actualizar la reserva.', type='warning')
                else:
                    if not tabla.is_deleted and obtener_actor(request) == actor:
                        filas = [vista_reserva(reserva) if r['codigo'] == fila['codigo'] else r for r in filas]
                        filtrar()
                        ui.notify('Reserva actualizada.', type='positive')
                finally:
                    guardando = False
                    if not tabla.is_deleted:
                        actualizar_acciones()

            with ui.dialog() as dialogo, ui.card().classes('w-full max-w-md p-5 gap-3'):
                ui.label(titulo).classes('text-base font-bold text-[#09234B]')
                ui.label(fila['codigo'])
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Volver', on_click=dialogo.close).props('flat no-caps')
                    ui.button('Confirmar', on_click=aplicar).props('no-caps')
            dialogo.open()

        def filtrar(*, conservar_seleccion=False):
            actual = seleccion['fila'] if conservar_seleccion else None
            ahora = datetime.now(ZONA_PERU)
            texto = str(buscar.value or '').strip().lower()
            estado = estado_filtro.value
            es_vigente = vista.value == 'Vigentes'
            tabla.rows = [r for r in filas
                          if acciones_fila(r, ahora).vigente == es_vigente
                          and (estado == 'Todos' or r['estado'] == estado)
                          and texto in r['codigo'].lower()]
            tabla.selected = [r for r in tabla.rows if actual and r['id_reserva'] == actual['id_reserva']]
            tabla.update()
            actualizar_acciones()

        def recargar():
            nonlocal filas
            if guardando or obtener_actor(request) != actor:
                return
            try:
                actualizadas = [vista_reserva(r) for r in repo.listar_por_usuario(actor.id_usuario)]
            except (ErrorMySQL, ErrorReserva):
                return
            if actualizadas != filas:
                filas = actualizadas
                filtrar(conservar_seleccion=True)

        def descargar():
            fila = seleccion['fila']
            if fila is None or obtener_actor(request) != actor:
                return
            try:
                reserva = repo.obtener_por_codigo(fila['codigo'], id_usuario=actor.id_usuario)
            except (ErrorMySQL, ErrorReserva):
                ui.notify('No se pudo obtener el comprobante.', type='warning')
                return
            if reserva:
                descargar_comprobante(reserva)

        btn_pdf.on('click', descargar)
        btn_consultar.on('click', lambda _: mostrar_detalle())
        btn_confirmar.on('click', lambda: confirmar_accion(ConfirmarReserva(repo), 'Confirmar asistencia', 'confirmar'))
        btn_cancelar.on('click', lambda: confirmar_accion(CancelarReserva(repo), 'Cancelar reserva', 'cancelar'))
        ui.timer(15, lambda: filtrar(conservar_seleccion=True), immediate=False)
        ui.timer(60, recargar, immediate=False)
        tabla.on_select(actualizar_acciones)
        for control in (vista, buscar, estado_filtro):
            control.on_value_change(filtrar)
        filtrar()
