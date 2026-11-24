# infraestructura/persistencia/reservas_mysql.py
"""Persistencia de reservas del unico polideportivo - PoliReserva UNAB V9.

No contiene NiceGUI ni datos simulados. Las llamadas de usuario deben recibir
el id_usuario_actor DESDE la sesion autenticada del servidor, nunca del cliente.
La conexion MySQL debe usar la zona horaria local del polideportivo (Peru).
"""

from datetime import date, datetime, time, timedelta
import json
import re
import secrets
from typing import Any

import mysql.connector

from dominio.reglas.reservas import (
    APERTURA, CIERRE, ESTADOS_CONSUMEN_CUPO, LIMITE_SEMANAL_MINUTOS, MAXIMO_RESERVA_MINUTOS,
    TOLERANCIA_ASISTENCIA, TOLERANCIA_MINUTOS, aviso_cupo_semanal, inicio_semana,
)
from infraestructura.persistencia.conexion_mysql import obtener_conexion


_MARCAS_ESTADOS_CUPO = ','.join(['%s'] * len(ESTADOS_CONSUMEN_CUPO))
_CONSUMO_SEMANAL = f"""
    SELECT COALESCE(SUM(TIME_TO_SEC(r.hora_fin) - TIME_TO_SEC(r.hora_inicio)), 0) AS segundos
    FROM tb_reservas r
    JOIN tb_estados_reserva e ON e.id_estado_reserva=r.id_estado_reserva
    JOIN tb_horarios_programados h ON h.id_horario=r.id_horario
    WHERE r.id_usuario=%s AND r.estado=b'1' AND r.id_reserva<>%s
      AND h.fecha_uso >= %s AND h.fecha_uso < DATE_ADD(%s, INTERVAL 7 DAY)
      AND e.nombre_estado IN ({_MARCAS_ESTADOS_CUPO})
"""


class ErrorReserva(ValueError):
    """Operacion de reserva rechazada por datos o reglas de negocio."""


class HorarioNoDisponible(ErrorReserva):
    """No existe un bloque LIBRE que admita el intervalo solicitado."""


class ReservaNoAutorizada(ErrorReserva):
    """El actor no dispone de permiso sobre esta reserva."""


def _id(valor: int, campo: str) -> int:
    try:
        if isinstance(valor, bool) or str(valor).strip() != str(int(valor)):
            raise ValueError
        numero = int(valor)
        if numero <= 0:
            raise ValueError
        return numero
    except (TypeError, ValueError, OverflowError) as exc:
        raise ErrorReserva(f'{campo} no es valido.') from exc


def _fecha(valor: date | str) -> date:
    if isinstance(valor, datetime):
        raise ErrorReserva('Indica solo la fecha, en formato AAAA-MM-DD.')
    if isinstance(valor, date):
        return valor
    try:
        if not isinstance(valor, str):
            raise ValueError
        return date.fromisoformat(valor.strip())
    except ValueError as exc:
        raise ErrorReserva('La fecha debe tener formato AAAA-MM-DD.') from exc


def _hora(valor: time | str) -> str:
    if isinstance(valor, time):
        if valor.second or valor.microsecond or valor.tzinfo is not None:
            raise ErrorReserva('Utiliza horas locales con precision de minutos.')
        return valor.strftime('%H:%M')
    if not isinstance(valor, str):
        raise ErrorReserva('La hora debe tener formato HH:MM.')
    coincidencia = re.fullmatch(r'(\d{1,2}):(\d{2})(?::00)?', valor.strip())
    if not coincidencia:
        raise ErrorReserva('La hora debe tener formato HH:MM.')
    horas, minutos = map(int, coincidencia.groups())
    if horas > 23 or minutos > 59:
        raise ErrorReserva('La hora indicada no es valida.')
    return f'{horas:02d}:{minutos:02d}'


