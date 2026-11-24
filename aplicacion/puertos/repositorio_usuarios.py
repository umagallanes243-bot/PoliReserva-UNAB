# aplicacion/puertos/repositorio_usuarios.py
"""Contrato de acceso a usuarios de PoliReserva UNAB V9.

La capa de aplicacion depende de este puerto, no de MySQL.
RepositorioUsuariosMySQL lo satisface por coincidencia de metodos
(typing.Protocol): no necesita heredar de esta clase.
"""

from typing import Any, Protocol
from dominio.reglas.usuarios import UsuarioAutenticado


Usuario = dict[str, Any]
Catalogo = dict[str, Any]


class RepositorioUsuarios(Protocol):
    """Operaciones que necesitan los casos de uso del modulo Usuarios."""

    def obtener_por_id(self, id_usuario: int) -> Usuario | None:
        """Obtiene un usuario con sus datos de perfil y rol."""
        ...

    def obtener_por_correo(self, correo: str) -> Usuario | None:
        """Busca un usuario por correo institucional."""
        ...

    def obtener_por_google_sub(self, google_sub: str) -> Usuario | None:
        """Busca un usuario por el identificador estable de Google."""
        ...

    def listar_escuelas(self) -> list[Catalogo]:
        """Devuelve las escuelas profesionales activas."""
        ...

    def listar_tipos_usuario(self) -> list[Catalogo]:
        """Devuelve ESTUDIANTE y DOCENTE habilitados."""
        ...

    def registrar_acceso_google(
        self, *, correo: str, google_sub: str, correo_verificado: bool
    ) -> Usuario:
        """Crea o vincula cuenta tras una autenticacion Google verificada.

        Los datos de identidad deben provenir del backend OAuth, nunca
        de campos manipulables desde el navegador.
        """
        ...

    def completar_perfil(
        self,
        *,
        actor: UsuarioAutenticado,
        nombres: str,
        apellidos: str,
        dni: str,
        codigo_institucional: str,
        id_tipo_usuario: int,
        id_escuela: int,
        telefono: str | None = None,
    ) -> Usuario:
        """Completa el perfil institucional sin permitir asignar roles."""
        ...

    def actualizar_telefono(
        self, *, actor: UsuarioAutenticado, telefono: str | None
    ) -> Usuario:
        """Modifica solo el telefono de un usuario activo."""
        ...
