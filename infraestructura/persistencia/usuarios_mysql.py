# infraestructura/persistencia/usuarios_mysql.py
"""Acceso a los datos de usuarios y perfiles de PoliReserva UNAB V9.

Este archivo solo accede a MySQL. La verificacion real de Google OAuth,
la autorizacion de rutas y los casos de uso pertenecen a otras capas.
"""

import re
from typing import Any

import mysql.connector
from mysql.connector import errorcode

from dominio.reglas.usuarios import (
    ErrorValidacionUsuario,
    ROLES_ADMINISTRATIVOS,
    ROL_AUTORREGISTRO,
    UsuarioAutenticado,
    validar_identidad_google,
)
from infraestructura.persistencia.conexion_mysql import obtener_conexion


class ErrorUsuario(Exception):
    """Error de validacion o acceso a un usuario."""


class AccesoDenegado(ErrorUsuario):
    """Cuenta deshabilitada o identidad de Google inconsistente."""


class AccesoTemporalmenteBloqueado(ErrorUsuario):
    """Una transacción concurrente impide registrar el acceso."""


class DatosInvalidos(ErrorUsuario):
    """Los datos enviados no cumplen las reglas del perfil."""


class DatosDuplicados(ErrorUsuario):
    """Ya existe un usuario con el mismo dato institucional."""


CONSULTA_USUARIO = """
    SELECT
        u.id_usuario, u.id_tipo_usuario, u.id_escuela, u.google_sub,
        u.codigo_institucional, u.dni, u.nombres, u.apellidos,
        u.correo_institucional, u.telefono, u.fecha_registro,
        u.perfil_completo, u.estado AS usuario_activo,
        p.id_perfil, p.id_rol, p.ultimo_acceso,
        p.estado AS perfil_activo,
        r.nombre_rol AS rol, r.estado AS rol_activo,
        t.nombre_tipo AS tipo_usuario, e.nombre_escuela AS escuela
    FROM tb_usuarios AS u
    LEFT JOIN tb_perfiles AS p ON p.id_usuario = u.id_usuario
    LEFT JOIN tb_roles AS r ON r.id_rol = p.id_rol
    LEFT JOIN tb_tipos_usuarios AS t ON t.id_tipo_usuario = u.id_tipo_usuario
    LEFT JOIN tb_escuelas AS e ON e.id_escuela = u.id_escuela
"""


def _es_activo(valor: Any) -> bool:
    """Normaliza BIT(1) de mysql-connector a bool (incluye b'\\x00')."""
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return int.from_bytes(bytes(valor), byteorder='big') == 1
    return valor == 1 or valor is True


def _normalizar_usuario(usuario: dict | None) -> dict | None:
    if usuario is None:
        return None
    for campo in ('perfil_completo', 'usuario_activo', 'perfil_activo', 'rol_activo'):
        usuario[campo] = _es_activo(usuario.get(campo))
    return usuario


def _id_positivo(valor: Any, campo: str) -> int:
    try:
        if isinstance(valor, bool) or str(valor).strip() != str(int(valor)):
            raise ValueError
        numero = int(valor)
        if numero <= 0:
            raise ValueError
        return numero
    except (ValueError, TypeError, OverflowError) as exc:
        raise DatosInvalidos(f'{campo} no es valido.') from exc


def _texto(valor: str, campo: str, maximo: int) -> str:
    if not isinstance(valor, str):
        raise DatosInvalidos(f'{campo} no es valido.')
    texto = ' '.join(valor.strip().split())
    if not texto or len(texto) > maximo:
        raise DatosInvalidos(f'{campo} debe tener entre 1 y {maximo} caracteres.')
    return texto


def _telefono(valor: str | None) -> str | None:
    if valor is None or not str(valor).strip():
        return None
    telefono = str(valor).strip()
    if len(telefono) > 15 or not re.fullmatch(r'\+?[0-9]{7,15}', telefono):
        raise DatosInvalidos('El telefono debe contener entre 7 y 15 digitos (maximo 15 caracteres).')
    return telefono


