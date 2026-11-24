# tests/pruebas_reservas.py
"""Pruebas de infraestructura/persistencia/reservas_mysql.py (PoliReserva V9).

Por defecto NO conecta con MySQL: simula las respuestas y valida operaciones,
permisos, transacciones y cambios de estado sin modificar registros reales.

Ejecutar desde la raiz del proyecto:
    python -m tests.pruebas_reservas

Para anadir la comprobacion REAL de solo lectura (opcional):
    PowerShell: $env:POLI_TEST_MYSQL_LECTURA="1"; python -m tests.pruebas_reservas
    CMD:        set POLI_TEST_MYSQL_LECTURA=1 && python -m tests.pruebas_reservas
"""

import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from aplicacion.casos_uso.reservas import actualizar_estados as proceso
from aplicacion.casos_uso.reservas.registrar_reserva_administrativa import RegistrarReservaAdministrativa
from infraestructura.persistencia import reservas_mysql as reservas


DIA = date(2026, 11, 24)
INICIO = timedelta(hours=10)
FIN = timedelta(hours=12)


def paso(texto_sql, *, uno=None, todos=None, filas=1):
    return {"sql": texto_sql, "uno": uno, "todos": todos, "filas": filas}


class CursorSimulado:
    """Exige que el repositorio ejecute las consultas en el orden esperado."""

    def __init__(self, pasos):
        self.pasos = list(pasos)
        self.realizados = []
        self.actual = None
        self.lastrowid = 41
        self.rowcount = 1
        self.cerrado = False

    def execute(self, sql, parametros=()):
        if not self.pasos:
            raise AssertionError(f"Consulta inesperada: {sql}")
        esperado = self.pasos.pop(0)
        normalizado = " ".join(sql.lower().split())
        assert esperado["sql"].lower() in normalizado, (
            f"Se esperaba una consulta con '{esperado['sql']}', pero llego: {normalizado}"
        )
        self.realizados.append((sql, parametros))
        self.actual = esperado
        self.rowcount = esperado["filas"]

    def fetchone(self):
        return self.actual["uno"]

    def fetchall(self):
        return self.actual["todos"] if self.actual["todos"] is not None else []

    def close(self):
        self.cerrado = True


class ConexionSimulada:
    def __init__(self, pasos):
        self.cursor_simulado = CursorSimulado(pasos)
        self.inicio = 0
        self.confirmaciones = 0
        self.reversiones = 0
        self.cerrada = False

    def start_transaction(self):
        self.inicio += 1

    def cursor(self, *, dictionary=False):
        if not dictionary:
            raise AssertionError("El repositorio debe emplear cursor(dictionary=True)")
        return self.cursor_simulado

    def commit(self):
        self.confirmaciones += 1

    def rollback(self):
        self.reversiones += 1

    def close(self):
        self.cerrada = True


USUARIO_VALIDO = {
    "id_usuario": 2, "perfil_completo": b"\x01",
    "usuario_activo": b"\x01", "perfil_activo": b"\x01",
    "rol_activo": b"\x01", "nombre_rol": "USUARIO",
    "nombre_tipo": "ESTUDIANTE",
    "tipo_activo": 1,
}


def fila_reserva(estado="RESERVADA"):
    return {
        "id_reserva": 41, "id_usuario": 2, "id_admin_gestor": None,
        "id_horario": 7, "id_estado_reserva": 1,
        "codigo_reserva": "RES-ABC123ABC123", "fecha_uso": DIA,
        "hora_inicio": INICIO, "hora_fin": FIN,
        "estado_reserva": estado, "bloquea_horario": b"\x01",
        "activo": b"\x01", "nombre_programacion": "Horario libre",
        "nombres": "Usuario", "apellidos": "Prueba",
    }


