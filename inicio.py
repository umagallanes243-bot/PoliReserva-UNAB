# inicio.py - PoliReserva UNAB V9
"""Punto de entrada NiceGUI: Google OIDC, sesión, cambio de cuenta y roles."""

import asyncio
import logging
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app, ui
from starlette.middleware.base import BaseHTTPMiddleware

import Presentacion.admin  # Registra las páginas administrativas existentes
from Presentacion.sesion import (
    DURACION_SESION,
    consumir_intento,
    crear_sesion,
    descartar_sesion_invalida,
    iniciar_intento,
    intento_vigente,
    invalidar_sesion,
    obtener_actor,
    seccion_protegida,
)
from Presentacion.estudiante import (
    calendario,
    inicio_usuario,
    mi_perfil,
    mis_prestamos,
    mis_reservas,
    registro_inicial,
    resumen_reserva,
    solicitar_prestamo,
)

from aplicacion.casos_uso.usuarios.identificar_usuario import (
    ErrorIdentificacionUsuario,
    identificar_usuario,
)
from aplicacion.casos_uso.reservas.actualizar_estados import actualizar_estados
from dominio.reglas.usuarios import (
    ErrorValidacionUsuario, ROLES_ADMINISTRATIVOS, ROL_AUTORREGISTRO,
    UsuarioAutenticado, validar_correo_institucional,
)
from infraestructura.autenticacion.google_oauth import (
    ErrorAutenticacionGoogle,
    iniciar_sesion_google,
    obtener_identidad_google,
    url_retorno,
)
from infraestructura.persistencia.usuarios_mysql import (
    AccesoTemporalmenteBloqueado,
    ErrorUsuario,
    RepositorioUsuariosMySQL,
)

load_dotenv(Path(__file__).resolve().parent / '.env')
logger = logging.getLogger(__name__)
ERROR_OAUTH = '/error-acceso?motivo=google'
HOST_LOCAL = '127.0.0.1'
PUERTO_LOCAL = 8080


