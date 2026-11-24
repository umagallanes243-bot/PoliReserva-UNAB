# Presentacion/estudiante/layout_usuario.py
"""Diseño compartido para las pantallas de estudiantes y docentes (NiceGUI)."""

from nicegui import app, ui

from Presentacion.componentes.encabezado import marca_institucional
from Presentacion.componentes.estilos import AZUL_UNAB, CELESTE_UNAB
from Presentacion.componentes.navegacion import boton_cerrar_sesion, opciones_menu

# Las rutas se registrarán al crear cada formulario de Presentacion/estudiante/.
OPCIONES_USUARIO = [
    ('INICIO', 'home', '/usuario/inicio'),
    ('DISPONIBILIDAD', 'calendar_month', '/usuario/calendario'),
    ('MIS RESERVAS', 'event_note', '/usuario/mis-reservas'),
    ('SOLICITAR IMPLEMENTOS', 'inventory_2', '/usuario/solicitar-prestamo'),
    ('MIS PRÉSTAMOS', 'assignment_return', '/usuario/mis-prestamos'),
    ('MI PERFIL', 'person', '/usuario/perfil'),
]


def crear_marco_usuario(seccion_activa: str) -> bool:
    """Muestra el encabezado y menú de las páginas autorizadas por el middleware."""
    correo = str(app.storage.user.get('correo') or '').strip()
    if not correo:
        ui.navigate.to('/')
        return False

    nombre = str(app.storage.user.get('nombre') or 'Usuario').strip()
    foto = app.storage.user.get('foto')

    ui.query('body').style('margin:0; padding:0; background:#F4F5F7;')
    ui.query('.nicegui-content').style(
        'padding:0; margin:0; width:100%; min-height:100vh;'
    )

    # Encabezado institucional: mismo estilo visual del panel administrador.
    with ui.header().classes(
        f'bg-[{AZUL_UNAB}] text-white px-4 md:px-6 py-3 '
        'items-center justify-between shadow-md'
    ):
        with ui.row().classes('items-center gap-3 md:gap-4 no-wrap'):
            ui.button(icon='menu', on_click=lambda: menu.toggle()) \
                .props('flat round aria-label="Abrir menú"').classes('md:hidden text-white')
            marca_institucional(
                logo_clases='w-28 md:w-36 h-10 md:h-12 object-contain',
                titulo_clases='text-base md:text-2xl',
                fila_clases='items-center gap-3 md:gap-4 no-wrap',
            )

        with ui.row().classes('items-center gap-2 no-wrap'):
            ui.icon('account_circle', size='22px').classes('hidden sm:block text-[#7EC4CF]')
            ui.label(nombre).classes(
                'hidden sm:block max-w-40 truncate text-sm font-semibold'
            )
            ui.label('PORTAL UNIVERSITARIO').classes(
                f'hidden lg:block text-[{AZUL_UNAB}] bg-[{CELESTE_UNAB}] '
                'rounded-md px-3 py-2 text-xs font-bold'
            )

    with ui.left_drawer(value=None, fixed=True).classes(
        'bg-[#E5E7EB] p-4 border-r border-gray-300'
    ).props('width=240 breakpoint=767') as menu:
        with ui.column().classes('w-full h-full gap-2'):
            # Perfil breve en el menú lateral.
            with ui.row().classes('w-full items-center gap-3 px-2 py-3'):
                if foto:
                    ui.image(foto).classes('w-10 h-10 rounded-full object-cover')
                else:
                    ui.icon('account_circle', size='40px').classes('text-[#164875]')
                with ui.column().classes('min-w-0 gap-0 flex-1'):
                    ui.label(nombre).classes(
                        'w-full truncate text-sm font-bold text-[#09234B]'
                    )
                    ui.label(correo).classes(
                        'w-full truncate text-xs text-slate-600'
                    )

            ui.separator().classes('mb-1')

            opciones_menu(OPCIONES_USUARIO, seccion_activa)
            ui.space()
            boton_cerrar_sesion()

    return True