def _hora_bd(valor: Any) -> str:
    """mysql-connector devuelve TIME normalmente como timedelta."""
    if isinstance(valor, timedelta):
        total = int(valor.total_seconds())
        if not 0 <= total < 86400 or total % 60:
            raise ErrorReserva('Hora de la base de datos no valida.')
        return f'{total // 3600:02d}:{(total // 60) % 60:02d}'
    return _hora(valor)


def _activo(valor: Any) -> bool:
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return int.from_bytes(bytes(valor), 'big') == 1
    return valor is True or valor == 1


def _codigo(valor: str) -> str:
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= 20:
        raise ErrorReserva('Codigo de reserva no valido.')
    return valor.strip()


def _normalizar(fila: dict | None) -> dict | None:
    if fila is None:
        return None
    if 'fecha_uso' in fila:
        fila['fecha_uso'] = _fecha(fila['fecha_uso']).isoformat()
    for campo in ('hora_inicio', 'hora_fin'):
        if campo in fila:
            fila[campo] = _hora_bd(fila[campo])
    for campo in ('activo', 'bloquea_horario'):
        if campo in fila:
            fila[campo] = _activo(fila[campo])
    return fila


CONSULTA_RESERVA = """
    SELECT r.id_reserva, r.codigo_reserva, r.id_usuario,
           r.id_admin_gestor, r.id_horario, r.id_estado_reserva,
           er.nombre_estado AS estado_reserva, er.bloquea_horario,
           h.fecha_uso, r.hora_inicio, r.hora_fin,
           TIME_TO_SEC(r.hora_fin) - TIME_TO_SEC(r.hora_inicio) AS duracion_segundos,
           r.fecha_solicitud, r.fecha_actualizacion_estado,
           r.estado AS activo, p.nombre_programacion, pa.nombre_periodo AS periodo,
           u.nombres, u.apellidos, u.dni, u.correo_institucional,
           u.codigo_institucional, tu.nombre_tipo AS tipo_usuario,
           es.nombre_escuela AS escuela, COALESCE(CONCAT_WS(' ', g.nombres, g.apellidos), '') AS admin_gestor
    FROM tb_reservas r
    JOIN tb_estados_reserva er ON er.id_estado_reserva = r.id_estado_reserva
    JOIN tb_horarios_programados h ON h.id_horario = r.id_horario
    JOIN tb_programaciones p ON p.id_programacion = h.id_programacion
    JOIN tb_periodos_academicos pa ON pa.id_periodo = p.id_periodo
    JOIN tb_usuarios u ON u.id_usuario = r.id_usuario
    LEFT JOIN tb_tipos_usuarios tu ON tu.id_tipo_usuario = u.id_tipo_usuario
    LEFT JOIN tb_escuelas es ON es.id_escuela = u.id_escuela
    LEFT JOIN tb_usuarios g ON g.id_usuario = r.id_admin_gestor
"""


