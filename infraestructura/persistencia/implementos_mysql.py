"""Persistencia patrimonial y de préstamos del polideportivo."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from dominio.reglas.implementos import (
    MAX_OBSERVACION_PRESTAMO, agrupar_unidades, fechas_sugeridas_prestamo, intervalo_reserva,
    nombre_tipo_implemento, reserva_admite_prestamo, validar_motivo_sin_reserva,
)
from dominio.reglas.reservas import ZONA_PERU
from infraestructura.persistencia.conexion_mysql import registrar_auditoria, transaccion_mysql
from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL, _activo, _id


class ErrorImplemento(ValueError):
    """La operación de inventario o préstamo no es válida."""


_TABLAS_PRESTAMOS = """
    FROM tb_operaciones_implementos p
    JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
    JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
"""
_ES_PRESTAMO = "t.nombre_tipo='PRESTAMO' AND p.estado=b'1'"

PRESTAMOS = f"""
    SELECT p.*, e.nombre_estado AS estado_prestamo, e.nombre_estado,
           CONCAT_WS(' ', u.nombres, u.apellidos) AS solicitante,
           u.codigo_institucional, es.nombre_escuela AS escuela,
           r.codigo_reserva, DATE_FORMAT(h.fecha_uso,'%Y-%m-%d') AS fecha_reserva,
           TIME_FORMAT(r.hora_inicio,'%H:%i') AS hora_inicio_reserva,
           TIME_FORMAT(r.hora_fin,'%H:%i') AS hora_fin_reserva,
           er.nombre_estado AS estado_reserva,
           IF(p.id_reserva IS NULL,'Sin reserva','Con reserva') AS modalidad,
           (SELECT COUNT(DISTINCT d.id_implemento) FROM tb_detalle_operacion d
            JOIN tb_tipos_movimiento m ON m.id_tipo_movimiento=d.id_tipo_movimiento
            WHERE d.id_operacion=p.id_operacion AND d.estado=b'1'
              AND m.nombre_tipo='SALIDA' AND d.fecha_movimiento IS NOT NULL) AS unidades_entregadas,
           (SELECT COUNT(DISTINCT d.id_implemento) FROM tb_detalle_operacion d
            WHERE d.id_operacion=p.id_operacion AND d.estado=b'1') AS total_implementos
    {_TABLAS_PRESTAMOS}
    JOIN tb_usuarios u ON u.id_usuario=p.id_usuario
    LEFT JOIN tb_escuelas es ON es.id_escuela=u.id_escuela
    LEFT JOIN tb_reservas r ON r.id_reserva=p.id_reserva
    LEFT JOIN tb_horarios_programados h ON h.id_horario=r.id_horario
    LEFT JOIN tb_estados_reserva er ON er.id_estado_reserva=r.id_estado_reserva
    WHERE {_ES_PRESTAMO}
"""

DISPONIBILIDAD = """
    SELECT i.id_implemento, i.nombre_implemento, i.id_categoria, i.codigo_patrimonial,
           i.descripcion, i.apto_prestamo, c.nombre_categoria, c.nombre_categoria AS categoria,
           CASE WHEN i.estado=b'0' THEN 'Baja'
           WHEN EXISTS (
               SELECT 1 FROM tb_detalle_operacion d
               JOIN tb_operaciones_implementos p ON p.id_operacion=d.id_operacion
               JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
               JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
               WHERE d.id_implemento=i.id_implemento AND d.estado=b'1'
                 AND p.estado=b'1' AND t.nombre_tipo='PRESTAMO' AND e.nombre_estado='ENTREGADO'
           ) THEN 'Prestado'
           WHEN i.apto_prestamo=b'1' AND c.estado=b'1' THEN 'Disponible'
           ELSE 'No disponible' END AS disponibilidad
    FROM tb_implementos i JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
