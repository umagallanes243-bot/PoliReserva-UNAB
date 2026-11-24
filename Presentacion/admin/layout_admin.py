# Presentacion/admin/layout_admin.py
import asyncio

from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from Presentacion.componentes.encabezado import marca_institucional
from Presentacion.componentes.estilos import AZUL_UNAB, CELESTE_UNAB
from Presentacion.componentes.navegacion import boton_cerrar_sesion, opciones_menu
from Presentacion.componentes.tablas import slot_badge_mapa
from Presentacion.sesion import exigir_administrador


# Solo rutas existentes.
# Las nuevas se agregarán cuando creemos sus formularios.
OPCIONES_MENU = [
    ('INICIO', 'home', '/admin/dashboard'),
    ('RESERVAS', 'event_note', '/admin/reservas'),
    ('ACTIVIDADES', 'event', '/admin/actividades'),
    ('INVENTARIO', 'inventory_2', '/admin/inventario'),
    ('USUARIOS', 'people', '/admin/usuarios'),
    ('PRÉSTAMOS', 'assignment_return', '/admin/prestamos'),
    ('REPORTES', 'bar_chart', '/admin/reportes'),
    ('AUDITORÍA', 'history', '/admin/auditoria'),
]


async def guardar_como_admin(request, boton, ejecutar, /, *, mensaje_error='No se pudo guardar la operación.', **datos):
    """Ejecuta una escritura con el rol vigente y bloquea clics repetidos."""
    if not boton.enabled:
        return False
    boton.disable()
    try:
        actor = await asyncio.to_thread(exigir_administrador, request)
        await asyncio.to_thread(ejecutar, id_usuario_sesion=actor.id_usuario, **datos)
    except (ErrorMySQL, ValueError) as exc:
        if not boton.is_deleted:
            ui.notify(str(exc) if isinstance(exc, ValueError) else mensaje_error, type='warning')
        return False
    finally:
        if not boton.is_deleted:
            boton.enable()
    return not boton.is_deleted


def crear_marco_admin(seccion_activa: str) -> bool:
    """Encabezado y menú de las páginas autorizadas por el middleware."""

    ui.query('body').style(
        'margin:0; padding:0; background-color:#F4F5F7;'
    )
    ui.query('.nicegui-content').style(
        'padding:0; margin:0; width:100%; min-height:100vh;'
    )

    # ENCABEZADO
    with ui.header().classes(
        f'bg-[{AZUL_UNAB}] text-white px-3 md:px-6 py-3 '
        'flex items-center justify-between shadow-md'
    ):
        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.button(icon='menu', on_click=lambda: menu.toggle()) \
                .props('flat round aria-label="Abrir menú"').classes('md:hidden text-white')
            marca_institucional(
                logo_clases='w-28 md:w-36 h-10 md:h-12 object-contain',
                titulo_clases='text-base md:text-2xl',
                fila_clases='items-center gap-2 md:gap-4 no-wrap',
            )

        with ui.row().classes(
            f'items-center gap-2 bg-[{CELESTE_UNAB}] text-[{AZUL_UNAB}] '
            'hidden sm:flex px-4 py-2 rounded-lg font-bold text-xs'
        ):
            ui.icon('verified_user', size='sm')
            ui.label('PANEL ADMINISTRATIVO')

    # MENÚ LATERAL
    with ui.left_drawer(value=None, fixed=True).classes(
        'bg-[#E5E7EB] p-4 flex flex-col justify-between '
        'border-r border-gray-300'
    ).props('width=220 breakpoint=767') as menu:

        with ui.column().classes('w-full gap-2 mt-2'):
            opciones_menu(OPCIONES_MENU, seccion_activa)

        boton_cerrar_sesion()

    return True


def aplicar_badge_estado(tabla):
    """Colores de estados de reservas y operaciones."""

    slot_badge_mapa(
        tabla, 'estado',
        {
            'RESERVADA': 'orange-7',
            'PENDIENTE': 'amber-8',
            'CONFIRMADA': 'green-7',
            'CONFIRMADO': 'green-7',
            'FINALIZADA': 'blue-7',
            'CANCELADA': 'grey-7',
            'INASISTENCIA': 'red-7',
            'ENTREGADO': 'blue-7',
            'DEVUELTO': 'green-7',
            'SUSPENDIDO': 'red-7',
        },
        defecto='grey-7',
        clases='text-white font-bold px-3 py-1 rounded-md',
        mayusculas=True,
    )
