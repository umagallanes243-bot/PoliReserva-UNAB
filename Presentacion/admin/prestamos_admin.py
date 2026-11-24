# Presentacion/admin/prestamos_admin.py
# Interfaz de solicitudes, entregas y devoluciones de implementos — PoliReserva V9.

from datetime import datetime, timedelta
from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui
from aplicacion.casos_uso.implementos.cancelar_solicitud import CancelarSolicitud
from aplicacion.casos_uso.implementos.devolver_prestamo import DevolverPrestamo
from aplicacion.casos_uso.implementos.entregar_prestamo import EntregarPrestamo
from aplicacion.casos_uso.implementos.solicitar_prestamo import SolicitarPrestamo
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from infraestructura.persistencia.usuarios_mysql import RepositorioUsuariosMySQL
from Presentacion.admin.layout_admin import crear_marco_admin, guardar_como_admin
from Presentacion.componentes.estilos import BOTON_PRIMARIO
from Presentacion.componentes.filtros import (boton_limpiar_filtros, campo_texto,
                                             fila_filtros)
from Presentacion.componentes.reserva_prestamo import CON_RESERVA, SIN_RESERVA, SelectorReservaPrestamo
from Presentacion.componentes.tablas import COLORES_PRESTAMO, slot_badge_mapa, tabla_datos
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina
from Presentacion.sesion import exigir_administrador
from dominio.reglas.implementos import agrupar_unidades, devolucion_vencida, nombre_tipo_implemento, texto_buscable
from dominio.reglas.reservas import ZONA_PERU

AZUL = '#09234B'
ESTADOS = ['PENDIENTE', 'ENTREGADO', 'DEVUELTO', 'CANCELADO']
VENCIDOS = 'Devoluciones vencidas'

COLUMNAS = [
    {'name': 'id_operacion', 'label': 'N.º OPERACIÓN', 'field': 'id_operacion', 'align': 'center'},
    {'name': 'solicitante', 'label': 'SOLICITANTE', 'field': 'solicitante', 'align': 'left'},
    {'name': 'codigo_institucional', 'label': 'CÓDIGO INSTITUCIONAL', 'field': 'codigo_institucional', 'align': 'center'},
    {'name': 'fecha_solicitud', 'label': 'SOLICITUD', 'field': 'fecha_solicitud', 'align': 'center'},
    {'name': 'fecha_inicio_prevista', 'label': 'ENTREGA PREVISTA', 'field': 'fecha_inicio_prevista', 'align': 'center'},
    {'name': 'fecha_devolucion_prevista', 'label': 'DEVOLUCIÓN PREVISTA', 'field': 'fecha_devolucion_prevista', 'align': 'center'},
    {'name': 'implementos', 'label': 'IMPLEMENTOS', 'field': 'implementos', 'align': 'center'},
    {'name': 'vinculo', 'label': 'MODALIDAD / RESERVA', 'field': 'vinculo', 'align': 'center'},
    {'name': 'estado_prestamo', 'label': 'ESTADO', 'field': 'estado_prestamo', 'align': 'center'},
]


