
# aplicacion/casos_uso/usuarios/identificar_usuario.py
"""Caso de uso: identificar usuario después del inicio de sesión con Google.

No verifica tokens OAuth ni conoce NiceGUI o MySQL. Recibe los datos
ya verificados por el servidor de autenticación y utiliza el puerto.
"""

from aplicacion.puertos.repositorio_usuarios import RepositorioUsuarios
from dominio.reglas.usuarios import (
    ROL_AUTORREGISTRO,
    ROLES_ADMINISTRATIVOS,
    UsuarioAutenticado,
    validar_identidad_google,
)


class ErrorIdentificacionUsuario(Exception):
    """El usuario no puede acceder al sistema con su perfil actual."""


def identificar_usuario(
    repositorio: RepositorioUsuarios,
    *,
    correo: str,
    google_sub: str,
    correo_verificado: bool,
) -> dict:
    """Identifica al usuario y determina el siguiente paso del flujo.

    Los datos de Google deben provenir exclusivamente de la respuesta
    OAuth/OIDC validada en el backend, nunca de un formulario o URL.

    Retorna id_usuario, rol, perfil_completo y siguiente_paso.
    La capa Presentacion decidirá la ruta web a partir de siguiente_paso.
    """
    identidad = validar_identidad_google(
        correo=correo,
        google_sub=google_sub,
        correo_verificado=correo_verificado,
    )

    # El repositorio vincula cuentas preconfiguradas por Google sub/correo
    # o crea cuentas nuevas únicamente con el rol USUARIO.
    usuario = repositorio.registrar_acceso_google(
        correo=identidad['correo'],
        google_sub=identidad['google_sub'],
        correo_verificado=True,
    )

    if not usuario:
        raise ErrorIdentificacionUsuario(
            'No fue posible identificar al usuario.'
        )

    actor = UsuarioAutenticado(usuario['id_usuario'], **identidad)
    if not actor.coincide_con(usuario):
        raise ErrorIdentificacionUsuario('La identidad o el estado de la cuenta no coincide.')

    rol = str(usuario.get('rol') or '').strip().upper()
    perfil_completo = usuario.get('perfil_completo') is True

    if rol == ROL_AUTORREGISTRO:
        siguiente_paso = (
            'INICIO_USUARIO' if perfil_completo
            else 'COMPLETAR_PERFIL'
        )

    elif rol in ROLES_ADMINISTRATIVOS:
        if not perfil_completo:
            raise ErrorIdentificacionUsuario(
                'El perfil administrativo debe estar preconfigurado.'
            )

        siguiente_paso = 'INICIO_ADMIN'

    else:
        raise ErrorIdentificacionUsuario(
            'La cuenta no tiene un rol permitido.'
        )

    return {
        'id_usuario': usuario['id_usuario'],
        'rol': rol,
        'perfil_completo': perfil_completo,
        'siguiente_paso': siguiente_paso,
    }