def pasos_registro(*, segundos=0, horario_disponible=True,
                   usuario_valido=True):
    usuario = dict(USUARIO_VALIDO)
    if not usuario_valido:
        usuario["perfil_completo"] = b"\x00"
    secuencia = [paso("from tb_usuarios u", uno=usuario)]
    if not usuario_valido:
        return secuencia
    secuencia += [
        paso("from tb_horarios_programados", todos=[{"id_horario": 7}]),
        paso("select now()", uno={"ahora": datetime(2026, 11, 23, 9)}),
        paso("from tb_estados_reserva", uno={"id_estado_reserva": 1,
                                              "bloquea_horario": b"\x01"}),
        paso("from tb_reservas r", uno={"segundos": segundos}),
    ]
    if segundos > 120 * 60:
        return secuencia
    secuencia.append(paso("from tb_horarios_programados h",
                         uno={"id_horario": 7} if horario_disponible else None))
    if not horario_disponible:
        return secuencia
    secuencia += [
        paso("insert into tb_reservas"),
        paso("from tb_tipos_accion", uno={"id_tipo_accion": 1}),
        paso("insert into tb_auditoria"),
        paso("from tb_reservas r", uno=fila_reserva()),
    ]
    return secuencia


def pasos_cambio(estado_origen, estado_destino, hora_actual, *, actor=True):
    inicial = {
        "id_reserva": 41, "id_usuario": 2, "id_admin_gestor": None,
        "activo": b"\x01", "nombre_estado": estado_origen,
        "fecha_uso": DIA, "hora_inicio": INICIO, "hora_fin": FIN,
    }
    pasos = [paso("select id_usuario from tb_reservas", uno={"id_usuario": 2}),
             paso("select id_usuario from tb_usuarios", uno={"id_usuario": 2})]
    if actor:
        pasos.append(paso("from tb_usuarios u", uno=dict(USUARIO_VALIDO)))
    pasos.append(paso("from tb_reservas r", uno=inicial))
    pasos.append(paso("select now()", uno={"ahora": hora_actual}))
    return pasos


def pasos_cambio_exitoso(estado_origen, estado_destino, hora_actual, *, actor=True):
    pasos = pasos_cambio(estado_origen, estado_destino, hora_actual, actor=actor)
    pasos += [
        paso("from tb_estados_reserva", uno={
            "id_estado_reserva": 2, "bloquea_horario":
                b"\x01" if estado_destino == "CONFIRMADA" else b"\x00",
        }),
        paso("update tb_reservas"),
        paso("from tb_tipos_accion", uno={"id_tipo_accion": 1}),
        paso("insert into tb_auditoria"),
    ]
    if estado_destino in ('CANCELADA', 'INASISTENCIA'):
        pasos.append(paso('from tb_operaciones_implementos', todos=[]))
    pasos.append(paso('from tb_reservas r', uno=fila_reserva(estado_destino)))
    return pasos


