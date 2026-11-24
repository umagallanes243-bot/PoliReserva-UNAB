# Presentacion/admin/actividades_admin.py
# Interfaz de programación del polideportivo — NiceGUI / PoliReserva V9.
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from aplicacion.casos_uso.programaciones.crear_periodo_academico import CrearPeriodoAcademico
from aplicacion.casos_uso.programaciones.desactivar_programacion import DesactivarProgramacion
from aplicacion.casos_uso.programaciones.modificar_programacion import ModificarProgramacion
from aplicacion.casos_uso.programaciones.publicar_horarios import PublicarHorarios
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from infraestructura.persistencia.usuarios_mysql import RepositorioUsuariosMySQL
from dominio.reglas.reservas import APERTURA, CIERRE, MAXIMO_RESERVA_MINUTOS, ZONA_PERU
from Presentacion.admin.calendario_admin import panel_calendario_admin
from Presentacion.admin.horarios_libres_admin import dialogo_horarios_libres
from Presentacion.admin.layout_admin import crear_marco_admin, guardar_como_admin
from Presentacion.admin.reservas_admin import dialogo_detalle_reserva, formulario_reserva
from Presentacion.componentes.agenda import a_minutos, hhmm, nombre_programacion_visible
from Presentacion.componentes.dialogos import grilla_detalle
from Presentacion.componentes.estilos import BOTON_PRIMARIO
from Presentacion.componentes.filtros import (boton_limpiar_filtros, campo_texto,
                                             fila_filtros)
from Presentacion.componentes.tablas import fila_seleccionada, tabla_datos
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina
from Presentacion.sesion import exigir_administrador

AZUL = '#09234B'
TIPOS = {
    'TALLER': ('Talleres', 'Taller deportivo', 'Nuevo taller', 'sports_basketball'),
    'EVENTO': ('Eventos', 'Evento institucional', 'Nuevo evento', 'event'),
    'MANTENIMIENTO': ('Mantenimiento', 'Mantenimiento y limpieza', 'Nuevo mantenimiento', 'build'),
    'LIBRE': ('Horarios libres', 'Horario habilitado', 'Nuevo horario', 'event_available'),
}


TIPOS_BD = {'TALLER': 'TALLER DEPORTIVO', 'EVENTO': 'EVENTO INSTITUCIONAL',
            'MANTENIMIENTO': 'MANTENIMIENTO', 'LIBRE': 'LIBRE'}


def _vista_programacion(h):
    return dict(h, periodo=h['nombre_periodo'], escuela=h['nombre_escuela'],
                nombre_visible=nombre_programacion_visible(h['nombre_programacion']),
                horario=f"{h['hora_inicio']} – {h['hora_fin']}", estado_programacion='Publicada')


def obtener_programaciones(tipo):
    return [_vista_programacion(h) for h in RepositorioProgramacionesMySQL().listar_horarios(tipo=TIPOS_BD[tipo])]


def obtener_escuelas():
    return {e['id_escuela']: e['nombre_escuela'] for e in RepositorioUsuariosMySQL().listar_escuelas()}


