"""Regresiones de agenda, indicadores, auditoría y comprobantes de V9."""

from datetime import date, datetime, timedelta
from unittest import TestCase
from unittest.mock import patch

from aplicacion import reportes
from dominio.reglas.implementos import agrupar_unidades, nombre_tipo_implemento, texto_buscable
from dominio.reglas.periodos import fechas_de_consulta
from dominio.reglas.reservas import ZONA_PERU, acciones_reserva
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from Presentacion.admin.auditoria_admin import normalizar
from Presentacion.admin.calendario_admin import filtrar_tramos
from Presentacion.componentes.agenda import horario_disponible, tramos_agenda
from Presentacion.componentes import exportaciones


LUNES = date(2026, 11, 30)


class AgendaV9Tests(TestCase):
    def test_mismo_lunes_en_consulta_diaria_y_semanal(self):
        horarios = [
            {'fecha_uso': str(LUNES), 'hora_inicio': '08:00', 'hora_fin': '12:00', 'id_horario': 10,
             'nombre_programacion': 'DEMO V9 - Horarios libres', 'nombre_tipo': 'LIBRE', 'permite_reserva': True},
            {'fecha_uso': str(LUNES), 'hora_inicio': '14:00', 'hora_fin': '18:00', 'id_horario': 11,
             'nombre_programacion': 'DEMO V9 - Mantenimiento', 'nombre_tipo': 'MANTENIMIENTO', 'permite_reserva': False},
        ]
        reservas = [{'fecha_uso': str(LUNES), 'hora_inicio': '09:00', 'hora_fin': '11:00',
                     'nombre_estado': 'RESERVADA'}]
        repo = RepositorioProgramacionesMySQL()
        with patch.object(repo, 'listar_horarios', return_value=horarios) as consulta, \
             patch.object(repo, '_listar_reservas_bloqueantes', return_value=reservas):
            semana = repo.obtener_agenda_semanal(date(2026, 12, 2))
            self.assertEqual(semana[str(LUNES)], repo.obtener_agenda(LUNES))
        consulta.assert_any_call(LUNES, date(2026, 12, 6))
        self.assertEqual(list(semana), [str(date(2026, 11, 30)), *[str(date(2026, 12, i)) for i in range(1, 7)]])
        self.assertIsNone(semana['2026-12-06'])
        agenda = semana[str(LUNES)]
        tramos = tramos_agenda(agenda, LUNES, datetime(2026, 11, 29, 10, tzinfo=ZONA_PERU))
        self.assertEqual([(t.inicio, t.fin, t.tipo, t.titulo) for t in tramos], [
            (480, 540, 'libre', 'Horarios libres'), (540, 660, 'reservado', 'Reservado'),
            (660, 720, 'libre', 'Horarios libres'), (840, 1080, 'mantenimiento', 'Mantenimiento'),
        ])
        self.assertFalse(horario_disponible(510, 570, agenda))
        self.assertTrue(horario_disponible(660, 720, agenda))
        self.assertEqual(horarios[0]['nombre_programacion'], 'DEMO V9 - Horarios libres')

    def test_fin_de_semana_no_reservable_y_actividad_visible(self):
        dia = date(2026, 12, 5)
        agenda = {
            'libres': [{'inicio': '08:00', 'fin': '11:00', 'titulo': 'Horarios libres'}],
            'ocupados': [{'inicio': '12:00', 'fin': '17:00', 'titulo': 'DEMO V9 - Taller de vóley',
                          'tipo': 'TALLER DEPORTIVO'}],
        }
        ahora = datetime(2026, 12, 4, 12, tzinfo=ZONA_PERU)
        self.assertEqual([t.tipo for t in tramos_agenda(agenda, dia, ahora)], ['no_disponible', 'taller'])
        self.assertEqual([t.tipo for t in tramos_agenda(agenda, dia, ahora, portal=False)], ['libre', 'taller'])

    def test_filtros_administrativos_conservan_los_bloqueos_del_espacio_unico(self):
        agenda = {
            'libres': [{'inicio': '08:00', 'fin': '18:00', 'id_horario': 1, 'id_periodo': 2, 'titulo': 'Libre'}],
            'ocupados': [
                {'inicio': '10:00', 'fin': '11:00', 'tipo': 'RESERVA', 'id_periodo': 2, 'codigo_reserva': 'RES-A'},
                {'inicio': '12:00', 'fin': '14:00', 'tipo': 'MANTENIMIENTO', 'id_periodo': 3, 'id_horario': 4},
            ],
        }
        ahora = datetime(2026, 11, 29, 21, tzinfo=ZONA_PERU)
        todos = tramos_agenda(agenda, LUNES, ahora, portal=False, mostrar_huecos=True)
        visibles = filtrar_tramos(todos, tipo='libre', periodo=2, mostrar_reservas=False)
        self.assertEqual([(t.inicio, t.fin, t.referencia) for t in visibles if t.tipo == 'libre'],
                         [(480, 600, 1), (660, 720, 1), (840, 1080, 1)])
        self.assertEqual([(t.inicio, t.fin) for t in visibles if t.tipo == 'sin_programacion'],
                         [(420, 480), (1080, 1320)])
        self.assertTrue(any(t.tipo == 'reservado' and t.referencia == 'RES-A' for t in todos))

    def test_acciones_y_vigencia_en_los_limites(self):
        def acciones(estado, horas, minutos):
            return acciones_reserva(estado, LUNES, '09:00', '10:00',
                                     datetime(2026, 11, 30, horas, minutos, tzinfo=ZONA_PERU))
        self.assertEqual(acciones('RESERVADA', 8, 59), (True, True, False))
        self.assertEqual(acciones('RESERVADA', 9, 0), (True, False, True))
        self.assertEqual(acciones('RESERVADA', 9, 15), (False, False, False))
        self.assertEqual(acciones('CONFIRMADA', 10, 0), (False, False, False))
        for estado in ('CANCELADA', 'INASISTENCIA', 'FINALIZADA'):
            self.assertEqual(acciones(estado, 9, 5), (False, False, False))


