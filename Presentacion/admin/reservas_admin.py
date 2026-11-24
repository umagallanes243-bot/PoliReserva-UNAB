# Presentacion/admin/reservas_admin.py
# Capa de presentación: estructura visual de reservas (sin datos de muestra).
from datetime import datetime

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from aplicacion.casos_uso.reservas.cancelar_reserva import CancelarReserva
from aplicacion.casos_uso.reservas.confirmar_reserva import ConfirmarReserva
from aplicacion.casos_uso.reservas.registrar_reserva_administrativa import RegistrarReservaAdministrativa
from aplicacion.casos_uso.reservas.reprogramar_reserva import ReprogramarReserva
from dominio.reglas.reservas import ESTADOS_RESERVA, ZONA_PERU, acciones_reserva
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL
from infraestructura.persistencia.usuarios_mysql import RepositorioUsuariosMySQL
from Presentacion.sesion import exigir_administrador
from Presentacion.admin.layout_admin import crear_marco_admin, guardar_como_admin
from Presentacion.componentes.cupo_reservas import IndicadorCupoSemanal
from Presentacion.componentes.dialogos import grilla_detalle
from Presentacion.componentes.estilos import BOTON_PRIMARIO
from Presentacion.componentes.filtros import (boton_limpiar_filtros, campo_texto,
                                             fila_filtros)
from Presentacion.componentes.tablas import COLORES_RESERVA, slot_badge_mapa, tabla_datos
from Presentacion.componentes.exportaciones import descargar_comprobante
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina

POR_CONFIRMAR = 'Por confirmar ahora'


def _vista_reserva(r):
    return dict(r, estado=r['estado_reserva'],
                solicitante=' '.join(p for p in (r['nombres'], r['apellidos']) if p),
                horario=f"{r['hora_inicio']} – {r['hora_fin']}")


def mostrar_reservas():
    return [_vista_reserva(r) for r in RepositorioReservasMySQL().listar_administracion()]


def acciones_fila(r, ahora=None):
    return acciones_reserva(r['estado_reserva'], r['fecha_uso'], r['hora_inicio'], r['hora_fin'],
                            ahora or datetime.now(ZONA_PERU))


def dialogo_cambio_reserva(request, recargar, reserva, *, confirmar):
    acciones = acciones_fila(reserva)
    if not (acciones.confirmar if confirmar else acciones.cancelar):
        ui.notify('Este turno ya no admite esa acción.', type='warning')
        return
    repo = RepositorioReservasMySQL()
    caso = ConfirmarReserva(repo) if confirmar else CancelarReserva(repo)
    texto = 'Confirmar asistencia' if confirmar else 'Cancelar reserva'

    async def aplicar():
        if await guardar_como_admin(
            request, boton, caso.ejecutar, codigo_reserva=reserva['codigo_reserva'],
            mensaje_error='No se pudo actualizar la reserva.',
        ):
            dlg.close()
            recargar()

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-sm p-5 gap-3'):
        ui.label(texto).classes('text-lg font-bold text-[#09234B]')
        ui.label(f"{reserva['codigo_reserva']} · {reserva['solicitante']}").classes('text-sm text-slate-600')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
            boton = ui.button('Confirmar' if confirmar else 'Cancelar reserva', on_click=aplicar) \
                .props('unelevated no-caps').classes(BOTON_PRIMARIO)
    dlg.open()


