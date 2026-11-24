# Presentacion/admin/reportes_admin.py
# Reportes historicos: una consulta a la vez. Sin duplicar Dashboard ni Auditoria.

import asyncio
from datetime import datetime

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui
from aplicacion.reportes import reporte_implementos, reporte_programaciones, reporte_reservas
from Presentacion.componentes.agenda import nombre_programacion_visible
from dominio.reglas.periodos import PERIODOS, PERIODOS_REFERENCIA, fechas_de_consulta
from dominio.reglas.reservas import ZONA_PERU
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from Presentacion.sesion import exigir_administrador
from Presentacion.admin.layout_admin import crear_marco_admin
from Presentacion.componentes.estilos import BOTON_PRIMARIO
from Presentacion.componentes.exportaciones import preparar_csv, preparar_pdf
from Presentacion.componentes.filtros import campo_texto, fila_filtros
from Presentacion.componentes.tablas import tabla_datos
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina

AZUL = '#09234B'

def obtener_periodos_academicos():
    return RepositorioProgramacionesMySQL().listar_periodos()


def obtener_resultados(modulo, codigo_reporte, fecha_inicio, fecha_fin, criterio=''):
    consulta = {'Reservas': reporte_reservas, 'Programaciones': reporte_programaciones,
                'Implementos': reporte_implementos}[modulo]
    return consulta(codigo_reporte, fecha_inicio, fecha_fin, criterio)