class ReportesV9Tests(TestCase):
    def test_rangos_calendario_y_periodo_academico(self):
        catalogo = [{'id_periodo': 9, 'fecha_inicio': '2026-08-01', 'fecha_fin': '2026-12-18'}]
        casos = {
            'Día': ('2026-12-02', '2026-12-02'), 'Semana': ('2026-11-30', '2026-12-06'),
            'Mes': ('2026-12-01', '2026-12-31'), 'Año': ('2026-01-01', '2026-12-31'),
            'Período académico': ('2026-08-01', '2026-12-18'), 'Personalizado': ('2026-12-01', '2026-12-10'),
        }
        for periodo, esperado in casos.items():
            with self.subTest(periodo=periodo):
                a, b = fechas_de_consulta(periodo, '2026-12-02', '2026-12-01', '2026-12-10', '9', catalogo)
                self.assertEqual((str(a), str(b)), esperado)
        self.assertEqual(fechas_de_consulta('Todo el historial', None, None, None, None, []), (None, None))
        with self.assertRaises(ValueError):
            fechas_de_consulta('Personalizado', None, '2026-12-18', '2026-12-01', None, [])

    def test_dashboard_ocupacion_y_operaciones_distintas(self):
        dia = str(LUNES)
        reservas = [
            dict(id_usuario=1, estado_reserva=estado, fecha_uso=dia, hora_inicio=inicio, hora_fin=fin,
                 bloquea_horario=estado == 'RESERVADA')
            for estado, inicio, fin in (
                ('FINALIZADA', '08:00', '09:00'), ('CANCELADA', '09:00', '10:00'),
                ('INASISTENCIA', '09:00', '10:00'), ('RESERVADA', '10:30', '11:00'),
            )
        ]
        horarios = [
            {'id_programacion': 7, 'fecha_uso': dia, 'nombre_tipo': 'LIBRE', 'permite_reserva': True,
             'hora_inicio': '08:00', 'hora_fin': '12:00'},
            {'id_programacion': 8, 'fecha_uso': dia, 'nombre_tipo': 'TALLER DEPORTIVO', 'permite_reserva': False,
             'hora_inicio': '11:00', 'hora_fin': '12:00'},
            {'id_programacion': 8, 'fecha_uso': '2026-12-01', 'nombre_tipo': 'TALLER DEPORTIVO',
             'permite_reserva': False, 'hora_inicio': '08:00', 'hora_fin': '11:00'},
        ]
        movimientos = [
            {'id_operacion': 5, 'movimiento': tipo, 'operacion': 'PRESTAMO',
             'nombre_implemento': f'Balon de voley N. {i}', 'fecha_movimiento': datetime(2026, 11, 30, 9)}
            for tipo, i in (('SALIDA', 1), ('SALIDA', 2), ('ENTRADA', 1), ('ENTRADA', 2))
        ]
        solicitudes = {'total': 1, 'con_reserva': 0, 'sin_reserva': 1, 'reservas_con_prestamo': 0, 'pendientes': 1}
        ahora = datetime(2026, 11, 30, 10, tzinfo=ZONA_PERU)
        with patch.object(reportes, 'RepositorioReservasMySQL') as repo_res, \
             patch.object(reportes, 'RepositorioProgramacionesMySQL') as repo_hor, \
             patch.object(reportes, 'RepositorioImplementosMySQL') as repo_imp:
            repo_res.return_value.listar_resumen.return_value = reservas
            repo_hor.return_value.listar_horarios.return_value = horarios
            repo_imp.return_value.resumen_solicitudes.return_value = solicitudes
            _, resumen, actividades, prestamos = reportes.datos_dashboard(LUNES, LUNES + timedelta(days=1), ahora)
            repo_imp.return_value.listar_movimientos.assert_not_called()
            repo_imp.return_value.listar_implementos.assert_not_called()
            repo_imp.return_value.resumen_inventario.assert_not_called()

            repo_imp.return_value.listar_movimientos.return_value = movimientos
            historial = reportes.reporte_implementos('devoluciones', LUNES, LUNES + timedelta(days=1), '')
            programadas, = reportes.reporte_programaciones('horas', LUNES, LUNES + timedelta(days=1), '')
        self.assertEqual(resumen['ocupacion'], 33.3)
        self.assertEqual((resumen['total'], resumen['vigentes'], resumen['usuarios']), (4, 1, 1))
        self.assertEqual((resumen['minutos_utilizados'], resumen['minutos_futuros']), (60, 30))
        self.assertEqual(actividades, {'TALLER DEPORTIVO': 1})
        self.assertEqual(prestamos, solicitudes)
        self.assertEqual((historial[0]['prestamos_entregados'], historial[0]['entregados']), (1, 2))
        self.assertEqual((programadas['programaciones'], programadas['jornadas'], programadas['horas']), (1, 2, 4))

    def test_tendencia_adapta_sus_franjas_y_representa_todos_los_estados(self):
        filas = [dict(fecha_uso=str(LUNES), hora_inicio=inicio, estado_reserva=estado)
                 for inicio, estado in (('08:00', 'CANCELADA'), ('09:00', 'RESERVADA'))]
        for periodo, desde, hasta, cantidad in (
            ('Día', LUNES, LUNES, 8), ('Semana', LUNES, LUNES + timedelta(days=6), 7),
            ('Mes', date(2026, 11, 1), LUNES, 6), ('Año', date(2026, 1, 1), date(2026, 12, 31), 12),
            ('Período académico', date(2026, 8, 1), date(2026, 12, 19), 5),
            ('Todo el historial', date(2022, 1, 1), LUNES, 5),
        ):
            with self.subTest(periodo=periodo):
                etiquetas, valores = reportes.tendencia_reservas(filas, desde, hasta, periodo)
                self.assertEqual((len(etiquetas), sum(valores)), (cantidad, 2))
        self.assertEqual(reportes.tendencia_reservas([], None, None, 'Todo el historial'), ([], []))


