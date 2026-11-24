# Presentacion/estudiante/solicitar_prestamo.py
"""Solicitud de implementos para estudiantes y docentes (solo interfaz NiceGUI)."""

import asyncio
from datetime import datetime

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import app, ui
from aplicacion.casos_uso.implementos.solicitar_prestamo import SolicitarPrestamo
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from dominio.reglas.implementos import agrupar_unidades, texto_buscable
from dominio.reglas.reservas import ZONA_PERU
from Presentacion.sesion import obtener_actor
from Presentacion.estudiante.layout_usuario import crear_marco_usuario
from Presentacion.componentes.filtros import campo_texto
from Presentacion.componentes.reserva_prestamo import SelectorReservaPrestamo
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina

AZUL = '#09234B'
AZUL_ACCION = '#164875'


def validar_fechas(recojo, devolucion):
    try:
        inicio = datetime.fromisoformat(str(recojo or ''))
        fin = datetime.fromisoformat(str(devolucion or ''))
    except ValueError:
        return 'Selecciona fecha y hora de recojo y devolución.'
    if inicio.tzinfo is not None or fin.tzinfo is not None:
        return 'Ingresa las horas de Perú.'
    if inicio <= datetime.now(ZONA_PERU).replace(tzinfo=None):
        return 'La fecha de recojo debe ser futura.'
    if fin <= inicio:
        return 'La devolución debe ser posterior al recojo.'
    return None


