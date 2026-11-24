
import os
import json
from collections import defaultdict
from contextlib import contextmanager

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def obtener_conexion():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        time_zone="-05:00",
        connection_timeout=10
    )


def probar_conexion():
    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT DATABASE(), VERSION()")
            return cursor.fetchone()
        finally:
            cursor.close()
    finally:
        conexion.close()


@contextmanager
def transaccion_mysql():
    with obtener_conexion() as conexion:
        conexion.start_transaction()
        try:
            with conexion.cursor(dictionary=True, buffered=True) as cursor:
                yield cursor
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise


def registrar_auditoria(cursor, actor, accion, tabla, registro, detalle):
    cursor.execute(
        """SELECT id_tipo_accion FROM tb_tipos_accion
           WHERE nombre_accion=%s AND estado=b'1'""", (accion,),
    )
    tipo = cursor.fetchone()
    if not tipo:
        raise ValueError(f'Falta configurar la acción de auditoría {accion}.')
    cursor.execute(
        """INSERT INTO tb_auditoria
           (id_usuario_actor, id_tipo_accion, tabla_afectada, id_registro_afectado, detalle_cambio)
           VALUES (%s,%s,%s,%s,%s)""",
        (actor, tipo['id_tipo_accion'], tabla, registro, json.dumps(detalle)),
    )


def consultar_auditoria():
    with obtener_conexion() as conexion, conexion.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(
            """SELECT a.*,t.nombre_accion AS accion,
                      NULLIF(CONCAT_WS(' ', u.nombres,u.apellidos),'') AS actor,
                      r.codigo_reserva, hr.fecha_uso AS fecha_reserva,
                      TIME_FORMAT(r.hora_inicio,'%H:%i') AS hora_reserva_inicio,
                      TIME_FORMAT(r.hora_fin,'%H:%i') AS hora_reserva_fin,
                      pg.nombre_programacion, pe.nombre_periodo, ci.nombre_categoria,
                      i.nombre_implemento,i.codigo_patrimonial,o.id_operacion,
                      ot.nombre_tipo AS tipo_operacion, rp.codigo_reserva AS codigo_reserva_prestamo,
                      NULLIF(CONCAT_WS(' ',su.nombres,su.apellidos),'') AS solicitante
               FROM tb_auditoria a
               JOIN tb_tipos_accion t ON t.id_tipo_accion=a.id_tipo_accion
               LEFT JOIN tb_usuarios u ON u.id_usuario=a.id_usuario_actor
               LEFT JOIN tb_reservas r ON a.tabla_afectada='tb_reservas' AND r.id_reserva=a.id_registro_afectado
               LEFT JOIN tb_horarios_programados hr ON hr.id_horario=r.id_horario
               LEFT JOIN tb_programaciones pg
                      ON a.tabla_afectada='tb_programaciones' AND pg.id_programacion=a.id_registro_afectado
               LEFT JOIN tb_periodos_academicos pe
                      ON a.tabla_afectada='tb_periodos_academicos' AND pe.id_periodo=a.id_registro_afectado
               LEFT JOIN tb_categorias_implementos ci
                      ON a.tabla_afectada='tb_categorias_implementos' AND ci.id_categoria=a.id_registro_afectado
               LEFT JOIN tb_implementos i
                      ON a.tabla_afectada='tb_implementos' AND i.id_implemento=a.id_registro_afectado
               LEFT JOIN tb_operaciones_implementos o
                      ON a.tabla_afectada='tb_operaciones_implementos' AND o.id_operacion=a.id_registro_afectado
               LEFT JOIN tb_tipos_operacion ot ON ot.id_tipo_operacion=o.id_tipo_operacion
               LEFT JOIN tb_reservas rp ON rp.id_reserva=o.id_reserva AND ot.nombre_tipo='PRESTAMO'
               LEFT JOIN tb_perfiles pf ON a.tabla_afectada='tb_perfiles' AND pf.id_perfil=a.id_registro_afectado
               LEFT JOIN tb_usuarios su ON su.id_usuario=COALESCE(
                   r.id_usuario,o.id_usuario,pf.id_usuario,
                   IF(a.tabla_afectada='tb_usuarios',a.id_registro_afectado,NULL))
               ORDER BY a.fecha_operacion DESC,a.id_auditoria DESC"""
        )
        filas = cursor.fetchall()
        operaciones = {f['id_operacion'] for f in filas if f['tipo_operacion'] == 'PRESTAMO'}
        detalles = defaultdict(list)
        if operaciones:
            marcas = ','.join(['%s'] * len(operaciones))
            cursor.execute(
                f"""SELECT d.id_operacion,d.id_implemento,i.nombre_implemento,i.codigo_patrimonial,
                           c.nombre_categoria,m.nombre_tipo AS movimiento,d.fecha_movimiento
                    FROM tb_detalle_operacion d
                    JOIN tb_implementos i ON i.id_implemento=d.id_implemento
                    JOIN tb_categorias_implementos c ON c.id_categoria=i.id_categoria
                    JOIN tb_tipos_movimiento m ON m.id_tipo_movimiento=d.id_tipo_movimiento
                    WHERE d.estado=b'1' AND d.id_operacion IN ({marcas})
                    ORDER BY d.id_operacion,d.id_detalle_operacion""", tuple(sorted(operaciones)),
            )
            for detalle in cursor.fetchall():
                detalles[detalle['id_operacion']].append(detalle)
        for fila in filas:
            fila['unidades'] = detalles.get(fila['id_operacion'], ())
        return filas