# (Titulo, columnas: [(clave, etiqueta)], tipo de gráfico, eje X, series)
REPORTES = {
    'Reservas': {
        'por_fecha': ('Reservas por fecha de uso', [('fecha', 'FECHA'), ('reservas', 'RESERVAS')], 'line', 'fecha', ['reservas']),
        'estados': ('Reservas por estado', [('estado', 'ESTADO'), ('reservas', 'RESERVAS')], 'bar', 'estado', ['reservas']),
        'tipo_usuario': ('Reservas por tipo de usuario', [('tipo_usuario', 'TIPO DE USUARIO'), ('reservas', 'RESERVAS')], 'bar', 'tipo_usuario', ['reservas']),
        'escuelas_reservas': ('Reservas por escuela profesional', [('escuela', 'ESCUELA'), ('reservas', 'RESERVAS')], 'bar', 'escuela', ['reservas']),
        'cupos': ('Cupo por usuario y semana completa', [('semana', 'SEMANA'), ('codigo', 'CÓDIGO'), ('usuario', 'TITULAR'), ('reservas', 'RESERVAS REGISTRADAS'), ('minutos', 'MINUTOS CONSUMIDOS'), ('saldo', 'SALDO EN MINUTOS')], None, None, []),
        'dias': ('Utilización por día de semana', [('dia', 'DÍA'), ('reservas', 'RESERVAS FINALIZADAS'), ('horas', 'HORAS DE USO')], 'bar', 'dia', ['reservas']),
        'horarios': ('Horarios de mayor demanda', [('horario', 'HORARIO'), ('reservas', 'RESERVAS')], 'bar', 'horario', ['reservas']),
        'escuelas': ('Utilización por escuela profesional', [('escuela', 'ESCUELA'), ('reservas', 'RESERVAS FINALIZADAS')], 'bar', 'escuela', ['reservas']),
        'usuarios': ('Usuarios más frecuentes', [('codigo', 'CÓDIGO'), ('usuario', 'USUARIO'), ('escuela', 'ESCUELA'), ('reservas', 'RESERVAS FINALIZADAS')], None, None, []),
        'ocupacion': ('Porcentaje de ocupación', [('fecha', 'FECHA'), ('horas_habilitadas', 'HORAS HABILITADAS'), ('horas_utilizadas', 'HORAS UTILIZADAS'), ('porcentaje', 'OCUPACIÓN %')], 'line', 'fecha', ['porcentaje']),
        'incidencias': ('Cancelaciones e inasistencias', [('periodo', 'PERÍODO'), ('cancelaciones', 'CANCELACIONES'), ('inasistencias', 'INASISTENCIAS')], 'bar', 'periodo', ['cancelaciones', 'inasistencias']),
        'ciclos': ('Comparación entre períodos académicos', [('periodo', 'PERÍODO ACADÉMICO'), ('reservas', 'RESERVAS FINALIZADAS'), ('horas', 'HORAS UTILIZADAS')], 'bar', 'periodo', ['reservas']),
        'historial': ('Historial de reservas por usuario', [('fecha', 'FECHA'), ('codigo_reserva', 'RESERVA'), ('horario', 'HORARIO'), ('estado', 'ESTADO')], None, None, []),
    },
    'Programaciones': {
        'horas': ('Horas programadas por tipo de actividad',
                  [('tipo', 'TIPO'), ('programaciones', 'PROGRAMACIONES'), ('jornadas', 'JORNADAS'), ('horas', 'HORAS PROGRAMADAS')],
                  'bar', 'tipo', ['horas']),
        'jornadas': ('Jornadas publicadas',
                     [('fecha_uso', 'FECHA'), ('nombre_visible', 'PROGRAMACIÓN'), ('nombre_tipo', 'TIPO'),
                      ('horario', 'HORARIO'), ('nombre_periodo', 'PERÍODO'), ('responsable', 'RESPONSABLE')],
                     None, None, []),
    },
    'Implementos': {
        'inventario': ('Inventario actual por categoría y tipo',
                       [('categoria', 'CATEGORÍA'), ('implemento', 'IMPLEMENTO'), ('total', 'ACTIVAS'),
                        ('disponibles', 'DISPONIBLES'), ('prestadas', 'PRESTADAS'), ('no_habilitadas', 'NO HABILITADAS')],
                       None, None, []),
        'solicitados': ('Implementos más solicitados',
                         [('implemento', 'IMPLEMENTO'), ('categoria', 'CATEGORÍA'), ('solicitadas', 'UNIDADES SOLICITADAS')],
                         'bar', 'implemento', ['solicitadas']),
        'pendientes': ('Solicitudes pendientes del período',
                      [('id_operacion', 'OPERACIÓN'), ('solicitante', 'TITULAR'), ('vinculo', 'MODALIDAD / RESERVA'),
                       ('fecha_inicio_prevista', 'RECOJO PREVISTO'), ('total_implementos', 'UNIDADES')],
                      None, None, []),
        'modalidades': ('Préstamos por modalidad', [('modalidad', 'MODALIDAD'), ('operaciones', 'OPERACIONES'), ('reservas', 'RESERVAS ASOCIADAS'), ('solicitadas', 'UNIDADES SOLICITADAS'), ('entregadas', 'UNIDADES ENTREGADAS')], None, None, []),
        'por_reserva': ('Materiales prestados por reserva', [('reserva', 'RESERVA'), ('categoria', 'CATEGORÍA'), ('material', 'MATERIAL'), ('operaciones', 'OPERACIONES'), ('solicitadas', 'UNIDADES SOLICITADAS'), ('entregadas', 'UNIDADES ENTREGADAS')], None, None, []),
        'implementos': ('Implementos más entregados', [('implemento', 'IMPLEMENTO'), ('categoria', 'CATEGORÍA'), ('prestamos', 'UNIDADES ENTREGADAS')], 'bar', 'implemento', ['prestamos']),
        'escuelas': ('Préstamos por escuela profesional', [('escuela', 'ESCUELA'), ('prestamos', 'PRÉSTAMOS')], 'bar', 'escuela', ['prestamos']),
        'usuarios': ('Usuarios con más préstamos', [('codigo', 'CÓDIGO'), ('usuario', 'USUARIO'), ('prestamos', 'PRÉSTAMOS')], None, None, []),
        'devoluciones': ('Entregas y devoluciones por período', [('periodo', 'PERÍODO'), ('prestamos_entregados', 'PRÉSTAMOS ENTREGADOS'),
                             ('prestamos_devueltos', 'PRÉSTAMOS DEVUELTOS'), ('entregados', 'UNIDADES ENTREGADAS'),
                             ('devueltos', 'UNIDADES DEVUELTAS')], 'bar', 'periodo', ['prestamos_entregados', 'prestamos_devueltos']),
        'movimientos': ('Altas y bajas de implementos', [('periodo', 'PERÍODO'), ('altas', 'ALTAS'), ('bajas', 'BAJAS')], 'bar', 'periodo', ['altas', 'bajas']),
        'atrasos': ('Préstamos con devolución vencida', [('id_operacion', 'OPERACIÓN'), ('usuario', 'USUARIO'), ('fecha_prevista', 'FECHA PREVISTA'), ('dias_atraso', 'DÍAS DE ATRASO')], None, None, []),
        'historial': ('Historial por código patrimonial', [('fecha', 'FECHA'), ('operacion', 'OPERACIÓN'), ('movimiento', 'MOVIMIENTO'), ('condicion', 'CONDICIÓN FÍSICA')], None, None, []),
    },
}


