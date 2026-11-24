
# aplicacion/casos_uso/usuarios/completar_perfil.py
"""Caso de uso para completar el perfil institucional (PoliReserva UNAB V9).

Recibe la identidad autenticada en el servidor.
"""

from aplicacion.puertos.repositorio_usuarios import RepositorioUsuarios
from dominio.reglas.usuarios import (
    TIPOS_AUTORREGISTRO,
    UsuarioAutenticado,
    validar_datos_perfil,
)


class ErrorCompletarPerfil(Exception):
    """El perfil no puede completarse en su estado actual."""


def completar_perfil(
    repositorio: RepositorioUsuarios,
    *,
    actor: UsuarioAutenticado,
    nombres: str,
    apellidos: str,
    dni: str,
    codigo_institucional: str,
    id_tipo_usuario: int,
    id_escuela: int,
    telefono: str | None = None,
) -> dict:
    """Valida y completa el perfil de un estudiante o docente.

    - El usuario ya fue autenticado con Google y creado/vinculado en MySQL.
    - Solo admite cuentas activas con rol USUARIO y perfil incompleto.
    - Los tipos y escuelas se validan contra los catálogos activos.
    - El repositorio realiza el UPDATE en una transacción.
    """
    usuario = repositorio.obtener_por_id(actor.id_usuario)
    if not actor.puede_editar_perfil(usuario, completo=False):
        raise ErrorCompletarPerfil('Se requiere una cuenta institucional activa con perfil incompleto.')

    datos = validar_datos_perfil(
        nombres=nombres,
        apellidos=apellidos,
        dni=dni,
        codigo_institucional=codigo_institucional,
        id_tipo_usuario=id_tipo_usuario,
        id_escuela=id_escuela,
        telefono=telefono,
    )

    tipos_validos = {
        item['id_tipo_usuario']
        for item in repositorio.listar_tipos_usuario()
        if str(item.get('nombre_tipo') or '').upper() in TIPOS_AUTORREGISTRO
    }
    if datos['id_tipo_usuario'] not in tipos_validos:
        raise ErrorCompletarPerfil('Selecciona Estudiante o Docente.')

    escuelas_validas = {
        item['id_escuela'] for item in repositorio.listar_escuelas()
    }
    if datos['id_escuela'] not in escuelas_validas:
        raise ErrorCompletarPerfil('Selecciona una escuela profesional válida.')

    # El repositorio vuelve a comprobar los permisos y catálogos bajo
    # transacción para evitar condiciones de carrera entre comprobación y UPDATE.
    perfil = repositorio.completar_perfil(actor=actor, **datos)
    if not actor.puede_editar_perfil(perfil, completo=True):
        raise ErrorCompletarPerfil('No fue posible completar el perfil.')

    return perfil
