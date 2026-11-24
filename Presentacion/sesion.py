"""Vincula la sesión web con la identidad autenticada en el servidor."""

from secrets import token_urlsafe
from math import isfinite
from time import time

from fastapi import Request
from nicegui import Client, app

from dominio.reglas.usuarios import ErrorValidacionUsuario, ROLES_ADMINISTRATIVOS, UsuarioAutenticado
from infraestructura.persistencia.usuarios_mysql import RepositorioUsuariosMySQL


CLAVE_SESION = 'polireserva_oidc_v1'
ESTADO_OAUTH = 'polireserva_oauth_estado'
DURACION_SESION = 8 * 60 * 60
DURACION_OAUTH = 10 * 60


def seccion_protegida(ruta: str) -> str | None:
    seccion = ruta.lstrip('/').split('/', 1)[0]
    return seccion if seccion in ('usuario', 'admin') else None


def _vigente(registro: dict) -> bool:
    vence = registro.get('vence')
    return type(vence) in (int, float) and isfinite(vence) and time() < vence


def invalidar_sesion(request: Request) -> None:
    id_nicegui = request.session['id']
    app.storage.user.clear()
    request.session.clear()
    request.session['id'] = id_nicegui
    # Cancela también los eventos de las páginas protegidas abiertas en otras pestañas.
    for cliente in tuple(Client.instances.values()):
        if not seccion_protegida(cliente.page.path):
            continue
        if cliente.request.session.get('id') == id_nicegui:
            cliente.delete()


def iniciar_intento(request: Request) -> str:
    invalidar_sesion(request)
    estado = token_urlsafe(32)
    app.storage.user[ESTADO_OAUTH] = {'estado': estado, 'vence': time() + DURACION_OAUTH}
    return estado


def consumir_intento(request: Request) -> str | None:
    estado = request.query_params.get('state')
    sesion = app.storage.user
    pendiente = sesion.get(ESTADO_OAUTH)
    if not estado or not isinstance(pendiente, dict) or pendiente.get('estado') != estado:
        return None
    if not _vigente(pendiente):
        invalidar_sesion(request)
        return None
    # Un callback repetido queda fuera antes del canje de código.
    if pendiente.get('en_canje'):
        return None
    sesion[ESTADO_OAUTH] = {**pendiente, 'en_canje': True}
    return estado


def intento_vigente(estado: str) -> bool:
    pendiente = app.storage.user.get(ESTADO_OAUTH)
    return isinstance(pendiente, dict) and pendiente.get('estado') == estado and _vigente(pendiente)


def crear_sesion(
    request: Request, actor: UsuarioAutenticado, *, rol: str, nombre: str, foto: str,
) -> None:
    invalidar_sesion(request)
    clave = token_urlsafe(32)
    request.session[CLAVE_SESION] = clave
    app.storage.user.update({
        CLAVE_SESION: {'clave': clave, 'vence': time() + DURACION_SESION},
        'id_usuario': actor.id_usuario,
        'correo': actor.correo,
        'google_sub': actor.google_sub,
        'rol': rol,
        'nombre': nombre,
        'foto': foto,
    })


def obtener_actor(request: Request) -> UsuarioAutenticado | None:
    sesion = app.storage.user
    registro = sesion.get(CLAVE_SESION)
    if not isinstance(registro, dict):
        return None
    clave = registro.get('clave')
    if not isinstance(clave, str) or not clave or request.session.get(CLAVE_SESION) != clave:
        return None
    if not _vigente(registro):
        return None
    try:
        return UsuarioAutenticado(
            sesion.get('id_usuario'), sesion.get('correo'), sesion.get('google_sub'),
        )
    except ErrorValidacionUsuario:
        return None


def exigir_administrador(request: Request) -> UsuarioAutenticado:
    """Autoriza también los eventos de páginas administrativas ya abiertas."""
    actor = obtener_actor(request)
    if actor is None:
        raise ErrorValidacionUsuario('Vuelve a iniciar sesión.')
    usuario = RepositorioUsuariosMySQL().obtener_por_id(actor.id_usuario)
    if (not actor.coincide_con(usuario) or usuario.get('perfil_completo') is not True
            or usuario.get('rol') not in ROLES_ADMINISTRATIVOS
            or usuario['rol'] != app.storage.user.get('rol')):
        raise ErrorValidacionUsuario('Vuelve a iniciar sesión con un rol administrativo vigente.')
    return actor

def descartar_sesion_invalida(request: Request) -> None:
    sesion = app.storage.user
    registro = sesion.get(CLAVE_SESION)
    if isinstance(registro, dict) and registro.get('clave') != request.session.get(CLAVE_SESION):
        # Una pestaña con una cookie anterior no puede cerrar la sesión vigente.
        request.session.pop(CLAVE_SESION, None)
        return
    pendiente = sesion.get(ESTADO_OAUTH)
    if not isinstance(pendiente, dict) or not _vigente(pendiente):
        invalidar_sesion(request)