class PruebasReservas(unittest.TestCase):
    def configurar(self, pasos):
        self.conexion = ConexionSimulada(pasos)
        parche = patch.object(reservas, "obtener_conexion", return_value=self.conexion)
        parche.start()
        self.addCleanup(parche.stop)
        return reservas.RepositorioReservasMySQL()

    def comprobar_cierre(self, *, guardado=False):
        self.assertTrue(self.conexion.cerrada)
        self.assertTrue(self.conexion.cursor_simulado.cerrado)
        self.assertEqual(self.conexion.cursor_simulado.pasos, [])
        self.assertEqual(self.conexion.confirmaciones, 1 if guardado else 0)
        self.assertEqual(self.conexion.reversiones, 0 if guardado else 1)

    def test_01_validaciones_de_datos(self):
        self.assertEqual(reservas._fecha("2026-11-24"), DIA)
        self.assertEqual(reservas._hora("9:30"), "09:30")
        self.assertEqual(reservas._hora("10:00:00"), "10:00")
        self.assertEqual(reservas._id(2, "Usuario"), 2)
        for valor in ("24-11-2026", "fecha"):
            with self.subTest(fecha=valor), self.assertRaises(reservas.ErrorReserva):
                reservas._fecha(valor)
        for valor in ("25:00", "10:60", "10:30:15"):
            with self.subTest(hora=valor), self.assertRaises(reservas.ErrorReserva):
                reservas._hora(valor)
        with self.assertRaises(reservas.ErrorReserva):
            reservas._id(0, "Usuario")
        with self.assertRaises(reservas.ErrorReserva):
            reservas._codigo("")

    def test_02_normalizacion_mysql(self):
        fila = reservas._normalizar(dict(fila_reserva()))
        self.assertEqual(fila["fecha_uso"], "2026-11-24")
        self.assertEqual(fila["hora_inicio"], "10:00")
        self.assertEqual(fila["hora_fin"], "12:00")
        self.assertTrue(fila["activo"])
        self.assertTrue(fila["bloquea_horario"])

    def test_03_listar_estados(self):
        repo = self.configurar([paso("from tb_estados_reserva", todos=[
            {"id_estado_reserva": 1, "nombre_estado": "RESERVADA",
             "bloquea_horario": b"\x01"},
            {"id_estado_reserva": 3, "nombre_estado": "CANCELADA",
             "bloquea_horario": b"\x00"},
        ])])
        lista = repo.listar_estados()
        self.assertEqual(len(lista), 2)
        self.assertTrue(lista[0]["bloquea_horario"])
        self.assertFalse(lista[1]["bloquea_horario"])
        self.assertTrue(self.conexion.cerrada)

    def test_04_listar_solo_reservas_activas(self):
        repo = self.configurar([paso("from tb_reservas r", todos=[fila_reserva()])])
        lista = repo.listar_por_usuario(2, solo_activas=True)
        self.assertEqual(lista[0]["hora_inicio"], "10:00")
        sql, parametros = self.conexion.cursor_simulado.realizados[0]
        self.assertIn("er.bloquea_horario", sql)
        self.assertEqual(parametros, (2,))

    def test_05_buscar_codigo_exige_usuario(self):
        repo = self.configurar([paso("from tb_reservas r", todos=[])])
        self.assertIsNone(repo.obtener_por_codigo("RES-ABC123ABC123", id_usuario=2))
        sql, parametros = self.conexion.cursor_simulado.realizados[0]
        self.assertIn("r.id_usuario = %s", sql)
        self.assertEqual(parametros, ("RES-ABC123ABC123", 2))

    def test_06_registro_valido_confirma_transaccion_y_auditoria(self):
        repo = self.configurar(pasos_registro())
        with patch.object(reservas.secrets, "token_hex", return_value="abc123abc123"):
            resultado = repo.registrar_reserva(
                id_usuario=2, fecha_uso=DIA, hora_inicio="10:00", hora_fin="12:00"
            )
        self.assertEqual(resultado["codigo_reserva"], "RES-ABC123ABC123")
        self.assertEqual(resultado["estado_reserva"], "RESERVADA")
        self.comprobar_cierre(guardado=True)
        consultas = [c[0].lower() for c in self.conexion.cursor_simulado.realizados]
        self.assertTrue(any("for update" in c for c in consultas))
        self.assertTrue(any("insert into tb_auditoria" in c for c in consultas))

    def test_reserva_ordinaria_fin_de_semana_se_rechaza_antes_de_consultar(self):
        with patch.object(reservas, 'obtener_conexion') as conectar:
            with self.assertRaisesRegex(reservas.ReservaNoAutorizada, 'fin de semana'):
                reservas.RepositorioReservasMySQL().registrar_reserva(
                    id_usuario=2, fecha_uso=date(2026, 11, 28), hora_inicio='10:00', hora_fin='11:00',
                )
            conectar.assert_not_called()

    def test_asistente_puede_crear_reserva_excepcional(self):
        pasos = pasos_registro()
        asistente = dict(USUARIO_VALIDO, nombre_rol='ASISTENTE', nombre_tipo='ADMINISTRATIVO')
        pasos.insert(1, paso('from tb_usuarios u', uno=asistente))
        repo = self.configurar(pasos)
        sabado = date(2026, 11, 28)
        RegistrarReservaAdministrativa(repo).ejecutar(
            id_usuario_sesion=7, id_usuario=2, fecha_uso=sabado, hora_inicio='10:00', hora_fin='11:00',
        )
        consultas = self.conexion.cursor_simulado.realizados
        self.assertIn((sabado,), [params for _, params in consultas])
        self.assertEqual(next(params for sql, params in consultas if 'INSERT INTO tb_reservas' in sql)[1], 7)
        self.comprobar_cierre(guardado=True)

    def test_usuario_sin_rol_admin_no_autoriza_excepcion(self):
        perfil = paso('from tb_usuarios u', uno=USUARIO_VALIDO)
        repo = self.configurar([perfil, perfil])
        with self.assertRaises(reservas.ReservaNoAutorizada):
            RegistrarReservaAdministrativa(repo).ejecutar(
                id_usuario_sesion=7, id_usuario=2, fecha_uso=date(2026, 11, 28),
                hora_inicio='10:00', hora_fin='11:00',
            )
        self.comprobar_cierre()

    def test_07_usuario_sin_saldo_suficiente_es_rechazado(self):
        repo = self.configurar(pasos_registro(segundos=135 * 60))
        with self.assertRaisesRegex(reservas.ErrorReserva, '45 minutos'):
            repo.registrar_reserva(id_usuario=2, fecha_uso=DIA,
                                  hora_inicio="10:00", hora_fin="11:00")
        self.comprobar_cierre()

    def test_08_horario_ocupado_es_rechazado(self):
        repo = self.configurar(pasos_registro(horario_disponible=False))
        with self.assertRaises(reservas.HorarioNoDisponible):
            repo.registrar_reserva(id_usuario=2, fecha_uso=DIA,
                                  hora_inicio="10:00", hora_fin="11:00")
        self.comprobar_cierre()

    def test_09_perfil_incompleto_no_puede_reservar(self):
        repo = self.configurar(pasos_registro(usuario_valido=False))
        with self.assertRaises(reservas.ReservaNoAutorizada):
            repo.registrar_reserva(id_usuario=2, fecha_uso=DIA,
                                  hora_inicio="10:00", hora_fin="11:00")
        self.comprobar_cierre()

    def test_10_duracion_superior_a_2_horas(self):
        with self.assertRaisesRegex(reservas.ErrorReserva, "2 horas"):
            reservas.RepositorioReservasMySQL().registrar_reserva(
                id_usuario=2, fecha_uso=DIA, hora_inicio="10:00", hora_fin="12:01"
            )

    def test_11_cancelar_antes_del_inicio(self):
        repo = self.configurar(pasos_cambio_exitoso(
            "RESERVADA", "CANCELADA", datetime(2026, 11, 24, 9)
        ))
        resultado = repo.cancelar_reserva(
            codigo_reserva="RES-ABC123ABC123", id_usuario_actor=2
        )
        self.assertEqual(resultado["estado_reserva"], "CANCELADA")
        self.comprobar_cierre(guardado=True)

    def test_12_no_cancelar_cuando_inicio_el_turno(self):
        repo = self.configurar(pasos_cambio(
            "RESERVADA", "CANCELADA", datetime(2026, 11, 24, 10)
        ))
        with self.assertRaisesRegex(reservas.ErrorReserva, "antes del inicio"):
            repo.cancelar_reserva(codigo_reserva="RES-ABC123ABC123",
                                  id_usuario_actor=2)
        self.comprobar_cierre()

    def test_13_confirmar_en_tolerancia(self):
        repo = self.configurar(pasos_cambio_exitoso(
            "RESERVADA", "CONFIRMADA", datetime(2026, 11, 24, 10, 10)
        ))
        resultado = repo.confirmar_asistencia(
            codigo_reserva="RES-ABC123ABC123", id_usuario_actor=2
        )
        self.assertEqual(resultado["estado_reserva"], "CONFIRMADA")
        self.comprobar_cierre(guardado=True)

    def test_confirmar_antes_del_inicio_se_revierte(self):
        repo = self.configurar(pasos_cambio('RESERVADA', 'CONFIRMADA', datetime(2026, 11, 24, 9, 59)))
        with self.assertRaisesRegex(reservas.ErrorReserva, '15 minutos'):
            repo.confirmar_asistencia(codigo_reserva='RES-ABC123ABC123', id_usuario_actor=2)
        self.comprobar_cierre()

    def test_14_confirmar_fuera_de_tolerancia(self):
        repo = self.configurar(pasos_cambio(
            "RESERVADA", "CONFIRMADA", datetime(2026, 11, 24, 10, 15)
        ))
        with self.assertRaisesRegex(reservas.ErrorReserva, "15 minutos"):
            repo.confirmar_asistencia(codigo_reserva="RES-ABC123ABC123",
                                      id_usuario_actor=2)
        self.comprobar_cierre()

    def test_15_inasistencia_automatica(self):
        repo = self.configurar(pasos_cambio_exitoso(
            "RESERVADA", "INASISTENCIA", datetime(2026, 11, 24, 10, 16),
            actor=False,
        ))
        resultado = repo.marcar_inasistencia(codigo_reserva="RES-ABC123ABC123")
        self.assertEqual(resultado["estado_reserva"], "INASISTENCIA")
        auditoria = next(
            parametros for sql, parametros in self.conexion.cursor_simulado.realizados
            if "INSERT INTO tb_auditoria" in sql
        )
        self.assertIsNone(auditoria[0])  # accion realizada por el sistema
        self.comprobar_cierre(guardado=True)

    def test_16_no_finalizar_antes_de_terminar(self):
        repo = self.configurar(pasos_cambio(
            "CONFIRMADA", "FINALIZADA", datetime(2026, 11, 24, 11, 59),
            actor=False,
        ))
        with self.assertRaisesRegex(reservas.ErrorReserva, "no ha terminado"):
            repo.finalizar_reserva(codigo_reserva="RES-ABC123ABC123")
        self.comprobar_cierre()

    def test_17_finalizar_despues_del_turno(self):
        repo = self.configurar(pasos_cambio_exitoso(
            "CONFIRMADA", "FINALIZADA", datetime(2026, 11, 24, 12, 1),
            actor=False,
        ))
        resultado = repo.finalizar_reserva(codigo_reserva="RES-ABC123ABC123")
        self.assertEqual(resultado["estado_reserva"], "FINALIZADA")
        self.comprobar_cierre(guardado=True)