@ui.page('/admin/prestamos')
def pagina_prestamos_admin(request: Request, estado: str = '', reserva: str = ''):
    if not crear_marco_admin('PRÉSTAMOS'):
        return

    estado = estado.upper()
    inicial = VENCIDOS if estado == 'VENCIDOS' else estado if estado in ESTADOS else 'Todos'
    repo = RepositorioImplementosMySQL()
    try:
        prestamos = repo.listar_prestamos()
    except ErrorMySQL:
        prestamos = []
        ui.notify('No se pudieron consultar los préstamos.', type='warning')

    def recargar():
        try:
            exigir_administrador(request)
            prestamos[:] = repo.listar_prestamos()
            filtrar()
        except (ErrorMySQL, ValueError):
            ui.notify('No se pudo actualizar la lista de préstamos.', type='warning')

    with ui.column().classes('w-full p-4 md:p-6 gap-3'):
        with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
            titulo_pagina('GESTIÓN DE PRÉSTAMOS', 'assignment', icono_px='25px')
            with ui.row().classes('items-center gap-2'):
                ui.button(icon='refresh', on_click=recargar).props('flat round').tooltip('Actualizar préstamos')
                nuevo = ui.button('Nueva solicitud', icon='add').props('no-caps').classes(BOTON_PRIMARIO)

        with tarjeta_seccion():
            with fila_filtros():
                buscar = ui.input('Buscar operación, usuario o reserva', value=reserva) \
                    .props('outlined dense clearable debounce=250').classes('min-w-[240px] flex-[2]')
                fecha = campo_texto('Fecha de solicitud', tipo='date')
                fecha.classes('min-w-[170px] flex-1')
                vista = ui.select(['Todos', 'Vigentes', 'Historial'], value='Todos', label='Vista') \
                    .props('outlined dense').classes('min-w-32')
                estado = ui.select(['Todos', VENCIDOS, *ESTADOS], value=inicial, label='Estado') \
                    .props('outlined dense').classes('min-w-[160px] flex-1')
                modalidad_filtro = ui.select(['Todos', CON_RESERVA, SIN_RESERVA], value='Todos', label='Modalidad') \
                    .props('outlined dense').classes('min-w-36')
                boton_limpiar_filtros(lambda: limpiar_filtros())

            tabla = tabla_datos(
                COLUMNAS, prestamos, 'id_operacion', paginacion=10,
                sin_datos='No hay préstamos para mostrar',
            )
            slot_badge_mapa(
                tabla, 'estado_prestamo', COLORES_PRESTAMO,
                defecto='grey-7', clases='px-3 py-1', vacio='—',
            )

            def filtrar():
                texto = texto_buscable(buscar.value).strip()
                f = str(fecha.value or '')
                ahora = datetime.now(ZONA_PERU)
                tabla.rows = [p for p in prestamos if (
                    (not texto or texto in texto_buscable(' '.join(str(p.get(k) or '') for k in (
                        'id_operacion', 'solicitante', 'codigo_institucional', 'codigo_reserva'
                    ))))
                    and (vista.value == 'Todos' or (vista.value == 'Vigentes') ==
                         (p.get('estado_prestamo') in ('PENDIENTE', 'ENTREGADO')))
                    and (not f or str(p.get('fecha_solicitud') or '').startswith(f))
                    and (estado.value == 'Todos' or p.get('estado_prestamo') == estado.value
                         or (estado.value == VENCIDOS and p.get('estado_prestamo') == 'ENTREGADO'
                             and devolucion_vencida(p.get('fecha_devolucion_prevista'), ahora)))
                    and (modalidad_filtro.value == 'Todos' or p.get('modalidad') == modalidad_filtro.value)
                )]
                tabla.selected.clear()
                tabla.update()
                actualizar_acciones()

            def limpiar_filtros():
                buscar.value = ''
                fecha.value = ''
                estado.value = 'Todos'
                vista.value = 'Todos'
                modalidad_filtro.value = 'Todos'
                filtrar()

            for control in (buscar, fecha, estado, vista, modalidad_filtro):
                control.on_value_change(filtrar)

        def seleccionado():
            clave = tabla.selected[0].get('id_operacion') if tabla.selected else None
            return next((p for p in tabla.rows if p['id_operacion'] == clave), None)

        def cargar_detalle(registro):
            try:
                exigir_administrador(request)
                return repo.detalle_prestamo(registro['id_operacion'])
            except ValueError as exc:
                ui.notify(str(exc), type='warning')
            except ErrorMySQL:
                ui.notify('No se pudo consultar el detalle del préstamo.', type='warning')
            return None

        def resumen_solicitado(detalles):
            ui.label('Material solicitado').classes('text-sm font-semibold text-[#09234B]')
            if not detalles:
                ui.label('Sin unidades registradas.').classes('text-sm text-slate-600')
            for (categoria, tipo), cantidad in sorted(agrupar_unidades(detalles).items()):
                with ui.row().classes('w-full justify-between gap-2'):
                    ui.label(f'{tipo} · {categoria}').classes('text-sm')
                    ui.label(f'× {cantidad}').classes('text-sm font-semibold')

        def detalle_visual(detalles):
            ui.label('Movimientos de unidades').classes('text-sm font-semibold text-[#09234B]')
            columnas = [
                {'name': 'codigo_patrimonial', 'label': 'CÓDIGO PATRIMONIAL', 'field': 'codigo_patrimonial'},
                {'name': 'nombre_implemento', 'label': 'IMPLEMENTO', 'field': 'nombre_implemento'},
                {'name': 'entrega', 'label': 'ENTREGADA', 'field': 'entrega'},
                {'name': 'devolucion', 'label': 'DEVUELTA', 'field': 'devolucion'},
                {'name': 'condicion_fisica', 'label': 'CONDICIÓN', 'field': 'condicion_fisica'},
            ]
            tabla_datos(columnas, detalles, 'id_implemento', paginacion=5,
                        seleccion=None, clases='w-full')

        def formulario_nuevo():
            try:
                exigir_administrador(request)
                usuarios = {u['id_usuario']: f"{u['nombres']} {u['apellidos']} | {u['codigo_institucional']}"
                            for u in RepositorioUsuariosMySQL().listar_usuarios()
                            if u['rol']=='USUARIO' and u['tipo_usuario'] in ('ESTUDIANTE', 'DOCENTE')
                            and u['usuario_activo'] and u['perfil_activo']
                            and u['rol_activo'] and u['perfil_completo']}
                disponibles = {i['id_implemento']: f"{i['codigo_patrimonial']} | {i['nombre_implemento']}"
                               for i in repo.listar_implementos() if i['disponibilidad'] == 'Disponible'}
            except ValueError as exc:
                ui.notify(str(exc), type='warning')
                return
            except ErrorMySQL:
                ui.notify('No se pudieron cargar los usuarios e implementos.', type='warning')
                return
            with ui.dialog() as dlg, ui.card().classes('w-full max-w-2xl p-5 gap-3 rounded-xl'):
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('NUEVA SOLICITUD DE PRÉSTAMO').classes('text-lg font-bold text-[#09234B]')
                    ui.button(icon='close', on_click=dlg.close).props('flat round dense')
                usuario = ui.select(usuarios, label='Usuario solicitante') \
                    .props('outlined dense use-input input-debounce=250').classes('w-full')
                modalidad = SelectorReservaPrestamo(repo)
                usuario.on_value_change(lambda: modalidad.cargar(usuario.value))
                modalidad.cargar(usuario.value)
                implementos = ui.select(
                    disponibles, label='Implementos disponibles (código patrimonial)',
                    multiple=True,
                ).props('outlined dense use-chips use-input').classes('w-full')
                with ui.element('div').classes('w-full grid grid-cols-1 sm:grid-cols-2 gap-3'):
                    inicio = campo_texto('Entrega prevista', tipo='datetime-local')
                    fin = campo_texto('Devolución prevista', tipo='datetime-local')
                def actualizar_implementos():
                    try:
                        if not inicio.value or not fin.value:
                            return
                        opciones = {
                            i['id_implemento']: f"{i['codigo_patrimonial']} | {i['nombre_implemento']}"
                            for i in repo.listar_disponibles(inicio.value, fin.value)
                        }
                    except ValueError:
                        return
                    except ErrorMySQL:
                        ui.notify('No se pudo consultar la disponibilidad.', type='warning')
                        return
                    actuales = [i for i in implementos.value or [] if i in opciones]
                    implementos.set_options(opciones, value=actuales)

                inicio.on_value_change(actualizar_implementos)
                fin.on_value_change(actualizar_implementos)
                modalidad.conectar_fechas(inicio, fin)
                obs = ui.textarea('Observación (opcional)').props('outlined rows=2').classes('w-full')
                obs.bind_visibility_from(modalidad.modalidad, 'value', lambda valor: valor == CON_RESERVA)
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
                    async def solicitar():
                        if usuario.value is None:
                            ui.notify('Selecciona un usuario.', type='warning')
                            return
                        try:
                            id_reserva = modalidad.id_reserva()
                            observacion = modalidad.motivo_sin_reserva() if id_reserva is None else obs.value
                        except ValueError as exc:
                            ui.notify(str(exc), type='warning')
                            return
                        if await guardar_como_admin(
                            request, boton, SolicitarPrestamo(repo).ejecutar_para_usuario, id_usuario=usuario.value,
                            unidades=tuple(implementos.value or ()), inicio=inicio.value,
                            fin=fin.value, observacion=observacion, id_reserva=id_reserva,
                        ):
                            dlg.close()
                            recargar()

                    boton = ui.button('Registrar solicitud', icon='save', on_click=solicitar) \
                        .props('no-caps').classes('bg-[#164875] text-white')
            dlg.open()

        def mostrar_vinculo(registro):
            ui.label(SelectorReservaPrestamo.descripcion(registro)).classes('text-sm font-semibold text-[#09234B]')
            if registro.get('id_reserva') is None:
                with ui.column().classes('w-full gap-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2'):
                    ui.label('Motivo del préstamo sin reserva').classes('text-xs font-semibold text-[#09234B]')
                    ui.label(registro.get('observacion') or 'Sin motivo registrado') \
                        .classes('text-sm whitespace-pre-wrap break-words w-full')

        def consultar():
            r = seleccionado()
            if not r:
                return
            detalles = cargar_detalle(r)
            if detalles is None:
                return
            with ui.dialog() as dlg, ui.card().classes('w-full max-w-2xl p-5 gap-3 rounded-xl'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label(f"PRÉSTAMO N.º {r['id_operacion']}") \
                        .classes('text-lg font-bold text-[#09234B]')
                    ui.button(icon='close', on_click=dlg.close).props('flat round dense')
                for titulo, clave in (
                    ('Solicitante', 'solicitante'), ('Código institucional', 'codigo_institucional'),
                    ('Estado', 'estado_prestamo'), ('Fecha de solicitud', 'fecha_solicitud'),
                    ('Entrega prevista', 'fecha_inicio_prevista'), ('Entrega real', 'fecha_entrega'),
                    ('Devolución prevista', 'fecha_devolucion_prevista'),
                ):
                    with ui.row().classes('w-full gap-2 items-baseline'):
                        ui.label(f'{titulo}:').classes('text-xs text-slate-500 min-w-[150px]')
                        ui.label(str(r.get(clave) or '—')).classes('text-sm text-slate-800')
                mostrar_vinculo(r)
                if r.get('id_reserva') is not None and r.get('observacion'):
                    ui.label('Observación').classes('text-xs text-slate-500')
                    ui.label(r['observacion']).classes('text-sm whitespace-pre-wrap break-words w-full')
                resumen_solicitado(detalles)
                if detalles:
                    detalle_visual(detalles)
                ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
            dlg.open()

        def movimiento(accion, estado_requerido, caso):
            r = seleccionado()
            if not r or r['estado_prestamo'] != estado_requerido:
                return
            detalles = cargar_detalle(r)
            if not detalles:
                if detalles is not None:
                    ui.notify('Este préstamo no tiene unidades registradas.', type='warning')
                return
            entrega = estado_requerido == 'PENDIENTE'
            if entrega:
                try:
                    ahora = datetime.now(ZONA_PERU).replace(tzinfo=None)
                    inicio = min(ahora, datetime.fromisoformat(r['fecha_inicio_prevista']))
                    fin = max(ahora + timedelta(seconds=1), datetime.fromisoformat(r['fecha_devolucion_prevista']))
                    tipos = set(agrupar_unidades(detalles))
                    candidatas = [d for d in repo.listar_disponibles(inicio, fin, excluir_operacion=r['id_operacion'])
                                  if (d['nombre_categoria'], nombre_tipo_implemento(d['nombre_implemento'])) in tipos]
                except (ErrorMySQL, ValueError, TypeError):
                    ui.notify('No se pudo consultar los códigos disponibles para la entrega.', type='warning')
                    return
            else:
                candidatas = [d for d in detalles if d.get('movimiento') == 'SALIDA']

            opciones = {d['id_implemento']: f"{d['codigo_patrimonial']} · {nombre_tipo_implemento(d['nombre_implemento'])}"
                        for d in candidatas}
            total = len(detalles)
            with ui.dialog() as dlg, ui.card().classes('w-full max-w-2xl p-5 gap-3 rounded-xl'):
                ui.label(f'{accion.upper()} · PRÉSTAMO N.º {r["id_operacion"]}') \
                    .classes('text-lg font-bold text-[#09234B]')
                if entrega:
                    mostrar_vinculo(r)
                resumen_solicitado(detalles)
                unidades = ui.select(
                    opciones, label='Códigos a entregar' if entrega else 'Códigos recibidos en la devolución',
                    multiple=True,
                ).props('outlined use-chips use-input').classes('w-full')
                if not opciones:
                    ui.label('No se encontraron unidades elegibles para esta operación.').classes('text-sm text-slate-600')
                cantidad = ui.label(f'Selecciona {total} códigos patrimoniales.').classes('text-xs text-slate-600')
                detalle = ui.textarea('Condición física u observación (opcional)') \
                    .props('outlined rows=2').classes('w-full')

                def actualizar_cantidad():
                    elegidas = len(unidades.value or ())
                    cantidad.set_text(f'{elegidas} de {total} unidades seleccionadas.')
                    boton.set_enabled(elegidas == total)

                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')

                    async def aplicar():
                        if await guardar_como_admin(
                            request, boton, caso.ejecutar, operacion=r['id_operacion'],
                            unidades=tuple(unidades.value or ()), detalle=detalle.value,
                        ):
                            dlg.close()
                            recargar()

                    boton = ui.button(f'Confirmar {accion.lower()}', on_click=aplicar).props('no-caps') \
                        .classes(BOTON_PRIMARIO)
                unidades.on_value_change(actualizar_cantidad)
                actualizar_cantidad()
            dlg.open()

        def cancelar():
            r = seleccionado()
            if not r:
                return
            if r.get('estado_prestamo') != 'PENDIENTE':
                ui.notify('Solo se pueden cancelar solicitudes pendientes.', type='warning')
                return
            with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-5 gap-3'):
                ui.label(f"CANCELAR SOLICITUD N.º {r['id_operacion']}") \
                    .classes('text-lg font-bold text-[#09234B]')
                motivo = ui.textarea('Motivo (opcional)').props('outlined rows=2').classes('w-full')
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
                    async def aplicar():
                        if await guardar_como_admin(
                            request, boton, CancelarSolicitud(repo).ejecutar_como_admin,
                            operacion=r['id_operacion'], motivo=motivo.value,
                        ):
                            dlg.close()
                            recargar()

                    boton = ui.button('Confirmar cancelación', on_click=aplicar).props('no-caps color=negative')
            dlg.open()

        nuevo.on('click', formulario_nuevo)
        with ui.row().classes('w-full gap-2 flex-wrap'):
            acciones = {}
            for titulo, icono, accion in (
                ('Consultar', 'visibility', consultar),
                ('Entregar', 'outbox', lambda: movimiento('Entrega', 'PENDIENTE', EntregarPrestamo(repo))),
                ('Devolver', 'assignment_return', lambda: movimiento('Devolución', 'ENTREGADO', DevolverPrestamo(repo))),
                ('Cancelar solicitud', 'cancel', cancelar),
            ):
                acciones[titulo] = ui.button(titulo, icon=icono, on_click=accion).props('outline no-caps') \
                    .classes('text-[#164875] rounded-lg')

        def actualizar_acciones():
            r = seleccionado()
            estado_actual = r['estado_prestamo'] if r else None
            acciones['Consultar'].set_enabled(r is not None)
            acciones['Entregar'].set_enabled(estado_actual == 'PENDIENTE')
            acciones['Cancelar solicitud'].set_enabled(estado_actual == 'PENDIENTE')
            acciones['Devolver'].set_enabled(estado_actual == 'ENTREGADO')

        tabla.on_select(actualizar_acciones)
        filtrar()