@ui.page('/usuario/solicitar-prestamo')
def pagina_solicitar_prestamo(request: Request, reserva: int | None = None):
    actor = obtener_actor(request)
    if actor is None:
        ui.navigate.to('/')
        return
    if not crear_marco_usuario('SOLICITAR IMPLEMENTOS'):
        return

    perfil = app.storage.user
    repo = RepositorioImplementosMySQL()
    try:
        stock = agrupar_unidades(i for i in repo.listar_implementos() if i['disponibilidad'] == 'Disponible')
        catalogo = [c['nombre_categoria'] for c in repo.listar_categorias()]
    except ErrorMySQL:
        stock, catalogo = {}, []
        ui.notify('No se pudo consultar la disponibilidad de implementos.', type='warning')
    disponibles = stock
    seleccion = {}
    guardando = False
    categorias = sorted(set(catalogo) | {c for c, _ in stock if c}, key=texto_buscable)

    def total_seleccionado():
        return sum(seleccion.values())

    def cambiar_cantidad(clave, cambio):
        actual = seleccion.get(clave, 0)
        nuevo = max(0, min(actual + cambio, disponibles.get(clave, 0)))
        if nuevo:
            seleccion[clave] = nuevo
        else:
            seleccion.pop(clave, None)
        mostrar_opciones.refresh()
        mostrar_resumen.refresh()

    with ui.column().classes('w-full max-w-[1200px] mx-auto px-4 md:px-6 py-4 gap-3'):
        titulo_pagina('SOLICITAR IMPLEMENTOS', 'sports_soccer', icono_px='24px')

        with tarjeta_seccion(padding='p-4'):
            ui.label('DATOS DEL SOLICITANTE').classes(f'text-sm font-bold text-[{AZUL}]')
            with ui.element('div').classes('grid grid-cols-1 md:grid-cols-3 gap-3 w-full'):
                for etiqueta, campo in (
                    ('Nombre', 'nombre'),
                    ('Código institucional', 'codigo_institucional'),
                    ('Escuela profesional', 'escuela'),
                ):
                    ui.input(etiqueta, value=str(perfil.get(campo) or '')) \
                        .props('outlined dense readonly').classes('w-full')

        with tarjeta_seccion(padding='p-4'):
            ui.label('SELECCIÓN DE IMPLEMENTOS').classes(f'text-sm font-bold text-[{AZUL}]')
            estado_stock = ui.label('Ingresa el recojo y la devolución para comprobar la disponibilidad.') \
                .classes('text-xs text-slate-600')

            with ui.element('div').classes('grid grid-cols-1 sm:grid-cols-2 gap-3 w-full'):
                categoria = ui.select(['Todas', *categorias], value='Todas', label='Categoría') \
                    .props('outlined dense options-dense').classes('w-full')
                buscar = ui.input('Buscar implemento', placeholder='Escribe el nombre del material') \
                    .props('outlined dense clearable').classes('w-full')

            @ui.refreshable
            def mostrar_opciones():
                consulta = texto_buscable(buscar.value).strip()
                filtrados = [
                    (clave, cantidad) for clave, cantidad in disponibles.items()
                    if (categoria.value == 'Todas' or clave[0] == categoria.value)
                    and consulta in texto_buscable(clave[1])
                ]
                filtrados.sort(key=lambda fila: (fila[0][0].casefold(), fila[0][1].casefold()))

                with ui.column().classes('w-full gap-2'):
                    if not filtrados:
                        ui.label('No hay implementos disponibles para mostrar.') \
                            .classes('text-sm text-slate-500 py-3')
                    for clave, cantidad in filtrados:
                        familia, nombre = clave
                        elegidos = seleccion.get(clave, 0)
                        with ui.row().classes(
                            'w-full items-center justify-between gap-3 px-3 py-2 '
                            'border border-slate-200 rounded-lg flex-wrap'
                        ):
                            with ui.column().classes('gap-0 flex-1 min-w-40'):
                                ui.label(nombre).classes('text-sm font-semibold text-[#09234B]')
                                ui.label(f'{familia} · {cantidad} disponibles' if familia
                                         else f'{cantidad} disponibles') \
                                    .classes('text-xs text-slate-500')
                            with ui.row().classes('items-center gap-2'):
                                btn_menos = ui.button(
                                    icon='remove', on_click=lambda k=clave: cambiar_cantidad(k, -1)
                                ).props('outline round').classes('text-[#164875]').tooltip(f'Quitar {nombre}')
                                if elegidos == 0:
                                    btn_menos.disable()
                                ui.label(str(elegidos)).classes('min-w-5 text-center font-semibold')
                                btn_mas = ui.button(
                                    icon='add', on_click=lambda k=clave: cambiar_cantidad(k, 1)
                                ).props('outline round').classes('text-[#164875]').tooltip(f'Añadir {nombre}')
                                if elegidos >= cantidad:
                                    btn_mas.disable()

            mostrar_opciones()
            categoria.on_value_change(mostrar_opciones.refresh)
            buscar.on_value_change(mostrar_opciones.refresh)

            ui.separator()

            @ui.refreshable
            def mostrar_resumen():
                with ui.column().classes('w-full gap-1'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('IMPLEMENTOS SELECCIONADOS').classes('text-xs font-bold text-[#09234B]')
                        ui.label(f'{total_seleccionado()} seleccionados') \
                            .classes('text-xs font-semibold text-[#164875]')
                    if not seleccion:
                        ui.label('Selecciona los materiales que necesitas.') \
                            .classes('text-xs text-slate-500')
                    else:
                        for (_, nombre), cantidad in sorted(seleccion.items()):
                            ui.label(f'{nombre} × {cantidad}').classes('text-sm text-slate-700')

            mostrar_resumen()

        with tarjeta_seccion(padding='p-4'):
            ui.label('DATOS DEL PRÉSTAMO').classes(f'text-sm font-bold text-[{AZUL}]')
            modalidad = SelectorReservaPrestamo(repo)
            modalidad.cargar(actor.id_usuario, reserva)
            with ui.element('div').classes('grid grid-cols-1 sm:grid-cols-2 gap-3 w-full'):
                recojo = campo_texto('Fecha y hora de recojo', tipo='datetime-local')
                devolucion = campo_texto('Devolución prevista', tipo='datetime-local')

            def actualizar_disponibilidad():
                nonlocal disponibles
                if obtener_actor(request) != actor:
                    return False
                if validar_fechas(recojo.value, devolucion.value):
                    disponibles = stock
                    estado_stock.set_text('Ingresa el recojo y la devolución para comprobar la disponibilidad.')
                    mostrar_opciones.refresh()
                    return False
                try:
                    disponibles = agrupar_unidades(repo.listar_disponibles(recojo.value, devolucion.value))
                except (ErrorMySQL, ValueError):
                    estado_stock.set_text('No se pudo comprobar la disponibilidad para esas fechas.')
                    return False
                anteriores = dict(seleccion)
                for clave, cantidad in anteriores.items():
                    disponible = min(cantidad, disponibles.get(clave, 0))
                    if disponible:
                        seleccion[clave] = disponible
                    else:
                        seleccion.pop(clave, None)
                estado_stock.set_text('Disponibilidad para el intervalo seleccionado.')
                if anteriores != seleccion:
                    estado_stock.set_text('Las cantidades se ajustaron a la disponibilidad de estas fechas.')
                mostrar_opciones.refresh()
                mostrar_resumen.refresh()
                return anteriores == seleccion

            recojo.on_value_change(lambda: actualizar_disponibilidad())
            devolucion.on_value_change(lambda: actualizar_disponibilidad())
            modalidad.conectar_fechas(recojo, devolucion)

            def solicitar():
                if guardando:
                    return
                if not seleccion:
                    ui.notify('Selecciona al menos un implemento.', type='warning')
                    return
                try:
                    id_reserva = modalidad.id_reserva()
                    motivo = modalidad.motivo_sin_reserva()
                except ValueError as exc:
                    ui.notify(str(exc), type='warning')
                    return
                error = validar_fechas(recojo.value, devolucion.value)
                if error:
                    ui.notify(error, type='warning')
                    return

                if not actualizar_disponibilidad():
                    ui.notify('Revisa las cantidades disponibles antes de confirmar.', type='warning')
                    return
                grupos = dict(seleccion)
                inicio, fin = recojo.value, devolucion.value

                async def confirmar():
                    nonlocal guardando
                    if guardando or not boton.enabled:
                        return
                    if obtener_actor(request) != actor:
                        ui.navigate.to('/')
                        return
                    boton.disable()
                    guardando = True
                    try:
                        await asyncio.to_thread(
                            SolicitarPrestamo(repo).ejecutar, id_usuario_sesion=actor.id_usuario,
                            grupos=grupos, inicio=inicio, fin=fin, id_reserva=id_reserva, observacion=motivo,
                        )
                    except (ErrorMySQL, ValueError) as exc:
                        guardando = False
                        if not boton.is_deleted:
                            ui.notify(str(exc) if isinstance(exc, ValueError) else
                                      'No se pudo registrar la solicitud.', type='warning')
                            boton.enable()
                            actualizar_disponibilidad()
                    else:
                        if not boton.is_deleted and obtener_actor(request) == actor:
                            ui.notify('Solicitud registrada.', type='positive')
                            ui.navigate.to('/usuario/mis-prestamos')

                with ui.dialog() as dialogo, ui.card().classes('w-full max-w-lg p-5 rounded-xl gap-3'):
                    ui.label('CONFIRMAR SOLICITUD').classes('text-lg font-bold text-[#09234B]')
                    ui.separator()
                    ui.label(str(perfil.get('nombre') or 'Solicitante')).classes('text-sm')
                    reserva_elegida = modalidad.elegida()
                    ui.label(reserva_elegida['codigo_reserva'] if reserva_elegida else 'Sin reserva').classes('text-sm')
                    if motivo:
                        ui.label('Motivo del préstamo sin reserva').classes('text-xs font-semibold text-slate-600')
                        ui.label(motivo).classes('text-sm whitespace-pre-wrap break-words w-full')
                    for (_, nombre), cantidad in sorted(seleccion.items()):
                        ui.label(f'{nombre} × {cantidad}').classes('text-sm')
                    ui.label(f'Recojo: {recojo.value}').classes('text-sm')
                    ui.label(f'Devolución prevista: {devolucion.value}').classes('text-sm')
                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Volver', on_click=dialogo.close).props('flat no-caps')
                        boton = ui.button('Confirmar solicitud', icon='send', on_click=confirmar).props('no-caps') \
                            .classes('bg-[#164875] text-white')
                dialogo.open()

            with ui.row().classes('w-full items-center justify-end gap-2 flex-wrap'):
                ui.button('Cancelar', icon='arrow_back',
                          on_click=lambda: ui.navigate.to('/usuario/inicio')) \
                    .props('flat no-caps').classes('text-[#164875]')
                ui.button('Solicitar préstamo', icon='assignment_turned_in', on_click=solicitar) \
                    .props('no-caps').classes('bg-[#164875] text-white font-semibold')
