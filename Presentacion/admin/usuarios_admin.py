# Presentacion/admin/usuarios_admin.py
# Vista administrativa de usuarios e inasistencias (PoliReserva UNAB V9).
from mysql.connector import Error as ErrorMySQL
from nicegui import ui
from infraestructura.persistencia.usuarios_mysql import RepositorioUsuariosMySQL
from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL
from Presentacion.admin.layout_admin import crear_marco_admin
from Presentacion.componentes.dialogos import grilla_detalle
from Presentacion.componentes.filtros import (boton_limpiar_filtros, fila_filtros)
from Presentacion.componentes.tablas import (fila_seleccionada, slot_badge_mapa,
                                             tabla_datos)
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina

AZUL = '#09234B'

COLUMNAS_USUARIOS = [
    {'name': 'codigo_institucional', 'label': 'CÓDIGO INSTITUCIONAL', 'field': 'codigo_institucional', 'align': 'left'},
    {'name': 'nombre_completo', 'label': 'USUARIO', 'field': 'nombre_completo', 'align': 'left'},
    {'name': 'correo_institucional', 'label': 'CORREO INSTITUCIONAL', 'field': 'correo_institucional', 'align': 'left'},
    {'name': 'tipo_usuario', 'label': 'TIPO', 'field': 'tipo_usuario', 'align': 'center'},
    {'name': 'escuela', 'label': 'ESCUELA / ÁREA', 'field': 'escuela', 'align': 'left'},
    {'name': 'perfil', 'label': 'PERFIL', 'field': 'perfil', 'align': 'center'},
    {'name': 'estado', 'label': 'ESTADO', 'field': 'estado', 'align': 'center'},
]

COLUMNAS_INASISTENCIAS = [
    {'name': 'codigo_reserva', 'label': 'RESERVA', 'field': 'codigo_reserva', 'align': 'left'},
    {'name': 'solicitante', 'label': 'USUARIO', 'field': 'solicitante', 'align': 'left'},
    {'name': 'codigo_institucional', 'label': 'CÓDIGO INSTITUCIONAL', 'field': 'codigo_institucional', 'align': 'left'},
    {'name': 'escuela', 'label': 'ESCUELA / ÁREA', 'field': 'escuela', 'align': 'left'},
    {'name': 'fecha_uso', 'label': 'FECHA', 'field': 'fecha_uso', 'align': 'center'},
    {'name': 'horario', 'label': 'HORARIO', 'field': 'horario', 'align': 'center'},
]


def obtener_usuarios():
    filas = RepositorioUsuariosMySQL().listar_usuarios()
    return [dict({k: v for k, v in u.items() if k not in ('google_sub', 'ultimo_acceso')}, nombre_completo=' '.join(x for x in (u['nombres'], u['apellidos']) if x),
                 perfil='Completo' if u['perfil_completo'] else 'Pendiente',
                 estado='Activo' if u['usuario_activo'] and u['perfil_activo'] and u['rol_activo'] else 'Inactivo')
            for u in filas]


def obtener_inasistencias():
    return [dict(r, solicitante=' '.join(x for x in (r['nombres'], r['apellidos']) if x),
                 horario=f"{r['hora_inicio']} – {r['hora_fin']}")
            for r in RepositorioReservasMySQL().listar_administracion(estado='INASISTENCIA')]


