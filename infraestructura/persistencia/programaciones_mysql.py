# infraestructura/persistencia/programaciones_mysql.py
"""Publicación y consulta MySQL de la programación del polideportivo V9."""

from datetime import date, datetime, time, timedelta
import re
from typing import Any

from dominio.reglas.reservas import inicio_semana
from infraestructura.persistencia.conexion_mysql import obtener_conexion, registrar_auditoria, transaccion_mysql
from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


_RESERVAS_DE_PROGRAMACION = """
    FROM tb_reservas r
    JOIN tb_horarios_programados h ON h.id_horario=r.id_horario
    JOIN tb_estados_reserva e ON e.id_estado_reserva=r.id_estado_reserva
    WHERE h.id_programacion=%s AND r.estado=b'1'
"""
_RESERVAS_BLOQUEANTES = " AND e.bloquea_horario=b'1' AND e.estado=b'1'"


class ErrorProgramacion(ValueError):
    """Fecha, hora o filtro de programación inválido."""


def _fecha(valor: date | str) -> date:
    if isinstance(valor, datetime):
        raise ErrorProgramacion('Indica una fecha, no una fecha con hora.')
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str):
        raise ErrorProgramacion('La fecha debe tener formato AAAA-MM-DD.')
    try:
        return date.fromisoformat(valor.strip())
    except ValueError as exc:
        raise ErrorProgramacion('La fecha debe tener formato AAAA-MM-DD.') from exc


def _hora(valor: time | str) -> str:
    """Normaliza a HH:MM; no redondea ni impone bloques de 30/60 min."""
    if isinstance(valor, time):
        if valor.second or valor.microsecond or valor.tzinfo is not None:
            raise ErrorProgramacion('Utiliza horas locales con precisión de minutos.')
        return valor.strftime('%H:%M')
    if not isinstance(valor, str):
        raise ErrorProgramacion('La hora debe tener formato HH:MM.')
    coincidencia = re.fullmatch(r'(\d{1,2}):(\d{2})(?::00)?', valor.strip())
    if not coincidencia:
        raise ErrorProgramacion('La hora debe tener formato HH:MM.')
    horas, minutos = map(int, coincidencia.groups())
    if not (0 <= horas <= 23 and 0 <= minutos <= 59):
        raise ErrorProgramacion('La hora indicada no es válida.')
    return f'{horas:02d}:{minutos:02d}'


def _hora_bd(valor: Any) -> str:
    """mysql-connector suele devolver TIME como timedelta."""
    if isinstance(valor, timedelta):
        total = int(valor.total_seconds())
        if total < 0 or total >= 24 * 3600 or total % 60:
            raise ErrorProgramacion('Existe una hora de BD fuera de precisión HH:MM.')
        return f'{total // 3600:02d}:{(total // 60) % 60:02d}'
    return _hora(valor)


def _activo(valor: Any) -> bool:
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return int.from_bytes(bytes(valor), 'big') == 1
    return valor == 1 or valor is True


def _id_positivo(valor: int, nombre: str) -> int:
    if isinstance(valor, bool):
        raise ErrorProgramacion(f'{nombre} no es válido.')
    try:
        numero = int(valor)
        if str(valor).strip() != str(numero) or numero <= 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ErrorProgramacion(f'{nombre} no es válido.') from exc
    return numero


def _rango(fecha_inicio: date | str, fecha_fin: date | str) -> tuple[date, date]:
    inicio, fin = _fecha(fecha_inicio), _fecha(fecha_fin)
    if fin < inicio:
        raise ErrorProgramacion('La fecha final no puede ser anterior a la inicial.')
    return inicio, fin


