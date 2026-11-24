"""Franjas y visualización de la agenda del polideportivo."""

import re
from typing import NamedTuple

from nicegui import ui

from dominio.reglas.agenda import a_minutos, hhmm, intervalo_jornada, restar_intervalos
from dominio.reglas.reservas import APERTURA, CIERRE


DIAS_CORTOS = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')
ETIQUETAS = {
    'libre': 'Disponible', 'reservado': 'Reservado', 'taller': 'Taller deportivo',
    'evento': 'Evento institucional', 'mantenimiento': 'Mantenimiento',
    'ocupado': 'Ocupado', 'no_disponible': 'No disponible', 'seleccionado': 'Seleccionado',
    'sin_programacion': 'Sin programación',
}
COLORES = {
    'libre': ('#E0F2F4', '#367581', '#164875'),
    'reservado': ('#FEE2E2', '#B91C1C', '#7F1D1D'),
    'taller': ('#DBEAFE', '#1D4ED8', '#1E3A8A'),
    'evento': ('#F3E8FF', '#7E22CE', '#581C87'),
    'mantenimiento': ('#FEF3C7', '#A16207', '#713F12'),
    'ocupado': ('#E2E8F0', '#64748B', '#334155'),
    'no_disponible': ('#F1F5F9', '#94A3B8', '#475569'),
    'seleccionado': ('#DCFCE7', '#15803D', '#14532D'),
    'sin_programacion': ('#F8FAFC', '#CBD5E1', '#475569'),
}
TIPOS = {'TALLER DEPORTIVO': 'taller', 'EVENTO INSTITUCIONAL': 'evento',
         'MANTENIMIENTO': 'mantenimiento', 'RESERVA': 'reservado'}
LEYENDA_ADMIN = ('libre', 'reservado', 'taller', 'evento', 'mantenimiento', 'no_disponible', 'sin_programacion')


def nombre_programacion_visible(nombre):
    valor = str(nombre or '').strip()
    return re.sub(r'^DEMO\s+V9\s*[-–—:]\s*', '', valor, count=1, flags=re.IGNORECASE) or valor


class Tramo(NamedTuple):
    inicio: int
    fin: int
    tipo: str
    titulo: str
    referencia: str | int | None = None
    id_periodo: int | None = None


def _intervalos(filas):
    for fila in filas:
        if (intervalo := intervalo_jornada(fila['inicio'], fila['fin'])) is not None:
            yield (*intervalo, fila)


def horario_disponible(inicio, fin, agenda):
    agenda = agenda or {}
    return (any(a <= inicio < fin <= b for a, b, _ in _intervalos(agenda.get('libres', ())))
            and not any(inicio < b and a < fin for a, b, _ in _intervalos(agenda.get('ocupados', ()))))