"""


def _filtro_solicitudes(desde, hasta):
    condiciones, parametros = [], []
    if desde is not None:
        condiciones.append(' AND p.fecha_solicitud >= %s')
        parametros.append(desde)
    if hasta is not None:
        condiciones.append(' AND p.fecha_solicitud < DATE_ADD(%s,INTERVAL 1 DAY)')
        parametros.append(hasta)
    return ''.join(condiciones), tuple(parametros)


def _catalogo(cursor, tabla, clave, columna, nombre, *, tiene_estado=True):
    filtro = " AND estado=b'1'" if tiene_estado else ''
    cursor.execute(f'SELECT {clave} FROM {tabla} WHERE {columna}=%s' + filtro, (nombre,))
    fila = cursor.fetchone()
    if not fila:
        raise ErrorImplemento(f'Falta configurar {nombre} en el catálogo.')
    return fila[clave]


def _estado(cursor, nombre):
    return _catalogo(cursor, 'tb_estados_prestamo', 'id_estado_prestamo', 'nombre_estado', nombre)


def _tipo(cursor, nombre):
    return _catalogo(cursor, 'tb_tipos_operacion', 'id_tipo_operacion', 'nombre_tipo', nombre, tiene_estado=False)


def _movimiento(cursor, nombre):
    return _catalogo(cursor, 'tb_tipos_movimiento', 'id_tipo_movimiento', 'nombre_tipo', nombre)


def _texto(valor, limite, etiqueta, *, obligatorio=False):
    valor = str(valor or '').strip()
    if len(valor) > limite or (obligatorio and not valor):
        raise ErrorImplemento(f'Revisa {etiqueta}. Máximo {limite} caracteres.')
    return valor or None


def _fechas(inicio, fin):
    try:
        fechas = [datetime.fromisoformat(str(x)) for x in (inicio, fin)]
    except (ValueError, TypeError) as exc:
        raise ErrorImplemento('Ingresa fecha y hora previstas para recojo y devolución.') from exc
    if any(x.tzinfo is not None for x in fechas) or fechas[0] >= fechas[1]:
        raise ErrorImplemento('La devolución debe ser posterior al recojo. Usa horas de Perú.')
    return fechas


_CONFLICTO_INTERVALO = """(e.nombre_estado='ENTREGADO' OR (
    e.nombre_estado='PENDIENTE' AND p.fecha_inicio_prevista<%s AND p.fecha_devolucion_prevista>%s))"""


class RepositorioImplementosMySQL:
    """Gestiona unidades patrimoniales y conserva cada movimiento en V9."""

    _consultar = staticmethod(RepositorioReservasMySQL._consultar)

    def listar_categorias(self):
        return self._consultar("""SELECT id_categoria,nombre_categoria
                                  FROM tb_categorias_implementos WHERE estado=b'1' ORDER BY nombre_categoria""")

    def crear_categoria(self, *, actor, nombre):
        nombre = _texto(nombre, 50, 'el nombre de la categoría', obligatorio=True)
        with transaccion_mysql() as cursor:
            RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            cursor.execute('INSERT INTO tb_categorias_implementos (nombre_categoria) VALUES (%s)', (nombre,))
            registrar_auditoria(cursor, actor, 'CREAR', 'tb_categorias_implementos',
                                cursor.lastrowid, {'nombre': nombre})

    def listar_implementos(self, *, incluir_bajas=False):
        filtro = '' if incluir_bajas else " WHERE i.estado=b'1'"
        filas = self._consultar(DISPONIBILIDAD + filtro + ' ORDER BY c.nombre_categoria, i.nombre_implemento, i.id_implemento')
        for fila in filas:
            fila['apto_prestamo'] = _activo(fila['apto_prestamo'])
            fila['aptitud'] = 'Apto' if fila['apto_prestamo'] else 'No apto'
        return filas

    def resumen_inventario(self):
        """Cuenta unidades activas según la misma disponibilidad que el inventario."""
        filas = self._consultar(
            'SELECT disponibilidad, COUNT(*) AS unidades FROM ('
            + DISPONIBILIDAD + " WHERE i.estado=b'1') AS inventario GROUP BY disponibilidad"
        )
        conteo = {f['disponibilidad']: f['unidades'] for f in filas}
        return {
            'total': sum(conteo.values()), 'disponibles': conteo.get('Disponible', 0),
            'prestadas': conteo.get('Prestado', 0), 'no_habilitadas': conteo.get('No disponible', 0),
        }

    def listar_disponibles(self, inicio, fin, *, excluir_operacion=None):
        inicio, fin = _fechas(inicio, fin)
        excluir = _id(excluir_operacion, 'Préstamo') if excluir_operacion is not None else 0
        return self._consultar(
            """SELECT i.id_implemento,i.codigo_patrimonial,i.nombre_implemento,c.nombre_categoria
               FROM tb_implementos i JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
               WHERE i.estado=b'1' AND i.apto_prestamo=b'1' AND c.estado=b'1'
               AND NOT EXISTS (
                   SELECT 1 FROM tb_detalle_operacion d
                   JOIN tb_operaciones_implementos p ON p.id_operacion=d.id_operacion
                   JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
                   WHERE d.id_implemento=i.id_implemento AND d.estado=b'1' AND p.estado=b'1'
                     AND p.id_operacion<>%s AND """ + _CONFLICTO_INTERVALO +
            ') ORDER BY c.nombre_categoria,i.nombre_implemento,i.id_implemento', (excluir, fin, inicio),
        )

    @staticmethod
    def _normalizar_prestamo(fila):
        fila['implementos'] = fila['total_implementos']
        fila['vinculo'] = fila['modalidad']
        if fila['codigo_reserva']:
            fila['vinculo'] += f" · {fila['codigo_reserva']}"
        for campo in ('fecha_solicitud', 'fecha_inicio_prevista', 'fecha_devolucion_prevista', 'fecha_entrega'):
            if fila[campo] is not None:
                fila[campo] = fila[campo].isoformat(sep=' ', timespec='seconds')
        fila['estado'] = _activo(fila['estado'])
        return fila

    def reservas_elegibles(self, id_usuario):
        ahora = datetime.now(ZONA_PERU).replace(tzinfo=None)
        reservas = RepositorioReservasMySQL().listar_por_usuario(id_usuario, solo_activas=True)
        return [r for r in reservas if reserva_admite_prestamo(r, ahora)
                and (horas := fechas_sugeridas_prestamo(r, ahora))[0] < horas[1]]

    def resumen_solicitudes(self, desde, hasta):
        filtro, parametros = _filtro_solicitudes(desde, hasta)
        resumen, = self._consultar(
            f"""SELECT COUNT(*) AS total, COUNT(p.id_reserva) AS con_reserva,
                       COUNT(DISTINCT p.id_reserva) AS reservas_con_prestamo,
                       COUNT(CASE WHEN e.nombre_estado='PENDIENTE' THEN 1 END) AS pendientes
                {_TABLAS_PRESTAMOS}
                WHERE {_ES_PRESTAMO}""" + filtro,
            parametros,
        )
        return dict(resumen, sin_reserva=resumen['total'] - resumen['con_reserva'])

    def resumen_prestamos_activos(self, ahora):
        """Operaciones únicas y unidades físicas pendientes de devolución."""
        resumen, = self._consultar(
            f"""SELECT
                    COUNT(DISTINCT CASE WHEN e.nombre_estado='PENDIENTE' THEN p.id_operacion END) AS pendientes,
                    COUNT(DISTINCT CASE WHEN e.nombre_estado='ENTREGADO' THEN p.id_operacion END) AS entregados,
                    COUNT(DISTINCT CASE WHEN e.nombre_estado='ENTREGADO' AND p.fecha_devolucion_prevista < %s
                                        THEN p.id_operacion END) AS vencidos,
                    COUNT(DISTINCT CASE WHEN m.nombre_tipo='SALIDA' THEN d.id_implemento END) AS por_devolver
                {_TABLAS_PRESTAMOS}
                LEFT JOIN tb_detalle_operacion d
                     ON d.id_operacion=p.id_operacion AND e.nombre_estado='ENTREGADO'
                         AND d.estado=b'1' AND d.fecha_movimiento IS NOT NULL
                LEFT JOIN tb_tipos_movimiento m ON m.id_tipo_movimiento=d.id_tipo_movimiento
                WHERE {_ES_PRESTAMO} AND e.nombre_estado IN ('PENDIENTE','ENTREGADO')""",
            (ahora.replace(tzinfo=None),),
        )
        return resumen

    def listar_prestamos(self, id_usuario=None, *, desde=None, hasta=None, id_reserva=None, estado=None):
        condiciones = []
        parametros = []
        if id_usuario is not None:
            condiciones.append('p.id_usuario=%s')
            parametros.append(_id(id_usuario, 'Usuario'))
        if id_reserva is not None:
            condiciones.append('p.id_reserva=%s')
            parametros.append(_id(id_reserva, 'Reserva'))
        if estado is not None:
            condiciones.append('e.nombre_estado=%s')
            parametros.append(estado)
        filtro = ' AND ' + ' AND '.join(condiciones) if condiciones else ''
        fechas, limites = _filtro_solicitudes(desde, hasta)
        return [self._normalizar_prestamo(fila) for fila in self._consultar(
            PRESTAMOS + filtro + fechas + ' ORDER BY p.fecha_solicitud DESC, p.id_operacion DESC',
            (*parametros, *limites),
        )]

    def obtener_prestamo(self, operacion, *, id_usuario=None):
        filtro = ' AND p.id_usuario=%s' if id_usuario is not None else ''
        parametros = (_id(operacion, 'Préstamo'),)
        if id_usuario is not None:
            parametros += (_id(id_usuario, 'Usuario'),)
        filas = self._consultar(PRESTAMOS + ' AND p.id_operacion=%s' + filtro, parametros)
        return self._normalizar_prestamo(filas[0]) if filas else None

    def detalle_prestamo(self, id_operacion, *, id_usuario=None):
        filtro = ' AND p.id_usuario=%s' if id_usuario is not None else ''
        parametros = (_id(id_operacion, 'Préstamo'),)
        if id_usuario is not None:
            parametros += (_id(id_usuario, 'Usuario'),)
        return self._consultar(
            """SELECT id_implemento, codigo_patrimonial, nombre_implemento, nombre_categoria,
                      movimiento, condicion_fisica, situacion, fecha_movimiento, entrega, devolucion
               FROM (
                   SELECT i.id_implemento, i.codigo_patrimonial, i.nombre_implemento, c.nombre_categoria,
                          CASE WHEN d.fecha_movimiento IS NOT NULL THEN m.nombre_tipo END AS movimiento,
                          d.condicion_fisica, e.nombre_estado AS situacion,
                          DATE_FORMAT(d.fecha_movimiento,'%Y-%m-%d %H:%i') AS fecha_movimiento,
                          MAX(CASE WHEN m.nombre_tipo='SALIDA'
                              THEN DATE_FORMAT(d.fecha_movimiento,'%Y-%m-%d %H:%i') END)
                              OVER (PARTITION BY i.id_implemento) AS entrega,
                          MAX(CASE WHEN m.nombre_tipo='ENTRADA'
                              THEN DATE_FORMAT(d.fecha_movimiento,'%Y-%m-%d %H:%i') END)
                              OVER (PARTITION BY i.id_implemento) AS devolucion,
                          ROW_NUMBER() OVER (PARTITION BY i.id_implemento ORDER BY d.id_detalle_operacion DESC) AS orden
                   FROM tb_detalle_operacion d
                   JOIN tb_operaciones_implementos p ON p.id_operacion=d.id_operacion
                   JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
                   JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
                   JOIN tb_implementos i ON i.id_implemento=d.id_implemento
                   JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
                   JOIN tb_tipos_movimiento m ON m.id_tipo_movimiento=d.id_tipo_movimiento
                   WHERE p.id_operacion=%s AND p.estado=b'1' AND d.estado=b'1' AND t.nombre_tipo='PRESTAMO'"""
            + filtro + ') filas WHERE orden=1 ORDER BY nombre_implemento, id_implemento', parametros,
        )

    def unidades_prestamos(self, desde=None, hasta=None, *, solo_asociados=False):
        fechas, parametros = _filtro_solicitudes(desde, hasta)
        vinculados = ' AND p.id_reserva IS NOT NULL' if solo_asociados else ''
        return self._consultar(
            """SELECT r.codigo_reserva, p.id_operacion, i.id_implemento,
                      i.nombre_implemento, c.nombre_categoria,
                      MAX(d.fecha_movimiento IS NOT NULL) AS entregada
               FROM tb_operaciones_implementos p
               JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
               LEFT JOIN tb_reservas r ON r.id_reserva=p.id_reserva
               JOIN tb_detalle_operacion d ON d.id_operacion=p.id_operacion
               JOIN tb_tipos_movimiento m ON m.id_tipo_movimiento=d.id_tipo_movimiento
               JOIN tb_implementos i ON i.id_implemento=d.id_implemento
               JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
               WHERE p.estado=b'1' AND d.estado=b'1' AND t.nombre_tipo='PRESTAMO' AND m.nombre_tipo='SALIDA'"""
            + fechas + vinculados
            + ' GROUP BY r.codigo_reserva,p.id_operacion,i.id_implemento,i.nombre_implemento,c.nombre_categoria',
            parametros,
        )

    def listar_movimientos(self, desde=None, hasta=None, *, unidad=None):
        condiciones = []
        parametros = []
        if unidad is not None:
            condiciones.append('d.id_implemento=%s')
            parametros.append(_id(unidad, 'Implemento'))
        if desde is not None:
            condiciones.append('d.fecha_movimiento >= %s')
            parametros.append(desde)
        if hasta is not None:
            condiciones.append('d.fecha_movimiento < DATE_ADD(%s,INTERVAL 1 DAY)')
            parametros.append(hasta)
        filtro = ' AND ' + ' AND '.join(condiciones) if condiciones else ''
        return self._consultar(
            """SELECT d.id_detalle_operacion AS id_movimiento, d.fecha_movimiento, d.id_operacion, d.id_implemento, d.condicion_fisica,
                      t.nombre_tipo AS operacion, m.nombre_tipo AS movimiento,
                      i.nombre_implemento, i.codigo_patrimonial, c.nombre_categoria
               FROM tb_detalle_operacion d
               JOIN tb_operaciones_implementos p ON p.id_operacion=d.id_operacion
               JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
               JOIN tb_tipos_movimiento m ON m.id_tipo_movimiento=d.id_tipo_movimiento
               JOIN tb_implementos i ON i.id_implemento=d.id_implemento
               JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
               WHERE d.estado=b'1' AND p.estado=b'1' AND d.fecha_movimiento IS NOT NULL"""
            + filtro + ' ORDER BY d.fecha_movimiento DESC, d.id_detalle_operacion DESC', tuple(parametros),
        )

    @staticmethod
    def _bloquear_unidades(cursor, ids):
        cursor.execute(
            f"""SELECT i.id_implemento, i.estado, i.apto_prestamo, c.estado AS categoria_activa,
                       i.nombre_implemento, i.codigo_patrimonial, i.id_categoria, c.nombre_categoria
                FROM tb_implementos i JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
                WHERE i.id_implemento IN ({','.join(['%s'] * len(ids))})
                ORDER BY i.id_implemento FOR UPDATE""", tuple(ids),
        )
        filas = cursor.fetchall()
        if len(filas) != len(ids) or any(not _activo(f['estado']) for f in filas):
            raise ErrorImplemento('Uno de los implementos ya no se encuentra activo.')
        return filas

    @staticmethod
    def _tiene_prestamo(cursor, unidad, *, inicio=None, fin=None, excluir=0):
        if inicio is not None:
            filtro, params = _CONFLICTO_INTERVALO, (fin, inicio)
        else:
            filtro, params = "e.nombre_estado IN ('PENDIENTE','ENTREGADO')", ()
        cursor.execute(
            """SELECT p.id_operacion FROM tb_detalle_operacion d
               JOIN tb_operaciones_implementos p ON p.id_operacion=d.id_operacion
               JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
               WHERE d.id_implemento=%s AND d.estado=b'1' AND p.estado=b'1'
                 AND p.id_operacion<>%s AND """ + filtro + ' LIMIT 1 FOR UPDATE',
            (unidad, excluir, *params),
        )
        return bool(cursor.fetchone())

    @staticmethod
    def _detalle_movimiento(cursor, operacion, unidad, movimiento, actor, observacion=None, condicion=None):
        cursor.execute(
            """INSERT INTO tb_detalle_operacion
               (id_operacion,id_implemento,id_tipo_movimiento,id_admin_movimiento,fecha_movimiento,observacion,condicion_fisica)
               VALUES (%s,%s,%s,%s,IF(%s IS NULL,NULL,NOW()),%s,%s)""",
            (operacion, unidad, movimiento, actor, actor, observacion, condicion),
        )

    def guardar_implemento(self, *, actor, codigo, nombre, categoria, descripcion, apto, id_implemento=None):
        codigo = _texto(codigo, 30, 'el código patrimonial', obligatorio=True)
        nombre = _texto(nombre, 100, 'el nombre', obligatorio=True)
        descripcion = _texto(descripcion, 200, 'la descripción')
        categoria = _id(categoria, 'Categoría')
        with transaccion_mysql() as cursor:
            RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            cursor.execute("SELECT id_categoria FROM tb_categorias_implementos WHERE id_categoria=%s AND estado=b'1'",
                           (categoria,))
            if cursor.fetchone() is None:
                raise ErrorImplemento('La categoría no está activa.')
            if id_implemento is not None:
                unidad = _id(id_implemento, 'Implemento')
                actual, = self._bloquear_unidades(cursor, [unidad])
                cambia_tipo = (actual['id_categoria'] != categoria or
                               nombre_tipo_implemento(actual['nombre_implemento']) != nombre_tipo_implemento(nombre))
                if (not apto or cambia_tipo) and self._tiene_prestamo(cursor, unidad):
                    raise ErrorImplemento('La categoría, el tipo y la aptitud deben conservarse mientras haya un préstamo pendiente o entregado.')
                cursor.execute(
                    """UPDATE tb_implementos SET id_categoria=%s,nombre_implemento=%s,descripcion=%s,
                       apto_prestamo=%s WHERE id_implemento=%s""", (categoria, nombre, descripcion, int(apto), unidad),
                )
                accion = 'modificar'
            else:
                cursor.execute("""INSERT INTO tb_implementos
                               (id_categoria,codigo_patrimonial,nombre_implemento,descripcion,apto_prestamo)
                               VALUES (%s,%s,%s,%s,%s)""", (categoria, codigo, nombre, descripcion, int(apto)))
                unidad = cursor.lastrowid
                self._registrar_movimiento_inventario(cursor, actor, unidad, 'ALTA', 'ENTRADA', None)
                accion = 'alta'
            registrar_auditoria(cursor, actor, 'REGISTRAR IMPLEMENTO', 'tb_implementos', unidad,
                                {'operacion': accion})

    def _registrar_movimiento_inventario(self, cursor, actor, unidad, tipo, movimiento, motivo):
        cursor.execute('INSERT INTO tb_operaciones_implementos (id_tipo_operacion,observacion) VALUES (%s,%s)',
                       (_tipo(cursor, tipo), motivo))
        operacion = cursor.lastrowid
        self._detalle_movimiento(cursor, operacion, unidad, _movimiento(cursor, movimiento), actor, motivo)

    def dar_de_baja(self, *, actor, unidad, motivo):
        unidad = _id(unidad, 'Implemento')
        motivo = _texto(motivo, 200, 'el motivo de baja')
        with transaccion_mysql() as cursor:
            RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            self._bloquear_unidades(cursor, [unidad])
            if self._tiene_prestamo(cursor, unidad):
                raise ErrorImplemento('El implemento tiene un préstamo pendiente o entregado.')
            self._registrar_movimiento_inventario(cursor, actor, unidad, 'BAJA', 'SALIDA', motivo)
            cursor.execute("UPDATE tb_implementos SET estado=b'0',apto_prestamo=b'0' WHERE id_implemento=%s", (unidad,))
            registrar_auditoria(cursor, actor, 'DAR DE BAJA', 'tb_implementos', unidad, {'motivo': motivo})

    @staticmethod
    def _reserva_para_prestamo(cursor, id_reserva, titular, inicio, fin, ahora):
        cursor.execute(
            """SELECT r.codigo_reserva, e.nombre_estado AS estado_reserva, h.fecha_uso,
                      CAST(r.hora_inicio AS CHAR) AS hora_inicio,
                      CAST(r.hora_fin AS CHAR) AS hora_fin
               FROM tb_reservas r JOIN tb_horarios_programados h ON h.id_horario=r.id_horario
               JOIN tb_estados_reserva e ON e.id_estado_reserva=r.id_estado_reserva
               WHERE r.id_reserva=%s AND r.id_usuario=%s AND r.estado=b'1' FOR UPDATE""",
            (id_reserva, titular),
        )
        reserva = cursor.fetchone()
        if not reserva or not reserva_admite_prestamo(reserva, ahora):
            raise ErrorImplemento('Selecciona una reserva vigente del usuario solicitante.')
        desde, hasta = intervalo_reserva(reserva)
        if not desde <= inicio < fin <= hasta:
            raise ErrorImplemento('El recojo y la devolución deben estar dentro del turno reservado.')
        return reserva['codigo_reserva']

    @staticmethod
    def _pendientes_asociados(cursor, id_reserva, *, bloquear):
        cursor.execute(
            """SELECT p.id_operacion, p.fecha_inicio_prevista, p.fecha_devolucion_prevista
               FROM tb_operaciones_implementos p
               JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
               JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
               WHERE p.id_reserva=%s AND p.estado=b'1'
                 AND t.nombre_tipo='PRESTAMO' AND e.nombre_estado='PENDIENTE'
               ORDER BY p.id_operacion""" + (' FOR UPDATE' if bloquear else ''),
            (id_reserva,),
        )
        return cursor.fetchall()

    @classmethod
    def cancelar_prestamos_pendientes(cls, cursor, id_reserva, codigo, motivo, actor):
        for fila in cls._pendientes_asociados(cursor, id_reserva, bloquear=True):
            operacion = fila['id_operacion']
            cursor.execute(
                'UPDATE tb_operaciones_implementos SET id_estado_prestamo=%s WHERE id_operacion=%s',
                (_estado(cursor, 'CANCELADO'), operacion),
            )
            registrar_auditoria(cursor, actor, 'CANCELAR', 'tb_operaciones_implementos', operacion,
                                {'estado_anterior': 'PENDIENTE', 'estado_nuevo': 'CANCELADO',
                                 'codigo_reserva': codigo, 'motivo_reserva': motivo})

    @classmethod
    def revalidar_prestamos_pendientes(cls, cursor, id_reserva, inicio, fin):
        pendientes = cls._pendientes_asociados(cursor, id_reserva, bloquear=False)
        if not pendientes:
            return
        salida = _movimiento(cursor, 'SALIDA')
        ids = {d['id_implemento'] for p in pendientes
               for d in cls._salidas_prestamo(cursor, p['id_operacion'], salida)}
        patrimonio = {f['id_implemento']: f for f in cls._bloquear_unidades(cursor, sorted(ids))} if ids else {}
        for fila in cls._pendientes_asociados(cursor, id_reserva, bloquear=True):
            operacion = fila['id_operacion']
            desde, hasta = fila['fecha_inicio_prevista'], fila['fecha_devolucion_prevista']
            if not desde or not hasta or not inicio <= desde < hasta <= fin:
                raise ErrorImplemento(f'El préstamo pendiente N.º {operacion} queda fuera del nuevo turno. '
                                      'Cancela la solicitud antes de mover la reserva.')
            salidas = cls._salidas_prestamo(cursor, operacion, salida, bloquear=True)
            for detalle in salidas:
                unidad = detalle['id_implemento']
                bien = patrimonio.get(unidad)
                if (not bien or not _activo(bien['apto_prestamo']) or not _activo(bien['categoria_activa'])
                        or cls._tiene_prestamo(cursor, unidad, inicio=desde, fin=hasta, excluir=operacion)):
                    raise ErrorImplemento(f'Revisa la disponibilidad del préstamo pendiente N.º {operacion}.')
            if not salidas:
                raise ErrorImplemento(f'El préstamo pendiente N.º {operacion} no tiene unidades asignadas.')

    def solicitar(self, *, actor, inicio, fin, unidades=(), grupos=None, id_usuario=None, observacion=None,
                  id_reserva=None):
        inicio, fin = _fechas(inicio, fin)
        if id_reserva is None:
            try:
                observacion = validar_motivo_sin_reserva(observacion)
            except ValueError as exc:
                raise ErrorImplemento(str(exc)) from exc
        else:
            observacion = _texto(observacion, MAX_OBSERVACION_PRESTAMO, 'la observación')
        ids = sorted({_id(i, 'Implemento') for i in unidades})
        if not ids and not grupos:
            raise ErrorImplemento('Selecciona al menos un implemento.')
        titular = actor if id_usuario is None else _id(id_usuario, 'Usuario')
        with transaccion_mysql() as cursor:
            persona = RepositorioReservasMySQL._validar_actor(cursor, titular)
            if id_usuario is not None:
                RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=True)
            if (persona['nombre_rol'] != 'USUARIO' or persona['nombre_tipo'] not in ('ESTUDIANTE', 'DOCENTE')
                    or not _activo(persona['tipo_activo'])):
                raise ErrorImplemento('Solo estudiantes y docentes habilitados pueden solicitar préstamos.')
            cursor.execute('SELECT NOW() AS ahora')
            ahora = cursor.fetchone()['ahora']
            if inicio <= ahora:
                raise ErrorImplemento('El recojo debe programarse para el futuro.')
            codigo_reserva = None
            if id_reserva is not None:
                id_reserva = _id(id_reserva, 'Reserva')
                codigo_reserva = self._reserva_para_prestamo(cursor, id_reserva, titular, inicio, fin, ahora)
            if grupos:
                cantidades = Counter()
                for (categoria, nombre), cantidad in grupos.items():
                    cantidades[categoria, nombre_tipo_implemento(nombre)] += _id(cantidad, 'Cantidad')
                categorias = sorted({categoria for categoria, _ in cantidades})
                cursor.execute(
                    "SELECT i.id_implemento,i.nombre_implemento,c.nombre_categoria "
                    "FROM tb_implementos i JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria "
                    "WHERE i.estado=b'1' AND i.apto_prestamo=b'1' AND c.estado=b'1' "
                    f"AND c.nombre_categoria IN ({','.join(['%s'] * len(categorias))}) "
                    "ORDER BY i.id_implemento FOR UPDATE", tuple(categorias),
                )
                for fila in cursor.fetchall():
                    clave = fila['nombre_categoria'], nombre_tipo_implemento(fila['nombre_implemento'])
                    unidad = fila['id_implemento']
                    if (cantidades[clave] and unidad not in ids
                            and not self._tiene_prestamo(cursor, unidad, inicio=inicio, fin=fin)):
                        ids.append(unidad)
                        cantidades[clave] -= 1
                faltante = next((nombre for (_, nombre), cantidad in cantidades.items() if cantidad), None)
                if faltante is not None:
                    raise ErrorImplemento(f'No hay suficientes unidades disponibles de {faltante}.')
            for fila in self._bloquear_unidades(cursor, sorted(ids)):
                if not _activo(fila['apto_prestamo']) or not _activo(fila['categoria_activa']) or self._tiene_prestamo(
                    cursor, fila['id_implemento'], inicio=inicio, fin=fin,
                ):
                    raise ErrorImplemento('Un implemento seleccionado ya no está disponible.')
            cursor.execute(
                """INSERT INTO tb_operaciones_implementos
                   (id_tipo_operacion,id_estado_prestamo,id_usuario,fecha_inicio_prevista,
                    fecha_devolucion_prevista,observacion,id_reserva)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (_tipo(cursor, 'PRESTAMO'), _estado(cursor, 'PENDIENTE'), titular, inicio, fin, observacion, id_reserva),
            )
            operacion = cursor.lastrowid
            salida = _movimiento(cursor, 'SALIDA')
            for unidad in sorted(set(ids)):
                self._detalle_movimiento(cursor, operacion, unidad, salida, None)
            registrar_auditoria(cursor, actor, 'CREAR', 'tb_operaciones_implementos', operacion,
                                {'tipo': 'PRESTAMO', 'estado': 'PENDIENTE', 'codigo_reserva': codigo_reserva})
            return operacion

    @staticmethod
    def _salidas_prestamo(cursor, operacion, salida, *, bloquear=False):
        cursor.execute(
            """SELECT id_detalle_operacion,id_implemento,fecha_movimiento FROM tb_detalle_operacion
               WHERE id_operacion=%s AND id_tipo_movimiento=%s AND estado=b'1' ORDER BY id_implemento"""
            + (' FOR UPDATE' if bloquear else ''), (operacion, salida),
        )
        return cursor.fetchall()

    def cambiar_estado(self, *, actor, operacion, destino, detalle=None, administrativo=False, unidades=()):
        operacion = _id(operacion, 'Préstamo')
        segun_destino = {'ENTREGADO': ('PENDIENTE', 'ENTREGAR'), 'DEVUELTO': ('ENTREGADO', 'DEVOLVER'),
                         'CANCELADO': ('PENDIENTE', 'CANCELAR')}
        if destino not in segun_destino or (destino != 'CANCELADO' and not administrativo):
            raise ErrorImplemento('Operación de préstamo no autorizada.')
        seleccion = tuple(_id(unidad, 'Implemento') for unidad in unidades)
        if destino != 'CANCELADO' and (not seleccion or len(set(seleccion)) != len(seleccion)):
            raise ErrorImplemento('Selecciona los códigos patrimoniales de las unidades, sin repetirlos.')
        detalle = _texto(detalle, 150 if destino != 'CANCELADO' else 200, 'la condición o el motivo')
        with transaccion_mysql() as cursor:
            persona = RepositorioReservasMySQL._validar_actor(cursor, actor, administrador=administrativo)
            if destino != 'CANCELADO':
                salida = _movimiento(cursor, 'SALIDA')
                referencia = self._salidas_prestamo(cursor, operacion, salida)
                ids_previos = {r['id_implemento'] for r in referencia}
                ids = sorted(ids_previos | set(seleccion))
                filas = self._bloquear_unidades(cursor, ids)
                patrimonio = {r['id_implemento']: r for r in filas}
            cursor.execute(
                """SELECT p.id_usuario,e.nombre_estado,p.fecha_inicio_prevista,p.fecha_devolucion_prevista,NOW() AS ahora
                   FROM tb_operaciones_implementos p
                   JOIN tb_tipos_operacion t ON t.id_tipo_operacion=p.id_tipo_operacion
                   JOIN tb_estados_prestamo e ON e.id_estado_prestamo=p.id_estado_prestamo
                   WHERE p.id_operacion=%s AND t.nombre_tipo='PRESTAMO' AND p.estado=b'1' FOR UPDATE""",
                (operacion,),
            )
            fila = cursor.fetchone()
            if not fila or (not administrativo and
                            (fila['id_usuario'] != actor or persona['nombre_rol'] != 'USUARIO')):
                raise ErrorImplemento('No tienes acceso a este préstamo.')
            anterior, accion = segun_destino[destino]
            if fila['nombre_estado'] != anterior:
                raise ErrorImplemento(f'La operación debe estar en estado {anterior}.')
            if destino != 'CANCELADO':
                salidas = self._salidas_prestamo(cursor, operacion, salida, bloquear=True)
                if not salidas or salidas != referencia:
                    raise ErrorImplemento('Las unidades de la solicitud cambiaron. Vuelve a consultar el préstamo.')
                if destino == 'ENTREGADO':
                    self._entregar(cursor, operacion, fila, salidas, patrimonio, seleccion, actor, detalle)
                else:
                    if set(seleccion) != ids_previos or any(r['fecha_movimiento'] is None for r in salidas):
                        raise ErrorImplemento('La devolución debe corresponder a todas las unidades entregadas.')
                    entrada = _movimiento(cursor, 'ENTRADA')
                    for unidad in seleccion:
                        self._detalle_movimiento(cursor, operacion, unidad, entrada, actor, condicion=detalle)
            cursor.execute(
                """UPDATE tb_operaciones_implementos SET id_estado_prestamo=%s,
                   fecha_entrega=IF(%s='ENTREGADO',NOW(),fecha_entrega)
                   WHERE id_operacion=%s""", (_estado(cursor, destino), destino, operacion),
            )
            registro = {'estado_anterior': anterior, 'estado_nuevo': destino, 'detalle': detalle}
            if destino != 'CANCELADO':
                registro['codigos_patrimoniales'] = [patrimonio[i]['codigo_patrimonial'] for i in seleccion]
            registrar_auditoria(cursor, actor, accion, 'tb_operaciones_implementos', operacion, registro)

    def _entregar(self, cursor, operacion, prestamo, salidas, patrimonio, seleccion, actor, detalle):
        provisionales = {fila['id_implemento']: fila['id_detalle_operacion'] for fila in salidas}
        solicitados = agrupar_unidades(patrimonio[unidad] for unidad in provisionales)
        entregados = agrupar_unidades(patrimonio[unidad] for unidad in seleccion)
        if solicitados != entregados or any(fila['fecha_movimiento'] is not None for fila in salidas):
            raise ErrorImplemento('Selecciona la misma cantidad de unidades por cada material solicitado.')
        previstas = prestamo['fecha_inicio_prevista'], prestamo['fecha_devolucion_prevista']
        if None in previstas or previstas[0] >= previstas[1]:
            raise ErrorImplemento('El préstamo no tiene fechas previstas válidas.')
        ahora = prestamo['ahora']
        inicio, fin = min(ahora, previstas[0]), max(ahora + timedelta(seconds=1), previstas[1])
        disponibles = defaultdict(list)
        asignadas = set(seleccion)
        for unidad in seleccion:
            fila = patrimonio[unidad]
            if (not _activo(fila['apto_prestamo']) or not _activo(fila['categoria_activa']) or
                    self._tiene_prestamo(cursor, unidad, inicio=inicio, fin=fin, excluir=operacion)):
                raise ErrorImplemento('Una de las unidades no está disponible para la entrega.')
            if unidad not in provisionales:
                clave = fila['nombre_categoria'], nombre_tipo_implemento(fila['nombre_implemento'])
                disponibles[clave].append(unidad)
        for unidad, id_detalle in provisionales.items():
            fisica = unidad
            if unidad not in asignadas:
                fila = patrimonio[unidad]
                clave = fila['nombre_categoria'], nombre_tipo_implemento(fila['nombre_implemento'])
                fisica = disponibles[clave].pop()
            cursor.execute(
                """UPDATE tb_detalle_operacion SET id_implemento=%s,id_admin_movimiento=%s,fecha_movimiento=NOW(),
                   condicion_fisica=%s WHERE id_detalle_operacion=%s AND fecha_movimiento IS NULL""",
                (fisica, actor, detalle, id_detalle),
            )
            if cursor.rowcount != 1:
                raise ErrorImplemento('La salida ya no está pendiente.')