def dialogo_detalle_reserva(request, recargar, codigo, *, contextual=False):
    repo = RepositorioReservasMySQL()
    try:
        exigir_administrador(request)
        registro = repo.obtener_para_gestion(codigo)
    except (ValueError, ErrorMySQL):
        ui.notify('No se pudo consultar la reserva.', type='warning')
        return
    if registro is None:
        ui.notify('La reserva ya no está disponible.', type='warning')
        return
    r = _vista_reserva(registro)
    try:
        prestamos = RepositorioImplementosMySQL().listar_prestamos(id_reserva=r['id_reserva'])
    except (ValueError, ErrorMySQL):
        prestamos = None

    datos = [('Código', 'codigo_reserva'), ('Titular', 'solicitante'),
             ('Fecha de uso', 'fecha_uso'), ('Horario', 'horario'), ('Estado', 'estado')]
    if not contextual:
        datos += [('DNI', 'dni'), ('Correo institucional', 'correo_institucional'),
                  ('Código institucional', 'codigo_institucional'), ('Tipo', 'tipo_usuario'),
                  ('Escuela / área', 'escuela'), ('Registrada el', 'fecha_solicitud'),
                  ('Administrador gestor', 'admin_gestor')]

    def abrir_accion(accion):
        dialogo.close()
        accion()

    def comprobante():
        try:
            exigir_administrador(request)
            actual = repo.obtener_para_gestion(codigo)
        except (ValueError, ErrorMySQL):
            ui.notify('No se pudo autorizar la descarga.', type='warning')
            return
        if actual:
            descargar_comprobante(actual)

    with ui.dialog() as dialogo, ui.card().classes('w-full max-w-lg p-5 gap-3'):
        ui.label('Detalle de reserva').classes('text-lg font-bold text-[#09234B]')
        grilla_detalle(r, datos, responsive=False, destacar=False, gap='gap-x-5 gap-y-2', falsy_como_vacio=True)
        if prestamos is None:
            ui.label('No se pudieron consultar los préstamos asociados.').classes('text-xs text-slate-600')
        elif prestamos:
            ui.label('Préstamos asociados').classes('text-sm font-semibold text-[#09234B]')
            with ui.column().classes('w-full max-h-32 overflow-auto gap-1'):
                for prestamo in prestamos:
                    ui.label(f"N.º {prestamo['id_operacion']} · {prestamo['estado_prestamo'].capitalize()} · "
                             f"{prestamo['total_implementos']} unidades").classes('text-sm text-slate-700')
            ui.link('Consultar préstamos', f'/admin/prestamos?reserva={codigo}').classes('text-sm')
        with ui.row().classes('w-full justify-end gap-2 flex-wrap'):
            if contextual:
                acciones = acciones_fila(r)
                if acciones.cancelar:
                    ui.button('Reprogramar', icon='edit_calendar',
                              on_click=lambda: abrir_accion(lambda: formulario_reserva(request, recargar, r))) \
                        .props('outline no-caps')
                    ui.button('Cancelar reserva', icon='event_busy',
                              on_click=lambda: abrir_accion(lambda: dialogo_cambio_reserva(
                                  request, recargar, r, confirmar=False))) \
                        .props('outline no-caps')
                if acciones.confirmar:
                    ui.button('Confirmar asistencia', icon='task_alt',
                              on_click=lambda: abrir_accion(lambda: dialogo_cambio_reserva(
                                  request, recargar, r, confirmar=True))) \
                        .props('outline no-caps')
            ui.button('Comprobante', icon='download', on_click=comprobante).props('flat no-caps')
            ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps')
    dialogo.open()


