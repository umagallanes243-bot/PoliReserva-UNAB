# Presentacion/admin/inventario_admin.py
# Interfaz administrativa de implementos individuales (MySQL V9).

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui
from aplicacion.casos_uso.implementos.crear_categoria_implemento import CrearCategoriaImplemento
from aplicacion.casos_uso.implementos.dar_de_baja_implemento import DarDeBajaImplemento
from aplicacion.casos_uso.implementos.modificar_implemento import ModificarImplemento
from aplicacion.casos_uso.implementos.registrar_implemento import RegistrarImplemento
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from Presentacion.admin.layout_admin import crear_marco_admin, guardar_como_admin
from Presentacion.componentes.filtros import fila_filtros
from Presentacion.componentes.tablas import (fila_seleccionada, slot_badge_mapa,
                                             tabla_datos)
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina
from Presentacion.sesion import exigir_administrador
from dominio.reglas.implementos import texto_buscable


COLUMNAS = [
    {'name': 'codigo_patrimonial', 'label': 'CÓDIGO PATRIMONIAL', 'field': 'codigo_patrimonial', 'align': 'left'},
    {'name': 'nombre_implemento', 'label': 'IMPLEMENTO', 'field': 'nombre_implemento', 'align': 'left'},
    {'name': 'categoria', 'label': 'CATEGORÍA', 'field': 'categoria', 'align': 'left'},
    {'name': 'aptitud', 'label': 'APTITUD', 'field': 'aptitud', 'align': 'center'},
    {'name': 'disponibilidad', 'label': 'DISPONIBILIDAD', 'field': 'disponibilidad', 'align': 'center'},
    {'name': 'descripcion', 'label': 'DESCRIPCIÓN', 'field': 'descripcion', 'align': 'left'},
]


