from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, create_autospec, patch

from mysql.connector import Error as ErrorMySQL

from aplicacion.casos_uso.implementos.cancelar_solicitud import CancelarSolicitud
from aplicacion.casos_uso.implementos.crear_categoria_implemento import CrearCategoriaImplemento
from aplicacion.casos_uso.implementos.dar_de_baja_implemento import DarDeBajaImplemento
from aplicacion.casos_uso.implementos.devolver_prestamo import DevolverPrestamo
from aplicacion.casos_uso.implementos.entregar_prestamo import EntregarPrestamo
from aplicacion.casos_uso.implementos.modificar_implemento import ModificarImplemento
from aplicacion.casos_uso.implementos.registrar_implemento import RegistrarImplemento
from aplicacion.casos_uso.implementos.solicitar_prestamo import SolicitarPrestamo
from infraestructura.persistencia import conexion_mysql, implementos_mysql
from infraestructura.persistencia.implementos_mysql import ErrorImplemento, RepositorioImplementosMySQL


class PruebasImplementos(TestCase):
    def setUp(self):
        self.conexion = MagicMock()
        self.conexion.__enter__.return_value = self.conexion
        self.cursor = self.conexion.cursor.return_value.__enter__.return_value
        self.enterContext(patch.object(conexion_mysql, 'obtener_conexion', return_value=self.conexion))
        self.repo = RepositorioImplementosMySQL()

    def test_un_usuario_no_puede_cancelar_prestamos_ajenos(self):
        actor = self.enterContext(patch.object(implementos_mysql.RepositorioReservasMySQL, '_validar_actor'))
        actor.return_value = {'nombre_rol': 'USUARIO'}
        self.cursor.fetchone.return_value = {'id_usuario': 2, 'nombre_estado': 'PENDIENTE'}

        with self.assertRaisesRegex(ErrorImplemento, 'No tienes acceso'):
            CancelarSolicitud(self.repo).ejecutar(id_usuario_sesion=1, operacion=3)

        actor.assert_called_once_with(self.cursor, 1, administrador=False)
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.conexion.commit.assert_not_called()
        self.conexion.rollback.assert_called_once_with()

    def test_fallo_en_auditoria_revierte_cancelacion(self):
        actor = self.enterContext(patch.object(implementos_mysql.RepositorioReservasMySQL, '_validar_actor'))
        actor.return_value = {'nombre_rol': 'USUARIO'}
        self.cursor.fetchone.side_effect = [
            {'id_usuario': 1, 'nombre_estado': 'PENDIENTE'}, {'id_estado_prestamo': 4},
        ]
        auditoria = self.enterContext(patch.object(implementos_mysql, 'registrar_auditoria',
                                                  side_effect=ErrorMySQL('Fallo simulado')))

        with self.assertRaises(ErrorMySQL):
            CancelarSolicitud(self.repo).ejecutar(id_usuario_sesion=1, operacion=3)

        self.assertIn('UPDATE tb_operaciones_implementos', self.cursor.execute.call_args.args[0])
        auditoria.assert_called_once()
        self.conexion.commit.assert_not_called()
        self.conexion.rollback.assert_called_once_with()


    unidades = {
        i: {'id_implemento': i, 'nombre_implemento': f'Balon de voley N. {i}', 'nombre_categoria': 'Balones',
            'codigo_patrimonial': f'PAT-{i}', 'estado': 1, 'apto_prestamo': 1, 'categoria_activa': 1}
        for i in (4, 8)
    }

    def test_catalogo_de_operacion_usa_columnas_reales(self):
        self.cursor.fetchone.return_value = {'id_tipo_operacion': 1}
        self.assertEqual(implementos_mysql._tipo(self.cursor, 'PRESTAMO'), 1)
        consulta, parametros = self.cursor.execute.call_args.args
        self.assertNotIn('estado', consulta)
        self.assertEqual(parametros, ('PRESTAMO',))

    def test_solicitud_por_tipo_revalida_stock_y_registra_salida_pendiente(self):
        ahora = datetime(2026, 11, 23, 8)
        titular = {'nombre_rol': 'USUARIO', 'nombre_tipo': 'ESTUDIANTE', 'tipo_activo': 1}
        self.enterContext(patch.object(implementos_mysql.RepositorioReservasMySQL, '_validar_actor', return_value=titular))
        self.enterContext(patch.object(self.repo, '_tiene_prestamo', side_effect=lambda _, unidad, **datos: unidad == 4))
        self.cursor.fetchall.side_effect = [list(self.unidades.values()), [self.unidades[8]]]
        self.cursor.fetchone.side_effect = [
            {'ahora': ahora}, {'id_tipo_operacion': 1}, {'id_estado_prestamo': 1}, {'id_tipo_movimiento': 2},
        ]
        self.cursor.lastrowid = 12
        auditoria = self.enterContext(patch.object(implementos_mysql, 'registrar_auditoria'))
        resultado = SolicitarPrestamo(self.repo).ejecutar(
            id_usuario_sesion=2, inicio='2026-11-24T08:00', fin='2026-11-24T10:00',
            grupos={('Balones', 'Balón de vóley'): 1}, observacion='Uso en otro espacio.',
        )
        self.assertEqual(resultado, 12)
        detalles = [llamada.args[1] for llamada in self.cursor.execute.call_args_list
                    if 'INSERT INTO tb_detalle_operacion' in llamada.args[0]]
        self.assertEqual(detalles, [(12, 8, 2, None, None, None, None)])
        auditoria.assert_called_once()
        self.conexion.commit.assert_called_once()

    def preparar_movimiento(self, estado, fecha_movimiento=None):
        self.enterContext(patch.object(implementos_mysql.RepositorioReservasMySQL, '_validar_actor'))
        salidas = [{'id_detalle_operacion': 10, 'id_implemento': 4, 'fecha_movimiento': fecha_movimiento}]
        self.enterContext(patch.object(self.repo, '_salidas_prestamo', return_value=salidas))
        self.cursor.fetchall.return_value = list(self.unidades.values())
        self.cursor.fetchone.side_effect = [
            {'id_tipo_movimiento': 2},
            {'id_usuario': 2, 'nombre_estado': estado, 'fecha_inicio_prevista': datetime(2026, 11, 24, 8),
             'fecha_devolucion_prevista': datetime(2026, 11, 24, 10), 'ahora': datetime(2026, 11, 24, 8)},
            {'id_estado_prestamo': 2},
        ]
        self.cursor.rowcount = 1
        return self.enterContext(patch.object(implementos_mysql, 'registrar_auditoria'))

    def test_entrega_reemplaza_la_unidad_provisional_por_la_fisica(self):
        auditoria = self.preparar_movimiento('PENDIENTE')
        verificar = self.enterContext(patch.object(self.repo, '_tiene_prestamo', return_value=False))
        EntregarPrestamo(self.repo).ejecutar(id_usuario_sesion=7, operacion=12, unidades=(8,))
        cambios = [llamada.args[1] for llamada in self.cursor.execute.call_args_list
                   if 'UPDATE tb_detalle_operacion' in llamada.args[0]]
        self.assertEqual(cambios, [(8, 7, None, 10)])
        self.assertEqual(verificar.call_args.args[1], 8)
        self.assertEqual(verificar.call_args.kwargs['excluir'], 12)
        self.assertEqual(auditoria.call_args.args[-1]['codigos_patrimoniales'], ['PAT-8'])
        self.conexion.commit.assert_called_once()

    def test_entrega_rechaza_unidad_ya_asignada_y_revierte(self):
        auditoria = self.preparar_movimiento('PENDIENTE')
        self.enterContext(patch.object(self.repo, '_tiene_prestamo', return_value=True))
        with self.assertRaisesRegex(ErrorImplemento, 'no está disponible'):
            EntregarPrestamo(self.repo).ejecutar(id_usuario_sesion=7, operacion=12, unidades=(8,))
        self.assertFalse(any('UPDATE tb_detalle_operacion' in c.args[0] for c in self.cursor.execute.call_args_list))
        auditoria.assert_not_called()
        self.conexion.rollback.assert_called_once_with()

    def test_devolucion_rechaza_codigo_distinto_al_entregado(self):
        auditoria = self.preparar_movimiento('ENTREGADO', datetime(2026, 11, 24, 8))
        with self.assertRaisesRegex(ErrorImplemento, 'todas las unidades entregadas'):
            DevolverPrestamo(self.repo).ejecutar(id_usuario_sesion=7, operacion=12, unidades=(8,))
        auditoria.assert_not_called()
        self.conexion.rollback.assert_called_once_with()


