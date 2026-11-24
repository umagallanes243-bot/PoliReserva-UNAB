# Presentacion/estudiante/mi_perfil.py
"""Consulta del perfil institucional y actualización del teléfono."""

import asyncio
import logging

from fastapi import Request
from nicegui import app, ui
from aplicacion.casos_uso.usuarios.actualizar_perfil import ErrorActualizarPerfil, actualizar_perfil
from dominio.reglas.usuarios import ErrorValidacionUsuario, validar_telefono
from infraestructura.persistencia.usuarios_mysql import ErrorUsuario, RepositorioUsuariosMySQL
from Presentacion.estudiante.layout_usuario import crear_marco_usuario
from Presentacion.componentes.tarjetas import tarjeta_seccion, titulo_pagina
from Presentacion.sesion import obtener_actor

logger = logging.getLogger(__name__)


def campo_lectura(etiqueta, valor):
    """Muestra datos del perfil sin permitir modificarlos."""
    ui.input(etiqueta, value=str(valor).strip() if valor else '—') \
        .props('outlined dense readonly') \
        .classes('w-full min-w-0')


@ui.page('/usuario/perfil', response_timeout=15)
def pagina_mi_perfil(request: Request):
    actor = obtener_actor(request)
    perfil = getattr(request.state, 'usuario', None)
    if actor is None or not actor.puede_editar_perfil(perfil, completo=True):
        ui.navigate.to('/')
        return
    if not crear_marco_usuario('MI PERFIL'):
        return

    nombre = ' '.join(
        str(perfil.get(k) or '').strip() for k in ('nombres', 'apellidos')
    ).strip() or app.storage.user.get('nombre')
    correo = actor.correo
    codigo = perfil.get('codigo_institucional')
    tipo = perfil.get('tipo_usuario') or perfil.get('nombre_tipo_usuario')
    escuela = perfil.get('nombre_escuela') or perfil.get('escuela')
    telefono_original = perfil.get('telefono') or ''
    telefono_revisado = None
    foto = app.storage.user.get('foto')

    with ui.column().classes('w-full max-w-[1160px] mx-auto px-3 md:px-5 py-4 gap-3'):
        titulo_pagina('MI PERFIL', 'account_circle', icono_px='23px')

        # Dos paneles proporcionados: sin alturas fijas ni espacios vacíos.
        with ui.element('div').classes(
            'w-full grid grid-cols-1 lg:grid-cols-[245px_minmax(0,1fr)] '
            'gap-3 items-start'
        ):
            # Panel izquierdo: identificación
            with tarjeta_seccion(padding='p-4', extra='items-center', gap='gap-2'):
                if foto:
                    ui.image(foto).classes('w-20 h-20 rounded-full object-cover')
                else:
                    ui.icon('account_circle', size='78px').classes('text-[#164875]')
                ui.label(nombre or '—').classes(
                    'text-sm font-bold text-center text-[#09234B] break-words w-full'
                )
                ui.label(correo or '—').classes(
                    'w-full text-xs text-center text-slate-500 break-all'
                )
                if tipo:
                    ui.badge(str(tipo)).props('color=blue-8')

            # Panel derecho: todos los datos en un solo cuadro compacto.
            with tarjeta_seccion(padding='p-4', extra='min-w-0'):
                ui.label('DATOS PERSONALES E INSTITUCIONALES').classes(
                    'text-sm font-bold text-[#09234B]'
                )
                with ui.element('div').classes(
                    'w-full grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-3'
                ):
                    campo_lectura('Nombre completo', nombre)
                    campo_lectura('DNI', perfil.get('dni'))
                    campo_lectura('Código institucional', codigo)
                    campo_lectura('Tipo de usuario', tipo)
                    campo_lectura('Escuela profesional', escuela)
                    campo_lectura('Correo institucional', correo)

                ui.separator().classes('my-1')
                ui.label('DATOS DE CONTACTO').classes('text-sm font-bold text-[#09234B]')
                telefono = ui.input('Teléfono (opcional)', value=telefono_original) \
                    .props('outlined dense maxlength=15') \
                    .classes('w-full sm:max-w-[330px]')

                async def guardar_telefono():
                    nonlocal telefono_original
                    if obtener_actor(request) != actor:
                        ui.navigate.to('/')
                        return
                    if not guardar.enabled:
                        return
                    guardar.disable()
                    try:
                        actualizado = await asyncio.to_thread(
                            actualizar_perfil, RepositorioUsuariosMySQL(),
                            actor=actor, telefono=telefono_revisado,
                        )
                    except (ErrorActualizarPerfil, ErrorUsuario):
                        if not guardar.is_deleted:
                            ui.navigate.to('/error-acceso')
                    except Exception as exc:
                        logger.error('No se pudo guardar el teléfono (%s)', type(exc).__name__)
                        if not guardar.is_deleted:
                            ui.notify('No se pudo guardar el teléfono.', type='negative')
                    else:
                        if not guardar.is_deleted and obtener_actor(request) == actor:
                            telefono_original = actualizado.get('telefono') or ''
                            telefono.set_value(telefono_original)
                            dialogo.close()
                            ui.notify('Teléfono actualizado.', type='positive')
                    finally:
                        if not guardar.is_deleted:
                            guardar.enable()

                with ui.dialog() as dialogo, ui.card().classes('w-full max-w-sm p-4 gap-3'):
                    ui.label('REVISAR CAMBIO DE TELÉFONO').classes(
                        'text-sm font-bold text-[#09234B]'
                    )
                    numero_revisado = ui.label().classes('text-sm text-slate-700')
                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cerrar', on_click=dialogo.close).props('flat no-caps')
                        guardar = ui.button('Guardar cambios', icon='save', on_click=guardar_telefono) \
                            .props('no-caps').disable()

                def revisar_cambios():
                    nonlocal telefono_revisado
                    try:
                        numero = validar_telefono(telefono.value)
                    except ErrorValidacionUsuario as exc:
                        ui.notify(str(exc), type='warning')
                        return
                    if (numero or '') == telefono_original:
                        ui.notify('No hay cambios.', type='info')
                        return
                    telefono_revisado = numero
                    numero_revisado.set_text(f'Teléfono: {numero or "Sin número"}')
                    guardar.enable()
                    dialogo.open()

                with ui.row().classes('w-full justify-end gap-2 mt-1 flex-wrap'):
                    ui.button(
                        'Guardar cambios', icon='visibility', on_click=revisar_cambios
                    ).props('no-caps').classes('bg-[#164875] text-white')
