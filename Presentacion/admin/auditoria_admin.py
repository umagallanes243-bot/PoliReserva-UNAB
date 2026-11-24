"""Bitácora administrativa de PoliReserva con acciones y referencias legibles."""

import json
from datetime import date, datetime, time, timedelta

from fastapi import Request
from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from dominio.reglas.implementos import agrupar_unidades, texto_buscable
from dominio.reglas.reservas import ZONA_PERU
from infraestructura.persistencia.conexion_mysql import consultar_auditoria
from Presentacion.admin.layout_admin import crear_marco_admin
from Presentacion.componentes.agenda import nombre_programacion_visible
from Presentacion.componentes.dialogos import grilla_detalle
from Presentacion.componentes.estilos import AZUL_TEXTO, BOTON_PRIMARIO
from Presentacion.componentes.filtros import boton_limpiar_filtros, campo_texto, fila_filtros
from Presentacion.componentes.tablas import slot_badge_color, tabla_datos
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina
from Presentacion.sesion import exigir_administrador

AREAS = {
    'tb_reservas': 'Reservas', 'tb_programaciones': 'Programaciones',
    'tb_periodos_academicos': 'Períodos académicos', 'tb_implementos': 'Inventario',
    'tb_categorias_implementos': 'Inventario', 'tb_operaciones_implementos': 'Préstamos y movimientos',
    'tb_usuarios': 'Usuarios', 'tb_perfiles': 'Perfiles',
}
ACCIONES = {
    'CONFIRMAR ASISTENCIA': 'Asistencia confirmada', 'FINALIZAR RESERVA': 'Reserva finalizada',
    'INASISTENCIA AUTOMATICA': 'Inasistencia registrada', 'DAR DE BAJA': 'Implemento dado de baja',
    'ENTREGAR': 'Préstamo entregado', 'DEVOLVER': 'Préstamo devuelto', 'COMPLETAR PERFIL': 'Perfil completado',
}
CREACIONES = {
    'tb_reservas': 'Reserva registrada', 'tb_operaciones_implementos': 'Solicitud de préstamo registrada',
    'tb_periodos_academicos': 'Período académico creado', 'tb_categorias_implementos': 'Categoría creada',
    'tb_usuarios': 'Usuario registrado', 'tb_perfiles': 'Perfil creado',
}
COLUMNAS = [
    {'name': clave, 'label': etiqueta, 'field': clave, 'align': 'left'}
    for clave, etiqueta in (
        ('fecha_visible', 'FECHA Y HORA'), ('accion', 'ACCIÓN'), ('actor', 'RESPONSABLE'),
        ('area', 'ÁREA'), ('referencia', 'REFERENCIA'),
    )
]