INTERVALO_ACTUALIZACION = 60
MENSAJE_CONSULTAR = 'Pulsa Consultar para cargar el informe.'
REPORTES_INICIALES = {'Reservas': 'dias', 'Programaciones': 'horas', 'Implementos': 'implementos'}


def opciones_grafico(filas, columnas, tipo, eje, series):
    """ECharts, una gráfica por consulta; las tablas quedan para el detalle."""
    etiquetas = [str(f.get(eje, '')) for f in filas]
    es_horizontal = tipo == 'bar' and len(etiquetas) > 6
    categorias = {'type': 'category', 'data': etiquetas, 'axisLabel': {'fontSize': 10}}
    valores = {'type': 'value', 'min': 0, 'axisLabel': {'fontSize': 10}}
    if es_horizontal:
        categorias['axisLabel'].update({'width': 135, 'overflow': 'truncate'})
    else:
        categorias['axisLabel']['rotate'] = 20 if len(etiquetas) > 5 else 0
    if series == ['porcentaje']:
        valores['max'] = 100
        valores['axisLabel']['formatter'] = '{value}%'
    colores = ['#2563EB', '#D97706', '#16A34A']
    nombres = dict(columnas)
    return {
        'tooltip': {'trigger': 'axis'},
        'legend': {'show': len(series) > 1, 'top': 0},
        'grid': {'left': 160 if es_horizontal else 52, 'right': 20,
                 'top': 38 if len(series) > 1 else 22, 'bottom': 56},
        'xAxis': valores if es_horizontal else categorias,
        'yAxis': categorias if es_horizontal else valores,
        'series': [
            {'name': nombres.get(k, k), 'type': tipo, 'smooth': tipo == 'line',
             'barMaxWidth': 35, 'data': [f.get(k, 0) or 0 for f in filas],
             'itemStyle': {'color': colores[i % len(colores)]}}
            for i, k in enumerate(series)
        ],
    }