def formulario_programacion(request, recargar, tipo, registro=None, existentes=(), *, preseleccion=None):
    """Formulario visual para tb_programaciones y varios tb_horarios_programados."""
    editando = registro is not None
    titulo = TIPOS[tipo][1]
    datos = registro or preseleccion or {}
    nombre_guardado = datos.get('nombre_programacion')
    nombre_inicial = nombre_programacion_visible(nombre_guardado) or ('Horario disponible' if tipo == 'LIBRE' else '')
    try:
        exigir_administrador(request)
        catalogo = {p['id_periodo']: p for p in RepositorioProgramacionesMySQL().listar_periodos()}
        periodos = {i: p['nombre_periodo'] for i, p in catalogo.items()}
        escuelas = obtener_escuelas() if tipo == 'EVENTO' else {}
    except (ValueError, ErrorMySQL):
        ui.notify('No se pudieron cargar los catálogos.', type='warning')
        return
    if not periodos:
        ui.notify('Crea un período académico antes de publicar una programación.', type='warning')
        return

    with ui.dialog() as dialogo, ui.card().classes('w-full max-w-2xl p-5 gap-3 rounded-xl'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(('Modificar ' if editando else 'Registrar ') + titulo.lower()) \
                .classes('text-lg font-bold text-[#09234B]')
            ui.button(icon='close', on_click=dialogo.close).props('flat round dense')

        with ui.element('div').classes('w-full grid grid-cols-1 md:grid-cols-2 gap-3'):
            nombre = campo_texto('Nombre de la programación', nombre_inicial)
            id_periodo = datos.get('id_periodo')
            periodo = ui.select(periodos, value=id_periodo if id_periodo in periodos else None,
                                label='Período académico') \
                .props('outlined dense').classes('w-full')
            escuela = responsable = None
            if tipo == 'EVENTO':
                escuela = ui.select(escuelas, value=datos.get('id_escuela'), label='Escuela profesional') \
                    .props('outlined dense clearable').classes('w-full')
            if tipo in ('TALLER', 'EVENTO'):
                responsable = campo_texto('Responsable (opcional)', (registro or {}).get('responsable', ''))
            if tipo == 'MANTENIMIENTO':
                responsable = campo_texto('Responsable de mantenimiento (opcional)',
                            (registro or {}).get('responsable', ''))

        descripcion = ui.textarea('Descripción (opcional)',
                    value=(registro or {}).get('descripcion', '')).props('outlined dense rows=2') \
            .classes('w-full')
        ui.separator()
        ui.label('Fechas y horarios').classes('text-sm font-semibold text-[#09234B]')
        with ui.element('div').classes('w-full grid grid-cols-2 md:grid-cols-4 gap-3'):
            hoy = datetime.now(ZONA_PERU).date().isoformat()
            fecha = campo_texto('Fecha', datos.get('fecha_uso', hoy), 'date')
            ultima_fecha = campo_texto('Última fecha (opcional)', tipo='date')
            inicio = campo_texto('Hora de inicio', datos.get('hora_inicio', ''), 'time')
            fin = campo_texto('Hora de fin', datos.get('hora_fin', ''), 'time')

        horarios = [(h["fecha_uso"], h["hora_inicio"], h["hora_fin"]) for h in existentes]
        lista_horarios = ui.column().classes('w-full gap-1 max-h-28 overflow-y-auto')

        def pintar_horarios():
            lista_horarios.clear()
            with lista_horarios:
                for indice, item in enumerate(horarios):
                    with ui.row().classes('w-full items-center justify-between bg-slate-50 border border-slate-200 rounded-md px-3 py-1'):
                        ui.label(f"{item[0]}  ·  {item[1]} – {item[2]}").classes('text-xs text-slate-700')
                        ui.button(icon='close', on_click=lambda i=indice: quitar_horario(i)) \
                            .props('flat round dense size=xs').classes('text-slate-500')

        def quitar_horario(indice):
            horarios.pop(indice)
            pintar_horarios()

        def agregar_horario():
            try:
                primera = date.fromisoformat(str(fecha.value))
                ultima = date.fromisoformat(str(ultima_fecha.value or fecha.value))
            except ValueError:
                ui.notify('Completa las fechas de la jornada.', type='warning')
                return
            hi, hf = a_minutos(inicio.value), a_minutos(fin.value)
            if ultima < primera or hi is None or hf is None or hi >= hf:
                ui.notify('Revisa el orden de las fechas y las horas de cada jornada.', type='warning')
                return
            seleccionado = catalogo.get(periodo.value)
            if not seleccionado:
                ui.notify('Selecciona el período académico.', type='warning')
                return
            desde, hasta = seleccionado.get('fecha_inicio'), seleccionado.get('fecha_fin')
            if desde and hasta and not desde <= primera.isoformat() <= ultima.isoformat() <= hasta:
                ui.notify('Todas las jornadas deben estar dentro del período académico.', type='warning')
                return
            nuevas = [((primera + timedelta(days=i)).isoformat(), hhmm(hi), hhmm(hf))
                      for i in range((ultima - primera).days + 1)]
            if any(f == anterior and a < fin_anterior and inicio_anterior < b
                   for f, a, b in nuevas for anterior, inicio_anterior, fin_anterior in horarios):
                ui.notify('Alguna jornada se superpone con un horario de esta programación.', type='warning')
                return
            horarios.extend(nuevas)
            horarios.sort()
            pintar_horarios()

        def jornada_completa():
            inicio.set_value(hhmm(APERTURA))
            fin.set_value(hhmm(CIERRE))

        caso = ModificarProgramacion() if editando else PublicarHorarios()
        identificador = {'id_programacion': datos['id_programacion']} if editando else {}

        async def guardar():
            if await guardar_como_admin(
                request, boton, caso.ejecutar,
                tipo=TIPOS_BD[tipo], id_periodo=periodo.value,
                nombre=nombre_guardado if editando and nombre.value == nombre_inicial else nombre.value,
                descripcion=descripcion.value, responsable=responsable.value if responsable else None,
                escuela=escuela.value if escuela else None, horarios=tuple(horarios),
                mensaje_error='No se pudo guardar la programación.', **identificador,
            ):
                dialogo.close()
                recargar()

        pintar_horarios()
        with ui.row().classes('w-full gap-2 flex-wrap'):
            ui.button('Agregar horario', icon='add', on_click=agregar_horario) \
                .props('outline no-caps').classes('text-[#164875]')
            ui.button('Jornada completa', icon='schedule', on_click=jornada_completa) \
                .props('flat no-caps').classes('text-[#164875]').tooltip('De 07:00 a 22:00 por fecha')
        with ui.row().classes('w-full justify-end gap-2 pt-2'):
            ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps')
            accion = 'Guardar cambios' if editando else ('Publicar horarios' if tipo == 'LIBRE' else 'Crear programación')
            boton = ui.button(accion, icon='save', on_click=guardar).props('no-caps').classes(BOTON_PRIMARIO)
    dialogo.open()


def dialogo_desactivar_programacion(request, recargar, registro, jornadas):
    id_programacion = registro['id_programacion']
    repo = RepositorioProgramacionesMySQL()

    def consultar_bloqueos():
        resumen.clear()
        with resumen:
            try:
                exigir_administrador(request)
                reservas = repo.reservas_que_impiden_desactivar(id_programacion)
            except (ValueError, ErrorMySQL):
                ui.label('No se pudieron consultar las reservas asociadas.').classes('text-sm text-slate-600')
                boton.disable()
                return
            boton.set_enabled(not reservas)
            if reservas:
                ui.label('Hay reservas que todavía ocupan jornadas de esta programación.') \
                    .classes('text-sm font-semibold text-amber-900')
                with ui.column().classes('w-full max-h-48 overflow-auto gap-2'):
                    for reserva in reservas:
                        codigo = reserva['codigo_reserva']
                        enlace = '/admin/reservas?' + urlencode({'codigo': codigo})
                        ui.link(codigo, enlace).classes('text-sm font-medium text-[#164875]')
                        ui.label(f"{reserva['fecha_uso']:%d/%m/%Y} · {reserva['hora_inicio']}–"
                                 f"{reserva['hora_fin']} · {reserva['nombre_estado'].capitalize()}") \
                            .classes('text-xs text-slate-600')

    async def aplicar():
        if await guardar_como_admin(
            request, boton, DesactivarProgramacion(repo).ejecutar, id_programacion=id_programacion,
            mensaje_error='No se pudo desactivar la programación.',
        ):
            dlg.close()
            recargar()
            ui.notify('Programación desactivada.', type='positive')
        elif not boton.is_deleted and dlg.value:
            consultar_bloqueos()

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-5 gap-3'):
        ui.label('Desactivar programación completa').classes('text-lg font-bold text-[#09234B]')
        ui.label(registro['nombre_visible']).classes('text-sm font-semibold')
        ui.label(f'Jornadas publicadas · {len(jornadas)}').classes('text-xs text-slate-600')
        ui.label('La desactivación retira del calendario todas las jornadas de esta programación.') \
            .classes('text-sm text-slate-700')
        resumen = ui.column().classes('w-full gap-2')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
            boton = ui.button('Desactivar', on_click=aplicar).props('no-caps')
        consultar_bloqueos()
    dlg.open()


def dialogo_programacion(request, recargar, tipo, registro, jornadas, *, desde_calendario=False, horario=None):
    campos = [
        (nombre, clave) for nombre, clave in (
            ('Programación', 'nombre_visible'), ('Tipo', 'tipo_visible'), ('Período', 'periodo'),
            ('Escuela', 'escuela'), ('Responsable', 'responsable'), ('Fecha', 'fecha_uso'),
            ('Horario publicado', 'horario'), ('Franja disponible', 'franja_disponible'),
            ('Estado', 'estado_programacion'), ('Descripción', 'descripcion'),
        )
        if not (clave == 'escuela' and tipo != 'EVENTO')
        and not (clave == 'responsable' and tipo == 'LIBRE')
        and not (clave == 'franja_disponible' and not registro.get(clave))
    ]

    def abrir(accion):
        dlg.close()
        accion()

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-lg p-5 gap-3'):
        ui.label('Detalle de programación').classes('font-bold text-[#09234B] text-lg')
        grilla_detalle(dict(registro, tipo_visible=TIPOS[tipo][1]), campos, responsive=False, destacar=False,
                       falsy_como_vacio=True)
        if len(jornadas) > 1:
            ui.label('Jornadas publicadas').classes('text-sm font-semibold text-[#09234B]')
            with ui.column().classes('w-full max-h-32 overflow-y-auto gap-1'):
                for jornada in jornadas:
                    ui.label(f"{jornada['fecha_uso']} · {jornada['hora_inicio']}–{jornada['hora_fin']}").classes('text-sm')
        with ui.row().classes('w-full justify-end items-center gap-2 flex-wrap'):
            if desde_calendario:
                if horario:
                    ui.button('Nueva reserva', icon='add', on_click=lambda: abrir(
                        lambda: formulario_reserva(request, recargar, horario=horario)
                    )).props('unelevated no-caps').classes(BOTON_PRIMARIO)
                ui.button('Modificar', icon='edit', on_click=lambda: abrir(
                    lambda: formulario_programacion(request, recargar, tipo, registro, jornadas)
                )).props('outline no-caps')
                ui.button('Desactivar', icon='block', on_click=lambda: abrir(
                    lambda: dialogo_desactivar_programacion(request, recargar, registro, jornadas)
                )).props('outline no-caps')
            ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
    dlg.open()


def panel_programacion(request, tipo, periodos, al_cambiar):
    etiqueta, _, boton_nuevo, icono = TIPOS[tipo]
    try:
        registros = obtener_programaciones(tipo)
    except ErrorMySQL:
        registros = []
        ui.notify('No se pudo consultar la programación.', type='warning')

    def recargar():
        al_cambiar()
        try:
            exigir_administrador(request)
            registros[:] = obtener_programaciones(tipo)
            filtrar()
        except (ValueError, ErrorMySQL):
            ui.notify('No se pudo actualizar la programación.', type='warning')

    with ui.column().classes('w-full gap-3 p-0'):
        with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
            titulo_pagina(etiqueta.upper(), icono, icono_px='21px',
                          color_icono='text-blue-800', tamano='text-sm')
            ui.button(boton_nuevo, icon='add', on_click=lambda: formulario_programacion(request, recargar, tipo)) \
                .props('no-caps unelevated').classes(BOTON_PRIMARIO)

        with tarjeta_seccion():
            with fila_filtros():
                buscar = campo_texto('Buscar programación')
                buscar.classes('min-w-[200px] flex-[2]')
                periodo = ui.select(periodos, label='Período académico') \
                    .props('outlined dense clearable').classes('min-w-[165px] flex-1')
                fecha = campo_texto('Fecha de uso', tipo='date')
                fecha.classes('min-w-[150px] flex-1')

                def limpiar():
                    buscar.value = ''
                    periodo.value = None
                    fecha.value = ''
                    filtrar()

                boton_limpiar_filtros(limpiar, icono='refresh')

            columnas = [
                {'name': 'nombre_programacion', 'label': 'PROGRAMACIÓN', 'field': 'nombre_visible', 'align': 'left'},
                {'name': 'periodo', 'label': 'PERÍODO', 'field': 'periodo', 'align': 'center'},
            ]
            if tipo == 'EVENTO':
                columnas.append({'name': 'escuela', 'label': 'ESCUELA', 'field': 'escuela', 'align': 'left'})
            columnas += [
                {'name': 'fecha_uso', 'label': 'FECHA', 'field': 'fecha_uso', 'align': 'center'},
                {'name': 'horario', 'label': 'HORARIO', 'field': 'horario', 'align': 'center'},
                {'name': 'responsable', 'label': 'RESPONSABLE', 'field': 'responsable', 'align': 'left'},
            ]
            if tipo == 'LIBRE':
                columnas = [c for c in columnas if c['name'] != 'responsable']

            tabla = tabla_datos(
                columnas, registros, 'id_horario', paginacion=8,
                sin_datos='Sin programaciones registradas',
            )

            def filtrar():
                q = (buscar.value or '').strip().lower()
                f = fecha.value or ''
                p = periodo.value
                tabla.rows = [r for r in registros if
                              (not q or q in r['nombre_visible'].lower())
                              and (not f or str(r.get('fecha_uso')) == f)
                              and (p is None or r.get('id_periodo') == p)]
                tabla.selected.clear()
                tabla.update()

            buscar.on_value_change(filtrar)
            periodo.on_value_change(filtrar)
            fecha.on_value_change(filtrar)

        def seleccion():
            fila = fila_seleccionada(tabla, 'Selecciona un horario de la tabla.')
            return next((r for r in tabla.rows if fila and r['id_horario'] == fila.get('id_horario')), None)

        def jornadas(registro):
            return [r for r in registros if r['id_programacion'] == registro['id_programacion']]

        def consultar():
            if (registro := seleccion()) is not None:
                dialogo_programacion(request, recargar, tipo, registro, jornadas(registro))

        def modificar():
            if (registro := seleccion()) is not None:
                formulario_programacion(request, recargar, tipo, registro, jornadas(registro))

        def desactivar():
            if (registro := seleccion()) is not None:
                dialogo_desactivar_programacion(request, recargar, registro, jornadas(registro))

        with ui.row().classes('w-full gap-2 flex-wrap'):
            for titulo, icono, accion in [
                ('Consultar', 'visibility', consultar),
                ('Modificar', 'edit', modificar),
                ('Desactivar', 'block', desactivar),
            ]:
                ui.button(titulo, icon=icono, on_click=accion).props('outline no-caps') \
                    .classes('text-[#164875] rounded-lg')


def dialogo_publicar(request, recargar, dia, *, id_periodo=None, tramo=None):
    preseleccion = {'fecha_uso': dia.isoformat(), 'id_periodo': id_periodo}
    if tramo:
        preseleccion.update(hora_inicio=hhmm(tramo.inicio), hora_fin=hhmm(tramo.fin))

    def abrir(tipo):
        dlg.close()
        formulario_programacion(request, recargar, tipo, preseleccion=preseleccion)

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-5 gap-3'):
        ui.label('Publicar programación').classes('text-lg font-bold text-[#09234B]')
        franja = f' · {hhmm(tramo.inicio)}–{hhmm(tramo.fin)}' if tramo else ''
        ui.label(f'{dia:%d/%m/%Y}{franja}').classes('text-sm text-slate-600')
        with ui.element('div').classes('grid grid-cols-1 sm:grid-cols-2 gap-2 w-full'):
            for tipo, (_, etiqueta, _, icono) in TIPOS.items():
                ui.button(etiqueta, icon=icono, on_click=lambda t=tipo: abrir(t)) \
                    .props('outline no-caps').classes('text-[#164875]')
        ui.button('Cerrar', on_click=dlg.close).props('flat no-caps').classes('self-end')
    dlg.open()


def _sugerir_reserva(dia, tramo, registro, ahora):
    if (tramo.tipo != 'libre' or registro['nombre_tipo'] != 'LIBRE' or not registro['permite_reserva']
            or dia < ahora.date()):
        return None
    inicio = max(tramo.inicio, a_minutos(registro['hora_inicio']))
    fin = min(tramo.fin, a_minutos(registro['hora_fin']))
    if dia == ahora.date():
        inicio = max(inicio, ahora.hour * 60 + ahora.minute + 1)
    if inicio >= fin:
        return None
    registro['franja_disponible'] = f'{hhmm(inicio)}–{hhmm(fin)}'
    return dict(fecha_uso=dia.isoformat(), hora_inicio=hhmm(inicio),
                hora_fin=hhmm(min(fin, inicio + MAXIMO_RESERVA_MINUTOS)))


def abrir_tramo(request, recargar, dia, tramo, id_periodo):
    if tramo.tipo == 'reservado' and tramo.referencia:
        dialogo_detalle_reserva(request, recargar, tramo.referencia, contextual=True)
        return
    try:
        exigir_administrador(request)
        if tramo.tipo == 'sin_programacion':
            dialogo_publicar(request, recargar, dia, id_periodo=id_periodo, tramo=tramo)
            return
        repo = RepositorioProgramacionesMySQL()
        filas = repo.listar_horarios(id_horario=tramo.referencia) if tramo.referencia else []
        if not filas:
            ui.notify('El bloque ya no está disponible. Actualiza el calendario.', type='warning')
            return
        registro = _vista_programacion(filas[0])
        tipo = next(t for t, nombre in TIPOS_BD.items() if nombre == registro['nombre_tipo'])
        jornadas = repo.listar_horarios(id_programacion=registro['id_programacion'])
    except (ValueError, ErrorMySQL, StopIteration):
        ui.notify('No se pudo consultar el bloque de programación.', type='warning')
        return

    horario = _sugerir_reserva(dia, tramo, registro, datetime.now(ZONA_PERU))
    dialogo_programacion(request, recargar, tipo, registro, jornadas, desde_calendario=True, horario=horario)


@ui.page('/admin/actividades')
def pagina_actividades(request: Request, vista: str = '', dia: str = '', tipo: str = 'TALLER'):
    if not crear_marco_admin('ACTIVIDADES'):
        return
    ui.query('.nicegui-content').style('min-height:0')
    try:
        fecha_inicial = date.fromisoformat(dia)
    except ValueError:
        fecha_inicial = datetime.now(ZONA_PERU).date()
    try:
        catalogo = RepositorioProgramacionesMySQL().listar_periodos()
    except ErrorMySQL:
        catalogo = []
        ui.notify('No se pudieron consultar los períodos académicos.', type='warning')
    periodos = {p['id_periodo']: p['nombre_periodo'] for p in catalogo}

    def nuevo_periodo():
        async def aplicar():
            if await guardar_como_admin(
                request, boton, CrearPeriodoAcademico().ejecutar,
                nombre=nombre.value, inicio=inicio.value, fin=fin.value,
            ):
                dlg.close()
                ui.navigate.to(request.url.path + ('?' + request.url.query if request.url.query else ''))

        with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-5 gap-3'):
            ui.label('Nuevo período académico').classes('text-lg font-bold text-[#09234B]')
            nombre = campo_texto('Nombre del período')
            inicio = campo_texto('Inicio', tipo='date')
            fin = campo_texto('Fin', tipo='date')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
                boton = ui.button('Guardar período', icon='save', on_click=aplicar).props('no-caps')
        dlg.open()

    with ui.column().classes('w-full max-w-[1600px] mx-auto px-3 md:px-5 py-4 gap-3'):
        with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
            titulo_pagina('ACTIVIDADES DEL POLIDEPORTIVO', 'event_note', icono_px='24px')
            ui.button('Nuevo período', icon='event_available', on_click=nuevo_periodo).props('outline no-caps')

        with ui.tabs().props('align=left no-caps inline-label dense').classes(
            'w-full text-[#164875] bg-white rounded-lg border border-slate-200'
        ) as tabs:
            calendario = ui.tab('calendario', label='Calendario', icon='calendar_month')
            listado = ui.tab('listado', label='Listado de programaciones', icon='view_list')
        vista_inicial = 'listado' if vista == 'listado' else 'calendario'
        with ui.tab_panels(tabs, value=vista_inicial, animated=False).classes(
            'w-full bg-transparent p-0'
        ) as paneles:
            with ui.tab_panel(calendario).classes('p-0'):
                espacio_calendario = ui.column().classes('w-full min-w-0 gap-0')
            with ui.tab_panel(listado).classes('p-0'):
                selector = ui.select({k: v[0] for k, v in TIPOS.items()},
                                     value=tipo if tipo in TIPOS else 'TALLER',
                                     label='Tipo de programación') \
                    .props('outlined dense').classes('w-52 mb-3')
                espacio_listado = ui.column().classes('w-full min-w-0 gap-0')

    recargar_calendario = None
    estado = {'calendario_pendiente': False, 'tipo_listado': None}

    def cambio_calendario(recargar):
        def actualizar():
            estado['tipo_listado'] = None
            recargar()
        return actualizar

    def cambio_listado():
        estado['calendario_pendiente'] = True

    def mostrar_vista():
        nonlocal recargar_calendario
        if paneles.value == 'listado':
            if estado['tipo_listado'] != selector.value:
                espacio_listado.clear()
                with espacio_listado:
                    panel_programacion(request, selector.value, periodos, cambio_listado)
                estado['tipo_listado'] = selector.value
        elif recargar_calendario is None:
            with espacio_calendario:
                recargar_calendario = panel_calendario_admin(
                    request, fecha_inicial, catalogo,
                    lambda d, t, recargar, p: abrir_tramo(request, cambio_calendario(recargar), d, t, p),
                    lambda d, recargar, **datos: dialogo_publicar(request, cambio_calendario(recargar), d, **datos),
                    lambda a, b, recargar, **datos: dialogo_horarios_libres(
                        request, cambio_calendario(recargar), catalogo, a, b, **datos,
                    ),
                )
            estado['calendario_pendiente'] = False
        elif estado['calendario_pendiente']:
            recargar_calendario()
            estado['calendario_pendiente'] = False

    selector.on_value_change(mostrar_vista)
    paneles.on_value_change(mostrar_vista)
    mostrar_vista()