class RepositorioReservasMySQL:
    """Lectura y operaciones transaccionales para reservas V9."""

    @staticmethod
    def _consultar(sql: str, parametros: tuple = ()) -> list[dict]:
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

    @staticmethod
    def _obtener_reserva(cursor, id_reserva: int) -> dict:
        cursor.execute(CONSULTA_RESERVA + ' WHERE r.id_reserva = %s', (id_reserva,))
        fila = cursor.fetchone()
        if fila is None:
            raise ErrorReserva('No se encontro la reserva.')
        return _normalizar(fila)

    @staticmethod
    def _validar_actor(cursor, id_usuario: int, *, administrador: bool = False) -> dict:
        """Comprueba cuenta, perfil y rol habilitados en MySQL."""
        cursor.execute(
            """SELECT u.id_usuario, u.perfil_completo, u.estado AS usuario_activo,
                      p.estado AS perfil_activo, ro.nombre_rol,
                      ro.estado AS rol_activo, tu.nombre_tipo, tu.estado AS tipo_activo
               FROM tb_usuarios u
               JOIN tb_perfiles p ON p.id_usuario = u.id_usuario
               JOIN tb_roles ro ON ro.id_rol = p.id_rol
               LEFT JOIN tb_tipos_usuarios tu ON tu.id_tipo_usuario = u.id_tipo_usuario
               WHERE u.id_usuario = %s FOR UPDATE""",
            (id_usuario,),
        )
        fila = cursor.fetchone()
        if not fila or not all((
            _activo(fila['usuario_activo']),
            _activo(fila['perfil_activo']),
            _activo(fila['rol_activo']),
            _activo(fila['perfil_completo']),
        )):
            raise ReservaNoAutorizada('Se necesita una cuenta activa con perfil completo.')
        if administrador and fila['nombre_rol'] not in ('ASISTENTE', 'ADMINISTRADOR'):
            raise ReservaNoAutorizada('El usuario no tiene permisos administrativos.')
        return fila

    @staticmethod
    def _estado_id(cursor, nombre: str, *, bloquea: bool | None = None) -> int:
        sql = """SELECT id_estado_reserva, bloquea_horario
                 FROM tb_estados_reserva
                 WHERE nombre_estado = %s AND estado = b'1'"""
        cursor.execute(sql, (nombre,))
        fila = cursor.fetchone()
        if not fila or (bloquea is not None and _activo(fila['bloquea_horario']) != bloquea):
            raise ErrorReserva(f'Configura correctamente el estado {nombre} en MySQL.')
        return fila['id_estado_reserva']

    @staticmethod
    def _auditar(cursor, *, acciones: tuple[str, ...], actor: int | None,
                 id_reserva: int, detalle: dict) -> None:
        """Registra la accion en la MISMA transaccion que la reserva."""
        id_accion = None
        for nombre in acciones:
            cursor.execute(
                """SELECT id_tipo_accion FROM tb_tipos_accion
                   WHERE nombre_accion = %s AND estado = b'1'""",
                (nombre,),
            )
            resultado = cursor.fetchone()
            if resultado:
                id_accion = resultado['id_tipo_accion']
                break
        if id_accion is None:
            raise ErrorReserva(f'Falta configurar el tipo de accion {acciones[0]}.')
        cursor.execute(
            """INSERT INTO tb_auditoria
               (id_usuario_actor, id_tipo_accion, tabla_afectada,
                id_registro_afectado, detalle_cambio)
               VALUES (%s, %s, 'tb_reservas', %s, %s)""",
            (actor, id_accion, id_reserva, json.dumps(detalle)),
        )

    def listar_estados(self) -> list[dict]:
        filas = self._consultar(
            """SELECT id_estado_reserva, nombre_estado, bloquea_horario
               FROM tb_estados_reserva WHERE estado = b'1'
               ORDER BY id_estado_reserva"""
        )
        for fila in filas:
            fila['bloquea_horario'] = _activo(fila['bloquea_horario'])
        return filas

    def listar_por_usuario(self, id_usuario: int, *, solo_activas: bool = False) -> list[dict]:
        usuario = _id(id_usuario, 'Usuario')
        filtro = ' AND er.estado = b\'1\' AND er.bloquea_horario = b\'1\'' if solo_activas else ''
        filas = self._consultar(
            CONSULTA_RESERVA +
            " WHERE r.id_usuario = %s AND r.estado = b'1'" + filtro +
            ' ORDER BY h.fecha_uso DESC, r.hora_inicio DESC, r.id_reserva DESC',
            (usuario,),
        )
        return [_normalizar(fila) for fila in filas]

    @staticmethod
    def _filtros_administracion(desde, hasta, estado):
        condiciones = ["r.estado = b'1'"]
        parametros = []
        if desde is not None:
            condiciones.append('h.fecha_uso >= %s')
            parametros.append(_fecha(desde))
        if hasta is not None:
            condiciones.append('h.fecha_uso <= %s')
            parametros.append(_fecha(hasta))
        if estado is not None:
            condiciones.append('er.nombre_estado = %s')
            parametros.append(estado)
        return ' WHERE ' + ' AND '.join(condiciones), tuple(parametros)

    def listar_administracion(self, desde=None, hasta=None, *, estado=None) -> list[dict]:
        filtro, parametros = self._filtros_administracion(desde, hasta, estado)
        return [_normalizar(fila) for fila in self._consultar(
            CONSULTA_RESERVA + filtro + ' ORDER BY h.fecha_uso DESC, r.hora_inicio DESC', parametros,
        )]

    def listar_resumen(self, desde=None, hasta=None, *, estado=None) -> list[dict]:
        """Proyección sin datos personales para estadísticas y recuentos operativos."""
        filtro, parametros = self._filtros_administracion(desde, hasta, estado)
        filas = self._consultar(
            """SELECT r.id_usuario, h.fecha_uso, r.hora_inicio, r.hora_fin, er.nombre_estado AS estado_reserva,
                      er.estado AND er.bloquea_horario AS bloquea_horario
               FROM tb_reservas r
               JOIN tb_estados_reserva er ON er.id_estado_reserva=r.id_estado_reserva
               JOIN tb_horarios_programados h ON h.id_horario=r.id_horario"""
            + filtro, parametros,
        )
        return [_normalizar(fila) for fila in filas]

    def listar_transiciones_vencidas(self) -> list[dict]:
        return self._consultar(
            """SELECT r.codigo_reserva, e.nombre_estado
               FROM tb_reservas r
               JOIN tb_estados_reserva e ON e.id_estado_reserva = r.id_estado_reserva
               JOIN tb_horarios_programados h ON h.id_horario = r.id_horario
               WHERE r.estado = b'1' AND e.estado = b'1' AND (
                   (e.nombre_estado = 'RESERVADA'
                    AND TIMESTAMPADD(MINUTE, %s, TIMESTAMP(h.fecha_uso, r.hora_inicio)) <= NOW())
                   OR (e.nombre_estado = 'CONFIRMADA' AND TIMESTAMP(h.fecha_uso, r.hora_fin) <= NOW())
               )
               ORDER BY h.fecha_uso, r.hora_inicio, r.id_reserva""", (TOLERANCIA_MINUTOS,),
        )

    def obtener_por_codigo(self, codigo_reserva: str, *, id_usuario: int) -> dict | None:
        """Consulta privada: el codigo por si solo NO autoriza ver la reserva."""
        filas = self._consultar(
            CONSULTA_RESERVA +
            " WHERE r.codigo_reserva = %s AND r.id_usuario = %s AND r.estado = b'1'",
            (_codigo(codigo_reserva), _id(id_usuario, 'Usuario')),
        )
        return _normalizar(filas[0]) if filas else None

    def obtener_para_gestion(self, codigo_reserva: str) -> dict | None:
        """Consulta para pantallas que ya verificaron el rol administrativo."""
        filas = self._consultar(
            CONSULTA_RESERVA + " WHERE r.codigo_reserva = %s AND r.estado = b'1'",
            (_codigo(codigo_reserva),),
        )
        return _normalizar(filas[0]) if filas else None

    def consumo_semanal(self, id_usuario: int, fecha, *, excluir_reserva: int = 0) -> int:
        lunes = inicio_semana(_fecha(fecha))
        fila, = self._consultar(
            _CONSUMO_SEMANAL, (_id(id_usuario, 'Usuario'), excluir_reserva, lunes, lunes, *ESTADOS_CONSUMEN_CUPO),
        )
        return int(fila['segundos'])

    def registrar_reserva(
        self, *, id_usuario: int, fecha_uso: date | str,
        hora_inicio: time | str, hora_fin: time | str,
        id_admin_gestor: int | None = None,
        codigo_a_reprogramar: str | None = None,
    ) -> dict:
        """Reserva un subintervalo libre, en transaccion con bloqueo por dia.

        Reglas: máximo de 2 horas por turno y 3 horas semanales,
        perfil habilitado, fecha futura y sin cruzarse con reservas o bloqueos.
        El usuario debe provenir de la sesion autenticada en el caso de uso.
        """
        usuario = _id(id_usuario, 'Usuario')
        gestor = _id(id_admin_gestor, 'Gestor') if id_admin_gestor is not None else None
        if codigo_a_reprogramar is not None and gestor is None:
            raise ReservaNoAutorizada('Reprogramar una reserva requiere permisos administrativos.')
        dia, inicio, fin = _fecha(fecha_uso), _hora(hora_inicio), _hora(hora_fin)
        if dia.weekday() >= 5 and gestor is None:
            raise ReservaNoAutorizada('Las reservas de fin de semana requieren gestión administrativa.')
        minutos_inicio = int(inicio[:2]) * 60 + int(inicio[3:])
        minutos_fin = int(fin[:2]) * 60 + int(fin[3:])
        if (not APERTURA <= minutos_inicio < minutos_fin <= CIERRE
                or minutos_fin - minutos_inicio > MAXIMO_RESERVA_MINUTOS):
            raise ErrorReserva('Reserva entre las 07:00 y las 22:00, con una duración máxima de 2 horas.')

        conexion = obtener_conexion()
        cursor = None
        try:
            conexion.start_transaction()
            cursor = conexion.cursor(dictionary=True)
            titular = self._validar_actor(cursor, usuario)
            if (titular['nombre_rol'] != 'USUARIO' or
                titular['nombre_tipo'] not in ('ESTUDIANTE', 'DOCENTE') or
                not _activo(titular['tipo_activo'])):
                raise ReservaNoAutorizada('Solo estudiantes y docentes habilitados pueden reservar.')
            if gestor is not None:
                self._validar_actor(cursor, gestor, administrador=True)
            id_anterior = 0
            if codigo_a_reprogramar is not None:
                cursor.execute(
                    """SELECT r.id_reserva, TIMESTAMP(h.fecha_uso, r.hora_inicio) > NOW() AS futura
                       FROM tb_reservas r
                       JOIN tb_estados_reserva e ON e.id_estado_reserva = r.id_estado_reserva
                       JOIN tb_horarios_programados h ON h.id_horario = r.id_horario
                       WHERE r.codigo_reserva=%s AND r.id_usuario=%s
                         AND r.estado=b'1' AND e.nombre_estado='RESERVADA' FOR UPDATE""",
                    (_codigo(codigo_a_reprogramar), usuario),
                )
                anterior = cursor.fetchone()
                if not anterior or not anterior['futura']:
                    raise ErrorReserva('Solo se pueden modificar reservas que aún no comenzaron.')
                id_anterior = anterior['id_reserva']

            # Todas las reservas de una fecha bloquean las mismas filas.
            # Asi dos peticiones simultaneas no pueden asignar el mismo intervalo.
            cursor.execute(
                """SELECT id_horario FROM tb_horarios_programados
                   WHERE fecha_uso = %s ORDER BY id_horario FOR UPDATE""",
                (dia,),
            )
            if not cursor.fetchall():
                raise HorarioNoDisponible('No hay horarios programados para la fecha.')

            cursor.execute('SELECT NOW() AS ahora')
            ahora = cursor.fetchone()['ahora']
            if datetime.combine(dia, time.fromisoformat(inicio)) <= ahora:
                raise ErrorReserva('Solo se permiten reservas para horarios futuros.')

            # No depender de IDs fijos: los estados validos los define MySQL.
            id_estado = self._estado_id(cursor, 'RESERVADA', bloquea=True)
            # El bloqueo del titular precede a la primera lectura consistente.
            lunes = inicio_semana(dia)
            cursor.execute(_CONSUMO_SEMANAL, (usuario, id_anterior, lunes, lunes, *ESTADOS_CONSUMEN_CUPO))
            segundos = int(cursor.fetchone()['segundos'])
            if segundos + (minutos_fin - minutos_inicio) * 60 > LIMITE_SEMANAL_MINUTOS * 60:
                raise ErrorReserva(aviso_cupo_semanal(segundos))

            # El horario LIBRE debe contener completamente el subintervalo.
            # Se comprueban bloqueos institucionales y reservas en todo el dia,
            # incluso cuando pertenecen a otro id_horario.
            cursor.execute(
                """SELECT h.id_horario
                   FROM tb_horarios_programados h
                   JOIN tb_programaciones p ON p.id_programacion = h.id_programacion
                   JOIN tb_periodos_academicos pa ON pa.id_periodo = p.id_periodo
                   JOIN tb_tipos_programacion t
                        ON t.id_tipo_programacion = p.id_tipo_programacion
                   WHERE h.fecha_uso = %s
                     AND h.estado = b'1' AND p.estado = b'1'
                     AND pa.estado = b'1' AND t.estado = b'1'
                     AND t.permite_reserva = b'1' AND t.nombre_tipo = 'LIBRE'
                     AND h.fecha_uso BETWEEN pa.fecha_inicio AND pa.fecha_fin
                     AND h.hora_inicio <= %s AND h.hora_fin >= %s
                     AND NOT EXISTS (
                         SELECT 1 FROM tb_horarios_programados bh
                         JOIN tb_programaciones bp
                              ON bp.id_programacion = bh.id_programacion
                         JOIN tb_tipos_programacion bt
                              ON bt.id_tipo_programacion = bp.id_tipo_programacion
                         JOIN tb_periodos_academicos bpa ON bpa.id_periodo = bp.id_periodo
                         WHERE bh.fecha_uso = h.fecha_uso AND bpa.estado = b'1'
                           AND bh.fecha_uso BETWEEN bpa.fecha_inicio AND bpa.fecha_fin
                           AND bh.estado = b'1' AND bp.estado = b'1'
                           AND bt.estado = b'1' AND (bt.permite_reserva = b'0' OR bt.nombre_tipo <> 'LIBRE')
                           AND bh.hora_inicio < %s AND bh.hora_fin > %s
                     )
                     AND NOT EXISTS (
                         SELECT 1 FROM tb_reservas r
                         JOIN tb_horarios_programados rh
                              ON rh.id_horario = r.id_horario
                         JOIN tb_estados_reserva er
                              ON er.id_estado_reserva = r.id_estado_reserva
                         WHERE rh.fecha_uso = h.fecha_uso
                           AND r.estado = b'1' AND er.estado = b'1'
                           AND er.bloquea_horario = b'1'
                           AND r.hora_inicio < %s AND r.hora_fin > %s AND r.id_reserva <> %s
                     )
                   ORDER BY h.hora_inicio, h.id_horario LIMIT 1""",
                (dia, inicio, fin, fin, inicio, fin, inicio, id_anterior),
            )
            horario = cursor.fetchone()
            if horario is None:
                raise HorarioNoDisponible('La franja ya esta ocupada o no es reservable.')

            if id_anterior:
                from infraestructura.persistencia.implementos_mysql import ErrorImplemento, RepositorioImplementosMySQL

                try:
                    RepositorioImplementosMySQL.revalidar_prestamos_pendientes(
                        cursor, id_anterior, datetime.combine(dia, time.fromisoformat(inicio)),
                        datetime.combine(dia, time.fromisoformat(fin)),
                    )
                except ErrorImplemento as exc:
                    raise ErrorReserva(str(exc)) from exc
                cursor.execute(
                    """UPDATE tb_reservas SET id_horario=%s, hora_inicio=%s, hora_fin=%s,
                              id_admin_gestor=%s WHERE id_reserva=%s""",
                    (horario['id_horario'], inicio, fin, gestor, id_anterior),
                )
                id_reserva = id_anterior
            else:
                codigo = 'RES-' + secrets.token_hex(6).upper()
                cursor.execute(
                    """INSERT INTO tb_reservas
                       (id_usuario, id_admin_gestor, id_horario, id_estado_reserva,
                        codigo_reserva, hora_inicio, hora_fin)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (usuario, gestor, horario['id_horario'], id_estado, codigo, inicio, fin),
                )
                id_reserva = cursor.lastrowid
            self._auditar(
                cursor, acciones=('MODIFICAR', 'PROGRAMAR ACTIVIDAD') if id_anterior else ('CREAR',), actor=gestor or usuario,
                id_reserva=id_reserva,
                detalle={'operacion': 'reprogramar' if id_anterior else 'crear',
                         'estado': 'RESERVADA', 'fecha_uso': dia.isoformat(),
                         'hora_inicio': inicio, 'hora_fin': fin},
            )
            resultado = self._obtener_reserva(cursor, id_reserva)
            conexion.commit()
            return resultado
        except mysql.connector.IntegrityError as exc:
            conexion.rollback()
            raise ErrorReserva('No se pudo registrar la reserva por un dato duplicado o invalido.') from exc
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def _cambiar_estado(self, codigo_reserva: str, destino: str,
                       *, id_usuario_actor: int | None = None) -> dict:
        """Transiciones verificadas. Sin actor solo para tareas del sistema."""
        codigo = _codigo(codigo_reserva)
        actor = _id(id_usuario_actor, 'Usuario actor') if id_usuario_actor is not None else None
        transiciones = {
            'CONFIRMADA': ('RESERVADA',),
            'CANCELADA': ('RESERVADA',),
            'INASISTENCIA': ('RESERVADA',),
            'FINALIZADA': ('CONFIRMADA',),
        }
        if destino not in transiciones:
            raise ErrorReserva('Transicion de estado no permitida.')
        if destino in ('CONFIRMADA', 'CANCELADA') and actor is None:
            raise ReservaNoAutorizada('La operacion requiere una sesion autenticada.')

        acciones = {
            'CONFIRMADA': ('CONFIRMAR ASISTENCIA', 'CONFIRMAR'),
            'CANCELADA': ('CANCELAR',),
            'INASISTENCIA': ('INASISTENCIA AUTOMATICA', 'INASISTENCIA'),
            'FINALIZADA': ('FINALIZAR RESERVA', 'CAMBIAR ESTADO'),
        }
        conexion = obtener_conexion()
        cursor = None
        try:
            conexion.start_transaction()
            cursor = conexion.cursor(dictionary=True)
            cursor.execute('SELECT id_usuario FROM tb_reservas WHERE codigo_reserva=%s', (codigo,))
            titular = cursor.fetchone()
            if titular is None:
                raise ErrorReserva('No existe una reserva activa con ese codigo.')
            cursor.execute('SELECT id_usuario FROM tb_usuarios WHERE id_usuario=%s FOR UPDATE',
                           (titular['id_usuario'],))
            cursor.fetchone()
            persona = self._validar_actor(cursor, actor) if actor is not None else None
            cursor.execute(
                """SELECT r.id_reserva, r.id_usuario, r.id_admin_gestor,
                          r.estado AS activo, e.nombre_estado,
                          h.fecha_uso, r.hora_inicio, r.hora_fin
                   FROM tb_reservas r
                   JOIN tb_estados_reserva e
                        ON e.id_estado_reserva = r.id_estado_reserva
                   JOIN tb_horarios_programados h ON h.id_horario = r.id_horario
                   WHERE r.codigo_reserva = %s FOR UPDATE""",
                (codigo,),
            )
            reserva = cursor.fetchone()
            if not reserva or not _activo(reserva['activo']):
                raise ErrorReserva('No existe una reserva activa con ese codigo.')
            if reserva['nombre_estado'] not in transiciones[destino]:
                raise ErrorReserva('La reserva no admite ese cambio de estado.')

            gestor = None
            if actor is not None:
                if actor != reserva['id_usuario']:
                    if persona['nombre_rol'] not in ('ASISTENTE', 'ADMINISTRADOR'):
                        raise ReservaNoAutorizada('No puede gestionar reservas de otra persona.')
                    gestor = actor
                elif destino in ('INASISTENCIA', 'FINALIZADA'):
                    raise ReservaNoAutorizada('Esta operacion corresponde al sistema o al personal.')
            elif destino not in ('INASISTENCIA', 'FINALIZADA'):
                raise ReservaNoAutorizada('La operacion requiere un actor autenticado.')

            cursor.execute('SELECT NOW() AS ahora')
            ahora = cursor.fetchone()['ahora']
            inicio = datetime.combine(
                reserva['fecha_uso'], time.fromisoformat(_hora_bd(reserva['hora_inicio']))
            )
            fin = datetime.combine(
                reserva['fecha_uso'], time.fromisoformat(_hora_bd(reserva['hora_fin']))
            )
            if destino == 'CANCELADA' and ahora >= inicio:
                raise ErrorReserva('Solo puedes cancelar antes del inicio de tu turno.')
            if destino == 'CONFIRMADA' and not inicio <= ahora < inicio + TOLERANCIA_ASISTENCIA:
                raise ErrorReserva('La asistencia se confirma dentro de los 15 minutos iniciales.')
            if destino == 'INASISTENCIA' and ahora < inicio + TOLERANCIA_ASISTENCIA:
                raise ErrorReserva('Aun no ha vencido la tolerancia de 15 minutos.')
            if destino == 'FINALIZADA' and ahora < fin:
                raise ErrorReserva('El turno aun no ha terminado.')

            id_estado = self._estado_id(
                cursor, destino, bloquea=destino == 'CONFIRMADA'
            )
            cursor.execute(
                """UPDATE tb_reservas
                   SET id_estado_reserva = %s,
                       id_admin_gestor = COALESCE(%s, id_admin_gestor),
                       fecha_actualizacion_estado = NOW()
                   WHERE id_reserva = %s AND estado = b'1'""",
                (id_estado, gestor, reserva['id_reserva']),
            )
            if cursor.rowcount != 1:
                raise ErrorReserva('No fue posible actualizar la reserva.')
            self._auditar(
                cursor, acciones=acciones[destino], actor=actor,
                id_reserva=reserva['id_reserva'],
                detalle={'estado_anterior': reserva['nombre_estado'],
                         'estado_nuevo': destino},
            )
            if destino in ('CANCELADA', 'INASISTENCIA'):
                from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL

                try:
                    RepositorioImplementosMySQL.cancelar_prestamos_pendientes(
                        cursor, reserva['id_reserva'], codigo, destino, actor,
                    )
                except ValueError as exc:
                    raise ErrorReserva('No se pudo registrar la cancelación de los préstamos asociados.') from exc
            resultado = self._obtener_reserva(cursor, reserva['id_reserva'])
            conexion.commit()
            return resultado
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def cancelar_reserva(self, *, codigo_reserva: str, id_usuario_actor: int) -> dict:
        return self._cambiar_estado(
            codigo_reserva, 'CANCELADA', id_usuario_actor=id_usuario_actor
        )

    def confirmar_asistencia(self, *, codigo_reserva: str, id_usuario_actor: int) -> dict:
        return self._cambiar_estado(
            codigo_reserva, 'CONFIRMADA', id_usuario_actor=id_usuario_actor
        )

    def marcar_inasistencia(self, *, codigo_reserva: str) -> dict:
        """Solo invocar desde un proceso interno confiable del servidor."""
        return self._cambiar_estado(codigo_reserva, 'INASISTENCIA')

    def finalizar_reserva(self, *, codigo_reserva: str) -> dict:
        """Solo invocar desde un proceso interno confiable del servidor."""
        return self._cambiar_estado(codigo_reserva, 'FINALIZADA')
