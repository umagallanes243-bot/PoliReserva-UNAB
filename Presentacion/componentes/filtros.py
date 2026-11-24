"""Controles de búsqueda y filtrado reutilizables."""

from nicegui import ui


def campo_texto(etiqueta, valor='', tipo='text', clases='w-full'):
    """Entrada de texto compacta con el estilo común de los filtros."""
    return ui.input(etiqueta, value=valor) \
        .props(f'outlined dense type={tipo}').classes(clases)


def fila_filtros(gap='gap-3'):
    """Fila de controles de filtro alineados por la base."""
    return ui.row().classes(f'w-full items-end {gap} flex-wrap')


def boton_limpiar_filtros(on_click=None, icono='filter_alt_off'):
    """Botón redondo que restablece los filtros de una sección."""
    return (ui.button(icon=icono, on_click=on_click)
            .props('flat round').tooltip('Limpiar filtros'))


def filtros_historial(texto_busqueda, estados):
    """Crea los controles de vigencia, búsqueda y estado del portal."""
    with ui.row().classes('w-full items-center gap-3 flex-wrap'):
        vista = ui.toggle(['Vigentes', 'Historial'], value='Vigentes') \
            .props('no-caps unelevated').classes('text-[#164875]')
        buscar = ui.input(placeholder=texto_busqueda) \
            .props('outlined dense clearable').classes('w-full sm:w-72')
        estado = ui.select(['Todos', *estados], value='Todos', label='Estado') \
            .props('outlined dense options-dense').classes('w-40')
    return vista, buscar, estado