@ui.page('/admin/inventario')
def pagina_inventario(request: Request):
    if not crear_marco_admin('INVENTARIO'):
        return

    repo = RepositorioImplementosMySQL()
    try:
        implementos, categorias = repo.listar_implementos(incluir_bajas=True), repo.listar_categorias()
    except ErrorMySQL:
        implementos, categorias = [], []
        ui.notify('No se pudo cargar el inventario.', type='warning')

    def recargar():
        try:
            implementos[:] = repo.listar_implementos(incluir_bajas=True)
            categorias[:] = repo.listar_categorias()
            categoria.set_options(['Todas', *(c['nombre_categoria'] for c in categorias)], value='Todas')
            filtrar()
        except ErrorMySQL:
            ui.notify('No se pudo actualizar el inventario.', type='warning')

    def nueva_categoria():
        async def aplicar():
            if await guardar_como_admin(
                request, boton, CrearCategoriaImplemento(repo).ejecutar, nombre=nombre.value,
            ):
                dlg.close()
                recargar()

        with ui.dialog() as dlg, ui.card().classes('w-full max-w-md p-5 gap-3'):
            ui.label('Nueva categoría').classes('text-lg font-bold text-[#09234B]')
            nombre = ui.input('Nombre').props('outlined dense maxlength=50').classes('w-full')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
                boton = ui.button('Guardar categoría', icon='save', on_click=aplicar).props('no-caps')
        dlg.open()

    with ui.column().classes('w-full p-5 gap-4'):
        with ui.row().classes('w-full items-center justify-between gap-3 flex-wrap'):
            titulo_pagina('GESTIÓN DE INVENTARIO', 'inventory_2', icono_px='24px')
            ui.button('Nueva categoría', icon='category', on_click=nueva_categoria).props('outline no-caps')
            btn_nuevo = ui.button('Nuevo implemento', icon='add').props('no-caps') \
                .classes('bg-[#164875] text-white font-semibold rounded-lg')

        with tarjeta_seccion():
            with fila_filtros():
                buscar = ui.input(placeholder='Nombre o código patrimonial') \
                    .props('outlined dense clearable debounce=250') \
                    .classes('flex-1 min-w-[230px]')
                categoria = ui.select(['Todas', *(c['nombre_categoria'] for c in categorias)], value='Todas', label='Categoría') \
                    .props('outlined dense').classes('w-44')
                aptitud = ui.select(['Todas', 'Apto', 'No apto'], value='Todas', label='Aptitud') \
                    .props('outlined dense').classes('w-36')
                disponibilidad = ui.select(
                    ['Todas', 'Disponible', 'Prestado', 'No disponible', 'Baja'],
                    value='Todas', label='Disponibilidad',
                ).props('outlined dense').classes('w-44')
                limpiar = ui.button('Limpiar', icon='filter_alt_off') \
                    .props('flat no-caps').classes('text-[#164875]')

            tabla = tabla_datos(
                COLUMNAS, implementos, 'id_implemento', paginacion=10,
                props='flat bordered',
            )
            slot_badge_mapa(tabla, 'aptitud', {'Apto': 'green-7'},
                            defecto='deep-orange-7', vacio='—')
            slot_badge_mapa(tabla, 'disponibilidad',
                            {'Disponible': 'blue-7', 'Prestado': 'amber-9'},
                            defecto='grey-7', vacio='—')

        def filtrar():
            texto = texto_buscable(buscar.value).strip()
            tabla.rows = [i for i in implementos if (
                texto in texto_buscable(f"{i.get('nombre_implemento', '')} {i.get('codigo_patrimonial', '')}")
                and (categoria.value == 'Todas' or i.get('categoria') == categoria.value)
                and (aptitud.value == 'Todas' or i.get('aptitud') == aptitud.value)
                and (disponibilidad.value == 'Todas' or i.get('disponibilidad') == disponibilidad.value)
            )]
            tabla.selected.clear()
            tabla.update()

        for control in (buscar, categoria, aptitud, disponibilidad):
            control.on_value_change(filtrar)

        def limpiar_filtros():
            buscar.value = ''
            categoria.value = 'Todas'
            aptitud.value = 'Todas'
            disponibilidad.value = 'Todas'
            filtrar()

        limpiar.on('click', limpiar_filtros)

        def seleccionado():
            fila = fila_seleccionada(tabla, 'Selecciona un implemento de la tabla.')
            return next((i for i in tabla.rows if fila and i['id_implemento'] == fila.get('id_implemento')), None)

        def formulario(modo, item=None):
            item = item or {}
            editable = modo != 'Consultar'
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-5 gap-3'):
                with ui.row().classes('w-full justify-between items-center'):
                    ui.label(f'{modo} implemento').classes('text-lg font-bold text-[#09234B]')
                    ui.button(icon='close', on_click=dialog.close).props('flat round dense')

                campo_codigo = ui.input(
                    'Código patrimonial', value=item.get('codigo_patrimonial', '')
                ).props('outlined dense').classes('w-full')
                campo_nombre = ui.input(
                    'Nombre del implemento', value=item.get('nombre_implemento', '')
                ).props('outlined dense').classes('w-full')
                campo_categoria = ui.select(
                    options={str(c.get('id_categoria')): c.get('nombre_categoria') for c in categorias},
                    value=str(item.get('id_categoria')) if item.get('id_categoria') is not None else None,
                    label='Categoría',
                ).props('outlined dense').classes('w-full')
                campo_descripcion = ui.textarea(
                    'Descripción (opcional)', value=item.get('descripcion') or ''
                ).props('outlined autogrow').classes('w-full')
                campo_aptitud = ui.switch(
                    'Apto para préstamo', value=item.get('apto_prestamo', True)
                )
                if modo != 'Nuevo':
                    campo_codigo.disable()  # El código patrimonial no se cambia.
                if not editable:
                    for campo in (campo_nombre, campo_categoria, campo_descripcion, campo_aptitud):
                        campo.disable()

                if modo == 'Consultar':
                    ui.label(f"Disponibilidad: {item.get('disponibilidad', '—')}") \
                        .classes('text-sm text-slate-600')
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cerrar', on_click=dialog.close).props('flat no-caps')
                    if editable:
                        caso = ModificarImplemento(repo) if modo == 'Modificar' else RegistrarImplemento(repo)
                        identificador = {'id_implemento': item['id_implemento']} if modo == 'Modificar' else {}

                        async def guardar():
                            if await guardar_como_admin(
                                request, boton, caso.ejecutar, codigo=campo_codigo.value,
                                nombre=campo_nombre.value, categoria=campo_categoria.value,
                                descripcion=campo_descripcion.value, apto=campo_aptitud.value, **identificador,
                            ):
                                dialog.close()
                                recargar()

                        boton = ui.button('Guardar', on_click=guardar).props('no-caps').classes('bg-[#164875] text-white')
            dialog.open()

        btn_nuevo.on('click', lambda: formulario('Nuevo'))

        def consultar():
            item = seleccionado()
            if item:
                formulario('Consultar', item)

        def historial():
            item = seleccionado()
            if not item:
                return
            try:
                exigir_administrador(request)
                movimientos = repo.listar_movimientos(unidad=item['id_implemento'])
            except (ValueError, ErrorMySQL):
                ui.notify('No se pudo consultar el historial del implemento.', type='warning')
                return
            filas = [dict(m, fecha_movimiento=str(m['fecha_movimiento'])) for m in movimientos]
            columnas = [
                {'name': 'fecha_movimiento', 'label': 'FECHA', 'field': 'fecha_movimiento'},
                {'name': 'operacion', 'label': 'OPERACIÓN', 'field': 'operacion'},
                {'name': 'movimiento', 'label': 'MOVIMIENTO', 'field': 'movimiento'},
                {'name': 'condicion_fisica', 'label': 'CONDICIÓN', 'field': 'condicion_fisica'},
            ]
            with ui.dialog() as dialogo, ui.card().classes('w-full max-w-2xl p-5 gap-3'):
                ui.label(f"Movimientos · {item['codigo_patrimonial']}").classes('text-lg font-bold text-[#09234B]')
                tabla_datos(columnas, filas, 'id_movimiento', paginacion=6, seleccion=None,
                            sin_datos='Sin movimientos registrados.')
                ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps')
            dialogo.open()

        def modificar():
            item = seleccionado()
            if item and item['disponibilidad'] != 'Baja':
                formulario('Modificar', item)
            elif item:
                ui.notify('El implemento está dado de baja.', type='warning')

        def baja():
            item = seleccionado()
            if item and item['disponibilidad'] == 'Baja':
                ui.notify('El implemento ya está dado de baja.', type='warning')
                return
            if item:
                with ui.dialog() as dialog, ui.card().classes('p-5 gap-3 w-full max-w-md'):
                    ui.label('Dar de baja implemento').classes('text-lg font-bold text-[#09234B]')
                    ui.label(f"{item.get('codigo_patrimonial', '')} — {item.get('nombre_implemento', '')}")
                    motivo = ui.textarea('Motivo de baja').props('outlined autogrow').classes('w-full')
                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cerrar', on_click=dialog.close).props('flat no-caps')
                        async def aplicar_baja():
                            if await guardar_como_admin(
                                request, boton, DarDeBajaImplemento(repo).ejecutar,
                                unidad=item['id_implemento'], motivo=motivo.value,
                            ):
                                dialog.close()
                                recargar()

                        boton = ui.button('Confirmar baja', on_click=aplicar_baja).props('no-caps color=negative')
                dialog.open()

        with ui.row().classes('w-full gap-2 flex-wrap'):
            for texto, icono, accion in (
                ('Consultar', 'visibility', consultar),
                ('Ver movimientos', 'history', historial),
                ('Modificar', 'edit', modificar),
                ('Dar de baja', 'block', baja),
            ):
                ui.button(texto, icon=icono, on_click=accion).props('outline no-caps') \
                    .classes('text-[#164875] rounded-lg')