def datos_registrados(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return {}
    return valor if isinstance(valor, dict) else {}


def normalizar(registro):
    tabla = registro.get('tabla_afectada')
    accion = registro.get('accion')
    datos = datos_registrados(registro.get('detalle_cambio'))
    operacion = datos.get('operacion') if isinstance(datos.get('operacion'), str) else None
    datos_visibles = {}
    referencia = None
    titulo = ACCIONES.get(accion, 'Operación registrada')

    if tabla == 'tb_reservas':
        referencia = registro.get('codigo_reserva')
        if accion == 'CREAR':
            titulo = CREACIONES[tabla]
        elif accion == 'CANCELAR':
            titulo = 'Reserva cancelada'
        elif accion == 'MODIFICAR' or operacion == 'reprogramar':
            titulo = 'Reserva reprogramada'
        fecha = datos.get('fecha_uso') or registro.get('fecha_reserva')
        inicio = datos.get('hora_inicio') or registro.get('hora_reserva_inicio')
        fin = datos.get('hora_fin') or registro.get('hora_reserva_fin')
        try:
            dia = date.fromisoformat(str(fecha))
            primera, ultima = (time.fromisoformat(str(hora)) for hora in (inicio, fin))
        except ValueError:
            pass
        else:
            datos_visibles['Turno'] = f'{dia:%d/%m/%Y} · {primera:%H:%M}–{ultima:%H:%M}'

    elif tabla == 'tb_programaciones':
        titulo = {'modificar': 'Programación modificada', 'desactivar': 'Programación desactivada'}.get(
            operacion, 'Programación publicada' if accion == 'PROGRAMAR ACTIVIDAD' else titulo,
        )
        nombre = datos.get('nombre') if isinstance(datos.get('nombre'), str) else None
        referencia = nombre_programacion_visible(nombre or registro.get('nombre_programacion'))
        if isinstance(datos.get('horarios'), int):
            datos_visibles['Horarios publicados'] = str(datos['horarios'])
        if datos.get('inicio') and datos.get('fin'):
            try:
                primera, ultima = (date.fromisoformat(str(datos[clave])) for clave in ('inicio', 'fin'))
            except ValueError:
                pass
            else:
                datos_visibles['Fechas'] = f'{primera:%d/%m/%Y} – {ultima:%d/%m/%Y}'

    elif tabla == 'tb_operaciones_implementos':
        if registro.get('id_operacion'):
            referencia = f"Operación N.º {registro['id_operacion']}"
        if accion == 'CREAR':
            titulo = (CREACIONES[tabla] if registro.get('tipo_operacion') == 'PRESTAMO'
                      else 'Movimiento registrado')
        elif accion == 'CANCELAR':
            titulo = 'Solicitud cancelada'
        codigo = datos.get('codigo_reserva') or registro.get('codigo_reserva_prestamo')
        if codigo:
            datos_visibles['Reserva asociada'] = codigo
            referencia = f'{referencia} · {codigo}' if referencia else codigo
        motivo = datos.get('motivo_reserva')
        if motivo == 'CANCELADA':
            datos_visibles['Motivo'] = 'La reserva asociada se canceló.'
        elif motivo == 'INASISTENCIA':
            datos_visibles['Motivo'] = 'Se registró inasistencia en la reserva asociada.'
        unidades = registro.get('unidades') or ()
        if accion in ('ENTREGAR', 'DEVOLVER'):
            movimiento = 'SALIDA' if accion == 'ENTREGAR' else 'ENTRADA'
            unidades = [u for u in unidades if u['movimiento'] == movimiento and u['fecha_movimiento']]
            if unidades:
                codigos = sorted({u['codigo_patrimonial'] for u in unidades})
                datos_visibles['Códigos patrimoniales'] = ', '.join(codigos)
        if unidades:
            datos_visibles['Material'] = ', '.join(
                f'{cantidad} × {tipo}' for (_, tipo), cantidad in sorted(agrupar_unidades(unidades).items())
            )

    elif tabla == 'tb_implementos':
        if accion == 'REGISTRAR IMPLEMENTO':
            titulo = 'Implemento modificado' if operacion == 'modificar' else 'Implemento registrado'
        codigo = datos.get('codigo_patrimonial')
        referencia = registro.get('codigo_patrimonial') or (codigo if isinstance(codigo, str) else None)
        if registro.get('nombre_implemento'):
            datos_visibles['Implemento'] = registro['nombre_implemento']

    elif tabla in CREACIONES:
        if accion == 'CREAR':
            titulo = CREACIONES[tabla]
        referencia = registro.get('nombre_periodo') or registro.get('nombre_categoria')

    if registro.get('solicitante'):
        datos_visibles['Solicitante' if tabla != 'tb_perfiles' else 'Titular'] = registro['solicitante']
    estado = datos.get('estado_nuevo', datos.get('estado'))
    if estado in ('RESERVADA', 'CONFIRMADA', 'CANCELADA', 'INASISTENCIA', 'FINALIZADA',
                  'PENDIENTE', 'ENTREGADO', 'DEVUELTO', 'CANCELADO'):
        datos_visibles['Estado registrado'] = estado.capitalize()
    fecha = registro['fecha_operacion']
    fecha_visible = fecha.strftime('%d/%m/%Y %H:%M:%S') if isinstance(fecha, datetime) else str(fecha or '')
    actor = registro.get('actor') or ('Sistema' if registro.get('id_usuario_actor') is None else 'Sin nombre registrado')
    return {
        'id_auditoria': registro['id_auditoria'],
        'fecha': str(fecha or '')[:10],
        'fecha_visible': fecha_visible,
        'actor': actor,
        'accion': titulo,
        'area': AREAS.get(tabla, 'Otra actividad'),
        'referencia': referencia,
        'datos': datos_visibles,
    }


@ui.page('/admin/auditoria')
def pagina_auditoria_admin(request: Request):
    if not crear_marco_admin('AUDITORÍA'):
        return
    registros = []
    hoy = datetime.now(ZONA_PERU).date()

    with ui.column().classes('w-full p-4 md:p-6 gap-3'):
        with ui.row().classes('w-full items-center justify-between gap-2 flex-wrap'):
            titulo_pagina('HISTORIAL DE AUDITORÍA', 'manage_search', icono_px='25px', responsive=True)
            refrescar = ui.button(icon='refresh').props('flat round').tooltip('Actualizar auditoría')
        with tarjeta_seccion():
            with fila_filtros(gap='gap-2'):
                buscar = ui.input('Buscar responsable, acción o referencia').props(
                    'outlined dense clearable debounce=250'
                ).classes('min-w-48 flex-[2]')
                accion = ui.select(['Todas'], value='Todas', label='Acción') \
                    .props('outlined dense').classes('min-w-40 flex-1')
                area = ui.select(['Todas'], value='Todas', label='Área') \
                    .props('outlined dense').classes('min-w-36 flex-1')
                desde = campo_texto('Desde', (hoy - timedelta(days=30)).isoformat(),
                                    tipo='date', clases='min-w-36 flex-1')
                hasta = campo_texto('Hasta', hoy.isoformat(), tipo='date', clases='min-w-36 flex-1')
                boton_limpiar_filtros(lambda: limpiar_filtros())
            tabla = tabla_datos(COLUMNAS, [], 'id_auditoria', paginacion=10,
                                sin_datos='Sin movimientos para los filtros seleccionados.')
            slot_badge_color(tabla, 'accion', 'blue-grey-7', clases='px-2 py-1')
            with ui.row().classes('w-full justify-end'):
                btn_detalle = ui.button('Consultar detalle', icon='visibility').props('no-caps').classes(BOTON_PRIMARIO)

        def seleccionado():
            clave = tabla.selected[0].get('id_auditoria') if tabla.selected else None
            if not any(fila['id_auditoria'] == clave for fila in tabla.rows):
                return None
            return next((r for r in registros if r['id_auditoria'] == clave), None)

        def actualizar_boton():
            btn_detalle.set_enabled(seleccionado() is not None)

        def filtrar():
            consulta = texto_buscable(buscar.value).strip()
            inicio, fin = desde.value or '', hasta.value or ''
            filas = [r for r in registros if (
                consulta in texto_buscable(' '.join(str(r.get(k) or '') for k in (
                    'actor', 'accion', 'referencia', 'area'
                )))
                and (accion.value == 'Todas' or r['accion'] == accion.value)
                and (area.value == 'Todas' or r['area'] == area.value)
                and (not inicio or r['fecha'] >= inicio)
                and (not fin or r['fecha'] <= fin)
            )]
            tabla.rows = [{k: v for k, v in fila.items() if k not in ('datos', 'fecha')} for fila in filas]
            tabla.selected.clear()
            tabla.update()
            actualizar_boton()

        def limpiar_filtros():
            buscar.value, accion.value, area.value = '', 'Todas', 'Todas'
            desde.value, hasta.value = '', ''
            filtrar()

        def recargar():
            try:
                exigir_administrador(request)
                registros[:] = [normalizar(r) for r in consultar_auditoria()]
            except (ValueError, ErrorMySQL):
                ui.notify('No se pudo consultar la auditoría.', type='warning')
                return
            for control, campo in ((accion, 'accion'), (area, 'area')):
                opciones = ['Todas', *sorted({r[campo] for r in registros})]
                control.set_options(opciones, value=control.value if control.value in opciones else 'Todas')
            filtrar()

        def consultar_detalle():
            fila = seleccionado()
            if fila is None:
                return
            try:
                exigir_administrador(request)
            except (ValueError, ErrorMySQL):
                ui.notify('No se pudo autorizar la consulta.', type='warning')
                return
            campos = {'Responsable': fila['actor'], 'Fecha y hora': fila['fecha_visible'],
                      'Área': fila['area'], 'Referencia': fila['referencia'], **fila['datos']}
            campos = {k: v for k, v in campos.items() if v}
            with ui.dialog() as dialogo, ui.card().classes('w-full max-w-2xl p-5 gap-3'):
                with ui.row().classes('w-full items-center justify-between gap-2'):
                    ui.label(fila['accion']).classes(f'text-lg font-bold text-[{AZUL_TEXTO}]')
                    ui.button(icon='close', on_click=dialogo.close).props('flat round dense')
                grilla_detalle(campos, [(campo, campo) for campo in campos])
                ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps').classes('self-end')
            dialogo.open()

        refrescar.on('click', recargar)
        btn_detalle.on('click', consultar_detalle)
        tabla.on_select(actualizar_boton)
        for control in (buscar, accion, area, desde, hasta):
            control.on_value_change(filtrar)
        actualizar_boton()
        recargar()