@unittest.skipUnless(
    os.getenv("POLI_TEST_MYSQL_LECTURA") == "1",
    "Prueba real desactivada: establece POLI_TEST_MYSQL_LECTURA=1 para habilitarla.",
)
class PruebaMysqlRealSoloLectura(unittest.TestCase):
    def test_catalogo_y_consultas_sin_modificar_registros(self):
        """Solo SELECT: verifica la conexion y las consultas contra la V9."""
        repo = reservas.RepositorioReservasMySQL()
        estados = repo.listar_estados()
        self.assertIsInstance(estados, list)
        for estado in estados:
            self.assertIn("nombre_estado", estado)
            self.assertIsInstance(estado["bloquea_horario"], bool)
        listado = repo.listar_por_usuario(1)
        self.assertIsInstance(listado, list)
        for reserva in listado:
            self.assertEqual(reserva["id_usuario"], 1)
            self.assertIn("codigo_reserva", reserva)




class PruebasActualizacionAutomatica(unittest.TestCase):
    def test_omite_el_ciclo_si_otra_instancia_lo_ejecuta(self):
        conexion = MagicMock()
        cursor = conexion.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (0,)
        with patch.object(proceso, 'obtener_conexion', return_value=conexion), \
             patch.object(proceso, 'RepositorioReservasMySQL') as repositorio:
            proceso.actualizar_estados()
        repositorio.assert_not_called()
        self.assertEqual(cursor.execute.call_count, 1)

    def test_avanza_ambos_estados_y_libera_el_candado_aunque_falle_una_reserva(self):
        conexion = MagicMock()
        cursor = conexion.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        with patch.object(proceso, 'obtener_conexion', return_value=conexion), \
             patch.object(proceso, 'RepositorioReservasMySQL') as repositorio, \
             patch.object(proceso, 'RegistrarInasistencia') as falta, \
             patch.object(proceso, 'FinalizarReserva') as cierre:
            repositorio.return_value.listar_transiciones_vencidas.return_value = [
                {'nombre_estado': 'RESERVADA', 'codigo_reserva': 'RES-FALTA'},
                {'nombre_estado': 'CONFIRMADA', 'codigo_reserva': 'RES-CIERRE'},
            ]
            falta.return_value.ejecutar.side_effect = reservas.ErrorReserva('Otro proceso cambió la reserva.')
            with self.assertLogs(proceso.logger, level='WARNING'):
                proceso.actualizar_estados()
        falta.return_value.ejecutar.assert_called_once_with(codigo_reserva='RES-FALTA')
        cierre.return_value.ejecutar.assert_called_once_with(codigo_reserva='RES-CIERRE')
        self.assertIn('RELEASE_LOCK', cursor.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