@ui.page('/admin/reportes')
def pagina_reportes_admin(request: Request, modulo: str = ''):
    if not crear_marco_admin('REPORTES'):
        return
    try:
        catalogo = obtener_periodos_academicos()
    except (ErrorMySQL, ValueError):
        catalogo = []
        ui.notify('No se pudieron consultar los períodos.', type='warning')
    ciclos = {str(p['id_periodo']): p['nombre_periodo'] for p in catalogo}
    hoy = datetime.now(ZONA_PERU).date().isoformat()
    inicial = modulo if modulo in REPORTES else 'Reservas'
    estado = {'filas': [], 'modulo': inicial, 'codigo': REPORTES_INICIALES[inicial],
              'consulta': None, 'sin_datos': MENSAJE_CONSULTAR}

    with ui.column().classes('w-full p-4 md:p-6 gap-3'):
        titulo_pagina('REPORTES HISTÓRICOS', 'assessment', icono_px='24px',
                      responsive=True)

        with tarjeta_seccion():
            modulo = ui.toggle({'Reservas': 'Reservas', 'Programaciones': 'Programaciones',
                                'Implementos': 'Préstamos e implementos'}, value=inicial) \
                .props('no-caps unelevated').classes('max-w-full')
            with fila_filtros(gap='gap-2'):
                reporte = ui.select({k: v[0] for k, v in REPORTES[inicial].items()},
                                    value=REPORTES_INICIALES[inicial], label='Tipo de reporte') \
                    .props('outlined dense options-dense').classes('w-72 max-w-full')
                periodo = ui.select(list(PERIODOS), value='Semana', label='Período') \
                    .props('outlined dense').classes('w-48')
                referencia = campo_texto('Fecha de referencia', hoy, tipo='date', clases='w-44')
                ciclo = ui.select(ciclos, label='Ciclo académico') \
                    .props('outlined dense').classes('w-44')
                desde = campo_texto('Desde', hoy, tipo='date', clases='w-40')
                hasta = campo_texto('Hasta', hoy, tipo='date', clases='w-40')
                criterio = ui.input('Código institucional o patrimonial') \
                    .props('outlined dense').classes('w-64')
                boton_consultar = ui.button('Consultar', icon='search', on_click=lambda: consultar()) \
                    .props('no-caps unelevated').classes(BOTON_PRIMARIO)
            with ui.row().classes('w-full items-center gap-x-3 gap-y-0 flex-wrap'):
                rango = ui.label().classes('text-xs text-slate-600')
                actualizacion = ui.label().classes('text-xs text-slate-600')

        @ui.refreshable
        def mostrar_resultado():
            metadata = REPORTES[estado['modulo']][estado['codigo']]
            titulo, columnas, tipo, eje, series = metadata
            filas = estado['filas']
            with tarjeta_seccion(padding='p-3 md:p-4'):
                with ui.row().classes('w-full justify-between items-center gap-2'):
                    ui.label(titulo.upper()).classes('text-sm font-bold text-[#09234B]')
                    with ui.row().classes('items-center justify-end gap-2 flex-wrap'):
                        ui.label('Exportar').classes(
                            'text-sm font-semibold text-[#09234B] whitespace-nowrap'
                        )
                        def exportar(pdf=False):
                            if not filas or estado['filas'] is not filas:
                                return
                            try:
                                exigir_administrador(request)
                                archivo = (preparar_pdf(titulo, columnas, filas, rango.text)
                                           if pdf else preparar_csv(columnas, filas))
                            except (ErrorMySQL, ValueError, ImportError):
                                ui.notify('No se pudo exportar el reporte.', type='warning')
                                return
                            extension = 'pdf' if pdf else 'csv'
                            ui.download.content(archivo, f'reporte_{estado["codigo"]}.{extension}')

                        exportar_excel = ui.button('Excel', icon='table_view', on_click=lambda: exportar()) \
                            .props('outline dense no-caps').classes('text-[#164875]')
                        exportar_pdf = ui.button('PDF', icon='picture_as_pdf', on_click=lambda: exportar(pdf=True)) \
                            .props('outline dense no-caps').classes('text-[#164875]')
                        if not filas:
                            exportar_excel.disable()
                            exportar_pdf.disable()

                if filas and tipo:
                    ui.echart(opciones_grafico(filas, columnas, tipo, eje, series)) \
                        .classes('w-full h-[260px]')

                definicion = [
                    {'name': clave, 'label': etiqueta, 'field': clave,
                     'align': 'left' if i == 0 else 'center'}
                    for i, (clave, etiqueta) in enumerate(columnas)
                ]
                valores = [dict(registro, _fila=i) for i, registro in enumerate(filas, start=1)]
                tabla_datos(definicion, valores, '_fila', paginacion=10,
                            seleccion=None, sin_datos=estado['sin_datos'],
                            clases='w-full')

        def limpiar_resultado():
            estado.update(filas=[], consulta=None, sin_datos=MENSAJE_CONSULTAR)
            rango.set_text('')
            actualizacion.set_text('')
            mostrar_resultado.refresh()

        def ajustar_controles():
            opcion, codigo = periodo.value, reporte.value
            historico = codigo != 'inventario'
            periodo.set_visibility(historico)
            referencia.set_visibility(historico and opcion in PERIODOS_REFERENCIA)
            ciclo.set_visibility(historico and opcion == 'Período académico')
            desde.set_visibility(historico and opcion == 'Personalizado')
            hasta.set_visibility(historico and opcion == 'Personalizado')
            criterio.set_visibility(codigo == 'historial')
            criterio.props('label="Código institucional"' if modulo.value == 'Reservas' else 'label="Código patrimonial"')
            estado.update(modulo=modulo.value, codigo=codigo)
            limpiar_resultado()

        def cambiar_modulo():
            seleccionado = modulo.value
            reporte.set_options({k: v[0] for k, v in REPORTES[seleccionado].items()},
                                value=REPORTES_INICIALES[seleccionado])
            if estado['modulo'] != seleccionado:
                ajustar_controles()

        async def consultar():
            if not boton_consultar.enabled:
                return
            codigo = reporte.value
            inicio = fin = None
            if codigo != 'inventario':
                try:
                    inicio, fin = fechas_de_consulta(periodo.value, referencia.value,
                                                    desde.value, hasta.value, ciclo.value, catalogo)
                except (ValueError, TypeError):
                    ui.notify('Selecciona un período válido.', type='warning')
                    return
            if codigo == 'historial' and not (criterio.value or '').strip():
                ui.notify('Ingresa el código para consultar el historial.', type='warning')
                return
            estado['consulta'] = modulo.value, codigo, inicio, fin, (criterio.value or '').strip()
            await actualizar_consulta()

        async def actualizar_consulta():
            consulta = estado['consulta']
            if consulta is None or not boton_consultar.enabled:
                return
            modo, codigo, inicio, fin, texto = consulta
            boton_consultar.disable()
            try:
                await asyncio.to_thread(exigir_administrador, request)
                filas = await asyncio.to_thread(obtener_resultados, modo, codigo, inicio, fin, texto)
            except (ErrorMySQL, ValueError) as exc:
                if boton_consultar.is_deleted or estado['consulta'] is not consulta:
                    return
                if isinstance(exc, ValueError):
                    estado['consulta'] = None
                estado.update(filas=[], sin_datos='No se pudo consultar el informe.')
                actualizacion.set_text('')
                mostrar_resultado.refresh()
                return
            finally:
                if not boton_consultar.is_deleted:
                    boton_consultar.enable()

            if boton_consultar.is_deleted or estado['consulta'] is not consulta:
                return
            if modo == 'Programaciones' and codigo == 'jornadas':
                filas = [dict(f, nombre_visible=nombre_programacion_visible(f['nombre_programacion'])) for f in filas]
            sin_datos = ('En este período todavía no hay reservas finalizadas.'
                         if modo == 'Reservas' and codigo == 'dias'
                         else 'No hay resultados para los filtros seleccionados.')
            if codigo == 'inventario':
                etiqueta = 'Inventario actual'
            else:
                etiqueta = f'{inicio:%d/%m/%Y} – {fin:%d/%m/%Y}' if inicio and fin else 'Todo el historial'
            rango.set_text(etiqueta)
            actualizacion.set_text(f'Actualizado a las {datetime.now(ZONA_PERU):%H:%M:%S} · Cada 60 s')
            if filas != estado['filas'] or sin_datos != estado['sin_datos']:
                estado.update(filas=filas, sin_datos=sin_datos)
                mostrar_resultado.refresh()

        modulo.on_value_change(cambiar_modulo)
        for control in (reporte, periodo):
            control.on_value_change(ajustar_controles)
        for control in (referencia, ciclo, desde, hasta, criterio):
            control.on_value_change(limpiar_resultado)
        mostrar_resultado()
        ajustar_controles()
        ui.timer(INTERVALO_ACTUALIZACION, actualizar_consulta, immediate=False)
