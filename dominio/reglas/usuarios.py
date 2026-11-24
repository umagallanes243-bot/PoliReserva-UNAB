
# dominio/reglas/usuarios.py
"""Reglas de negocio del módulo Usuarios - PoliReserva UNAB V9."""

import re
from dataclasses import dataclass

TIPOS_AUTORREGISTRO = frozenset({'ESTUDIANTE', 'DOCENTE'})
ROLES_ADMINISTRATIVOS = frozenset({'ASISTENTE', 'ADMINISTRADOR'})
ROL_AUTORREGISTRO = 'USUARIO'


class ErrorValidacionUsuario(ValueError):
    """Error de validación de datos o permisos."""


def validar_correo_institucional(correo: str) -> str:
    if not isinstance(correo, str):
        raise ErrorValidacionUsuario('Correo institucional inválido.')

    correo = correo.strip().lower()

    if len(correo) > 120 or not re.fullmatch(
        r'[a-z0-9._%+\-]+@unab\.edu\.pe', correo
    ):
        raise ErrorValidacionUsuario(
            'Se requiere un correo @unab.edu.pe válido.'
        )

    return correo


def validar_identidad_google(
    *, correo: str, google_sub: str, correo_verificado: bool
) -> dict:
    # Estos datos deben proceder del backend OAuth verificado.
    if correo_verificado is not True:
        raise ErrorValidacionUsuario(
            'Google debe haber verificado el correo.'
        )

    correo = validar_correo_institucional(correo)
    return {'correo': correo, 'google_sub': validar_google_sub(google_sub)}


def validar_google_sub(google_sub: str) -> str:
    if not isinstance(google_sub, str) or not re.fullmatch(r'[!-~]{1,255}', google_sub):
        raise ErrorValidacionUsuario('La identidad de Google no es válida.')
    return google_sub


@dataclass(frozen=True)
class UsuarioAutenticado:
    """Identidad que el servidor obtuvo de una sesión OAuth vigente."""

    id_usuario: int
    correo: str
    google_sub: str

    def __post_init__(self):
        object.__setattr__(self, 'id_usuario', validar_id_catalogo(self.id_usuario, 'Usuario'))
        object.__setattr__(self, 'correo', validar_correo_institucional(self.correo))
        validar_google_sub(self.google_sub)

    def coincide_con(self, usuario: dict | None) -> bool:
        return bool(
            usuario
            and usuario.get('id_usuario') == self.id_usuario
            and str(usuario.get('correo_institucional') or '').lower() == self.correo
            and usuario.get('google_sub') == self.google_sub
            and all(usuario.get(campo) is True
                    for campo in ('usuario_activo', 'perfil_activo', 'rol_activo'))
        )

    def puede_editar_perfil(self, usuario: dict | None, *, completo: bool) -> bool:
        return bool(
            self.coincide_con(usuario)
            and usuario.get('rol') == ROL_AUTORREGISTRO
            and usuario.get('perfil_completo') is completo
        )


def _texto_obligatorio(valor: str, campo: str, maximo: int) -> str:
    if not isinstance(valor, str):
        raise ErrorValidacionUsuario(f'{campo} no es válido.')

    valor = ' '.join(valor.split())

    if not 1 <= len(valor) <= maximo:
        raise ErrorValidacionUsuario(
            f'{campo} debe tener entre 1 y {maximo} caracteres.'
        )

    return valor


def validar_dni(dni: str) -> str:
    if not isinstance(dni, str) or not re.fullmatch(
        r'[0-9]{8}', dni.strip()
    ):
        raise ErrorValidacionUsuario(
            'El DNI debe tener exactamente 8 dígitos.'
        )

    return dni.strip()


def validar_codigo_institucional(codigo: str) -> str:
    codigo = _texto_obligatorio(
        codigo, 'Código institucional', 25
    )

    if any(caracter.isspace() for caracter in codigo):
        raise ErrorValidacionUsuario(
            'El código institucional no debe contener espacios.'
        )

    return codigo


def validar_telefono(telefono: str | None) -> str | None:
    if telefono is None or (
        isinstance(telefono, str) and not telefono.strip()
    ):
        return None

    if not isinstance(telefono, str):
        raise ErrorValidacionUsuario('Teléfono inválido.')

    telefono = telefono.strip()

    if len(telefono) > 15 or not re.fullmatch(
        r'\+?[0-9]{7,15}', telefono
    ):
        raise ErrorValidacionUsuario(
            'El teléfono debe contener de 7 a 15 dígitos.'
        )

    return telefono


def validar_id_catalogo(valor: int, nombre: str) -> int:
    if isinstance(valor, bool):
        raise ErrorValidacionUsuario(
            f'{nombre} no es válido.'
        )

    try:
        numero = int(valor)

        if str(valor).strip() != str(numero) or numero <= 0:
            raise ValueError

    except (TypeError, ValueError, OverflowError) as exc:
        raise ErrorValidacionUsuario(
            f'{nombre} no es válido.'
        ) from exc

    return numero


def validar_tipo_autorregistro(tipo: str) -> str:
    if not isinstance(tipo, str) or (
        tipo.strip().upper() not in TIPOS_AUTORREGISTRO
    ):
        raise ErrorValidacionUsuario(
            'Solo pueden autorregistrarse estudiantes y docentes.'
        )

    return tipo.strip().upper()


def validar_rol_autorregistro(
    rol: str = ROL_AUTORREGISTRO
) -> str:
    if rol != ROL_AUTORREGISTRO:
        raise ErrorValidacionUsuario(
            'Los roles administrativos no se pueden autorasignar.'
        )

    return ROL_AUTORREGISTRO


def validar_datos_perfil(
    *,
    nombres: str,
    apellidos: str,
    dni: str,
    codigo_institucional: str,
    id_tipo_usuario: int,
    id_escuela: int,
    telefono: str | None = None,
) -> dict:
    """Valida los datos enviados por el registro inicial."""

    return {
        'nombres': _texto_obligatorio(
            nombres, 'Nombres', 80
        ),
        'apellidos': _texto_obligatorio(
            apellidos, 'Apellidos', 100
        ),
        'dni': validar_dni(dni),
        'codigo_institucional': validar_codigo_institucional(
            codigo_institucional
        ),
        'id_tipo_usuario': validar_id_catalogo(
            id_tipo_usuario, 'Tipo de usuario'
        ),
        'id_escuela': validar_id_catalogo(
            id_escuela, 'Escuela profesional'
        ),
        'telefono': validar_telefono(telefono),
    }


def es_rol_administrativo(rol: str) -> bool:
    return (
        isinstance(rol, str)
        and rol.strip().upper() in ROLES_ADMINISTRATIVOS
    )