def tramos_agenda(agenda, dia, ahora, *, portal=True, mostrar_huecos=False):
    """Divide los horarios libres contra todos los bloqueos antes de pintar o filtrar."""
    agenda = agenda or {}
    ocupados = list(_intervalos(agenda.get('ocupados', ())))
    libres = list(_intervalos(agenda.get('libres', ())))
    tramos = []
    for inicio, fin, fila in ocupados:
        tipo = TIPOS.get(fila.get('tipo'), 'ocupado')
        if tipo == 'reservado':
            titulo = 'Asistencia confirmada' if fila.get('estado_reserva') == 'CONFIRMADA' else 'Reservado'
            referencia = fila.get('codigo_reserva')
        else:
            titulo = nombre_programacion_visible(fila.get('titulo')) or ETIQUETAS[tipo]
            referencia = fila.get('id_horario')
        tramos.append(Tramo(inicio, fin, tipo, titulo, referencia, fila.get('id_periodo')))

    cortes = [(a, b) for a, b, _ in ocupados]
    minuto_actual = ahora.hour * 60 + ahora.minute
    for a, b, fila in libres:
        titulo = nombre_programacion_visible(fila.get('titulo')) or ETIQUETAS['libre']
        referencia = fila.get('id_horario'), fila.get('id_periodo')
        for inicio, fin in restar_intervalos(a, b, cortes):
            if dia < ahora.date() or (portal and dia.weekday() >= 5):
                corte = fin
            elif dia == ahora.date():
                corte = max(inicio, min(fin, minuto_actual + 1))
            else:
                corte = inicio
            if inicio < corte:
                rotulo = titulo if portal else 'Horario transcurrido'
                tramos.append(Tramo(inicio, corte, 'no_disponible', rotulo, *referencia))
            if corte < fin:
                tramos.append(Tramo(corte, fin, 'libre', titulo, *referencia))

    if mostrar_huecos:
        publicados = [(a, b) for a, b, _ in libres] + cortes
        tramos.extend(Tramo(a, b, 'sin_programacion', ETIQUETAS['sin_programacion'])
                      for a, b in restar_intervalos(APERTURA, CIERRE, publicados))
    return sorted(tramos, key=lambda t: (t.inicio, t.fin, t.tipo))


def leyenda_agenda(*tipos):
    with ui.row().classes('items-center gap-x-3 gap-y-1 flex-wrap'):
        for tipo in tipos:
            with ui.row().classes('items-center gap-1 no-wrap'):
                ui.icon('square', size='11px').style(f'color:{COLORES[tipo][1]}')
                ui.label(ETIQUETAS[tipo]).classes('text-xs text-slate-600')


def pintar_tramo(tramo, px_hora, *, margen=4, mostrar_hora=False, al_elegir=None):
    top = (tramo.inicio - APERTURA) / 60 * px_hora
    alto = (tramo.fin - tramo.inicio) / 60 * px_hora
    fondo, borde, texto = COLORES[tramo.tipo]
    horario = f'{hhmm(tramo.inicio)}–{hhmm(tramo.fin)}'
    categoria = ETIQUETAS[tramo.tipo]
    titulo = tramo.titulo
    rotulo = f'{horario} · {titulo}' if mostrar_hora else titulo
    ayuda = f'{horario} · {categoria}' + (f' · {titulo}' if titulo != categoria else '')
    clases = 'absolute rounded border-l-[3px] px-1.5 overflow-hidden flex'
    clases += ' items-start pt-1.5' if al_elegir and alto >= 65 else ' items-center'
    if al_elegir:
        clases += ' text-left hover:brightness-95 focus-visible:outline focus-visible:outline-2 cursor-pointer'
    elemento = ui.element('button' if al_elegir else 'div').classes(clases).style(
        f'left:{margen}px;right:4px;top:{top:.2f}px;height:{alto:.2f}px;'
        f'background:{fondo};border-color:{borde};color:{texto};'
        f'z-index:{5 if tramo.tipo == "seleccionado" else 3}'
    )
    if al_elegir:
        elemento.props('type=button')
        elemento.props['aria-label'] = ayuda
        elemento.on('click', al_elegir)
    with elemento:
        if alto >= 14:
            with ui.column().classes('w-full gap-0 min-w-0'):
                ui.label(rotulo).classes('text-xs font-semibold truncate block w-full')
                if al_elegir and alto >= 34 and tramo.tipo != 'sin_programacion':
                    ui.label(horario).classes('text-[11px] truncate block w-full tabular-nums')
        ui.tooltip(ayuda).classes('text-xs')


def _rejilla_horaria(px_hora, *, medias=False):
    if not medias:
        return f'background-image:repeating-linear-gradient(#E2E8F0 0 1px, transparent 1px {px_hora}px);'
    return (
        f'background-image:repeating-linear-gradient(#E2E8F0 0 1px, transparent 1px {px_hora}px),'
        f'repeating-linear-gradient(#F1F5F9 0 1px, transparent 1px {px_hora / 2}px);'
    )


