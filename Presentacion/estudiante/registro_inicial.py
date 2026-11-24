# Presentacion/estudiante/registro_inicial.py
"""Registro institucional - PoliReserva UNAB V9.

Interfaz de registro con navegación segura para salir o cambiar de cuenta.
Guarda el perfil en MySQL por medio del caso de uso completar_perfil.
"""

import asyncio
import logging
import re

from fastapi import Request
from nicegui import app, ui

from aplicacion.casos_uso.usuarios.completar_perfil import (
    ErrorCompletarPerfil,
    completar_perfil,
)
from infraestructura.persistencia.usuarios_mysql import (
    AccesoDenegado,
    DatosDuplicados,
    DatosInvalidos,
    RepositorioUsuariosMySQL,
)
from dominio.reglas.usuarios import ErrorValidacionUsuario
from Presentacion.sesion import obtener_actor

logger = logging.getLogger(__name__)


@ui.page('/usuario/registro', response_timeout=15)
async def pagina_registro_inicial(request: Request):
    actor = obtener_actor(request)
    if actor is None or not actor.puede_editar_perfil(
        getattr(request.state, 'usuario', None), completo=False,
    ):
        ui.navigate.to('/')
        return

    correo = actor.correo
    # Catálogos reales de la V9: no agregar opciones ficticias.
    try:
        repositorio = RepositorioUsuariosMySQL()
        tipos, escuelas = await asyncio.gather(
            asyncio.to_thread(repositorio.listar_tipos_usuario),
            asyncio.to_thread(repositorio.listar_escuelas),
        )
    except Exception:
        logger.exception('No se pudo validar la cuenta y cargar los catálogos')
        ui.navigate.to('/error-acceso')
        return

    if obtener_actor(request) != actor:
        ui.navigate.to('/')
        return

    opciones_tipos = {
        item['id_tipo_usuario']: item['nombre_tipo'].title()
        for item in tipos
    }
    opciones_escuelas = {
        item['id_escuela']: item['nombre_escuela']
        for item in escuelas
    }

    ui.query('body').style('margin:0; background:#F4F5F7;')
    ui.query('.nicegui-content').style('padding:0; margin:0; min-height:100vh;')

    with ui.header().classes(
        'bg-[#0A1B3F] text-white px-4 md:px-6 py-3 '
        'items-center justify-between shadow-md'
    ):
        with ui.row().classes('items-center gap-3'):
            ui.image('logo_unab.png').classes('w-28 md:w-36 h-10 md:h-12 object-contain')
            ui.label('POLIRESERVA - UNAB').classes(
                'text-[#FFC000] text-base md:text-2xl font-bold tracking-wide'
            )
        ui.label('REGISTRO INSTITUCIONAL').classes(
            'hidden sm:block bg-[#7EC4CF] text-[#0A1B3F] '
            'px-3 py-2 rounded-md font-bold text-xs'
        )

    with ui.column().classes('w-full items-center px-4 py-6'):
        with ui.card().classes(
            'w-full max-w-[780px] p-5 md:p-7 gap-4 '
            'rounded-xl border border-slate-200 shadow-sm'
        ):
            with ui.row().classes('items-center gap-3'):
                ui.icon('badge', size='28px').classes('text-[#164875]')
                with ui.column().classes('gap-0'):
                    ui.label('COMPLETAR PERFIL').classes(
                        'text-xl font-bold text-[#09234B]'
                    )
                    ui.label('Datos personales e institucionales').classes(
                        'text-sm text-slate-500'
                    )
            ui.separator()

            ui.input('Correo institucional', value=correo).props(
                'outlined dense readonly'
            ).classes('w-full')

            with ui.element('div').classes(
                'w-full grid grid-cols-1 sm:grid-cols-2 gap-4'
            ):
                nombres = ui.input('Nombres *').props('outlined dense').classes('w-full')
                apellidos = ui.input('Apellidos *').props('outlined dense').classes('w-full')
                dni = ui.input('DNI *', placeholder='8 dígitos').props(
                    'outlined dense maxlength=8'
                ).classes('w-full')
                codigo = ui.input('Código institucional *').props(
                    'outlined dense maxlength=25'
                ).classes('w-full')
                tipo = ui.select(
                    opciones_tipos, label='Tipo de usuario *'
                ).props('outlined dense options-dense').classes('w-full')
                escuela = ui.select(
                    opciones_escuelas, label='Escuela profesional *', with_input=True
                ).props('outlined dense options-dense').classes('w-full')
                telefono = ui.input('Teléfono (opcional)').props(
                    'outlined dense maxlength=15'
                ).classes('w-full')

            def validar_datos() -> bool:
                if not str(nombres.value or '').strip():
                    ui.notify('Ingresa tus nombres.', type='warning')
                    return False
                if not str(apellidos.value or '').strip():
                    ui.notify('Ingresa tus apellidos.', type='warning')
                    return False
                if not re.fullmatch(r'\d{8}', str(dni.value or '').strip()):
                    ui.notify('El DNI debe tener 8 dígitos.', type='warning')
                    return False
                if not str(codigo.value or '').strip():
                    ui.notify('Ingresa tu código institucional.', type='warning')
                    return False
                if tipo.value not in opciones_tipos:
                    ui.notify('Selecciona Estudiante o Docente.', type='warning')
                    return False
                if escuela.value not in opciones_escuelas:
                    ui.notify('Selecciona tu escuela profesional.', type='warning')
                    return False
                tel = str(telefono.value or '').strip()
                if tel and not re.fullmatch(r'\+?\d{7,15}', tel):
                    ui.notify('Verifica el número de teléfono.', type='warning')
                    return False
                return True

            with ui.dialog() as dlg_resumen, ui.card().classes(
                'w-full max-w-md p-5 gap-3 rounded-xl'
            ):
                ui.label('REVISIÓN DEL PERFIL').classes(
                    'text-lg font-bold text-[#09234B]'
                )
                resumen = ui.column().classes('w-full gap-1')
                with ui.row().classes('w-full justify-end'):
                    ui.button('Cerrar', on_click=dlg_resumen.close).props('flat no-caps')

            def mostrar_resumen():
                if not validar_datos():
                    return
                resumen.clear()
                campos = [
                    ('Nombre', f'{nombres.value} {apellidos.value}'),
                    ('DNI', dni.value),
                    ('Código institucional', codigo.value),
                    ('Tipo', opciones_tipos.get(tipo.value, '—')),
                    ('Escuela', opciones_escuelas.get(escuela.value, '—')),
                    ('Correo', correo),
                    ('Teléfono', telefono.value or '—'),
                ]
                with resumen:
                    for titulo, valor in campos:
                        with ui.row().classes('w-full justify-between gap-2'):
                            ui.label(titulo).classes('text-xs text-slate-500')
                            ui.label(str(valor)).classes(
                                'text-xs text-[#09234B] font-medium text-right'
                            )
                dlg_resumen.open()

            with ui.row().classes(
                'w-full justify-end items-center gap-2 flex-wrap mt-2'
            ):
                # Las dos rutas limpian la sesión en el servidor (inicio.py).
                ui.button(
                    'Salir', icon='logout',
                    on_click=lambda: ui.navigate.to('/logout')
                ).props('flat no-caps').classes('text-[#164875]')

                ui.button(
                    'Cambiar de cuenta', icon='switch_account',
                    on_click=lambda: ui.navigate.to('/logout?cambiar=true')
                ).props('outline no-caps').classes('text-[#164875]')

                ui.button('Revisar datos', icon='preview',
                          on_click=mostrar_resumen).props('outline no-caps').classes(
                    'text-[#164875]'
                )

                async def guardar_perfil():
                    if not guardar.enabled or not validar_datos():
                        return

                    # Una sesión en otra pestaña pudo cambiar de cuenta.
                    if obtener_actor(request) != actor:
                        ui.notify('La sesión cambió. Vuelve a iniciar sesión.', type='warning')
                        ui.navigate.to('/')
                        return

                    datos = {
                        'nombres': nombres.value,
                        'apellidos': apellidos.value,
                        'dni': dni.value,
                        'codigo_institucional': codigo.value,
                        'id_tipo_usuario': tipo.value,
                        'id_escuela': escuela.value,
                        'telefono': telefono.value or None,
                    }
                    guardar.disable()
                    try:
                        # Confirmar nuevamente la identidad y permisos desde MySQL.
                        actual = await asyncio.to_thread(
                            repositorio.obtener_por_id, actor.id_usuario
                        )
                        if guardar.is_deleted:
                            return
                        if obtener_actor(request) != actor:
                            ui.notify('La sesión cambió. Vuelve a iniciar sesión.', type='warning')
                            ui.navigate.to('/')
                            return
                        if actor.puede_editar_perfil(actual, completo=True):
                            ui.navigate.to('/usuario/inicio')
                            return
                        if not actor.puede_editar_perfil(actual, completo=False):
                            ui.notify('La cuenta ya no está autorizada.', type='negative')
                            ui.navigate.to('/logout')
                            return

                        perfil = await asyncio.to_thread(
                            completar_perfil, repositorio, actor=actor, **datos,
                        )
                        if guardar.is_deleted or obtener_actor(request) != actor:
                            return

                        app.storage.user['nombre'] = f"{perfil['nombres']} {perfil['apellidos']}"
                        ui.notify('Perfil registrado correctamente.', type='positive')
                        ui.navigate.to('/usuario/inicio')
                    except DatosDuplicados:
                        if not guardar.is_deleted:
                            ui.notify('El DNI o código institucional ya está registrado.',
                                      type='warning')
                    except (ErrorValidacionUsuario, ErrorCompletarPerfil,
                            DatosInvalidos, AccesoDenegado) as exc:
                        if not guardar.is_deleted:
                            ui.notify(str(exc), type='warning')
                    except Exception:
                        logger.exception('Error al guardar perfil institucional')
                        if not guardar.is_deleted:
                            ui.notify('No se pudo guardar el perfil. Intenta nuevamente.',
                                      type='negative')
                    finally:
                        if not guardar.is_deleted:
                            guardar.enable()

                guardar = ui.button(
                    'Guardar perfil', icon='save', on_click=guardar_perfil
                ).props('no-caps').classes(
                    'bg-[#164875] text-white font-semibold'
                )
                if not opciones_tipos or not opciones_escuelas:
                    guardar.disable()
                    ui.notify('No están disponibles los catálogos institucionales.',
                              type='warning')