@ui.page('/admin/usuarios')
def pagina_usuarios_admin():
    if not crear_marco_admin('USUARIOS'):
        return

    try:
        usuarios, inasistencias = obtener_usuarios(), obtener_inasistencias()
    except ErrorMySQL:
        usuarios, inasistencias = [], []
        ui.notify('No se pudieron consultar los usuarios y sus inasistencias.', type='warning')

    with ui.column().classes('w-full p-4 md:p-6 gap-3'):
        titulo_pagina('GESTIÓN DE USUARIOS', 'people', icono_px='25px',
                      responsive=True)

        with ui.tabs().classes('text-[#164875] font-semibold') as tabs:
            tab_usuarios = ui.tab('USUARIOS', icon='people')
            tab_inasistencias = ui.tab('INASISTENCIAS', icon='event_busy')

        with ui.tab_panels(tabs, value=tab_usuarios).classes('w-full bg-transparent p-0'):
            with ui.tab_panel(tab_usuarios).classes('p-0'):
                with tarjeta_seccion():
                    with fila_filtros():
                        buscar = ui.input('Buscar por nombre, DNI, código o correo') \
                            .props('outlined dense clearable debounce=250') \
                            .classes('flex-[2] min-w-[230px]')
                        tipo = ui.select(
                            ['Todos', 'ESTUDIANTE', 'DOCENTE', 'ADMINISTRATIVO'],
                            value='Todos', label='Tipo de usuario'
                        ).props('outlined dense').classes('min-w-[170px] flex-1')
                        perfil = ui.select(
                            ['Todos', 'Completo', 'Incompleto'],
                            value='Todos', label='Perfil'
                        ).props('outlined dense').classes('min-w-[145px] flex-1')
                        estado = ui.select(
                            ['Todos', 'Activo', 'Inactivo'],
                            value='Todos', label='Estado'
                        ).props('outlined dense').classes('min-w-[125px] flex-1')
                        boton_limpiar_filtros(lambda: limpiar_usuarios())

                    tabla = tabla_datos(
                        COLUMNAS_USUARIOS, usuarios, 'id_usuario', paginacion=10,
                        sin_datos='No hay usuarios para mostrar',
                    )
                    slot_badge_mapa(tabla, 'perfil', {'Completo': 'green-7'},
                                    defecto='amber-8', vacio='—')
                    slot_badge_mapa(tabla, 'estado', {'Activo': 'blue-7'},
                                    defecto='grey-7', vacio='—')

                    def filtrar_usuarios():
                        texto = str(buscar.value or '').strip().lower()
                        tabla.rows = [u for u in usuarios if (
                            (not texto or texto in ' '.join(str(u.get(k) or '') for k in (
                                'nombre_completo', 'dni', 'codigo_institucional', 'correo_institucional'
                            )).lower())
                            and (tipo.value == 'Todos' or u.get('tipo_usuario') == tipo.value)
                            and (perfil.value == 'Todos' or u.get('perfil') == perfil.value)
                            and (estado.value == 'Todos' or u.get('estado') == estado.value)
                        )]
                        tabla.selected.clear()
                        tabla.update()

                    def limpiar_usuarios():
                        buscar.value = ''
                        tipo.value = 'Todos'
                        perfil.value = 'Todos'
                        estado.value = 'Todos'
                        filtrar_usuarios()

                    for control in (buscar, tipo, perfil, estado):
                        control.on_value_change(filtrar_usuarios)

                    def consultar_usuario():
                        u = fila_seleccionada(tabla, 'Selecciona un usuario.')
                        if u is None:
                            return
                        campos = [
                            ('Nombre completo', 'nombre_completo'), ('DNI', 'dni'),
                            ('Código institucional', 'codigo_institucional'),
                            ('Correo institucional', 'correo_institucional'),
                            ('Teléfono', 'telefono'), ('Tipo de usuario', 'tipo_usuario'),
                            ('Escuela / área', 'escuela'), ('Rol de acceso', 'rol'),
                            ('Perfil', 'perfil'), ('Estado', 'estado'),
                            ('Fecha de registro', 'fecha_registro'),
                            ('Último acceso', 'ultimo_acceso'),
                        ]
                        with ui.dialog() as dialogo, ui.card().classes('w-full max-w-xl p-5 gap-3'):
                            with ui.row().classes('w-full items-center justify-between'):
                                ui.label('DETALLE DEL USUARIO').classes('text-lg font-bold text-[#09234B]')
                                ui.button(icon='close', on_click=dialogo.close).props('flat round dense')
                            grilla_detalle(u, campos)
                            with ui.row().classes('w-full justify-end'):
                                ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps')
                        dialogo.open()

                    with ui.row().classes('w-full justify-end'):
                        ui.button('Consultar perfil', icon='visibility', on_click=consultar_usuario) \
                            .props('no-caps').classes('bg-[#164875] text-white rounded-lg')

            with ui.tab_panel(tab_inasistencias).classes('p-0'):
                with tarjeta_seccion():
                    with fila_filtros():
                        buscar_inasistencia = ui.input('Usuario, código institucional o reserva') \
                            .props('outlined dense clearable debounce=250') \
                            .classes('flex-[2] min-w-[230px]')
                        fecha_inasistencia = ui.input('Fecha de uso') \
                            .props('outlined dense type=date') \
                            .classes('min-w-[170px] flex-1')
                        boton_limpiar_filtros(lambda: limpiar_inasistencias())

                    tabla_inasistencias = tabla_datos(
                        COLUMNAS_INASISTENCIAS, inasistencias, 'id_reserva',
                        paginacion=10, seleccion=None,
                        sin_datos='No hay inasistencias para mostrar',
                    )

                    def filtrar_inasistencias():
                        texto = str(buscar_inasistencia.value or '').strip().lower()
                        fecha = str(fecha_inasistencia.value or '')
                        tabla_inasistencias.rows = [r for r in inasistencias if (
                            (not texto or texto in ' '.join(str(r.get(k) or '') for k in (
                                'codigo_reserva', 'solicitante', 'codigo_institucional'
                            )).lower())
                            and (not fecha or str(r.get('fecha_uso') or '') == fecha)
                        )]
                        tabla_inasistencias.update()

                    def limpiar_inasistencias():
                        buscar_inasistencia.value = ''
                        fecha_inasistencia.value = ''
                        filtrar_inasistencias()

                    buscar_inasistencia.on_value_change(filtrar_inasistencias)
                    fecha_inasistencia.on_value_change(filtrar_inasistencias)
