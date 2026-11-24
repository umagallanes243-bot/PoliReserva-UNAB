"""Vista previa y confirmación de horarios libres en lote."""

import asyncio
from datetime import date, datetime

from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from aplicacion.casos_uso.programaciones.publicar_horarios_libres import PublicarHorariosLibres
from dominio.reglas.agenda import hhmm
from dominio.reglas.reservas import APERTURA, CIERRE, ZONA_PERU
from Presentacion.admin.layout_admin import guardar_como_admin
from Presentacion.componentes.estilos import BOTON_PRIMARIO
from Presentacion.componentes.filtros import campo_texto
from Presentacion.componentes.tablas import tabla_datos
from Presentacion.sesion import exigir_administrador


def dialogo_horarios_libres(request, recargar, catalogo, desde, hasta, *, id_periodo=None):
    if not catalogo:
        ui.notify('Crea un período académico antes de publicar horarios libres.', type='warning')
        return
    periodos = {p['id_periodo']: p for p in catalogo}
    hoy = datetime.now(ZONA_PERU).date()
    if desde <= hoy <= hasta:
        desde = hoy
    if id_periodo not in periodos:
        compatibles = [p['id_periodo'] for p in catalogo
                       if p['fecha_inicio'] <= desde.isoformat() <= p['fecha_fin']]
        id_periodo = compatibles[0] if len(compatibles) == 1 else None
    if id_periodo is not None:
        periodo = periodos[id_periodo]
        a, b = date.fromisoformat(periodo['fecha_inicio']), date.fromisoformat(periodo['fecha_fin'])
        if desde <= b and a <= hasta:
            desde, hasta = max(a, desde), min(b, hasta)

    caso = PublicarHorariosLibres()
    propuesta = None
    consultando = False
    guardando = False

    with ui.dialog() as dlg, ui.card().classes('w-full max-w-xl p-5 gap-3'):
        ui.label('Completar horarios libres').classes('text-lg font-bold text-[#09234B]')
        ui.label('Revisa las franjas antes de habilitarlas para reservas.').classes('text-sm text-slate-600')
        periodo = ui.select({i: p['nombre_periodo'] for i, p in periodos.items()},
                            value=id_periodo, label='Período del lote').props('outlined dense').classes('w-full')
        with ui.element('div').classes('w-full grid grid-cols-2 sm:grid-cols-4 gap-2'):
            primero = campo_texto('Desde', desde.isoformat(), 'date')
            ultimo = campo_texto('Hasta', hasta.isoformat(), 'date')
            apertura = campo_texto('Apertura', hhmm(APERTURA), 'time')
            cierre = campo_texto('Cierre', hhmm(CIERRE), 'time')
        incluir = ui.switch('Incluir sábados y domingos', value=False)
        aviso = ui.label().classes('text-sm text-slate-600')
        tabla = tabla_datos([
            {'name': 'fecha', 'label': 'Fecha', 'field': 'fecha', 'align': 'left'},
            {'name': 'inicio', 'label': 'Desde', 'field': 'inicio'},
            {'name': 'fin', 'label': 'Hasta', 'field': 'fin'},
        ], [], 'id', paginacion=7, seleccion=None)
        tabla.set_visibility(False)

        def parametros():
            return dict(id_periodo=periodo.value, desde=primero.value, hasta=ultimo.value,
                        inicio=apertura.value, fin=cierre.value, fines_de_semana=incluir.value)

        def invalidar():
            nonlocal propuesta
            propuesta = None
            confirmar.disable()
            tabla.set_visibility(False)
            aviso.set_text('')

        async def previsualizar():
            nonlocal propuesta, consultando
            if consultando or guardando:
                return
            invalidar()
            consultando = True
            revisar.disable()
            datos = parametros()
            try:
                await asyncio.to_thread(exigir_administrador, request)
                resultado = await asyncio.to_thread(caso.previsualizar, **datos)
            except (ValueError, ErrorMySQL) as exc:
                if not revisar.is_deleted and datos == parametros():
                    aviso.set_text(str(exc) if isinstance(exc, ValueError) else 'No se pudo calcular la vista previa.')
            else:
                if not revisar.is_deleted and datos == parametros():
                    propuesta = resultado
                    if resultado.horarios:
                        tabla.rows = [dict(id=i, fecha=dia.strftime('%d/%m/%Y'), inicio=a, fin=b)
                                      for i, (dia, a, b) in enumerate(resultado.horarios)]
                        tabla.set_visibility(True)
                        aviso.set_text(f'Franjas para publicar · {len(resultado.horarios)} · '
                                       f'Fechas · {len({f[0] for f in resultado.horarios})}')
                        confirmar.enable()
                    else:
                        aviso.set_text('No hay franjas futuras sin programación en ese rango.')
            finally:
                consultando = False
                if not revisar.is_deleted:
                    revisar.enable()

        async def publicar():
            nonlocal guardando
            if propuesta is None or guardando:
                return
            cantidad = len(propuesta.horarios)
            guardando = True
            revisar.disable()
            try:
                if await guardar_como_admin(request, confirmar, caso.ejecutar, propuesta=propuesta,
                                            mensaje_error='No se pudo publicar el lote.'):
                    dlg.close()
                    recargar()
                    ui.notify(f'Franjas publicadas como horarios libres · {cantidad}', type='positive')
                elif not confirmar.is_deleted:
                    invalidar()
                    aviso.set_text('Calcula la vista previa nuevamente antes de publicar.')
            finally:
                guardando = False
                if not revisar.is_deleted:
                    revisar.enable()

        with ui.row().classes('w-full justify-end gap-2 flex-wrap'):
            ui.button('Cerrar', on_click=dlg.close).props('flat no-caps')
            revisar = ui.button('Vista previa', icon='visibility', on_click=previsualizar).props('outline no-caps')
            confirmar = ui.button('Publicar horarios libres', icon='check', on_click=publicar) \
                .props('unelevated no-caps').classes(BOTON_PRIMARIO)
            confirmar.disable()
        for control in (periodo, primero, ultimo, apertura, cierre, incluir):
            control.on_value_change(invalidar)
    dlg.open()