class MaterialesYComprobantesTests(TestCase):
    def test_agrupacion_reserva_variantes_y_busqueda_sin_tildes(self):
        filas = [{'id_implemento': i, 'nombre_implemento': n, 'nombre_categoria': 'Balones'} for i, n in enumerate(
            ('Balon de voley N. 1', 'Balón de vóley N.º 2', 'Balón de futsal N. 1', 'Balón talla 5'), 1,
        )]
        conteo = agrupar_unidades([*filas, filas[0]])
        self.assertEqual(conteo, {('Balones', 'Balón de vóley'): 2, ('Balones', 'Balón de futsal'): 1,
                                 ('Balones', 'Balón talla 5'): 1})
        self.assertIn('voley', texto_buscable(nombre_tipo_implemento(filas[1]['nombre_implemento'])))

    def test_comprobante_cancelado_identifica_titular_y_estado_real(self):
        fila = {'codigo_reserva': 'R-123', 'fecha_uso': str(LUNES), 'hora_inicio': '08:00', 'hora_fin': '09:00',
                'estado_reserva': 'CANCELADA', 'nombres': 'Usuario', 'apellidos': 'Prueba'}
        with patch.object(exportaciones, 'preparar_pdf', return_value=b'%PDF') as generar, \
             patch.object(exportaciones.ui.download, 'content') as enviar:
            exportaciones.descargar_comprobante(fila)
        self.assertEqual(generar.call_args.args[2][0]['titular'], 'Usuario Prueba')
        self.assertEqual(generar.call_args.args[2][0]['estado_reserva'], 'CANCELADA')
        enviar.assert_called_once_with(b'%PDF', 'R-123.pdf')

    def test_comprobante_prestamo_pendiente_no_presenta_unidad_como_entregada(self):
        prestamo = {'id_operacion': 14, 'estado_prestamo': 'PENDIENTE', 'solicitante': 'Usuario Prueba'}
        unidad = {'id_implemento': 3, 'nombre_categoria': 'Petos', 'nombre_implemento': 'Peto deportivo N. 2',
                  'codigo_patrimonial': 'PAT-3', 'movimiento': None}
        with patch.object(exportaciones, 'preparar_pdf', return_value=b'%PDF') as generar, \
             patch.object(exportaciones.ui.download, 'content'):
            exportaciones.descargar_comprobante_prestamo(prestamo, [unidad])
            datos = generar.call_args.args[2][0]
            self.assertEqual((datos['cantidad'], datos['unidades']), (1, ''))
            self.assertIn('Sin reserva', generar.call_args.args[3])
            prestamo.update(estado_prestamo='DEVUELTO', vinculo='Con reserva · RES-ABC')
            exportaciones.descargar_comprobante_prestamo(prestamo, [dict(unidad, movimiento='ENTRADA')])
            self.assertEqual(generar.call_args.args[2][0]['unidades'], 'PAT-3')
            self.assertIn('RES-ABC', generar.call_args.args[3])