@ui.page('/admin/reservas')
def pagina_gestion_reservas(request: Request, filtro: str = '', codigo: str = ''):
    if not crear_marco_admin('RESERVAS'):
        return
    try:
        registros = mostrar_reservas()
    except ErrorMySQL:
        registros = []
        ui.notify('No se pudieron consultar las reservas.', type='warning')

    def recargar(*, avisar=True):
        try:
            exigir_administrador(request)
            actualizadas = mostrar_reservas()
        except (ValueError, ErrorMySQL):
            if avisar:
                ui.notify('No se pudo actualizar la lista.', type='warning')
            return
        if actualizadas != registros:
            registros[:] = actualizadas
            filtrar()
        else:
            actualizar_acciones()

    with ui.column().classes('w-full p-4 md:p-6 gap-3'):
        # Encabezado
        with ui.row().classes('w-full items-center justify-between gap-2 flex-wrap'):
            titulo_pagina('GESTIÓN DE RESERVAS', 'event_note', icono_px='26px',
                          color_icono='text-blue-800', responsive=True)
            with ui.row().classes('items-center gap-2'):
                ui.button(icon='refresh', on_click=recargar).props('flat round').tooltip('Actualizar reservas')
                ui.button('Nueva reserva', icon='add', on_click=lambda: formulario_reserva(request, recargar)) \
                    .props('no-caps unelevated').classes(BOTON_PRIMARIO)

        # Filtros y tabla
        with tarjeta_seccion():
            with fila_filtros():
                buscar = campo_texto(
                    'Buscar por correo, nombre, código institucional o reserva', valor=codigo,
                    clases='w-full bg-white',
                )
                buscar.classes('min-w-[230px] flex-[2]')
                fecha = campo_texto('Fecha de uso', tipo='date',
                                    clases='w-full bg-white')
                fecha.classes('min-w-[165px] flex-1')
                estado = ui.select(['Todos', POR_CONFIRMAR, *ESTADOS_RESERVA], label='Estado',
                                   value=POR_CONFIRMAR if filtro == 'asistencia' else 'Todos') \
                    .props('outlined dense').classes('min-w-[160px] flex-1 bg-white')
                boton_limpiar_filtros(lambda: limpiar_filtros(), icono='refresh')

            columnas = [
                {'name': 'codigo_reserva', 'label': 'CÓDIGO', 'field': 'codigo_reserva', 'align': 'left'},
                {'name': 'solicitante', 'label': 'SOLICITANTE', 'field': 'solicitante', 'align': 'left'},
                {'name': 'tipo_usuario', 'label': 'TIPO', 'field': 'tipo_usuario', 'align': 'left'},
                {'name': 'escuela', 'label': 'ESCUELA / ÁREA', 'field': 'escuela', 'align': 'left'},
                {'name': 'fecha_uso', 'label': 'FECHA', 'field': 'fecha_uso', 'align': 'center'},
                {'name': 'horario', 'label': 'HORARIO', 'field': 'horario', 'align': 'center'},
                {'name': 'estado', 'label': 'ESTADO', 'field': 'estado', 'align': 'center'},
            ]
            tabla = tabla_datos(
                columnas, registros, 'id_reserva', paginacion=10,
                sin_datos='No hay reservas para mostrar',
            )
            slot_badge_mapa(
                tabla, 'estado', COLORES_RESERVA,
                defecto='grey-6', clases='text-white text-weight-bold',
            )

            def filtrar(*, conservar=False):
                previa = tabla.selected[0]['id_reserva'] if conservar and tabla.selected else None
                ahora = datetime.now(ZONA_PERU)
                termino = str(buscar.value or '').strip().lower()
                f = str(fecha.value or '').strip()
                e = estado.value
                tabla.rows = [
                    r for r in registros
                    if (not termino or termino in ' '.join(str(r.get(k) or '') for k in (
                        'codigo_reserva', 'solicitante', 'correo_institucional',
                        'codigo_institucional', 'dni')).lower())
                    and (not f or str(r.get('fecha_uso') or '') == f)
                    and (e == 'Todos' or r.get('estado') == e or
                         (e == POR_CONFIRMAR and r.get('bloquea_horario', True)
                          and acciones_fila(r, ahora).confirmar))
                ]
                tabla.selected = [r for r in tabla.rows if r['id_reserva'] == previa]
                tabla.update()
                actualizar_acciones()

            def limpiar_filtros():
                buscar.value = ''
                fecha.value = ''
                estado.value = 'Todos'
                filtrar()

            buscar.on_value_change(filtrar)
            fecha.on_value_change(filtrar)
            estado.on_value_change(filtrar)

        def seleccion():
            clave = tabla.selected[0].get('id_reserva') if tabla.selected else None
            return next((r for r in tabla.rows if r['id_reserva'] == clave), None)

        def detalle():
            r = seleccion()
            if r is not None:
                dialogo_detalle_reserva(request, recargar, r['codigo_reserva'])

        def modificar():
            r = seleccion()
            if r is not None and acciones_fila(r).cancelar:
                formulario_reserva(request, recargar, r)

        def cambiar(confirmar):
            if (r := seleccion()) is not None:
                dialogo_cambio_reserva(request, recargar, r, confirmar=confirmar)

        with ui.row().classes('w-full gap-2 flex-wrap'):
            botones = {}
            for texto, icono, accion in (
                ('Consultar', 'visibility', detalle),
                ('Modificar', 'edit_calendar', modificar),
                ('Confirmar asistencia', 'task_alt', lambda: cambiar(True)),
                ('Cancelar reserva', 'event_busy', lambda: cambiar(False)),
            ):
                botones[texto] = ui.button(texto, icon=icono, on_click=accion).props('outline no-caps') \
                    .classes('border-slate-200 text-[#164875] rounded-lg')
        aviso = ui.label().classes('text-xs text-slate-600')

        def actualizar_acciones():
            r = seleccion()
            acciones = acciones_fila(r) if r else None
            botones['Consultar'].set_enabled(r is not None)
            botones['Modificar'].set_enabled(bool(acciones and acciones.cancelar))
            botones['Cancelar reserva'].set_enabled(bool(acciones and acciones.cancelar))
            botones['Confirmar asistencia'].set_enabled(bool(acciones and acciones.confirmar))
            aviso.set_text('La asistencia se confirma durante los primeros 15 minutos del turno.'
                           if r and r['estado'] == 'RESERVADA' else '')

        tabla.on_select(actualizar_acciones)
        filtrar()
        ui.timer(60, lambda: recargar(avisar=False), immediate=False)
        ui.timer(15, lambda: filtrar(conservar=True) if estado.value == POR_CONFIRMAR else actualizar_acciones(),
                 immediate=False)


