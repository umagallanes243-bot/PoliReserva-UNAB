
# aplicacion/casos_uso/usuarios/actualizar_perfil.py
"""Caso de uso: actualizar el teléfono de un usuario de PoliReserva UNAB V9.

Recibe la identidad autenticada en el servidor.
"""

from aplicacion.puertos.repositorio_usuarios import RepositorioUsuarios
from dominio.reglas.usuarios import UsuarioAutenticado, validar_telefono


class ErrorActualizarPerfil(Exception):
    """La cuenta no cumple las condiciones para modificar su perfil."""


def actualizar_perfil(
    repositorio: RepositorioUsuarios,
    *,
    actor: UsuarioAutenticado,
    telefono: str | None,
) -> dict:
    """Valida y actualiza solamente el teléfono de un perfil completo y activo."""
    usuario = repositorio.obtener_por_id(actor.id_usuario)
    if not actor.puede_editar_perfil(usuario, completo=True):
        raise ErrorActualizarPerfil('El perfil no existe, está incompleto o deshabilitado.')

    actualizado = repositorio.actualizar_telefono(
        actor=actor,
        telefono=validar_telefono(telefono),
    )
    if not actor.puede_editar_perfil(actualizado, completo=True):
        raise ErrorActualizarPerfil('No fue posible actualizar el teléfono.')

    return actualizado