class CasosUsoImplementosTests(TestCase):
    def setUp(self):
        self.repo = create_autospec(RepositorioImplementosMySQL, instance=True)

    def test_registro_edicion_categoria_y_baja(self):
        datos = {'codigo': 'PAT-01', 'nombre': 'Balón', 'categoria': '2', 'apto': True}
        RegistrarImplemento(self.repo).ejecutar(id_usuario_sesion=7, **datos)
        self.repo.guardar_implemento.assert_called_once_with(actor=7, descripcion=None, **datos)
        self.repo.guardar_implemento.reset_mock()
        ModificarImplemento(self.repo).ejecutar(id_usuario_sesion=7, id_implemento=8, **datos)
        self.repo.guardar_implemento.assert_called_once_with(actor=7, id_implemento=8, descripcion=None, **datos)
        CrearCategoriaImplemento(self.repo).ejecutar(id_usuario_sesion=7, nombre='Material deportivo')
        self.repo.crear_categoria.assert_called_once_with(actor=7, nombre='Material deportivo')
        DarDeBajaImplemento(self.repo).ejecutar(id_usuario_sesion=7, unidad=8, motivo='Desgaste')
        self.repo.dar_de_baja.assert_called_once_with(actor=7, unidad=8, motivo='Desgaste')

    def test_modificacion_sin_id_falla_antes_de_guardar(self):
        with self.assertRaises(ErrorImplemento):
            ModificarImplemento(self.repo).ejecutar(
                id_usuario_sesion=7, id_implemento=None, codigo='PAT-01', nombre='Balón', categoria='2', apto=True,
            )
        self.repo.guardar_implemento.assert_not_called()

    def test_solicitud_propia_y_en_nombre_de_otro_usuario(self):
        caso = SolicitarPrestamo(self.repo)
        fechas = {'inicio': '2026-12-01T08:00', 'fin': '2026-12-01T09:00'}
        grupos = {('Material deportivo', 'Balón'): 2}
        self.repo.solicitar.return_value = 12
        self.assertEqual(caso.ejecutar(id_usuario_sesion=1, grupos=grupos, observacion='Otro espacio', **fechas), 12)
        self.repo.solicitar.assert_called_once_with(actor=1, grupos=grupos, id_reserva=None,
                                                  observacion='Otro espacio', **fechas)
        self.repo.solicitar.reset_mock()
        self.assertEqual(caso.ejecutar_para_usuario(id_usuario_sesion=7, id_usuario=1, unidades=(8, 9),
                                                   observacion='Otro espacio', **fechas), 12)
        self.repo.solicitar.assert_called_once_with(
            actor=7, id_usuario=1, unidades=(8, 9), observacion='Otro espacio', id_reserva=None, **fechas,
        )

    def test_solicitud_administrativa_requiere_titular(self):
        with self.assertRaises(ErrorImplemento):
            SolicitarPrestamo(self.repo).ejecutar_para_usuario(
                id_usuario_sesion=7, id_usuario=None, unidades=(8,), inicio='2026-12-01T08:00', fin='2026-12-01T09:00',
            )
        self.repo.solicitar.assert_not_called()

    def test_entrega_devolucion_y_cancelacion_administrativa(self):
        for clase, estado in ((EntregarPrestamo, 'ENTREGADO'), (DevolverPrestamo, 'DEVUELTO')):
            with self.subTest(estado=estado):
                clase(self.repo).ejecutar(id_usuario_sesion=7, operacion=12, unidades=(8,), detalle='En buen estado')
                self.repo.cambiar_estado.assert_called_once_with(
                    actor=7, operacion=12, destino=estado, administrativo=True, detalle='En buen estado', unidades=(8,),
                )
                self.repo.cambiar_estado.reset_mock()
        CancelarSolicitud(self.repo).ejecutar_como_admin(id_usuario_sesion=7, operacion=12, motivo='Solicitud duplicada')
        self.repo.cambiar_estado.assert_called_once_with(
            actor=7, operacion=12, destino='CANCELADO', administrativo=True, detalle='Solicitud duplicada',
        )