def formulario_reserva(request, recargar, reserva=None, *, horario=None):
    editando = reserva is not None
    datos = reserva or horario or {}
    with ui.dialog() as dialogo, ui.card().classes('w-full max-w-lg p-5 gap-3'):
        ui.label('Modificar reserva' if editando else 'Nueva reserva') \
            .classes('text-lg font-bold text-[#09234B]')
        if not editando:
            try:
                usuarios = {u['id_usuario']: f"{u['nombres']} {u['apellidos']}"
                            for u in RepositorioUsuariosMySQL().listar_usuarios()
                            if u['rol'] == 'USUARIO' and u['tipo_usuario'] in ('ESTUDIANTE', 'DOCENTE')
                            and u['usuario_activo'] and u['perfil_activo']
                            and u['rol_activo'] and u['perfil_completo']}
            except ErrorMySQL:
                ui.notify('No se pudieron consultar los usuarios.', type='warning')
                return
            titular = ui.select(usuarios, label='Usuario registrado').props('outlined dense use-input') \
                .classes('w-full')
        fecha = campo_texto('Fecha de uso', datos.get('fecha_uso', datetime.now(ZONA_PERU).date().isoformat()),
                    'date', clases='w-full bg-white')
        with ui.row().classes('w-full gap-3'):
            inicio = campo_texto('Hora inicial', datos.get('hora_inicio', ''),
                        'time', clases='w-full bg-white').classes('flex-1')
            fin = campo_texto('Hora final', datos.get('hora_fin', ''),
                        'time', clases='w-full bg-white').classes('flex-1')
        repo = RepositorioReservasMySQL()
        indicador = IndicadorCupoSemanal()

        def mostrar_cupo():
            usuario = reserva['id_usuario'] if editando else titular.value
            if not usuario or not fecha.value:
                indicador.actualizar(None, mensaje='Selecciona al titular y la fecha de uso.')
                return
            try:
                segundos = repo.consumo_semanal(
                    usuario, fecha.value, excluir_reserva=reserva['id_reserva'] if editando else 0,
                )
            except (ErrorMySQL, ValueError):
                segundos = None
            indicador.actualizar(segundos)

        fecha.on_value_change(mostrar_cupo)
        if not editando:
            titular.on_value_change(mostrar_cupo)
        mostrar_cupo()
        caso = ReprogramarReserva(repo) if editando else RegistrarReservaAdministrativa(repo)
        codigo = {'codigo_reserva': reserva['codigo_reserva']} if editando else {}

        async def guardar():
            if await guardar_como_admin(
                request, boton, caso.ejecutar,
                id_usuario=reserva['id_usuario'] if editando else titular.value,
                fecha_uso=fecha.value, hora_inicio=inicio.value, hora_fin=fin.value,
                mensaje_error='No se pudo guardar la reserva.', **codigo,
            ):
                dialogo.close()
                recargar()

        ui.label('Hasta 2 horas. La gestión administrativa permite reservar turnos publicados en fin de semana.') \
            .classes('text-xs text-slate-600')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps')
            boton = ui.button('Guardar', icon='save', on_click=guardar).props('no-caps') \
                .classes('bg-[#164875] text-white')
    dialogo.open()
