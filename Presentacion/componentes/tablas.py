"""Tablas y distintivos de estado reutilizables."""

from nicegui import ui


COLORES_RESERVA = {
    'RESERVADA': 'orange-7',
    'CONFIRMADA': 'green-7',
    'FINALIZADA': 'blue-7',
    'CANCELADA': 'grey-7',
    'INASISTENCIA': 'red-7',
}
COLORES_PRESTAMO = {
    'PENDIENTE': 'amber-8',
    'ENTREGADO': 'blue-7',
    'DEVUELTO': 'green-7',
    'CANCELADO': 'grey-7',
}


def tabla_datos(columnas, filas=None, clave_fila=None, paginacion=10,
                seleccion='single', sin_datos=None, props='flat bordered dense',
                clases='w-full rounded-lg'):
    """Crea una tabla con el aspecto común del sistema.

    ``props`` y ``clases`` se exponen para conservar las pequeñas variantes
    que ya existían (por ejemplo, tablas de solo consulta sin selección).
    """
    etiqueta = f' no-data-label="{sin_datos}"' if sin_datos else ''
    return (ui.table(columns=columnas, rows=filas or [], row_key=clave_fila,
                     selection=seleccion, pagination=paginacion)
            .props(props + etiqueta).classes(clases))


def slot_badge_mapa(tabla, columna, mapa, defecto='grey-7', clases='',
                    mayusculas=False, vacio=''):
    """Pinta una columna con ``q-badge`` según un mapa valor → color.

    ``mapa`` usa los nombres de color de Quasar (``orange-7``, ``green-7``…).
    El valor que no figure en el mapa toma el color ``defecto``. Si ``vacio``
    no está vacío, se muestra ese texto cuando la celda no tiene valor.
    """
    opciones = ', '.join(f'{clave!r}: {valor!r}' for clave, valor in mapa.items())
    clave_vue = ("String(props.value || '').toUpperCase()"
                 if mayusculas else 'props.value')
    expresion = f"({{ {opciones} }})[{clave_vue}] || '{defecto}'"
    contenido = ('{{ props.value }}' if not vacio
                 else f"{{{{ props.value || '{vacio}' }}}}")
    tabla.add_slot(f'body-cell-{columna}', (
        '<q-td :props="props">'
        f'<q-badge :color="{expresion}" class="{clases}">'
        f'{contenido}'
        '</q-badge>'
        '</q-td>'
    ))


def slot_badge_color(tabla, columna, color='blue-grey-7', clases='px-2 py-1'):
    """Pinta una columna con un ``q-badge`` de color fijo."""
    tabla.add_slot(f'body-cell-{columna}', (
        '<q-td :props="props">'
        f'<q-badge color="{color}" class="{clases}">'
        '{{ props.value }}'
        '</q-badge>'
        '</q-td>'
    ))


def fila_seleccionada(tabla, mensaje):
    """Devuelve la fila elegida o avisa al usuario cuando no hay selección."""
    if not tabla.selected:
        ui.notify(mensaje, type='warning')
        return None
    return tabla.selected[0]
