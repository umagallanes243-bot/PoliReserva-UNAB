from datetime import date, datetime
from unittest import TestCase
from unittest.mock import MagicMock, create_autospec, patch

from aplicacion.casos_uso.programaciones.crear_periodo_academico import CrearPeriodoAcademico
from aplicacion.casos_uso.programaciones.desactivar_programacion import DesactivarProgramacion
from aplicacion.casos_uso.programaciones.modificar_programacion import ModificarProgramacion
from aplicacion.casos_uso.programaciones.publicar_horarios import PublicarHorarios
from aplicacion.casos_uso.programaciones.publicar_horarios_libres import PublicarHorariosLibres
from infraestructura.persistencia import conexion_mysql, programaciones_mysql
from infraestructura.persistencia.programaciones_mysql import ErrorProgramacion, RepositorioProgramacionesMySQL


class CasosUsoProgramacionesTests(TestCase):
    def setUp(self):
        self.repo = create_autospec(RepositorioProgramacionesMySQL, instance=True)
        self.datos = {
            'tipo': 'LIBRE', 'id_periodo': 5, 'nombre': 'Horario libre',
            'horarios': (('2026-12-01', '08:00', '11:00'),),
        }

    def test_crear_periodo_usa_actor_de_la_sesion(self):
        CrearPeriodoAcademico(self.repo).ejecutar(
            id_usuario_sesion=3, nombre='2026-II', inicio='2026-08-01', fin='2026-12-31',
        )
        self.repo.crear_periodo.assert_called_once_with(
            actor=3, nombre='2026-II', inicio='2026-08-01', fin='2026-12-31',
        )

    def test_vista_previa_excluye_el_pasado_y_los_fines_de_semana_por_defecto(self):
        viernes = date(2026, 11, 27)
        self.repo.listar_periodos.return_value = [
            dict(id_periodo=5, fecha_inicio='2026-11-20', fecha_fin='2026-12-10'),
        ]
        self.repo.intervalos_para_publicacion.return_value = [(viernes, '10:00', '11:00')]
        datos = dict(id_periodo=5, desde='2026-11-26', hasta='2026-11-28', inicio='07:00', fin='12:00')
        caso = PublicarHorariosLibres(self.repo)
        reloj = self.enterContext(patch('aplicacion.casos_uso.programaciones.publicar_horarios_libres.datetime'))
        reloj.now.return_value = datetime(2026, 11, 27, 9, 23)
        self.assertEqual(caso.previsualizar(**datos).horarios,
                         ((viernes, '09:24', '10:00'), (viernes, '11:00', '12:00')))
        sabado = date(2026, 11, 28)
        self.assertEqual(caso.previsualizar(**datos, fines_de_semana=True).horarios[-1], (sabado, '07:00', '12:00'))
        self.repo.guardar_programacion.assert_not_called()

    def test_publicar_envia_horarios_y_retorna_identificador(self):
        self.repo.guardar_programacion.return_value = 17
        self.assertEqual(PublicarHorarios(self.repo).ejecutar(id_usuario_sesion=3, **self.datos), 17)
        self.repo.guardar_programacion.assert_called_once_with(
            actor=3, descripcion=None, responsable=None, escuela=None, **self.datos,
        )

    def test_modificar_envia_el_id_de_la_programacion(self):
        self.repo.guardar_programacion.return_value = 17
        self.assertEqual(ModificarProgramacion(self.repo).ejecutar(
            id_usuario_sesion=3, id_programacion=17, **self.datos,
        ), 17)
        self.repo.guardar_programacion.assert_called_once_with(
            actor=3, id_programacion=17, descripcion=None, responsable=None, escuela=None, **self.datos,
        )

    def test_modificacion_sin_identificador_falla_antes_de_guardar(self):
        with self.assertRaises(ErrorProgramacion):
            ModificarProgramacion(self.repo).ejecutar(id_usuario_sesion=3, id_programacion=None, **self.datos)
        self.repo.guardar_programacion.assert_not_called()

    def test_desactivacion_propaga_el_bloqueo_por_reservas(self):
        self.repo.desactivar_programacion.side_effect = ErrorProgramacion('La programación tiene reservas asociadas.')
        with self.assertRaisesRegex(ErrorProgramacion, 'reservas asociadas'):
            DesactivarProgramacion(self.repo).ejecutar(id_usuario_sesion=3, id_programacion=17)
        self.repo.desactivar_programacion.assert_called_once_with(actor=3, id_programacion=17)


class ProgramacionesTransaccionalesTests(TestCase):
    def setUp(self):
        self.conexion = MagicMock()
        self.conexion.__enter__.return_value = self.conexion
        self.cursor = self.conexion.cursor.return_value.__enter__.return_value
        self.cursor.lastrowid = 21
        self.enterContext(patch.object(conexion_mysql, 'obtener_conexion', return_value=self.conexion))
        self.enterContext(patch.object(programaciones_mysql.RepositorioReservasMySQL, '_validar_actor'))
        self.auditoria = self.enterContext(patch.object(programaciones_mysql, 'registrar_auditoria'))
        self.periodo = {'fecha_inicio': date(2026, 11, 23), 'fecha_fin': date(2026, 12, 19)}
        self.tipo = {'id_tipo_programacion': 3}
        self.datos = {'id_usuario_sesion': 3, 'tipo': 'EVENTO INSTITUCIONAL', 'id_periodo': 5,
                      'nombre': 'Encuentro institucional',
                      'horarios': (('2026-12-05', '07:00', '22:00'), ('2026-12-06', '07:00', '22:00'))}

    def test_publica_jornadas_completas_en_dias_separados(self):
        self.cursor.fetchone.side_effect = [self.periodo, self.tipo, None, None, None, None]
        self.assertEqual(PublicarHorarios().ejecutar(**self.datos), 21)
        self.assertEqual(self.cursor.executemany.call_args.args[1], [
            (21, date(2026, 12, 5), '07:00', '22:00'),
            (21, date(2026, 12, 6), '07:00', '22:00'),
        ])
        self.auditoria.assert_called_once()
        self.conexion.commit.assert_called_once()

    def test_programacion_solapada_con_reserva_no_escribe(self):
        self.cursor.fetchone.side_effect = [self.periodo, self.tipo, None, {'id_reserva': 5}]
        with self.assertRaisesRegex(ErrorProgramacion, 'reserva vigente'):
            PublicarHorarios().ejecutar(**self.datos)
        self.cursor.executemany.assert_not_called()
        self.auditoria.assert_not_called()
        self.conexion.rollback.assert_called_once()

    def test_modificar_con_reservas_asociadas_no_desactiva_franjas(self):
        self.cursor.fetchone.side_effect = [self.periodo, self.tipo, {'id_programacion': 21}, {'id_reserva': 5}]
        with self.assertRaisesRegex(ErrorProgramacion, 'reservas asociadas'):
            ModificarProgramacion().ejecutar(id_programacion=21, **self.datos)
        self.assertFalse(any('UPDATE tb_' in c.args[0] for c in self.cursor.execute.call_args_list))
        self.conexion.rollback.assert_called_once()