class AuditoriaV9Tests(TestCase):
    def test_entrega_legible_con_datos_verificados(self):
        registro = {
            'id_auditoria': 12, 'tabla_afectada': 'tb_operaciones_implementos', 'accion': 'ENTREGAR',
            'fecha_operacion': datetime(2026, 11, 30, 10, 15), 'id_operacion': 9, 'actor': 'Asistente Prueba',
            'solicitante': 'Usuario Prueba', 'detalle_cambio': '{"estado_nuevo":"ENTREGADO","token":"EXCLUIR"}',
            'unidades': [{
                'id_implemento': 3, 'nombre_categoria': 'Balones', 'nombre_implemento': 'Balón de voley N. 1',
                'codigo_patrimonial': 'PAT-001', 'movimiento': 'SALIDA', 'fecha_movimiento': '10:15',
            }],
        }
        fila = normalizar(registro)
        self.assertEqual((fila['accion'], fila['actor']), ('Préstamo entregado', 'Asistente Prueba'))
        self.assertEqual(fila['datos']['Códigos patrimoniales'], 'PAT-001')
        self.assertEqual(fila['datos']['Material'], '1 × Balón de vóley')
        self.assertNotIn('EXCLUIR', str(fila))
        self.assertNotIn('tb_operaciones_implementos', str(fila))

    def test_auditoria_explica_cancelacion_por_inasistencia(self):
        fila = normalizar({
            'id_auditoria': 2, 'tabla_afectada': 'tb_operaciones_implementos', 'accion': 'CANCELAR',
            'fecha_operacion': datetime(2026, 11, 30, 10, 15), 'id_operacion': 13,
            'detalle_cambio': {'codigo_reserva': 'RES-ABC', 'motivo_reserva': 'INASISTENCIA'},
        })
        self.assertEqual(fila['actor'], 'Sistema')
        self.assertIn('RES-ABC', fila['referencia'])
        self.assertIn('inasistencia', fila['datos']['Motivo'])

    def test_registro_antiguo_sin_datos_deja_solo_hechos(self):
        fila = normalizar({'id_auditoria': 1, 'tabla_afectada': 'tb_reservas', 'accion': 'CANCELAR',
                          'fecha_operacion': '2026-11-22 08:00', 'detalle_cambio': 'texto legado'})
        self.assertEqual(fila['accion'], 'Reserva cancelada')
        self.assertIsNone(fila['referencia'])
        self.assertEqual(fila['datos'], {})
