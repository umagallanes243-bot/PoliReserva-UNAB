"""Bloques reutilizables para ventanas de consulta."""

from nicegui import ui

from Presentacion.componentes.estilos import AZUL_TEXTO


def grilla_detalle(registro, campos, columnas=2, responsive=True,
                   destacar=True, gap='gap-3', falsy_como_vacio=False):
    """Muestra pares etiqueta/valor de un registro en una cuadrícula.

    ``campos`` es una lista de ``(etiqueta, clave)``. Los valores vacíos se
    representan con una raya, igual que en los formularios existentes.
    """
    base = (f'grid grid-cols-1 sm:grid-cols-{columnas}' if responsive
            else f'grid grid-cols-{columnas}')
    clases_valor = 'text-sm font-medium'
    if destacar:
        clases_valor += f' text-[{AZUL_TEXTO}] break-all'

    with ui.element('div').classes(f'{base} {gap} w-full'):
        for etiqueta, clave in campos:
            with ui.column().classes('gap-0'):
                ui.label(etiqueta).classes('text-xs text-slate-500')
                valor = registro.get(clave)
                if falsy_como_vacio:
                    texto = str(valor) if valor else '—'
                else:
                    texto = str(valor) if valor not in (None, '') else '—'
                ui.label(texto).classes(clases_valor)


def filas_detalle(campos):
    """Muestra cada etiqueta y su valor en los extremos de una fila."""
    for etiqueta, valor in campos:
        with ui.row().classes('w-full justify-between gap-3'):
            ui.label(etiqueta).classes('text-sm text-slate-500')
            ui.label(valor or '—').classes(f'text-sm font-semibold text-[{AZUL_TEXTO}]')
