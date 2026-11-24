"""Botones compartidos por los menús laterales."""

from nicegui import ui

from Presentacion.componentes.estilos import AZUL_MEDIO


def opciones_menu(opciones, seccion_activa):
    for texto, icono, ruta in opciones:
        estilo = (
            'bg-[#38BDF8] text-black font-bold shadow-sm'
            if texto == seccion_activa else
            f'bg-transparent text-[{AZUL_MEDIO}] hover:bg-gray-300'
        )
        ui.button(texto, icon=icono, on_click=lambda destino=ruta: ui.navigate.to(destino)) \
            .props('flat no-caps align=left').classes(f'w-full rounded-lg px-3 py-2 text-xs {estilo}')


def boton_cerrar_sesion():
    ui.button('CERRAR SESIÓN', icon='logout', on_click=lambda: ui.navigate.to('/logout')) \
        .props('outline no-caps').classes(
            'w-full bg-[#E5E7EB] text-black font-bold text-xs '
            'py-2 rounded-lg border border-black'
        )
