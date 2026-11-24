# Presentacion/estudiante/calendario.py
"""Calendario semanal del único polideportivo (capa de presentación)."""
import asyncio
import logging
from datetime import date, datetime, timedelta

from fastapi import Request
from nicegui import app, ui
from mysql.connector import Error as ErrorMySQL
from aplicacion.casos_uso.reservas.registrar_reserva import RegistrarReserva
from infraestructura.persistencia.programaciones_mysql import ErrorProgramacion, RepositorioProgramacionesMySQL
from infraestructura.persistencia.reservas_mysql import ErrorReserva, RepositorioReservasMySQL
from dominio.reglas.reservas import (
    APERTURA, CIERRE, MAXIMO_RESERVA_MINUTOS, ZONA_PERU,
    aviso_cupo_semanal, inicio_semana, minutos_disponibles,
)
from Presentacion.componentes.cupo_reservas import IndicadorCupoSemanal
from Presentacion.componentes.agenda import (
    Tramo, a_minutos, hhmm, horario_disponible, leyenda_agenda, pintar_semana as pintar_cuadricula, tramos_agenda,
)
from Presentacion.sesion import obtener_actor
from Presentacion.estudiante.layout_usuario import crear_marco_usuario
from Presentacion.componentes.filtros import campo_texto, fila_filtros
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina

PX_HORA = 44

logger = logging.getLogger(__name__)