def _rotulos_hora(px_hora):
    for minuto in range(APERTURA, CIERRE, 60):
        y = (minuto - APERTURA) / 60 * px_hora
        ui.label(hhmm(minuto)).classes(
            'absolute left-2 text-[11px] font-semibold text-slate-600 tabular-nums'
        ).style(f'top:{y+4}px')


def pintar_semana(dias, tramos, elegido, *, al_dia, al_tramo=None, dias_vacios=(),
                  px_hora=36, alto_visible=500, ancho_dia=106):
    altura = (CIERRE - APERTURA) / 60 * px_hora
    cuadricula = f'grid-template-columns:58px repeat(7,minmax({ancho_dia}px,1fr));'
    altura_visible = f'{alto_visible}px' if isinstance(alto_visible, int) else alto_visible
    with ui.element('div').classes(
        'w-full overflow-auto rounded-lg border border-slate-200 bg-white'
    ).style(f'height:{altura_visible}').props('tabindex=0 aria-label="Agenda semanal"'):
        with ui.element('div').style(f'min-width:{58 + ancho_dia * 7}px'):
            with ui.element('div').classes(
                'sticky top-0 z-20 grid border-b border-slate-200 bg-white'
            ).style(cuadricula):
                ui.label('Hora').classes(
                    'sticky left-0 z-30 bg-slate-50 py-3 text-center text-xs font-semibold text-slate-600'
                )
                for i, dia in enumerate(dias):
                    color = 'bg-blue-100' if elegido == dia else 'bg-slate-50'
                    with ui.element('button').props('type=button').classes(
                        f'{color} border-l border-slate-200 py-2 text-center hover:bg-blue-50 '
                        'focus-visible:outline focus-visible:outline-2'
                    ).on('click', lambda _, d=dia: al_dia(d)):
                        ui.label(DIAS_CORTOS[i]).classes('block text-xs font-bold text-[#09234B]')
                        ui.label(dia.strftime('%d/%m')).classes('block text-xs text-slate-600')
            with ui.element('div').classes('grid').style(f'{cuadricula}height:{altura}px;'):
                with ui.element('div').classes('relative sticky left-0 z-10 bg-slate-50').style(
                    _rejilla_horaria(px_hora)
                ):
                    _rotulos_hora(px_hora)
                for dia in dias:
                    with ui.element('div').classes('relative border-l border-slate-200').style(
                        _rejilla_horaria(px_hora, medias=True)
                    ):
                        for tramo in tramos.get(dia, ()):
                            accion = None if al_tramo is None else lambda _, d=dia, t=tramo: al_tramo(d, t)
                            pintar_tramo(tramo, px_hora, al_elegir=accion)
                        if dia in dias_vacios:
                            ui.label('Sin programación').classes('absolute left-2 top-2 text-xs text-slate-600')


def pintar_miniagenda(tramos, mensaje, *, alto_visible=226, px_hora=30, compacto=False):
    if not tramos:
        clases = 'p-3 min-h-16' if compacto else 'p-5 min-h-36'
        with ui.column().classes(f'w-full items-center justify-center rounded-lg bg-slate-50 gap-2 {clases}'):
            if not compacto:
                ui.icon('event_busy', size='24px').classes('text-slate-500')
            ui.label(mensaje).classes('text-sm text-center text-slate-600')
        return

    alto = (CIERRE - APERTURA) / 60 * px_hora
    with ui.element('div').classes(
        'w-full min-w-0 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50'
    ).style(f'height:{alto_visible}px;').props('tabindex=0 aria-label="Agenda del día"'):
        with ui.element('div').classes('relative w-full').style(f'height:{alto}px;{_rejilla_horaria(px_hora)}'):
            _rotulos_hora(px_hora)
            for tramo in tramos:
                pintar_tramo(tramo, px_hora, margen=51, mostrar_hora=True)
