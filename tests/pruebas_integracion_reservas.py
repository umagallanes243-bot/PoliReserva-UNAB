# tests/pruebas_integracion_reservas.py
"""Pruebas de integracion REAL de PoliReserva UNAB V9.

SEGURIDAD:
- Solo se ejecutan con POLI_INTEGRACION_ESCRITURA=SI.
- Exigen una base EXCLUSIVA llamada polireserva_unab_v9_test.
- La base debe contener la estructura V9, pero NINGUN registro.
- No crean, borran ni alteran bases de datos o tablas.
- Insertan datos ficticios temporales y los eliminan al finalizar.
- Todas las conexiones del repositorio se redirigen a esa base aislada.

Preparación: seleccionar polireserva_unab_v9_test y aplicar sql/esquema_v9.sql.
El DDL no incluye registros de producción.

Ejecutar desde la raiz del proyecto (PowerShell):
    $env:POLI_INTEGRACION_DB = "polireserva_unab_v9_test"
    $env:POLI_INTEGRACION_ESCRITURA = "SI"
    python -m tests.pruebas_integracion_reservas
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from itertools import count
import os
import secrets
from threading import Barrier
import unittest
from unittest.mock import patch

from infraestructura.persistencia.conexion_mysql import obtener_conexion as _conexion_proyecto
from infraestructura.persistencia import conexion_mysql, implementos_mysql, reservas_mysql as _modulo_reservas
from infraestructura.persistencia import programaciones_mysql as _modulo_programaciones
from aplicacion import reportes
from aplicacion.casos_uso.implementos.solicitar_prestamo import SolicitarPrestamo
from aplicacion.casos_uso.implementos.entregar_prestamo import EntregarPrestamo
from aplicacion.casos_uso.implementos.devolver_prestamo import DevolverPrestamo
from aplicacion.casos_uso.programaciones.desactivar_programacion import DesactivarProgramacion
from aplicacion.casos_uso.programaciones.publicar_horarios import PublicarHorarios
from aplicacion.casos_uso.programaciones.publicar_horarios_libres import PublicarHorariosLibres
from aplicacion.casos_uso.reservas.reprogramar_reserva import ReprogramarReserva
from aplicacion.casos_uso.reservas.registrar_reserva_administrativa import RegistrarReservaAdministrativa
from dominio.reglas.reservas import ZONA_PERU
from infraestructura.persistencia.reservas_mysql import (
    ErrorReserva, HorarioNoDisponible, ReservaNoAutorizada,
    RepositorioReservasMySQL,
)
from aplicacion.casos_uso.reservas.registrar_reserva import RegistrarReserva
from aplicacion.casos_uso.reservas.cancelar_reserva import CancelarReserva
from aplicacion.casos_uso.reservas.confirmar_reserva import ConfirmarReserva
from aplicacion.casos_uso.reservas.registrar_inasistencia import RegistrarInasistencia
from aplicacion.casos_uso.reservas.finalizar_reserva import FinalizarReserva


BD_PRUEBAS = 'polireserva_unab_v9_test'
TABLAS_DEBEN_ESTAR_VACIAS = (
    'tb_usuarios', 'tb_perfiles', 'tb_roles', 'tb_tipos_usuarios',
    'tb_periodos_academicos', 'tb_tipos_programacion',
    'tb_programaciones', 'tb_horarios_programados',
    'tb_estados_reserva', 'tb_reservas',
    'tb_tipos_accion', 'tb_auditoria', 'tb_operaciones_implementos', 'tb_detalle_operacion',
    'tb_categorias_implementos', 'tb_implementos', 'tb_estados_prestamo', 'tb_tipos_movimiento',
    'tb_tipos_operacion', 'tb_escuelas',
)


def _conexion_pruebas():
    """Abre la conexion configurada del proyecto, pero cambia a BD aislada.

    Los nombres de esquema son constantes, nunca vienen de SQL del usuario.
    El cambio USE se verifica ANTES de entregar la conexion al repositorio.
    """
    conexion = _conexion_proyecto()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(f'USE `{BD_PRUEBAS}`')
        cursor.execute("SET time_zone = '-05:00'")  # hora del Peru
        cursor.execute('SELECT DATABASE()')
        if cursor.fetchone()[0] != BD_PRUEBAS:
            raise RuntimeError('Proteccion: la conexion no usa la base de pruebas.')
        # Evita que la comprobacion inicial deje una transaccion abierta.
        conexion.rollback()
        return conexion
    except Exception:
        conexion.close()
        raise
    finally:
        if cursor is not None:
            cursor.close()


class PruebasIntegracionReservas(unittest.TestCase):
    """Ejecuta DML real solo en la V9 de pruebas, que debe estar vacia."""

    @classmethod
    def setUpClass(cls):
        if (os.getenv('POLI_INTEGRACION_ESCRITURA') != 'SI'
                or os.getenv('POLI_INTEGRACION_DB') != BD_PRUEBAS):
            raise unittest.SkipTest(
                'Proteccion activada. Configura POLI_INTEGRACION_DB='
                f'{BD_PRUEBAS} y POLI_INTEGRACION_ESCRITURA=SI.'
            )

        cls._patch_conexion = patch.object(
            _modulo_reservas, 'obtener_conexion', side_effect=_conexion_pruebas
        )
        cls.enterClassContext(cls._patch_conexion)
        cls.enterClassContext(patch.object(conexion_mysql, 'obtener_conexion', side_effect=_conexion_pruebas))
        cls.enterClassContext(patch.object(_modulo_programaciones, 'obtener_conexion', side_effect=_conexion_pruebas))
        cls._identificador = secrets.token_hex(4)
        cls._numerador = count(1)
        cls._preparado = False
        cls._preparar_datos()
        cls._preparado = True

    @classmethod
    def _preparar_datos(cls):
        conexion = _conexion_pruebas()
        cursor = None
        try:
            cursor = conexion.cursor(dictionary=True)
            # La base se prepara con el SQL V9 y NO debe tener datos reales.
            for tabla in TABLAS_DEBEN_ESTAR_VACIAS:
                cursor.execute(f'SELECT COUNT(*) AS total FROM `{tabla}`')
                if cursor.fetchone()['total'] != 0:
                    raise RuntimeError(
                        f'La tabla {tabla} no esta vacia en {BD_PRUEBAS}. '
                        'Usa una base V9 de pruebas NUEVA y sin registros.'
                    )

            cursor.execute('SELECT NOW() AS ahora')
            hoy = cursor.fetchone()['ahora'].date()
            cls._fecha_pasada = hoy - timedelta(days=1)
            cls._fecha_hoy = hoy
            cls._fecha_futura = hoy + timedelta(days=2)
            if cls._fecha_futura.weekday() >= 5:
                cls._fecha_futura += timedelta(days=7 - cls._fecha_futura.weekday())
            cls._fecha_manana = hoy + timedelta(days=1)
            cls._fecha_sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7 or 7)
            cls._fecha_destino = cls._fecha_futura + timedelta(days=7)
            adyacente = -1 if cls._fecha_futura.weekday() == 4 else 1
            cls._fecha_paralela = cls._fecha_futura + timedelta(days=adyacente)

            conexion.rollback()
            conexion.start_transaction()

            def insertar(sql, valores):
                cursor.execute(sql, valores)
                return cursor.lastrowid

            cls._rol_usuario = insertar(
                "INSERT INTO tb_roles (nombre_rol) VALUES (%s)", ('USUARIO',)
            )
            cls._rol_asistente = insertar(
                "INSERT INTO tb_roles (nombre_rol) VALUES (%s)", ('ASISTENTE',)
            )
            cls._tipo_estudiante = insertar(
                "INSERT INTO tb_tipos_usuarios (nombre_tipo) VALUES (%s)",
                ('ESTUDIANTE',),
            )
            cls._tipo_libre = insertar(
                """INSERT INTO tb_tipos_programacion
                   (nombre_tipo, permite_reserva) VALUES (%s, b'1')""",
                ('LIBRE',),
            )

            for nombre, bloquea in (
                ('RESERVADA', 1), ('CONFIRMADA', 1),
                ('CANCELADA', 0), ('INASISTENCIA', 0), ('FINALIZADA', 0),
            ):
                # BIT(1) se expresa con literales SQL, no con bytes Python.
                sql_estado = (
                    "INSERT INTO tb_estados_reserva "
                    "(nombre_estado, bloquea_horario) VALUES (%s, b'1')"
                    if bloquea else
                    "INSERT INTO tb_estados_reserva "
                    "(nombre_estado, bloquea_horario) VALUES (%s, b'0')"
                )
                insertar(sql_estado, (nombre,))

            for nombre in (
                'CREAR', 'CANCELAR', 'CONFIRMAR ASISTENCIA',
                'INASISTENCIA AUTOMATICA', 'FINALIZAR RESERVA', 'MODIFICAR', 'ENTREGAR', 'DEVOLVER',
                'PROGRAMAR ACTIVIDAD',
            ):
                insertar('INSERT INTO tb_tipos_accion (nombre_accion) VALUES (%s)',
                         (nombre,))

            for nombre in ('PENDIENTE', 'ENTREGADO', 'DEVUELTO', 'CANCELADO'):
                insertar('INSERT INTO tb_estados_prestamo (nombre_estado) VALUES (%s)', (nombre,))
            insertar('INSERT INTO tb_tipos_operacion (nombre_tipo) VALUES (%s)', ('PRESTAMO',))
            for nombre, factor in (('SALIDA', -1), ('ENTRADA', 1)):
                insertar('INSERT INTO tb_tipos_movimiento (nombre_tipo,factor_movimiento) VALUES (%s,%s)',
                         (nombre, factor))
            categoria = insertar('INSERT INTO tb_categorias_implementos (nombre_categoria) VALUES (%s)', ('Pruebas',))
            cls.unidades = tuple(insertar(
                'INSERT INTO tb_implementos (id_categoria,codigo_patrimonial,nombre_implemento) VALUES (%s,%s,%s)',
                (categoria, f'IT-PAT-{i}', f'Balón N. {i}'),
            ) for i in (1, 2))
            cls._usuarios = []
            for numero in (1, 2, 3):
                tipo = cls._tipo_estudiante if numero <= 2 else None
                id_usuario = insertar(
                    """INSERT INTO tb_usuarios
                       (id_tipo_usuario, nombres, apellidos,
                        correo_institucional, perfil_completo)
                       VALUES (%s, %s, 'Integracion', %s, b'1')""",
                    (tipo, f'Usuario{numero}',
                     f'int-{cls._identificador}-{numero}@unab.edu.pe'),
                )
                rol = cls._rol_usuario if numero <= 2 else cls._rol_asistente
                insertar(
                    'INSERT INTO tb_perfiles (id_usuario, id_rol) VALUES (%s, %s)',
                    (id_usuario, rol),
                )
                cls._usuarios.append(id_usuario)
            cls.usuario_1, cls.usuario_2, cls.asistente = cls._usuarios

            cls._periodo = insertar(
                """INSERT INTO tb_periodos_academicos
                   (nombre_periodo, fecha_inicio, fecha_fin)
                   VALUES (%s, %s, %s)""",
                (f'IT-{cls._identificador}', hoy - timedelta(days=3),
                 hoy + timedelta(days=15)),
            )
            cls._programacion = insertar(
                """INSERT INTO tb_programaciones
                   (id_periodo, id_tipo_programacion, id_admin_registra,
                    nombre_programacion)
                   VALUES (%s, %s, %s, %s)""",
                (cls._periodo, cls._tipo_libre, cls.asistente,
                 f'Integracion {cls._identificador}'),
            )
            cls._horarios = {}
            for fecha in sorted({cls._fecha_pasada, cls._fecha_hoy, cls._fecha_manana,
                                 cls._fecha_futura, cls._fecha_destino, cls._fecha_paralela, cls._fecha_sabado}):
                cls._horarios[fecha] = insertar(
                    """INSERT INTO tb_horarios_programados
                       (id_programacion, fecha_uso, hora_inicio, hora_fin)
                       VALUES (%s, %s, '00:00:00', '23:59:00')""",
                    (cls._programacion, fecha),
                )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    @classmethod
    def _limpiar_reservas(cls):
        """Quita solo reservas de los usuarios ficticios del test."""
        conexion = _conexion_pruebas()
        cursor = None
        try:
            cursor = conexion.cursor()
            ids = (cls.usuario_1, cls.usuario_2)
            cursor.execute("DELETE FROM tb_auditoria WHERE tabla_afectada='tb_operaciones_implementos'")
            cursor.execute('DELETE FROM tb_detalle_operacion')
            cursor.execute('DELETE FROM tb_operaciones_implementos')
            cursor.execute(
                """DELETE a FROM tb_auditoria a
                   INNER JOIN tb_reservas r
                     ON a.tabla_afectada = 'tb_reservas'
                    AND a.id_registro_afectado = r.id_reserva
                   WHERE r.id_usuario IN (%s, %s)""", ids,
            )
            cursor.execute(
                'DELETE FROM tb_reservas WHERE id_usuario IN (%s, %s)', ids
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    @classmethod
    def tearDownClass(cls):
        try:
            if not getattr(cls, '_preparado', False):
                return
            cls._limpiar_reservas()
            conexion = _conexion_pruebas()
            cursor = None
            try:
                cursor = conexion.cursor()
                cursor.execute(
                    'DELETE FROM tb_horarios_programados WHERE id_programacion = %s',
                    (cls._programacion,),
                )
                cursor.execute(
                    'DELETE FROM tb_programaciones WHERE id_programacion = %s',
                    (cls._programacion,),
                )
                cursor.execute(
                    'DELETE FROM tb_periodos_academicos WHERE id_periodo = %s',
                    (cls._periodo,),
                )
                cursor.execute(
                    'DELETE FROM tb_perfiles WHERE id_usuario IN (%s, %s, %s)',
                    tuple(cls._usuarios),
                )
                cursor.execute(
                    'DELETE FROM tb_usuarios WHERE id_usuario IN (%s, %s, %s)',
                    tuple(cls._usuarios),
                )
                for tabla in ('tb_implementos', 'tb_categorias_implementos', 'tb_estados_prestamo',
                              'tb_tipos_movimiento', 'tb_tipos_operacion'):
                    cursor.execute(f'DELETE FROM `{tabla}`')
                cursor.execute('DELETE FROM tb_tipos_accion')
                cursor.execute('DELETE FROM tb_estados_reserva')
                cursor.execute(
                    'DELETE FROM tb_tipos_programacion WHERE id_tipo_programacion = %s',
                    (cls._tipo_libre,),
                )
                cursor.execute(
                    'DELETE FROM tb_tipos_usuarios WHERE id_tipo_usuario = %s',
                    (cls._tipo_estudiante,),
                )
                cursor.execute('DELETE FROM tb_roles WHERE id_rol IN (%s, %s)',
                               (cls._rol_usuario, cls._rol_asistente))
                conexion.commit()
            except Exception:
                conexion.rollback()
                raise
            finally:
                if cursor is not None:
                    cursor.close()
                conexion.close()
        finally:
            cls._preparado = False

    def setUp(self):
        self._limpiar_reservas()

    def tearDown(self):
        self._limpiar_reservas()

    def _codigo_nuevo(self):
        return f'INT-{self._identificador}-{next(self._numerador):03d}'

    def _sembrar_reserva(self, *, id_usuario, fecha, inicio, fin, estado):
        """Reserva controlada para probar cambios de estado dependientes del tiempo."""
        conexion = _conexion_pruebas()
        cursor = None
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute(
                """SELECT id_estado_reserva FROM tb_estados_reserva
                   WHERE nombre_estado = %s""", (estado,)
            )
            id_estado = cursor.fetchone()['id_estado_reserva']
            codigo = self._codigo_nuevo()
            cursor.execute(
                """INSERT INTO tb_reservas
                   (id_usuario, id_horario, id_estado_reserva,
                    codigo_reserva, hora_inicio, hora_fin)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (id_usuario, self._horarios[fecha], id_estado, codigo,
                 inicio, fin),
            )
            conexion.commit()
            return codigo
        except Exception:
            conexion.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def _consultar_uno(self, sql, parametros=()):
        conexion = _conexion_pruebas()
        cursor = None
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute(sql, parametros)
            return cursor.fetchone()
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

    def _numero_auditorias(self, id_reserva, accion=None):
        filtro = ' AND t.nombre_accion = %s' if accion else ''
        parametros = (id_reserva, accion) if accion else (id_reserva,)
        fila = self._consultar_uno(
            """SELECT COUNT(*) AS total FROM tb_auditoria a
               JOIN tb_tipos_accion t ON t.id_tipo_accion = a.id_tipo_accion
               WHERE a.tabla_afectada = 'tb_reservas'
                 AND a.id_registro_afectado = %s""" + filtro,
            parametros,
        )
        return fila['total']

    def test_01_registrar_y_auditar(self):
        reserva = RegistrarReserva().ejecutar(
            id_usuario_sesion=self.usuario_1,
            fecha_uso=self._fecha_futura,
            hora_inicio='09:00', hora_fin='10:00',
        )
        self.assertEqual(reserva['estado_reserva'], 'RESERVADA')
        self.assertEqual(reserva['id_usuario'], self.usuario_1)
        self.assertTrue(reserva['codigo_reserva'].startswith('RES-'))
        self.assertEqual(self._numero_auditorias(reserva['id_reserva'], 'CREAR'), 1)
        leida = RepositorioReservasMySQL().obtener_por_codigo(
            reserva['codigo_reserva'], id_usuario=self.usuario_1
        )
        self.assertEqual(leida['id_reserva'], reserva['id_reserva'])

    def _reservar(self, inicio='09:00', fin='11:00', *, fecha=None, usuario=None):
        return RegistrarReserva().ejecutar(
            id_usuario_sesion=usuario or self.usuario_1, fecha_uso=fecha or self._fecha_futura,
            hora_inicio=inicio, hora_fin=fin,
        )

    def _prestar(self, reserva=None, *, unidad=0, usuario=None, inicio='09:00', fin='10:00'):
        return SolicitarPrestamo().ejecutar_para_usuario(
            id_usuario_sesion=self.asistente, id_usuario=usuario or self.usuario_1,
            unidades=(self.unidades[unidad],), id_reserva=reserva and reserva['id_reserva'],
            observacion=None if reserva else '  Polideportivo en mantenimiento.  ',
            inicio=f'{self._fecha_futura}T{inicio}', fin=f'{self._fecha_futura}T{fin}',
        )

    def test_02_dos_turnos_de_120_y_60_y_rechazo_al_agotar(self):
        self._reservar()
        self._reservar('13:00', '14:00')
        repo = RepositorioReservasMySQL()
        self.assertEqual(repo.consumo_semanal(self.usuario_1, self._fecha_futura), 180 * 60)
        with self.assertRaisesRegex(ErrorReserva, '3 horas'):
            self._reservar('15:00', '15:01')
        self.assertEqual(len(repo.listar_por_usuario(self.usuario_1, solo_activas=True)), 2)

    def test_tres_turnos_de_60_y_rechazo_por_un_minuto(self):
        self._reservar('09:00', '10:00')
        self._reservar('10:00', '11:00')
        with self.assertRaisesRegex(ErrorReserva, '60 minutos'):
            self._reservar('12:00', '13:01')
        self._reservar('12:00', '13:00')
        self.assertEqual(RepositorioReservasMySQL().consumo_semanal(self.usuario_1, self._fecha_futura), 10800)


    def test_03_impedir_solapamientos(self):
        RegistrarReserva().ejecutar(id_usuario_sesion=self.usuario_1,
                                   fecha_uso=self._fecha_futura,
                                   hora_inicio='09:00', hora_fin='10:00')
        with self.assertRaises(HorarioNoDisponible):
            RegistrarReserva().ejecutar(id_usuario_sesion=self.usuario_2,
                                       fecha_uso=self._fecha_futura,
                                       hora_inicio='09:30', hora_fin='10:30')

    def test_04_cancelar_libera_horario_y_audita(self):
        primera = RegistrarReserva().ejecutar(
            id_usuario_sesion=self.usuario_1, fecha_uso=self._fecha_futura,
            hora_inicio='11:00', hora_fin='12:00',
        )
        cancelada = CancelarReserva().ejecutar(
            id_usuario_sesion=self.usuario_1,
            codigo_reserva=primera['codigo_reserva'],
        )
        self.assertEqual(cancelada['estado_reserva'], 'CANCELADA')
        self.assertEqual(RepositorioReservasMySQL().consumo_semanal(self.usuario_1, self._fecha_futura), 0)
        self.assertEqual(self._numero_auditorias(primera['id_reserva'], 'CANCELAR'), 1)
        segunda = RegistrarReserva().ejecutar(
            id_usuario_sesion=self.usuario_2, fecha_uso=self._fecha_futura,
            hora_inicio='11:00', hora_fin='12:00',
        )
        self.assertEqual(segunda['estado_reserva'], 'RESERVADA')

    def test_05_usuario_ajeno_no_puede_cancelar(self):
        reserva = RegistrarReserva().ejecutar(
            id_usuario_sesion=self.usuario_1, fecha_uso=self._fecha_futura,
            hora_inicio='13:00', hora_fin='14:00',
        )
        with self.assertRaises(ReservaNoAutorizada):
            CancelarReserva().ejecutar(
                id_usuario_sesion=self.usuario_2,
                codigo_reserva=reserva['codigo_reserva'],
            )
        actual = RepositorioReservasMySQL().obtener_por_codigo(
            reserva['codigo_reserva'], id_usuario=self.usuario_1
        )
        self.assertEqual(actual['estado_reserva'], 'RESERVADA')
        self.assertEqual(self._numero_auditorias(reserva['id_reserva']), 1)

    def _reloj_reservas(self, hora_simulada):
        def conexion_con_reloj():
            conn = _conexion_pruebas()
            with conn.cursor() as cursor:
                cursor.execute('SET timestamp=UNIX_TIMESTAMP(%s)', (hora_simulada,))
            return conn

        return patch.object(_modulo_reservas, 'obtener_conexion', side_effect=conexion_con_reloj)

    def test_06_confirmar_dentro_de_15_minutos(self):
        hora_simulada = datetime.fromisoformat(f'{self._fecha_manana}T09:04')
        codigo = self._sembrar_reserva(
            id_usuario=self.usuario_1, fecha=self._fecha_manana, inicio='09:00', fin='10:00', estado='RESERVADA',
        )
        with self._reloj_reservas(hora_simulada):
            confirmada = ConfirmarReserva().ejecutar(id_usuario_sesion=self.usuario_1, codigo_reserva=codigo)
        self.assertEqual(confirmada['estado_reserva'], 'CONFIRMADA')
        self.assertEqual(
            self._numero_auditorias(confirmada['id_reserva'], 'CONFIRMAR ASISTENCIA'), 1
        )

    def test_07_inasistencia_tras_tolerancia(self):
        codigo = self._sembrar_reserva(
            id_usuario=self.usuario_1, fecha=self._fecha_pasada,
            inicio='09:00', fin='10:00', estado='RESERVADA',
        )
        resultado = RegistrarInasistencia().ejecutar(codigo_reserva=codigo)
        self.assertEqual(resultado['estado_reserva'], 'INASISTENCIA')
        self.assertEqual(RepositorioReservasMySQL().consumo_semanal(self.usuario_1, self._fecha_pasada), 3600)
        self.assertEqual(
            self._numero_auditorias(resultado['id_reserva'], 'INASISTENCIA AUTOMATICA'),
            1,
        )

    def test_08_finalizar_reserva_terminada(self):
        codigo = self._sembrar_reserva(
            id_usuario=self.usuario_1, fecha=self._fecha_pasada,
            inicio='11:00', fin='12:00', estado='CONFIRMADA',
        )
        resultado = FinalizarReserva().ejecutar(codigo_reserva=codigo)
        self.assertEqual(resultado['estado_reserva'], 'FINALIZADA')
        self.assertEqual(RepositorioReservasMySQL().consumo_semanal(self.usuario_1, self._fecha_pasada), 3600)
        self.assertEqual(
            self._numero_auditorias(resultado['id_reserva'], 'FINALIZAR RESERVA'),
            1,
        )

    def test_09_no_finalizar_turno_futuro(self):
        codigo = self._sembrar_reserva(
            id_usuario=self.usuario_1, fecha=self._fecha_manana,
            inicio='10:00', fin='11:00', estado='CONFIRMADA',
        )
        with self.assertRaises(ErrorReserva):
            FinalizarReserva().ejecutar(codigo_reserva=codigo)
        actual = RepositorioReservasMySQL().obtener_por_codigo(
            codigo, id_usuario=self.usuario_1
        )
        self.assertEqual(actual['estado_reserva'], 'CONFIRMADA')

    def test_10_rollback_si_falla_auditoria(self):
        """Deshabilitar CREAR impide insertar una reserva sin su auditoria."""
        conexion = _conexion_pruebas()
        cursor = None
        try:
            cursor = conexion.cursor()
            cursor.execute(
                "UPDATE tb_tipos_accion SET estado = b'0' WHERE nombre_accion = 'CREAR'"
            )
            conexion.commit()
        finally:
            if cursor is not None:
                cursor.close()
            conexion.close()

        try:
            with self.assertRaises(ErrorReserva):
                RegistrarReserva().ejecutar(
                    id_usuario_sesion=self.usuario_1,
                    fecha_uso=self._fecha_futura,
                    hora_inicio='15:00', hora_fin='16:00',
                )
            fila = self._consultar_uno(
                'SELECT COUNT(*) AS total FROM tb_reservas WHERE id_usuario = %s',
                (self.usuario_1,),
            )
            self.assertEqual(fila['total'], 0)
        finally:
            conexion = _conexion_pruebas()
            cursor = None
            try:
                cursor = conexion.cursor()
                cursor.execute(
                    "UPDATE tb_tipos_accion SET estado = b'1' WHERE nombre_accion = 'CREAR'"
                )
                conexion.commit()
            finally:
                if cursor is not None:
                    cursor.close()
                conexion.close()

    def test_11_dos_usuarios_simultaneos_no_duplican_turno(self):
        """Dos conexiones reales compiten por el mismo intervalo."""
        barrera = Barrier(2)

        def intento(usuario):
            barrera.wait(timeout=10)
            try:
                return RegistrarReserva().ejecutar(
                    id_usuario_sesion=usuario,
                    fecha_uso=self._fecha_futura,
                    hora_inicio='17:00', hora_fin='18:00',
                )
            except ErrorReserva as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            futuros = [ejecutor.submit(intento, u)
                       for u in (self.usuario_1, self.usuario_2)]
            resultados = [f.result(timeout=25) for f in futuros]

        aceptadas = [r for r in resultados if isinstance(r, dict)]
        rechazadas = [r for r in resultados if isinstance(r, ErrorReserva)]
        self.assertEqual(len(aceptadas), 1, resultados)
        self.assertEqual(len(rechazadas), 1, resultados)
        fila = self._consultar_uno(
            """SELECT COUNT(*) AS total FROM tb_reservas r
               JOIN tb_estados_reserva e ON e.id_estado_reserva = r.id_estado_reserva
               WHERE r.estado = b'1' AND e.bloquea_horario = b'1'
                 AND r.hora_inicio < '18:00:00'
                 AND r.hora_fin > '17:00:00'"""
        )
        self.assertEqual(fila['total'], 1)

    def test_reprogramacion_recalcula_ambas_semanas_y_verifica_saldo(self):
        origen = self._reservar('09:00', '10:00')
        self._reservar('12:00', '14:00', fecha=self._fecha_destino)
        repo = RepositorioReservasMySQL()
        datos = dict(id_usuario_sesion=self.asistente, id_usuario=self.usuario_1,
                     codigo_reserva=origen['codigo_reserva'], fecha_uso=self._fecha_destino, hora_inicio='09:00')
        with self.assertRaisesRegex(ErrorReserva, '60 minutos'):
            ReprogramarReserva(repo).ejecutar(**datos, hora_fin='10:01')
        ReprogramarReserva(repo).ejecutar(**datos, hora_fin='10:00')
        self.assertEqual(repo.consumo_semanal(self.usuario_1, self._fecha_futura), 0)
        self.assertEqual(repo.consumo_semanal(self.usuario_1, self._fecha_destino), 10800)
        self._reservar('09:00', '11:00')
        cupos = reportes.reporte_reservas('cupos', self._fecha_destino, self._fecha_destino, '')
        self.assertEqual([(c['reservas'], c['minutos'], c['saldo']) for c in cupos], [(2, 180, 0)])

    def test_solicitudes_simultaneas_del_mismo_usuario_respetan_cupo(self):
        self._reservar('09:00', '10:30')
        barrera = Barrier(2)

        def reservar(fecha):
            barrera.wait(timeout=5)
            try:
                self._reservar('14:00', '15:00', fecha=fecha)
            except ErrorReserva as exc:
                return str(exc)
            return 'aceptada'

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            a = ejecutor.submit(reservar, self._fecha_futura)
            b = ejecutor.submit(reservar, self._fecha_paralela)
            resultados = [a.result(timeout=20), b.result(timeout=20)]
        self.assertEqual(resultados.count('aceptada'), 1)
        self.assertTrue(any('30 minutos' in item for item in resultados))
        self.assertEqual(RepositorioReservasMySQL().consumo_semanal(self.usuario_1, self._fecha_futura), 9000)

    def test_confirmacion_fuera_de_los_15_minutos(self):
        codigo = self._sembrar_reserva(id_usuario=self.usuario_1, fecha=self._fecha_pasada,
                                      inicio='09:00', fin='10:00', estado='RESERVADA')
        with self.assertRaisesRegex(ErrorReserva, '15 minutos'):
            ConfirmarReserva().ejecutar(id_usuario_sesion=self.usuario_1, codigo_reserva=codigo)

    def test_desactivar_protege_reservas_y_retirar_todas_las_jornadas_conserva_historial(self):
        repo = _modulo_programaciones.RepositorioProgramacionesMySQL()
        caso = DesactivarProgramacion(repo)
        reserva = self._reservar()
        datos = dict(id_usuario_sesion=self.asistente, id_programacion=self._programacion)
        try:
            jornadas = repo.listar_horarios(id_programacion=self._programacion)
            self.assertGreater(len(jornadas), 1)
            bloqueo, = repo.reservas_que_impiden_desactivar(self._programacion)
            self.assertEqual(bloqueo['codigo_reserva'], reserva['codigo_reserva'])
            with self.assertRaisesRegex(_modulo_programaciones.ErrorProgramacion, 'todavía ocupan'):
                caso.ejecutar(**datos)
            self.assertEqual(repo.listar_horarios(id_programacion=self._programacion), jornadas)

            CancelarReserva().ejecutar(id_usuario_sesion=self.usuario_1, codigo_reserva=reserva['codigo_reserva'])
            self.assertFalse(repo.reservas_que_impiden_desactivar(self._programacion))
            caso.ejecutar(**datos)
            self.assertFalse(repo.listar_horarios(id_programacion=self._programacion))
            self.assertIsNone(repo.obtener_agenda(self._fecha_futura))
            self.assertIsNone(repo.obtener_agenda(self._fecha_destino))
            historica = RepositorioReservasMySQL().obtener_para_gestion(reserva['codigo_reserva'])
            self.assertEqual(historica['estado_reserva'], 'CANCELADA')
            auditoria = self._consultar_uno(
                "SELECT COUNT(*) AS total FROM tb_auditoria WHERE tabla_afectada='tb_programaciones' "
                "AND id_registro_afectado=%s AND JSON_UNQUOTE(JSON_EXTRACT(detalle_cambio,'$.operacion'))='desactivar'",
                (self._programacion,),
            )
            self.assertEqual(auditoria['total'], 1)
        finally:
            with _conexion_pruebas() as conn, conn.cursor() as cur:
                cur.execute("UPDATE tb_programaciones SET estado=b'1' WHERE id_programacion=%s", (self._programacion,))
                cur.execute("DELETE FROM tb_auditoria WHERE tabla_afectada='tb_programaciones' "
                            "AND id_registro_afectado=%s", (self._programacion,))
                conn.commit()

    def test_publicar_huecos_en_lote_revalida_conflictos_y_crea_horarios_reservables(self):
        dia = self._fecha_futura
        originales = self._horarios[dia]
        caso = PublicarHorariosLibres()
        ids = []
        with _conexion_pruebas() as conn, conn.cursor() as cur:
            cur.execute("UPDATE tb_horarios_programados SET hora_inicio='09:00',hora_fin='11:00' WHERE id_horario=%s",
                        (originales,))
            conn.commit()
        try:
            datos = dict(id_periodo=self._periodo, desde=dia, hasta=dia, inicio='07:00', fin='15:00')
            previa = caso.previsualizar(**datos)
            self.assertEqual(previa.horarios, ((dia, '07:00', '09:00'), (dia, '11:00', '15:00')))
            with self.assertRaises(ReservaNoAutorizada):
                caso.ejecutar(id_usuario_sesion=self.usuario_1, propuesta=previa)
            ids.append(PublicarHorarios().ejecutar(
                id_usuario_sesion=self.asistente, tipo='LIBRE', id_periodo=self._periodo,
                nombre='Horario de prueba concurrente', horarios=((dia, '12:00', '13:00'),),
            ))
            with self.assertRaisesRegex(_modulo_programaciones.ErrorProgramacion, 'superpone'):
                caso.ejecutar(id_usuario_sesion=self.asistente, propuesta=previa)

            exacta = caso.previsualizar(**datos)
            self.assertEqual(exacta.horarios, ((dia, '07:00', '09:00'), (dia, '11:00', '12:00'),
                                              (dia, '13:00', '15:00')))
            ids.append(caso.ejecutar(id_usuario_sesion=self.asistente, propuesta=exacta))
            self.assertFalse(caso.previsualizar(**datos).horarios)
            self.assertEqual(self._reservar('07:00', '08:00')['estado_reserva'], 'RESERVADA')
            auditada = self._consultar_uno(
                "SELECT COUNT(*) AS total FROM tb_auditoria WHERE tabla_afectada='tb_programaciones' "
                'AND id_registro_afectado=%s', (ids[-1],),
            )
            self.assertEqual(auditada['total'], 1)
        finally:
            self._limpiar_reservas()
            with _conexion_pruebas() as conn, conn.cursor() as cur:
                for id_programacion in ids:
                    cur.execute("DELETE FROM tb_auditoria WHERE tabla_afectada='tb_programaciones' "
                                'AND id_registro_afectado=%s', (id_programacion,))
                    cur.execute('DELETE FROM tb_horarios_programados WHERE id_programacion=%s', (id_programacion,))
                    cur.execute('DELETE FROM tb_programaciones WHERE id_programacion=%s', (id_programacion,))
                cur.execute("UPDATE tb_horarios_programados SET hora_inicio='00:00',hora_fin='23:59' "
                            'WHERE id_horario=%s', (originales,))
                conn.commit()

    def test_reserva_excepcional_y_solapamiento_en_sabado(self):
        with self.assertRaisesRegex(ReservaNoAutorizada, 'fin de semana'):
            self._reservar(fecha=self._fecha_sabado)
        caso = RegistrarReservaAdministrativa()
        datos = dict(id_usuario_sesion=self.asistente, fecha_uso=self._fecha_sabado,
                     hora_inicio='09:00', hora_fin='11:00')
        reserva = caso.ejecutar(id_usuario=self.usuario_1, **datos)
        self.assertEqual(reserva['id_admin_gestor'], self.asistente)
        with self.assertRaises(HorarioNoDisponible):
            caso.ejecutar(id_usuario=self.usuario_2, **datos)

    def test_indicadores_del_periodo_y_actuales_distinguen_operaciones_y_unidades(self):
        reserva = self._reservar()
        operacion = SolicitarPrestamo().ejecutar_para_usuario(
            id_usuario_sesion=self.asistente, id_usuario=self.usuario_1,
            unidades=self.unidades, id_reserva=reserva['id_reserva'],
            inicio=f'{self._fecha_futura}T09:00', fin=f'{self._fecha_futura}T10:00',
        )
        self._prestar(reserva, inicio='10:00', fin='11:00')
        self._prestar(unidad=1, inicio='14:00', fin='15:00')
        EntregarPrestamo().ejecutar(id_usuario_sesion=self.asistente, operacion=operacion, unidades=self.unidades)
        ahora = datetime.fromisoformat(f'{self._fecha_futura}T10:30').replace(tzinfo=ZONA_PERU)

        _, _, _, solicitudes = reportes.datos_dashboard(None, None, ahora)
        self.assertEqual(solicitudes, {'total': 3, 'con_reserva': 2, 'sin_reserva': 1,
                                       'reservas_con_prestamo': 1, 'pendientes': 2})
        inventario, atencion = reportes.datos_operativos_dashboard(ahora)
        self.assertEqual(inventario, {'total': 2, 'disponibles': 0, 'prestadas': 2, 'no_habilitadas': 0})
        self.assertEqual(atencion, {'pendientes': 2, 'entregados': 1, 'vencidos': 1,
                                    'por_devolver': 2, 'por_confirmar': 0})
        con, sin = reportes.reporte_implementos('modalidades', None, None, '')
        self.assertEqual((con['operaciones'], con['reservas'], con['entregadas'], sin['operaciones']), (2, 1, 2, 1))
        solicitados, = reportes.reporte_implementos('solicitados', None, None, '')
        self.assertEqual(solicitados['solicitadas'], 4)

    def test_prestamos_con_y_sin_reserva_titularidad_y_stock(self):
        repo = implementos_mysql.RepositorioImplementosMySQL()
        reserva = self._reservar()
        independiente = self._prestar(inicio='14:00', fin='15:00')
        prestamo = repo.obtener_prestamo(independiente)
        self.assertIsNone(prestamo['id_reserva'])
        self.assertEqual(prestamo['observacion'], 'Polideportivo en mantenimiento.')
        with self.assertRaisesRegex(implementos_mysql.ErrorImplemento, 'usuario solicitante'):
            self._prestar(reserva, usuario=self.usuario_2)
        with self.assertRaisesRegex(implementos_mysql.ErrorImplemento, 'dentro del turno'):
            self._prestar(reserva, inicio='08:59')
        operacion_1 = self._prestar(reserva)
        with self.assertRaisesRegex(implementos_mysql.ErrorImplemento, 'disponible'):
            self._prestar(reserva)
        operacion_2 = SolicitarPrestamo(repo).ejecutar(
            id_usuario_sesion=self.usuario_1, grupos={('Pruebas', 'Balón'): 1}, id_reserva=reserva['id_reserva'],
            inicio=f'{self._fecha_futura}T09:00', fin=f'{self._fecha_futura}T10:00',
        )
        filas = repo.listar_prestamos(self.usuario_1, id_reserva=reserva['id_reserva'])
        self.assertEqual({r['id_operacion'] for r in filas}, {operacion_1, operacion_2})
        self.assertTrue(all(r['codigo_reserva'] == reserva['codigo_reserva'] for r in filas))
        self.assertFalse(repo.listar_prestamos(self.usuario_2, id_reserva=reserva['id_reserva']))
        self.assertEqual({r['id_reserva'] for r in repo.reservas_elegibles(self.usuario_1)}, {reserva['id_reserva']})

    def test_prestamo_sin_reserva_rechaza_motivo_vacio_o_muy_largo_en_ambos_portales(self):
        caso = SolicitarPrestamo()
        fechas = dict(inicio=f'{self._fecha_futura}T09:00', fin=f'{self._fecha_futura}T10:00')
        for motivo, mensaje in ((None, 'Indica el motivo'), ('  ', 'Indica el motivo'), ('x' * 201, '200 caracteres')):
            with self.subTest(mensaje=mensaje, motivo_nulo=motivo is None):
                with self.assertRaisesRegex(implementos_mysql.ErrorImplemento, mensaje):
                    caso.ejecutar(id_usuario_sesion=self.usuario_1, grupos={('Pruebas', 'Balón'): 1},
                                  observacion=motivo, **fechas)
                with self.assertRaisesRegex(implementos_mysql.ErrorImplemento, mensaje):
                    caso.ejecutar_para_usuario(id_usuario_sesion=self.asistente, id_usuario=self.usuario_1,
                                               unidades=self.unidades, observacion=motivo, **fechas)
        self.assertFalse(implementos_mysql.RepositorioImplementosMySQL().listar_prestamos())

    def test_cancelar_reserva_libera_pendientes_y_preserva_entrega_y_devolucion(self):
        repo = implementos_mysql.RepositorioImplementosMySQL()
        reserva = self._reservar()
        entregado = self._prestar(reserva)
        pendiente = self._prestar(reserva, unidad=1)
        EntregarPrestamo(repo).ejecutar(id_usuario_sesion=self.asistente, operacion=entregado,
                                      unidades=(self.unidades[0],))
        CancelarReserva().ejecutar(id_usuario_sesion=self.usuario_1, codigo_reserva=reserva['codigo_reserva'])
        self.assertEqual(repo.obtener_prestamo(pendiente)['nombre_estado'], 'CANCELADO')
        self.assertEqual(repo.obtener_prestamo(entregado)['nombre_estado'], 'ENTREGADO')
        self.assertEqual(repo.obtener_prestamo(pendiente)['codigo_reserva'], reserva['codigo_reserva'])
        with self.assertRaisesRegex(implementos_mysql.ErrorImplemento, 'reserva vigente'):
            self._prestar(reserva, unidad=1)
        independiente = self._prestar(unidad=1)
        self.assertIsNone(repo.obtener_prestamo(independiente)['id_reserva'])
        DevolverPrestamo(repo).ejecutar(id_usuario_sesion=self.asistente, operacion=entregado,
                                      unidades=(self.unidades[0],))
        detalle, = repo.detalle_prestamo(entregado, id_usuario=self.usuario_1)
        self.assertEqual(detalle['codigo_patrimonial'], 'IT-PAT-1')
        self.assertIsNotNone(detalle['entrega'])
        self.assertIsNotNone(detalle['devolucion'])
        self.assertEqual(repo.obtener_prestamo(entregado)['nombre_estado'], 'DEVUELTO')
        modalidades = reportes.reporte_implementos('modalidades', None, None, '')
        self.assertEqual([(f['operaciones'], f['reservas'], f['solicitadas'], f['entregadas'])
                          for f in modalidades], [(2, 1, 2, 1), (1, 0, 1, 0)])
        materiales, = reportes.reporte_implementos('por_reserva', None, None, '')
        self.assertEqual((materiales['operaciones'], materiales['solicitadas'], materiales['entregadas']), (2, 2, 1))
        aud = [r for r in conexion_mysql.consultar_auditoria() if r['id_operacion'] == pendiente]
        self.assertTrue(any(r['codigo_reserva_prestamo'] == reserva['codigo_reserva'] for r in aud))

    def test_inasistencia_cancela_prestamo_pendiente(self):
        reserva = self._reservar()
        operacion = self._prestar(reserva)
        hora_simulada = datetime.fromisoformat(f'{self._fecha_futura}T09:16')

        with self._reloj_reservas(hora_simulada):
            RegistrarInasistencia().ejecutar(codigo_reserva=reserva['codigo_reserva'])
        repo = implementos_mysql.RepositorioImplementosMySQL()
        self.assertEqual(repo.obtener_prestamo(operacion)['nombre_estado'], 'CANCELADO')
        self.assertEqual(RepositorioReservasMySQL().consumo_semanal(self.usuario_1, self._fecha_futura), 7200)

    def test_reprogramacion_valida_prestamo_sin_mover_sus_fechas(self):
        reserva = self._reservar()
        operacion = self._prestar(reserva, inicio='09:30', fin='10:00')
        editar = ReprogramarReserva()
        datos = dict(id_usuario_sesion=self.asistente, id_usuario=self.usuario_1,
                     codigo_reserva=reserva['codigo_reserva'], hora_inicio='09:15', hora_fin='10:30')
        with self.assertRaisesRegex(ErrorReserva, 'fuera del nuevo turno'):
            editar.ejecutar(**datos, fecha_uso=self._fecha_destino)
        editar.ejecutar(**datos, fecha_uso=self._fecha_futura)
        repo = implementos_mysql.RepositorioImplementosMySQL()
        p = repo.obtener_prestamo(operacion)
        self.assertEqual(p['fecha_inicio_prevista'], f'{self._fecha_futura} 09:30:00')
        self.assertEqual(p['id_reserva'], reserva['id_reserva'])

    def test_prestamos_concurrentes_respetan_patrimonio(self):
        reserva = self._reservar()
        barrera = Barrier(2)

        def solicitar():
            barrera.wait(timeout=5)
            try:
                return self._prestar(reserva)
            except implementos_mysql.ErrorImplemento as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            a = ejecutor.submit(solicitar)
            b = ejecutor.submit(solicitar)
            resultados = a.result(timeout=20), b.result(timeout=20)
        self.assertEqual(sum(isinstance(r, int) for r in resultados), 1)
        self.assertTrue(any('disponible' in r for r in resultados if isinstance(r, str)))

    def test_auditoria_de_cancelacion_vinculada_revierte_ambos_estados(self):
        reserva = self._reservar()
        operacion = self._prestar(reserva)
        with patch.object(implementos_mysql, 'registrar_auditoria',
                          side_effect=ValueError('Fallo de auditoría simulado')):
            with self.assertRaisesRegex(ErrorReserva, 'cancelación de los préstamos'):
                CancelarReserva().ejecutar(id_usuario_sesion=self.usuario_1, codigo_reserva=reserva['codigo_reserva'])
        repo = implementos_mysql.RepositorioImplementosMySQL()
        self.assertEqual(repo.obtener_prestamo(operacion)['nombre_estado'], 'PENDIENTE')
        actual = RepositorioReservasMySQL().obtener_por_codigo(
            reserva['codigo_reserva'], id_usuario=self.usuario_1,
        )
        self.assertEqual(actual['estado_reserva'], 'RESERVADA')
        self.assertEqual(self._numero_auditorias(reserva['id_reserva'], 'CANCELAR'), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
