"""Tarjetas y títulos de sección reutilizables."""

from nicegui import ui

from Presentacion.componentes.estilos import AZUL_MEDIO, AZUL_TEXTO, TARJETA_BASE


def titulo_pagina(texto, icono, icono_px='25px', color_icono=None,
                  tamano='text-xl', responsive=False):
    """Encabezado de pantalla con icono y título institucional."""
    clases_texto = f'{tamano} {"md:text-2xl " if responsive else ""}' \
                   f'font-bold text-[{AZUL_TEXTO}]'
    with ui.row().classes('items-center gap-2'):
        ui.icon(icono, size=icono_px).classes(color_icono or f'text-[{AZUL_MEDIO}]')
        ui.label(texto).classes(clases_texto)


def tarjeta_seccion(padding='p-3', extra='', *, gap='gap-3'):
    """Contenedor estándar de filtros, tablas y formularios."""
    return ui.card().classes(f'{TARJETA_BASE} {gap} {padding} {extra}'.strip())