class RepositorioProgramacionesMySQL:
    """Repositorio de lectura para la programación del único polideportivo."""

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

    def listar_periodos(self) -> list[dict]:
        """Periodos académicos activos (sin inventar un periodo actual)."""
        filas = self._consultar(
            """SELECT id_periodo, nombre_periodo, fecha_inicio, fecha_fin
               FROM tb_periodos_academicos
               WHERE estado = b'1'
               ORDER BY fecha_inicio DESC, id_periodo DESC"""
        )
        for fila in filas:
            fila['fecha_inicio'] = _fecha(fila['fecha_inicio']).isoformat()
            fila['fecha_fin'] = _fecha(fila['fecha_fin']).isoformat()
        return filas

    def listar_tipos_programacion(self) -> list[dict]:
        """LIBRE, talleres, eventos, mantenimiento, según catálogo real."""
        filas = self._consultar(
            """SELECT id_tipo_programacion, nombre_tipo, permite_reserva
               FROM tb_tipos_programacion
               WHERE estado = b'1'
               ORDER BY id_tipo_programacion"""
        )
        for fila in filas:
            fila['permite_reserva'] = _activo(fila['permite_reserva'])
        return filas

    def listar_programaciones(self, id_periodo: int | None = None) -> list[dict]:
        """Programaciones activas y su clasificación institucional."""
        parametros: tuple = ()
        filtro = ''
        if id_periodo is not None:
            filtro = ' AND p.id_periodo = %s'
            parametros = (_id_positivo(id_periodo, 'Periodo académico'),)
        filas = self._consultar(
            """SELECT p.id_programacion, p.id_periodo, pa.nombre_periodo,
                      p.id_tipo_programacion, t.nombre_tipo, t.permite_reserva,
                      p.id_escuela, e.nombre_escuela, p.id_admin_registra,
                      p.nombre_programacion, p.descripcion, p.responsable,
                      p.fecha_registro
               FROM tb_programaciones p
               JOIN tb_periodos_academicos pa ON pa.id_periodo = p.id_periodo
               JOIN tb_tipos_programacion t
                    ON t.id_tipo_programacion = p.id_tipo_programacion
               LEFT JOIN tb_escuelas e ON e.id_escuela = p.id_escuela
               WHERE p.estado = b'1' AND pa.estado = b'1' AND t.estado = b'1'"""
            + filtro +
            ' ORDER BY p.id_periodo DESC, p.id_programacion',
            parametros,
        )
        for fila in filas:
            fila['permite_reserva'] = _activo(fila['permite_reserva'])
        return filas

    def listar_horarios(
        self, fecha_inicio: date | str | None = None, fecha_fin: date | str | None = None,
        *, tipo: str | None = None, id_programacion: int | None = None, id_horario: int | None = None,
    ) -> list[dict]:
        """Todos los horarios publicados, con precisión de minutos."""
        parametros = ()
        filtro = ''
        if fecha_inicio is not None and fecha_fin is not None:
            parametros = _rango(fecha_inicio, fecha_fin)
            filtro = ' AND h.fecha_uso BETWEEN %s AND %s'
        elif fecha_inicio is not None:
            parametros = (_fecha(fecha_inicio),)
            filtro = ' AND h.fecha_uso >= %s'
        elif fecha_fin is not None:
            parametros = (_fecha(fecha_fin),)
            filtro = ' AND h.fecha_uso <= %s'
        if tipo is not None:
            filtro += ' AND t.nombre_tipo = %s'
            parametros = (*parametros, tipo)
        if id_programacion is not None:
            filtro += ' AND p.id_programacion = %s'
            parametros = (*parametros, _id_positivo(id_programacion, 'Programación'))
        if id_horario is not None:
            filtro += ' AND h.id_horario = %s'
            parametros = (*parametros, _id_positivo(id_horario, 'Horario'))
        filas = self._consultar(
            """SELECT h.id_horario, h.id_programacion, h.fecha_uso,
                      h.hora_inicio, h.hora_fin,
                      p.nombre_programacion, p.id_periodo, pa.nombre_periodo,
                      p.id_tipo_programacion, t.nombre_tipo, t.permite_reserva,
                      p.id_escuela, e.nombre_escuela, p.descripcion, p.responsable
               FROM tb_horarios_programados h
               JOIN tb_programaciones p ON p.id_programacion = h.id_programacion
               JOIN tb_periodos_academicos pa ON pa.id_periodo = p.id_periodo
               JOIN tb_tipos_programacion t
                    ON t.id_tipo_programacion = p.id_tipo_programacion
               LEFT JOIN tb_escuelas e ON e.id_escuela = p.id_escuela
               WHERE h.estado = b'1' AND p.estado = b'1'
                 AND pa.estado = b'1' AND t.estado = b'1'
                 AND h.fecha_uso BETWEEN pa.fecha_inicio AND pa.fecha_fin"""
            + filtro + ' ORDER BY h.fecha_uso, h.hora_inicio, h.hora_fin, h.id_horario',
            parametros,
        )
        for fila in filas:
            fila['fecha_uso'] = _fecha(fila['fecha_uso']).isoformat()
            fila['hora_inicio'] = _hora_bd(fila['hora_inicio'])
            fila['hora_fin'] = _hora_bd(fila['hora_fin'])
            fila['permite_reserva'] = _activo(fila['permite_reserva'])
        return filas

    def intervalos_para_publicacion(self, desde, hasta):
        """Incluye todos los horarios que bloquean una nueva publicación."""
        desde, hasta = _rango(desde, hasta)
        horarios = self._consultar(
            """SELECT h.fecha_uso, h.hora_inicio, h.hora_fin
               FROM tb_horarios_programados h
               JOIN tb_programaciones p ON p.id_programacion=h.id_programacion
               WHERE h.fecha_uso BETWEEN %s AND %s AND h.estado=b'1' AND p.estado=b'1'""",
            (desde, hasta),
        )
        ocupados = [(_fecha(h['fecha_uso']), _hora_bd(h['hora_inicio']), _hora_bd(h['hora_fin'])) for h in horarios]
        ocupados.extend(
            (_fecha(r['fecha_uso']), r['hora_inicio'], r['hora_fin'])
            for r in self._listar_reservas_bloqueantes(desde, hasta)
        )
        return ocupados

    def _listar_reservas_bloqueantes(
        self, fecha_inicio: date, fecha_fin: date,
    ) -> list[dict]:
        """Solo reservas activas cuyo ESTADO bloquea el espacio."""
        filas = self._consultar(
            """SELECT h.fecha_uso, r.hora_inicio, r.hora_fin, er.nombre_estado,
                      r.codigo_reserva, p.id_periodo
               FROM tb_reservas r
               JOIN tb_estados_reserva er
                    ON er.id_estado_reserva = r.id_estado_reserva
               JOIN tb_horarios_programados h ON h.id_horario = r.id_horario
               JOIN tb_programaciones p ON p.id_programacion = h.id_programacion
               WHERE r.estado = b'1' AND er.estado = b'1'
                 AND er.bloquea_horario = b'1'
                 AND h.fecha_uso BETWEEN %s AND %s
               ORDER BY h.fecha_uso, r.hora_inicio""",
            (fecha_inicio, fecha_fin),
        )
        for fila in filas:
            fila['fecha_uso'] = _fecha(fila['fecha_uso']).isoformat()
            fila['hora_inicio'] = _hora_bd(fila['hora_inicio'])
            fila['hora_fin'] = _hora_bd(fila['hora_fin'])
        return filas

    def _agendas_en_rango(self, inicio: date, fin: date) -> dict[str, dict | None]:
        """Una reserva bloqueante siempre prevalece sobre horarios LIBRES."""
        dias = (fin - inicio).days + 1
        agendas: dict[str, dict | None] = {
            (inicio + timedelta(days=i)).isoformat(): None
            for i in range(dias)
        }
        for horario in self.listar_horarios(inicio, fin):
            clave = horario['fecha_uso']
            if agendas[clave] is None:
                agendas[clave] = {'libres': [], 'ocupados': []}
            intervalo = {
                'inicio': horario['hora_inicio'],
                'fin': horario['hora_fin'],
                'id_horario': horario['id_horario'],
                'id_periodo': horario.get('id_periodo'),
                'titulo': horario['nombre_programacion'],
                'tipo': horario['nombre_tipo'],
            }
            destino = 'libres' if horario['permite_reserva'] and horario.get('nombre_tipo') == 'LIBRE' else 'ocupados'
            agendas[clave][destino].append(intervalo)

        for reserva in self._listar_reservas_bloqueantes(inicio, fin):
            clave = reserva['fecha_uso']
            if agendas[clave] is None:
                # Inconsistencia de datos: más seguro mostrar bloqueo que LIBRE.
                agendas[clave] = {'libres': [], 'ocupados': []}
            agendas[clave]['ocupados'].append({
                'inicio': reserva['hora_inicio'],
                'fin': reserva['hora_fin'],
                'titulo': 'Reservado',
                'tipo': 'RESERVA',
                'estado_reserva': reserva['nombre_estado'],
                'codigo_reserva': reserva.get('codigo_reserva'),
                'id_periodo': reserva.get('id_periodo'),
            })
        return agendas

    def obtener_agendas(self, fecha_inicio: date | str, fecha_fin: date | str) -> dict:
        inicio, fin = _rango(fecha_inicio, fecha_fin)
        if (fin - inicio).days > 366:
            raise ErrorProgramacion('Consulta como máximo 367 días de agenda por solicitud.')
        return self._agendas_en_rango(inicio, fin)

    def obtener_agenda(self, fecha_uso: date | str) -> dict | None:
        """Agenda para calendario.py; None significa sin horarios publicados.

        {'libres': [{'inicio': '09:30', 'fin': '13:00', ...}],
         'ocupados': [{'inicio': '09:00', 'fin': '09:30', ...}]}
        """
        dia = _fecha(fecha_uso)
        return self.obtener_agendas(dia, dia)[dia.isoformat()]

    def obtener_agenda_semanal(self, fecha_referencia: date | str) -> dict:
        """Mapea lunes a domingo: {'AAAA-MM-DD': agenda_o_None}."""
        dia = _fecha(fecha_referencia)
        lunes = inicio_semana(dia)
        return self.obtener_agendas(lunes, lunes + timedelta(days=6))

    def buscar_horario_reservable(
        self, fecha_uso: date | str, hora_inicio: time | str, hora_fin: time | str,
    ) -> dict | None:
        """Consulta preliminar de intervalo libre contenido en UN horario.

        No autoriza ni registra una reserva: la transacción de inserción debe
        repetir las comprobaciones y serializar reservas del mismo día para
        evitar duplicidades por concurrencia.
        """
        dia, inicio, fin = _fecha(fecha_uso), _hora(hora_inicio), _hora(hora_fin)
        if inicio >= fin:
            raise ErrorProgramacion('La hora final debe ser posterior a la inicial.')
        filas = self._consultar(
            """SELECT h.id_horario, h.id_programacion, h.fecha_uso,
                      h.hora_inicio, h.hora_fin
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
                     SELECT 1 FROM tb_horarios_programados bloqueo
                     JOIN tb_programaciones bp
                          ON bp.id_programacion = bloqueo.id_programacion
                     JOIN tb_tipos_programacion bt
                          ON bt.id_tipo_programacion = bp.id_tipo_programacion
                     JOIN tb_periodos_academicos bpa ON bpa.id_periodo = bp.id_periodo
                     WHERE bloqueo.fecha_uso = h.fecha_uso AND bpa.estado = b'1'
                       AND bloqueo.fecha_uso BETWEEN bpa.fecha_inicio AND bpa.fecha_fin
                       AND bloqueo.estado = b'1' AND bp.estado = b'1'
                       AND bt.estado = b'1' AND (bt.permite_reserva = b'0' OR bt.nombre_tipo <> 'LIBRE')
                       AND bloqueo.hora_inicio < %s AND bloqueo.hora_fin > %s
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM tb_reservas r
                     JOIN tb_horarios_programados rh
                          ON rh.id_horario = r.id_horario
                     JOIN tb_estados_reserva er
                          ON er.id_estado_reserva = r.id_estado_reserva
                     WHERE rh.fecha_uso = h.fecha_uso
                       AND r.estado = b'1'
                       AND er.estado = b'1' AND er.bloquea_horario = b'1'
                       AND r.hora_inicio < %s AND r.hora_fin > %s
                 )
               ORDER BY h.hora_inicio, h.id_horario LIMIT 1""",
            (dia, inicio, fin, fin, inicio, fin, inicio),
        )
        if not filas:
            return None
        fila = filas[0]
        fila['fecha_uso'] = _fecha(fila['fecha_uso']).isoformat()
        fila['hora_inicio'] = _hora_bd(fila['hora_inicio'])
        fila['hora_fin'] = _hora_bd(fila['hora_fin'])
        return fila

    def reservas_que_impiden_desactivar(self, id_programacion):
        filas = self._consultar(
            'SELECT r.codigo_reserva,h.fecha_uso,r.hora_inicio,r.hora_fin,e.nombre_estado'
            + _RESERVAS_DE_PROGRAMACION + _RESERVAS_BLOQUEANTES + ' ORDER BY h.fecha_uso,r.hora_inicio',
            (_id_positivo(id_programacion, 'Programación'),),
        )
        for fila in filas:
            fila['hora_inicio'] = _hora_bd(fila['hora_inicio'])
            fila['hora_fin'] = _hora_bd(fila['hora_fin'])
        return filas

    @staticmethod
    def _bloquear_programacion(cursor, id_programacion, *, solo_vigentes):
        cursor.execute(
            'SELECT id_programacion FROM tb_programaciones WHERE id_programacion=%s AND estado=b\'1\' FOR UPDATE',
            (id_programacion,),
        )
        if cursor.fetchone() is None:
            raise ErrorProgramacion('La programación ya no está activa.')
        filtro = _RESERVAS_BLOQUEANTES if solo_vigentes else ''
        cursor.execute(
            'SELECT r.id_reserva' + _RESERVAS_DE_PROGRAMACION + filtro + ' LIMIT 1 FOR UPDATE',
            (id_programacion,),
        )
        if cursor.fetchone():
            mensaje = ('Hay reservas que todavía ocupan jornadas de esta programación.' if solo_vigentes
                       else 'La programación tiene reservas asociadas.')
            raise ErrorProgramacion(mensaje)

    def guardar_programacion(self, *, actor, tipo, id_periodo, nombre, descripcion, responsable,
                             escuela, horarios, id_programacion=None, solo_futuros=False):
        id_periodo = _id_positivo(id_periodo, 'Período académico')
        if id_programacion is not None:
            id_programacion = _id_positivo(id_programacion, 'Programación')
        nombre, descripcion, responsable = (str(x or '').strip() for x in (nombre, descripcion, responsable))
        if not nombre or len(nombre) > 120 or len(descripcion) > 200 or len(responsable) > 100:
            raise ErrorProgramacion('Revisa el nombre, la descripción y el responsable.')
        franjas = sorted((_fecha(f), _hora(a), _hora(b)) for f, a, b in horarios)
        if not franjas:
            raise ErrorProgramacion('Agrega al menos un horario.')
        with transaccion_mysql() as cursor:
            RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            cursor.execute(
                """SELECT fecha_inicio, fecha_fin FROM tb_periodos_academicos
                   WHERE id_periodo=%s AND estado=b'1' FOR SHARE""", (id_periodo,),
            )
            periodo = cursor.fetchone()
            if not periodo:
                raise ErrorProgramacion('El período académico no está activo.')
            cursor.execute(
                """SELECT id_tipo_programacion, permite_reserva FROM tb_tipos_programacion
                   WHERE nombre_tipo=%s AND estado=b'1'""", (tipo,),
            )
            catalogo = cursor.fetchone()
            if not catalogo:
                raise ErrorProgramacion('El tipo de programación no está activo.')
            if solo_futuros and not _activo(catalogo['permite_reserva']):
                raise ErrorProgramacion('El tipo de programación no está habilitado para reservas.')
            if escuela is not None:
                escuela = _id_positivo(escuela, 'Escuela')
                cursor.execute('SELECT id_escuela FROM tb_escuelas WHERE id_escuela=%s AND estado=b\'1\'', (escuela,))
                if cursor.fetchone() is None:
                    raise ErrorProgramacion('La escuela no está activa.')
            if id_programacion:
                self._bloquear_programacion(cursor, id_programacion, solo_vigentes=False)
            anterior = None
            for dia, inicio, fin in franjas:
                if not periodo['fecha_inicio'] <= dia <= periodo['fecha_fin'] or inicio >= fin:
                    raise ErrorProgramacion('Cada horario debe estar dentro del período y tener un rango válido.')
                if anterior and anterior[0] == dia and inicio < anterior[2]:
                    raise ErrorProgramacion('Hay horarios superpuestos en esta programación.')
                anterior = (dia, inicio, fin)
                cursor.execute(
                    """SELECT id_horario FROM tb_horarios_programados WHERE fecha_uso=%s
                       ORDER BY id_horario FOR UPDATE""", (dia,),
                )
                cursor.fetchall()
                cursor.execute(
                    """SELECT h.id_horario FROM tb_horarios_programados h
                       JOIN tb_programaciones p ON p.id_programacion=h.id_programacion
                       WHERE h.fecha_uso=%s AND h.estado=b'1' AND p.estado=b'1'
                         AND h.id_programacion<>%s AND h.hora_inicio<%s AND h.hora_fin>%s
                       LIMIT 1 FOR UPDATE""", (dia, id_programacion or 0, fin, inicio),
                )
                if cursor.fetchone():
                    raise ErrorProgramacion('El horario se superpone con una programación publicada.')
                cursor.execute(
                    """SELECT r.id_reserva FROM tb_reservas r
                       JOIN tb_horarios_programados h ON h.id_horario=r.id_horario
                       JOIN tb_estados_reserva e ON e.id_estado_reserva=r.id_estado_reserva
                       WHERE h.fecha_uso=%s AND r.estado=b'1' AND e.estado=b'1' AND e.bloquea_horario=b'1'
                         AND r.hora_inicio<%s AND r.hora_fin>%s
                       LIMIT 1 FOR UPDATE""", (dia, fin, inicio),
                )
                if cursor.fetchone():
                    raise ErrorProgramacion('El horario se superpone con una reserva vigente.')
            if solo_futuros:
                cursor.execute('SELECT NOW() AS ahora')
                ahora = cursor.fetchone()['ahora']
                dia, inicio, _ = franjas[0]
                if datetime.combine(dia, time.fromisoformat(inicio)) <= ahora:
                    raise ErrorProgramacion('Una franja ya comenzó. Calcula la vista previa nuevamente.')

            editando = bool(id_programacion)
            datos = (id_periodo, catalogo['id_tipo_programacion'], escuela, nombre,
                     descripcion or None, responsable or None)
            if editando:
                cursor.execute(
                    """UPDATE tb_programaciones SET id_periodo=%s,id_tipo_programacion=%s,id_escuela=%s,
                         nombre_programacion=%s,descripcion=%s,responsable=%s WHERE id_programacion=%s""",
                    (*datos, id_programacion),
                )
                cursor.execute('UPDATE tb_horarios_programados SET estado=b\'0\' WHERE id_programacion=%s',
                               (id_programacion,))
            else:
                cursor.execute(
                    """INSERT INTO tb_programaciones (id_periodo,id_tipo_programacion,id_escuela,
                         nombre_programacion,descripcion,responsable,id_admin_registra)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""", (*datos, actor),
                )
                id_programacion = cursor.lastrowid
            cursor.executemany(
                """INSERT INTO tb_horarios_programados (id_programacion,fecha_uso,hora_inicio,hora_fin)
                   VALUES (%s,%s,%s,%s)""",
                [(id_programacion, *franja) for franja in franjas],
            )
            registrar_auditoria(cursor, actor, 'PROGRAMAR ACTIVIDAD', 'tb_programaciones', id_programacion,
                                {'operacion': 'modificar' if editando else 'crear', 'nombre': nombre,
                                 'horarios': len(franjas), 'inicio': franjas[0][0].isoformat(),
                                 'fin': franjas[-1][0].isoformat()})
            return id_programacion

    def desactivar_programacion(self, *, actor, id_programacion):
        id_programacion = _id_positivo(id_programacion, 'Programación')
        with transaccion_mysql() as cursor:
            RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            cursor.execute('SELECT id_horario FROM tb_horarios_programados WHERE id_programacion=%s FOR UPDATE',
                           (id_programacion,))
            cursor.fetchall()
            self._bloquear_programacion(cursor, id_programacion, solo_vigentes=True)
            cursor.execute('UPDATE tb_programaciones SET estado=b\'0\' WHERE id_programacion=%s', (id_programacion,))
            registrar_auditoria(cursor, actor, 'PROGRAMAR ACTIVIDAD', 'tb_programaciones', id_programacion,
                                {'operacion': 'desactivar'})

    def crear_periodo(self, *, actor, nombre, inicio, fin):
        nombre = str(nombre or '').strip()
        inicio, fin = _fecha(inicio), _fecha(fin)
        if not 1 <= len(nombre) <= 20 or inicio > fin:
            raise ErrorProgramacion('Ingresa un nombre válido y las fechas del período.')
        with transaccion_mysql() as cursor:
            RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            cursor.execute(
                'INSERT INTO tb_periodos_academicos (nombre_periodo,fecha_inicio,fecha_fin) VALUES (%s,%s,%s)',
                (nombre, inicio, fin),
            )
            registrar_auditoria(cursor, actor, 'CREAR', 'tb_periodos_academicos', cursor.lastrowid,
                                {'nombre': nombre})
