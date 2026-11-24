"""Pruebas de autorización y transacciones con repositorios y cursores simulados."""

from unittest import TestCase
from unittest.mock import Mock, patch

import mysql.connector

from aplicacion.casos_uso.usuarios.actualizar_perfil import ErrorActualizarPerfil, actualizar_perfil
from aplicacion.casos_uso.usuarios.completar_perfil import ErrorCompletarPerfil, completar_perfil
from dominio.reglas.usuarios import UsuarioAutenticado
from infraestructura.persistencia.usuarios_mysql import (
    AccesoDenegado, AccesoTemporalmenteBloqueado, DatosDuplicados, RepositorioUsuariosMySQL,
)


IDENTIDAD = {
    'correo': 'estudiante@unab.edu.pe', 'google_sub': 'id-de-prueba',
    'correo_verificado': True,
}
ACTOR = UsuarioAutenticado(1, IDENTIDAD['correo'], IDENTIDAD['google_sub'])
DATOS = dict(
    nombres='Nombre', apellidos='Apellido', dni='12345678',
    codigo_institucional='PRUEBA', id_tipo_usuario=2, id_escuela=1, telefono=None,
)


def perfil(**cambios):
    return {
        'id_usuario': ACTOR.id_usuario, 'id_perfil': 1,
        'correo_institucional': ACTOR.correo, 'google_sub': ACTOR.google_sub,
        'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
        'perfil_completo': False, 'rol': 'USUARIO', **cambios,
    }


