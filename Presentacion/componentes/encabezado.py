"""Elementos institucionales compartidos por los encabezados."""

from pathlib import Path

from nicegui import app, ui

from Presentacion.componentes.estilos import AMARILLO_UNAB


LOGO_UNAB = app.add_static_file(url_path='/assets/logo-unab.png',
                                local_file=Path(__file__).resolve().parents[2] / 'logo_unab.png')


def marca_institucional(titulo='POLIRESERVA - UNAB',
                        logo_clases='w-36 h-12',
                        titulo_clases='text-2xl',
                        espaciado='tracking-wide',
                        fila_clases='items-center gap-4'):
    """Dibuja el logo UNAB y el nombre del sistema.

    Los tamaños se reciben como parámetros porque el encabezado administrativo,
    el del portal y el del registro usan escalas ligeramente distintas.
    """
    with ui.row().classes(fila_clases):
        ui.image(LOGO_UNAB).props('alt="Universidad Nacional de Barranca"').classes(logo_clases)
        ui.label(titulo).classes(
            f'text-[{AMARILLO_UNAB}] {titulo_clases} font-bold {espaciado}'.strip()
        )