def comprobar_puerto_local() -> None:
    """Detecta otro servidor antes de que la recarga de Uvicorn reserve el puerto."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as comprobacion:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            comprobacion.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            comprobacion.bind((HOST_LOCAL, PUERTO_LOCAL))
        except OSError as exc:
            raise SystemExit(
                f'El puerto {PUERTO_LOCAL} no está disponible. '
                'Cierra la instancia que lo usa antes de iniciar PoliReserva.'
            ) from exc


def correo_institucional_valido(correo) -> bool:
    """Acepta únicamente direcciones exactas @unab.edu.pe."""
    try:
        validar_correo_institucional(correo)
        return True
    except ErrorValidacionUsuario:
        return False


def redirigir(ruta: str) -> RedirectResponse:
    return RedirectResponse(url=ruta, status_code=303, headers={'Cache-Control': 'no-store'})


@app.add_middleware
class ProteccionDeRutas(BaseHTTPMiddleware):
    """Comprueba en MySQL quién puede entrar a cada sección.

    Este control complementa las validaciones que también deben existir
    en cada caso de uso antes de escribir datos.
    """

    async def dispatch(self, request: Request, call_next):
        ruta = request.url.path.rstrip('/') or '/'

        if ruta == '/vista-previa':
            return redirigir('/')

        seccion = seccion_protegida(ruta)
        if not seccion and ruta != '/':
            return await call_next(request)

        sesion = app.storage.user
        actor = obtener_actor(request)
        if actor is None:
            correo = sesion.get('correo')
            if sesion or seccion:
                descartar_sesion_invalida(request)
            if not seccion:
                return await call_next(request)
            return redirigir('/error-dominio' if correo and not correo_institucional_valido(correo) else '/')

        try:
            registro = await asyncio.to_thread(
                RepositorioUsuariosMySQL().obtener_por_id, actor.id_usuario,
            )
        except Exception as exc:
            logger.error('No se pudo comprobar la cuenta en MySQL (%s)', type(exc).__name__)
            return redirigir('/error-acceso')

        if obtener_actor(request) != actor:
            return redirigir('/')
        if not actor.coincide_con(registro):
            invalidar_sesion(request)
            return redirigir('/error-acceso')

        rol = registro.get('rol')
        completo = registro.get('perfil_completo') is True
        es_admin = rol in ROLES_ADMINISTRATIVOS and completo
        if rol != ROL_AUTORREGISTRO and not es_admin:
            invalidar_sesion(request)
            return redirigir('/error-acceso')
        if rol != sesion.get('rol'):
            # Los nuevos permisos requieren una autenticación nueva.
            invalidar_sesion(request)
            return redirigir('/login')

        if seccion == 'admin':
            if not es_admin:
                return redirigir('/')
        elif seccion == 'usuario':
            if es_admin:
                return redirigir('/admin/dashboard')
            if ruta == '/usuario/registro' and completo:
                return redirigir('/usuario/inicio')
            if ruta != '/usuario/registro' and not completo:
                return redirigir('/usuario/registro')

        request.state.actor = actor
        request.state.usuario = registro
        sesion.update({
            'codigo_institucional': registro.get('codigo_institucional'),
            'escuela': registro.get('escuela'),
        })
        respuesta = await call_next(request)
        respuesta.headers['Cache-Control'] = 'no-store'
        return respuesta


@app.get('/login')
async def login(request: Request):
    """Envía al navegador a Google para la autenticación institucional."""
    estado = None
    try:
        retorno = urlsplit(url_retorno())
        locales = {'localhost', '127.0.0.1'}
        if (request.url.hostname in locales and retorno.hostname in locales
                and request.url.netloc != retorno.netloc):
            # La cookie del intento debe guardarse en el mismo origen del callback.
            return redirigir(f'{retorno.scheme}://{retorno.netloc}/login')

        estado = iniciar_intento(request)
        respuesta = await iniciar_sesion_google(request, estado=estado)
    except Exception as exc:
        logger.error('No se pudo iniciar Google OAuth (%s)', type(exc).__name__)
        if estado and intento_vigente(estado):
            invalidar_sesion(request)
        return redirigir('/error-acceso')
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta


@app.get('/auth/callback')
async def auth_callback(request: Request):
    """Recibe la identidad validada y decide el destino con datos MySQL."""
    estado = consumir_intento(request)
    if estado is None:
        logger.warning('El retorno de Google llegó sin un intento de acceso vigente.')
        if obtener_actor(request) is None:
            descartar_sesion_invalida(request)
        return redirigir(ERROR_OAUTH)

    destino = '/error-acceso'
    try:
        identidad = await obtener_identidad_google(request)
        if not intento_vigente(estado):
            return redirigir(ERROR_OAUTH)
        resultado = await asyncio.to_thread(
            identificar_usuario,
            RepositorioUsuariosMySQL(),
            correo=identidad['correo'],
            google_sub=identidad['google_sub'],
            correo_verificado=identidad['correo_verificado'],
        )
    except ErrorValidacionUsuario as exc:
        logger.warning('Autenticación institucional rechazada: %s', exc)
        destino = '/error-dominio'
    except ErrorAutenticacionGoogle as exc:
        logger.warning('No se pudo verificar el acceso con Google: %s', exc)
        destino = ERROR_OAUTH
    except AccesoTemporalmenteBloqueado:
        logger.warning('Otra transacción en MySQL bloqueó el registro del acceso.')
        destino = '/error-acceso?motivo=base-ocupada'
    except (ErrorIdentificacionUsuario, ErrorUsuario):
        logger.warning('Cuenta institucional rechazada en el proceso de acceso')
    except Exception as exc:
        logger.error('Error durante la autenticación (%s)', type(exc).__name__)
    else:
        if not intento_vigente(estado):
            return redirigir(ERROR_OAUTH)
        actor = UsuarioAutenticado(resultado['id_usuario'], identidad['correo'], identidad['google_sub'])
        crear_sesion(
            request, actor,
            rol=resultado['rol'],
            nombre=identidad['nombre'] or actor.correo.split('@')[0],
            foto=identidad['foto'],
        )
        return redirigir({
            'COMPLETAR_PERFIL': '/usuario/registro',
            'INICIO_USUARIO': '/usuario/inicio',
            'INICIO_ADMIN': '/admin/dashboard',
        }[resultado['siguiente_paso']])

    if intento_vigente(estado):
        invalidar_sesion(request)
    return redirigir(destino)


@app.get('/logout')
async def logout(request: Request, cambiar: bool = False):
    """Cierra PoliReserva, incluso con el perfil institucional incompleto.

    cambiar=true inicia un nuevo acceso con el selector de cuentas Google.
    No cierra Gmail ni otras sesiones de Google del navegador.
    """
    invalidar_sesion(request)
    return redirigir('/login' if cambiar else '/')


@ui.page('/')
def vista_login(request: Request):
    # El OAuth local utiliza exactamente localhost, no 127.0.0.1.
    ui.run_javascript(
        "if (window.location.hostname === '127.0.0.1') "
        "window.location.hostname = 'localhost';"
    )
    ui.query('body').style('margin:0; padding:0; overflow:hidden;')
    ui.query('.nicegui-content').style(
        'padding:0; margin:0; width:100%; height:100vh;'
    )

    with ui.element('div').classes('relative w-full h-screen overflow-hidden'):
        ui.image('CanchaUNAB.png').classes(
            'absolute inset-0 w-full h-full object-cover'
        )
        with ui.row().classes(
            'absolute top-0 left-0 w-full bg-[#0A1B3F] '
            'p-4 items-center gap-4 z-10 shadow-md'
        ):
            ui.image('logo_unab.png').classes('w-43 h-15')
            ui.label('ACCESO - POLIRESERVA').classes(
                'text-yellow-400 text-h5 font-bold tracking-wide'
            )

        with ui.column().classes(
            'absolute inset-0 flex items-center justify-center p-4 z-10'
        ):
            ui.image('logo_unab_azul.png').classes('w-55 h-20 mb-4') \
                .style('filter:drop-shadow(0 0 8px rgba(255,255,255,.9))')
            with ui.card().classes(
                'w-full max-w-sm p-6 text-center shadow-12 '
                'rounded-2xl bg-white/95 backdrop-blur-sm'
            ):
                usuario = getattr(request.state, 'usuario', None)
                if usuario:
                    sesion = app.storage.user
                    if sesion.get('foto'):
                        ui.image(sesion['foto']).classes(
                            'w-20 h-20 rounded-full mx-auto mb-3 object-cover'
                        )
                    else:
                        ui.icon('account_circle', size='5rem').classes(
                            'mx-auto text-gray-400 mb-2'
                        )
                    ui.label(f"¡Hola, {sesion.get('nombre', 'Usuario')}!") \
                        .classes('text-lg font-bold text-gray-800')
                    ui.label(sesion.get('correo', '')).classes(
                        'text-xs text-gray-500 mb-4'
                    )
                    destino = (
                        '/admin/dashboard' if usuario['rol'] in ROLES_ADMINISTRATIVOS else
                        '/usuario/inicio' if usuario['perfil_completo'] else
                        '/usuario/registro'
                    )
                    ui.button(
                        'Ir a mi panel', on_click=lambda: ui.navigate.to(destino)
                    ).classes('w-full bg-blue-600 text-white rounded-xl')
                    ui.button(
                        'Cambiar de cuenta', icon='switch_account',
                        on_click=lambda: ui.navigate.to('/logout?cambiar=true'),
                    ).props('outline no-caps').classes('w-full text-[#164875]')
                    ui.button(
                        'Cerrar sesión', icon='logout',
                        on_click=lambda: ui.navigate.to('/logout'),
                    ).props('flat no-caps').classes('w-full text-red-600')
                else:
                    ui.label('¡Bienvenido a PoliReserva!').classes(
                        'text-lg font-bold text-gray-800'
                    )
                    ui.label(
                        'Inicia sesión con tu cuenta institucional para gestionar tus reservas.'
                    ).classes('text-sm text-gray-600 mb-2 leading-relaxed')
                    ui.button(
                        'Continuar con Correo Institucional UNAB',
                        icon='school',
                        on_click=lambda: ui.navigate.to('/login'),
                    ).classes(
                        'w-full bg-blue-600 hover:bg-blue-700 '
                        'text-white font-bold text-xs py-3 rounded-xl'
                    )


@ui.page('/error-dominio')
def pagina_error_dominio():
    with ui.card().classes('w-full max-w-md mx-auto my-20 p-6 text-center'):
        ui.icon('warning', color='red', size='4em')
        ui.label('Acceso no autorizado').classes('text-xl font-bold text-red-600')
        ui.label('Debes autenticarte con una cuenta institucional UNAB verificada.')
        ui.button('Cambiar de cuenta', icon='switch_account',
                  on_click=lambda: ui.navigate.to('/logout?cambiar=true')) \
            .props('no-caps').classes('bg-[#164875] text-white')
        ui.button('Volver al inicio', on_click=lambda: ui.navigate.to('/')) \
            .props('flat no-caps')


@ui.page('/error-acceso')
def pagina_error_acceso(motivo: str = ''):
    with ui.card().classes('w-full max-w-md mx-auto my-20 p-6 text-center'):
        ui.icon('warning', color='red', size='4em')
        ui.label('No fue posible iniciar sesión').classes('text-xl font-bold')
        if motivo == 'google':
            ui.label('No se pudo verificar este intento de acceso con Google. Puedes volver a usar la misma cuenta.')
        elif motivo == 'base-ocupada':
            ui.label('Otra transacción está bloqueando el acceso. Si estás editando el rol en MySQL, '
                     'confirma o revierte esa edición y vuelve a iniciar sesión.')
        else:
            ui.label('Comprueba que tu cuenta esté habilitada o comunícate con el administrador.')
        ui.button('Volver a iniciar sesión', icon='switch_account',
                  on_click=lambda: ui.navigate.to('/logout?cambiar=true')) \
            .props('no-caps').classes('bg-[#164875] text-white')
        ui.button('Volver al inicio', on_click=lambda: ui.navigate.to('/')) \
            .props('flat no-caps')


def programar_cierre_reservas(intervalo=60):
    """Registra un temporizador del servidor, independiente de las páginas."""
    async def cerrar_reservas_vencidas():
        await asyncio.to_thread(actualizar_estados)

    return app.timer(intervalo, cerrar_reservas_vencidas, immediate=False)


if __name__ in {'__main__', '__mp_main__'}:
    secreto = os.getenv('NICEGUI_STORAGE_SECRET', '').strip()
    if len(secreto) < 32:
        raise RuntimeError('Configura NICEGUI_STORAGE_SECRET seguro en el archivo .env')

    if __name__ == '__main__':
        comprobar_puerto_local()

    programar_cierre_reservas()

    ui.run(
        title='POLIRESERVA - UNAB',
        host=HOST_LOCAL,
        port=PUERTO_LOCAL,
        reload=True,
        storage_secret=secreto,
        session_middleware_kwargs={
            'https_only': url_retorno().startswith('https://'),
            'same_site': 'lax',
            'max_age': DURACION_SESION,
        },
    )