class RepositorioUsuariosMySQL:
    """Repositorio de usuarios, perfiles, tipos de usuario y escuelas."""

    def _consultar_uno(self, sql: str, parametros: tuple) -> dict | None:
        conexion = obtener_conexion()
        cursor = None
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute(sql, parametros)
            return _normalizar_usuario(cursor.fetchone())
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def _consultar_lista(self, sql: str, parametros: tuple = ()) -> list[dict]:
        conexion = obtener_conexion()
        cursor = None
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute(sql, parametros)
            return cursor.fetchall()
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def obtener_por_id(self, id_usuario: int) -> dict | None:
        return self._consultar_uno(
            CONSULTA_USUARIO + ' WHERE u.id_usuario = %s',
            (_id_positivo(id_usuario, 'Usuario'),),
        )

    def listar_usuarios(self) -> list[dict]:
        return [_normalizar_usuario(fila) for fila in self._consultar_lista(
            CONSULTA_USUARIO + ' ORDER BY u.apellidos, u.nombres, u.id_usuario'
        )]

    def obtener_por_correo(self, correo: str) -> dict | None:
        return self._consultar_uno(
            CONSULTA_USUARIO + ' WHERE u.correo_institucional = %s',
            (correo.strip().lower(),),
        )

    def obtener_por_google_sub(self, google_sub: str) -> dict | None:
        usuario = self._consultar_uno(
            CONSULTA_USUARIO + ' WHERE u.google_sub = %s',
            (google_sub,),
        )
        return usuario if usuario and usuario['google_sub'] == google_sub else None

    def listar_escuelas(self) -> list[dict]:
        """Escuelas activas; lista vacia hasta cargar el catalogo institucional."""
        return self._consultar_lista(
            """SELECT id_escuela, nombre_escuela, sigla
               FROM tb_escuelas WHERE estado = b'1'
               ORDER BY nombre_escuela"""
        )

    def listar_tipos_usuario(self) -> list[dict]:
        """Solo tipos que se pueden seleccionar en el registro inicial."""
        return self._consultar_lista(
            """SELECT id_tipo_usuario, nombre_tipo
               FROM tb_tipos_usuarios
               WHERE estado = b'1'
                 AND nombre_tipo IN ('ESTUDIANTE', 'DOCENTE')
               ORDER BY id_tipo_usuario"""
        )

    def registrar_acceso_google(
        self, *, correo: str, google_sub: str, correo_verificado: bool
    ) -> dict:
        """Identifica una cuenta vinculada o crea un perfil nuevo con rol USUARIO."""
        try:
            identidad = validar_identidad_google(
                correo=correo, google_sub=google_sub, correo_verificado=correo_verificado,
            )
        except ErrorValidacionUsuario as exc:
            raise AccesoDenegado('La identidad institucional no es válida.') from exc
        correo, google_sub = identidad['correo'], identidad['google_sub']

        conexion = obtener_conexion()
        cursor = None
        try:
            conexion.start_transaction()
            cursor = conexion.cursor(dictionary=True)
            cursor.execute('SET SESSION innodb_lock_wait_timeout = 5')

            # google_sub identifica una cuenta de Google de forma estable.
            cursor.execute(
                """SELECT id_usuario, correo_institucional
                   FROM tb_usuarios WHERE google_sub = %s FOR UPDATE""",
                (google_sub,),
            )
            vinculado = cursor.fetchone()
            if vinculado and vinculado['correo_institucional'].lower() != correo:
                raise AccesoDenegado('La identidad de Google no coincide con el correo registrado.')

            cursor.execute(
                """SELECT id_usuario, google_sub
                   FROM tb_usuarios WHERE correo_institucional = %s FOR UPDATE""",
                (correo,),
            )
            existente = cursor.fetchone()

            if existente:
                # Un correo institucional puede reasignarse a otra persona.
                if existente['google_sub'] != google_sub or not vinculado:
                    raise AccesoDenegado('El correo registrado requiere un vínculo Google autorizado.')
                id_usuario = existente['id_usuario']
            else:
                if vinculado:
                    raise AccesoDenegado('La cuenta de Google ya pertenece a otro usuario.')
                cursor.execute(
                    """SELECT id_rol FROM tb_roles
                       WHERE nombre_rol = 'USUARIO' AND estado = b'1'"""
                )
                rol = cursor.fetchone()
                if rol is None:
                    raise DatosInvalidos('Falta configurar el rol USUARIO en MySQL.')

                cursor.execute(
                    """INSERT INTO tb_usuarios (correo_institucional, google_sub)
                       VALUES (%s, %s)""",
                    (correo, google_sub),
                )
                id_usuario = cursor.lastrowid
                cursor.execute(
                    'INSERT INTO tb_perfiles (id_usuario, id_rol) VALUES (%s, %s)',
                    (id_usuario, rol['id_rol']),
                )

            cursor.execute(
                CONSULTA_USUARIO + ' WHERE u.id_usuario = %s', (id_usuario,)
            )
            usuario = _normalizar_usuario(cursor.fetchone())
            actor = UsuarioAutenticado(id_usuario, correo, google_sub)
            if not actor.coincide_con(usuario) or usuario['id_perfil'] is None:
                raise AccesoDenegado('La cuenta no esta habilitada o no tiene perfil valido.')
            rol = usuario['rol']
            if rol != ROL_AUTORREGISTRO and (
                rol not in ROLES_ADMINISTRATIVOS or usuario['perfil_completo'] is not True
            ):
                raise AccesoDenegado('La cuenta no tiene un perfil autorizado.')

            cursor.execute(
                'UPDATE tb_perfiles SET ultimo_acceso = NOW() WHERE id_perfil = %s',
                (usuario['id_perfil'],),
            )
            cursor.execute(
                CONSULTA_USUARIO + ' WHERE u.id_usuario = %s', (id_usuario,)
            )
            usuario = _normalizar_usuario(cursor.fetchone())
            conexion.commit()
            return usuario

        except mysql.connector.IntegrityError as exc:
            conexion.rollback()
            raise DatosDuplicados('Ya existe un usuario con esos datos de Google.') from exc
        except mysql.connector.DatabaseError as exc:
            conexion.rollback()
            if exc.errno in (errorcode.ER_LOCK_WAIT_TIMEOUT, errorcode.ER_LOCK_DEADLOCK):
                raise AccesoTemporalmenteBloqueado('El registro de acceso está bloqueado en MySQL.') from exc
            raise
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def completar_perfil(
        self, *, actor: UsuarioAutenticado, nombres: str, apellidos: str,
        dni: str, codigo_institucional: str, id_tipo_usuario: int,
        id_escuela: int, telefono: str | None = None,
    ) -> dict:
        """Completa un perfil USUARIO previamente autenticado con Google.

        Comprueba la autorización bajo el bloqueo de la transacción.
        """
        id_usuario = _id_positivo(actor.id_usuario, 'Usuario')
        id_tipo_usuario = _id_positivo(id_tipo_usuario, 'Tipo de usuario')
        id_escuela = _id_positivo(id_escuela, 'Escuela profesional')
        nombres = _texto(nombres, 'Nombres', 80)
        apellidos = _texto(apellidos, 'Apellidos', 100)
        codigo_institucional = _texto(codigo_institucional, 'Codigo institucional', 25)
        dni = str(dni).strip()
        if not re.fullmatch(r'[0-9]{8}', dni):
            raise DatosInvalidos('El DNI debe contener 8 digitos.')
        telefono = _telefono(telefono)

        conexion = obtener_conexion()
        cursor = None
        try:
            conexion.start_transaction()
            cursor = conexion.cursor(dictionary=True)
            self._autorizar_edicion(cursor, actor, completo=False)

            cursor.execute(
                """SELECT id_tipo_usuario FROM tb_tipos_usuarios
                   WHERE id_tipo_usuario = %s AND estado = b'1'
                     AND nombre_tipo IN ('ESTUDIANTE', 'DOCENTE')""",
                (id_tipo_usuario,),
            )
            if cursor.fetchone() is None:
                raise DatosInvalidos('Selecciona Estudiante o Docente.')
            cursor.execute(
                """SELECT id_escuela FROM tb_escuelas
                   WHERE id_escuela = %s AND estado = b'1'""",
                (id_escuela,),
            )
            if cursor.fetchone() is None:
                raise DatosInvalidos('Selecciona una escuela profesional valida.')

            cursor.execute(
                """UPDATE tb_usuarios
                   SET nombres = %s, apellidos = %s, dni = %s,
                       codigo_institucional = %s, id_tipo_usuario = %s,
                       id_escuela = %s, telefono = %s, perfil_completo = b'1'
                   WHERE id_usuario = %s AND perfil_completo = b'0'""",
                (nombres, apellidos, dni, codigo_institucional,
                 id_tipo_usuario, id_escuela, telefono, id_usuario),
            )
            if cursor.rowcount != 1:
                raise DatosInvalidos('No fue posible completar el perfil.')

            cursor.execute(
                CONSULTA_USUARIO + ' WHERE u.id_usuario = %s', (id_usuario,)
            )
            usuario = _normalizar_usuario(cursor.fetchone())
            conexion.commit()
            return usuario

        except mysql.connector.IntegrityError as exc:
            conexion.rollback()
            raise DatosDuplicados('El DNI o codigo institucional ya esta registrado.') from exc
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    @staticmethod
    def _autorizar_edicion(cursor, actor: UsuarioAutenticado, *, completo: bool) -> None:
        cursor.execute(
            CONSULTA_USUARIO + ' WHERE u.id_usuario = %s FOR UPDATE',
            (actor.id_usuario,),
        )
        if not actor.puede_editar_perfil(_normalizar_usuario(cursor.fetchone()), completo=completo):
            raise AccesoDenegado('La identidad o el estado del perfil no permite esta operación.')

    def actualizar_telefono(self, *, actor: UsuarioAutenticado, telefono: str | None) -> dict:
        """Modifica solamente el telefono del usuario con perfil completo."""
        id_usuario = _id_positivo(actor.id_usuario, 'Usuario')
        telefono = _telefono(telefono)
        conexion = obtener_conexion()
        cursor = None
        try:
            conexion.start_transaction()
            cursor = conexion.cursor(dictionary=True)
            self._autorizar_edicion(cursor, actor, completo=True)
            cursor.execute(
                'UPDATE tb_usuarios SET telefono = %s WHERE id_usuario = %s',
                (telefono, id_usuario),
            )
            cursor.execute(
                CONSULTA_USUARIO + ' WHERE u.id_usuario = %s', (id_usuario,)
            )
            usuario = _normalizar_usuario(cursor.fetchone())
            conexion.commit()
            return usuario
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()