class PermisosDelPerfilTests(TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.obtener_por_id.return_value = perfil()
        self.repo.listar_tipos_usuario.return_value = [
            {'id_tipo_usuario': 2, 'nombre_tipo': 'ESTUDIANTE'},
            {'id_tipo_usuario': 3, 'nombre_tipo': 'ADMINISTRADOR'},
        ]
        self.repo.listar_escuelas.return_value = [{'id_escuela': 1}]
        self.repo.completar_perfil.return_value = perfil(perfil_completo=True)
        self.repo.actualizar_telefono.return_value = perfil(perfil_completo=True, telefono='1234567')

    def test_permiso_para_completar_y_actualizar_perfil_propio(self):
        self.assertTrue(completar_perfil(self.repo, actor=ACTOR, **DATOS)['perfil_completo'])
        self.repo.completar_perfil.assert_called_once_with(actor=ACTOR, **DATOS)
        self.repo.obtener_por_id.return_value = perfil(perfil_completo=True)
        self.assertEqual(actualizar_perfil(self.repo, actor=ACTOR, telefono='1234567')['telefono'], '1234567')
        self.repo.actualizar_telefono.assert_called_once_with(actor=ACTOR, telefono='1234567')

    def test_estudiante_no_puede_asignarse_administrador(self):
        with self.assertRaises(TypeError):
            completar_perfil(self.repo, actor=ACTOR, rol='ADMINISTRADOR', **DATOS)
        with self.assertRaises(ErrorCompletarPerfil):
            completar_perfil(self.repo, actor=ACTOR, **dict(DATOS, id_tipo_usuario=3))
        self.repo.completar_perfil.assert_not_called()

    def test_cambio_de_identidad_rol_o_estado_impide_editar(self):
        for cambio in (
            {'google_sub': 'otra-identidad'}, {'correo_institucional': 'otro@unab.edu.pe'},
            {'id_usuario': 2}, {'usuario_activo': False}, {'perfil_activo': False},
            {'rol_activo': False}, {'rol': 'ADMINISTRADOR'},
        ):
            with self.subTest(cambio=cambio):
                self.repo.obtener_por_id.return_value = perfil(**cambio)
                with self.assertRaises(ErrorCompletarPerfil):
                    completar_perfil(self.repo, actor=ACTOR, **DATOS)
                self.repo.obtener_por_id.return_value = perfil(perfil_completo=True, **cambio)
                with self.assertRaises(ErrorActualizarPerfil):
                    actualizar_perfil(self.repo, actor=ACTOR, telefono='1234567')
        self.repo.completar_perfil.assert_not_called()
        self.repo.actualizar_telefono.assert_not_called()


class RepositorioUsuariosTests(TestCase):
    def setUp(self):
        self.conectar = self.enterContext(patch('infraestructura.persistencia.usuarios_mysql.obtener_conexion'))
        self.conexion = self.conectar.return_value
        self.cursor = self.conexion.cursor.return_value
        self.cursor.lastrowid = ACTOR.id_usuario
        self.repo = RepositorioUsuariosMySQL()

    def sentencias(self, tipo):
        return [llamada.args for llamada in self.cursor.execute.call_args_list
                if llamada.args[0].strip().startswith(tipo)]

    def test_dominio_invalido_se_rechaza_antes_de_conectar(self):
        for cambio in ({'correo': 'prueba@gmail.com'}, {'correo_verificado': False}):
            with self.subTest(cambio=cambio), self.assertRaises(AccesoDenegado):
                self.repo.registrar_acceso_google(**dict(IDENTIDAD, **cambio))
        self.conectar.assert_not_called()

    def test_usuario_nuevo_y_perfil_se_crean_en_la_misma_transaccion(self):
        self.cursor.fetchone.side_effect = [None, None, {'id_rol': 7}, perfil(), perfil()]
        usuario = self.repo.registrar_acceso_google(**IDENTIDAD)
        self.assertEqual(usuario['rol'], 'USUARIO')
        self.conexion.start_transaction.assert_called_once_with()
        self.assertIn("nombre_rol = 'USUARIO'", self.sentencias('SELECT')[2][0])
        self.assertEqual([parametros for _, parametros in self.sentencias('INSERT')], [
            (ACTOR.correo, ACTOR.google_sub), (ACTOR.id_usuario, 7),
        ])
        self.conexion.commit.assert_called_once_with()
        self.conexion.rollback.assert_not_called()

    def test_correo_preexistente_no_se_vincula_por_correo(self):
        for sub in (None, 'identidad-de-otra-persona'):
            with self.subTest(sub=sub):
                self.cursor.reset_mock()
                self.conexion.rollback.reset_mock()
                self.cursor.fetchone.side_effect = [None, {'id_usuario': 9, 'google_sub': sub}]
                with self.assertRaises(AccesoDenegado):
                    self.repo.registrar_acceso_google(**IDENTIDAD)
                self.assertEqual(self.sentencias('INSERT') + self.sentencias('UPDATE'), [])
                self.conexion.rollback.assert_called_once_with()
        self.conexion.commit.assert_not_called()

    def test_rollback_si_falla_la_creacion_del_perfil(self):
        self.cursor.fetchone.side_effect = [None, None, {'id_rol': 7}]

        def ejecutar(sql, parametros=()):
            if sql.strip().startswith('INSERT INTO tb_perfiles'):
                raise mysql.connector.IntegrityError()

        self.cursor.execute.side_effect = ejecutar
        with self.assertRaises(DatosDuplicados):
            self.repo.registrar_acceso_google(**IDENTIDAD)
        self.conexion.commit.assert_not_called()
        self.conexion.rollback.assert_called_once_with()

    def test_bloqueo_al_registrar_el_ultimo_acceso_revierte_la_transaccion(self):
        self.cursor.fetchone.side_effect = [perfil(), perfil(), perfil()]

        def ejecutar(sql, parametros=()):
            if sql.strip().startswith('UPDATE tb_perfiles'):
                raise mysql.connector.DatabaseError(errno=1205)

        self.cursor.execute.side_effect = ejecutar
        with self.assertRaises(AccesoTemporalmenteBloqueado):
            self.repo.registrar_acceso_google(**IDENTIDAD)
        self.assertEqual(self.sentencias('SET'), [('SET SESSION innodb_lock_wait_timeout = 5',)])
        self.conexion.commit.assert_not_called()
        self.conexion.rollback.assert_called_once_with()

    def test_transaccion_rechaza_cambio_de_identidad_o_rol_antes_de_escribir(self):
        self.cursor.fetchone.return_value = perfil(google_sub='otra-identidad')
        with self.assertRaises(AccesoDenegado):
            self.repo.completar_perfil(actor=ACTOR, **DATOS)
        self.cursor.fetchone.return_value = perfil(perfil_completo=True, rol='ADMINISTRADOR')
        with self.assertRaises(AccesoDenegado):
            self.repo.actualizar_telefono(actor=ACTOR, telefono='1234567')
        self.assertTrue(all('FOR UPDATE' in sql for sql, _ in self.sentencias('SELECT')))
        self.assertEqual(self.sentencias('UPDATE'), [])
        self.conexion.commit.assert_not_called()
        self.assertEqual(self.conexion.rollback.call_count, 2)