@ui.page('/usuario/calendario', response_timeout=15)
def pagina_calendario(request: Request, dia: str = ''):
    actor = obtener_actor(request)
    if actor is None:
        ui.navigate.to('/')
        return
    if not crear_marco_usuario('DISPONIBILIDAD'):
        return

    programaciones = RepositorioProgramacionesMySQL()
    repo = RepositorioReservasMySQL()
    hoy = datetime.now(ZONA_PERU).date()
    try:
        dia_inicial = date.fromisoformat(dia) if dia else hoy
    except ValueError:
        dia_inicial = hoy
    estado = {'lunes': inicio_semana(dia_inicial), 'agendas': {}, 'error_agenda': False,
              'seleccion': None, 'guardando': False}

    def dias_semana():
        return [estado['lunes'] + timedelta(days=i) for i in range(7)]

    def cargar_cupo():
        try:
            segundos = repo.consumo_semanal(actor.id_usuario, estado['lunes'])
        except (ErrorMySQL, ErrorReserva):
            segundos = None
        indicador.actualizar(segundos)
        return segundos

    def cargar_semana(*, mostrar_error=True):
        segundos = cargar_cupo()
        try:
            agendas = programaciones.obtener_agenda_semanal(estado['lunes'])
        except (ErrorMySQL, ErrorProgramacion) as exc:
            logger.warning('No se pudo cargar la agenda (%s)', type(exc).__name__)
            estado['agendas'] = {}
            estado['error_agenda'] = True
            if mostrar_error:
                mensaje.set_text('No se pudo consultar la programación.')
        else:
            estado['agendas'] = {date.fromisoformat(dia): agenda for dia, agenda in agendas.items()}
            estado['error_agenda'] = False
            if mostrar_error:
                mensaje.set_text('')
        return segundos

    with ui.column().classes('w-full max-w-[1600px] mx-auto px-3 sm:px-5 py-3 gap-3'):
        titulo_pagina('DISPONIBILIDAD SEMANAL', 'calendar_month', icono_px='22px')

        with tarjeta_seccion():
            with fila_filtros(gap='gap-2'):
                fecha = campo_texto('Fecha', dia_inicial.isoformat(), tipo='date', clases='w-40')
                hora_inicio = campo_texto('Hora inicial', tipo='time', clases='w-32')
                hora_fin = campo_texto('Hora final', tipo='time', clases='w-32')
                btn_ver = ui.button('Ver disponibilidad', icon='search').props('no-caps').classes('bg-[#164875] text-white')
                mensaje = ui.label('').classes('text-xs text-slate-600 self-center')

            with ui.row().classes('w-full items-center justify-between gap-2 flex-wrap'):
                with ui.row().classes('items-center gap-2'):
                    ui.button(icon='chevron_left', on_click=lambda: cambiar_semana(-7)).props('round flat dense')
                    texto_semana = ui.label('').classes('text-sm font-bold text-[#09234B]')
                    ui.button(icon='chevron_right', on_click=lambda: cambiar_semana(7)).props('round flat dense')
                    ui.button('Esta semana', on_click=lambda: ir_hoy()).props('outline dense no-caps')
                leyenda_agenda('libre', 'reservado', 'taller', 'evento', 'mantenimiento',
                               'no_disponible', 'seleccionado')

            indicador = IndicadorCupoSemanal()

            @ui.refreshable
            def pintar_semana():
                dias = dias_semana()
                ahora = datetime.now(ZONA_PERU)
                agendas = estado['agendas']
                tramos = {dia: tramos_agenda(agendas.get(dia), dia, ahora) for dia in dias}
                if estado['seleccion']:
                    dia, a, b = estado['seleccion']
                    tramos[dia].append(Tramo(a, b, 'seleccionado', 'Seleccionado'))
                vacios = () if estado['error_agenda'] else [dia for dia in dias if agendas.get(dia) is None]
                elegido = next((dia for dia in dias if dia.isoformat() == fecha.value), None)
                pintar_cuadricula(dias, tramos, elegido, al_dia=lambda dia: seleccionar_dia(dia), dias_vacios=vacios,
                                  px_hora=PX_HORA, alto_visible=460, ancho_dia=140)

            cargar_semana()
            pintar_semana()

            with ui.row().classes('w-full justify-between items-center gap-3 flex-wrap'):
                ui.label('Reservas de lunes a viernes · 07:00–22:00 · Hasta 2 horas').classes(
                    'text-xs text-slate-600'
                )

                async def continuar():
                    if estado['seleccion'] is None or estado['guardando']:
                        return
                    if obtener_actor(request) != actor:
                        ui.navigate.to('/')
                        return
                    dia, a, b = estado['seleccion']
                    estado['guardando'] = True
                    limpiar_seleccion()
                    try:
                        reserva = await asyncio.to_thread(
                            RegistrarReserva().ejecutar, id_usuario_sesion=actor.id_usuario,
                            fecha_uso=dia, hora_inicio=hhmm(a), hora_fin=hhmm(b),
                        )
                    except ErrorReserva as exc:
                        if not btn_reservar.is_deleted:
                            cargar_semana()
                            pintar_semana.refresh()
                            mensaje.set_text(str(exc))
                        return
                    except ErrorMySQL as exc:
                        logger.warning('No se pudo registrar la reserva (%s)', exc.errno)
                        if not btn_reservar.is_deleted:
                            mensaje.set_text('No se pudo guardar la reserva. Revisa Mis reservas antes de reintentar.')
                        return
                    finally:
                        estado['guardando'] = False
                    if btn_reservar.is_deleted or obtener_actor(request) != actor:
                        return
                    app.storage.user['ultima_reserva'] = {'codigo_reserva': reserva['codigo_reserva']}
                    cargar_semana()
                    pintar_semana.refresh()
                    ui.notify('Reserva registrada.', type='positive')
                    ui.navigate.to('/usuario/resumen-reserva')

                btn_reservar = ui.button('Realizar Reserva', icon='arrow_forward', on_click=continuar) \
                    .props('no-caps').classes('bg-[#164875] text-white')
                btn_reservar.disable()

    def limpiar_seleccion():
        estado['seleccion'] = None
        btn_reservar.disable()
        pintar_semana.refresh()

    def seleccionar_dia(dia):
        fecha.set_value(dia.isoformat())

    def actualizar_fecha():
        try:
            dia = date.fromisoformat(str(fecha.value))
        except ValueError:
            mensaje.set_text('Selecciona una fecha válida.')
        else:
            if not estado['lunes'] <= dia <= estado['lunes'] + timedelta(days=6):
                estado['lunes'] = inicio_semana(dia)
                cargar_semana()
            actualizar_titulo()
        limpiar_seleccion()

    def actualizar_titulo():
        lunes = estado['lunes']
        domingo = lunes + timedelta(days=6)
        texto_semana.set_text(f'{lunes:%d/%m/%Y} – {domingo:%d/%m/%Y}')

    def cambiar_semana(dias):
        seleccionar_dia(estado['lunes'] + timedelta(days=dias))

    def ir_hoy():
        hoy = datetime.now(ZONA_PERU).date()
        estado['lunes'] = inicio_semana(hoy)
        cargar_semana()
        if fecha.value == hoy.isoformat():
            actualizar_fecha()
        else:
            seleccionar_dia(hoy)

    def verificar():
        if estado['guardando']:
            return
        limpiar_seleccion()
        try:
            dia = date.fromisoformat(str(fecha.value))
        except ValueError:
            mensaje.set_text('Selecciona una fecha válida.')
            return
        if dia.weekday() >= 5:
            mensaje.set_text('Las reservas de fin de semana requieren gestión administrativa.')
            return
        a, b = a_minutos(hora_inicio.value), a_minutos(hora_fin.value)
        if a is None or b is None or not (APERTURA <= a < b <= CIERRE):
            mensaje.set_text('Selecciona un horario válido entre 07:00 y 22:00.')
            return
        if b - a > MAXIMO_RESERVA_MINUTOS:
            mensaje.set_text('La duración máxima es de 2 horas.')
            return
        inicio = datetime(dia.year, dia.month, dia.day, a // 60, a % 60, tzinfo=ZONA_PERU)
        if inicio <= datetime.now(ZONA_PERU):
            mensaje.set_text('El turno debe comenzar en el futuro.')
            return
        segundos = cargar_cupo()
        # Nueva lectura del día elegido; no se valida con una agenda obsoleta.
        try:
            agenda = programaciones.obtener_agenda(dia)
            disponible = horario_disponible(a, b, agenda) and programaciones.buscar_horario_reservable(
                dia, hhmm(a), hhmm(b),
            )
        except (ErrorMySQL, ErrorProgramacion):
            mensaje.set_text('No se pudo verificar la disponibilidad.')
            return
        estado['agendas'][dia] = agenda
        if disponible and segundos is not None and b - a > minutos_disponibles(segundos):
            mensaje.set_text(aviso_cupo_semanal(segundos))
        elif disponible:
            estado['seleccion'] = (dia, a, b)
            btn_reservar.enable()
            mensaje.set_text('Horario disponible.')
        else:
            mensaje.set_text('No hay programación publicada para esa fecha.' if agenda is None else
                             'Esa franja no está disponible.')
        pintar_semana.refresh()

    def refrescar_semana():
        if estado['guardando'] or obtener_actor(request) != actor:
            return
        anterior = estado['agendas'], estado['error_agenda']
        segundos = cargar_semana(mostrar_error=False)
        ahora = datetime.now(ZONA_PERU)
        seleccion = estado['seleccion']
        if seleccion:
            dia, a, b = seleccion
            inicio = datetime.combine(dia, datetime.strptime(hhmm(a), '%H:%M').time(), ZONA_PERU)
            if inicio <= ahora or not horario_disponible(a, b, estado['agendas'].get(dia)):
                limpiar_seleccion()
                mensaje.set_text('La franja seleccionada dejó de estar disponible.')
                return
            if segundos is not None and b - a > minutos_disponibles(segundos):
                limpiar_seleccion()
                mensaje.set_text(aviso_cupo_semanal(segundos))
                return
        if anterior != (estado['agendas'], estado['error_agenda']):
            if estado['error_agenda']:
                mensaje.set_text('No se pudo consultar la programación.')
            elif anterior[1]:
                mensaje.set_text('')
            pintar_semana.refresh()

    fecha.on_value_change(actualizar_fecha)
    hora_inicio.on_value_change(limpiar_seleccion)
    hora_fin.on_value_change(limpiar_seleccion)
    btn_ver.on('click', lambda _: verificar())

    actualizar_titulo()
    ui.timer(60, refrescar_semana, immediate=False)
