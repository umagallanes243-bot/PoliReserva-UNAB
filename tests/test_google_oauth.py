"""Pruebas HTTP de OAuth con firmas y repositorio locales."""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx2
from joserfc import jwt
from joserfc.jwk import RSAKey
from nicegui import Client, app, ui
from nicegui.storage import Storage
from nicegui.testing.user import User

import inicio
from infraestructura.autenticacion.google_oauth import obtener_oauth
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from infraestructura.persistencia.usuarios_mysql import AccesoTemporalmenteBloqueado
from aplicacion.casos_uso.programaciones.publicar_horarios_libres import PropuestaHorariosLibres
from Presentacion.admin import dashboard_admin, horarios_libres_admin, prestamos_admin, reportes_admin, reservas_admin
from Presentacion.estudiante import (
    calendario, inicio_usuario, mi_perfil, mis_prestamos, mis_reservas, registro_inicial, resumen_reserva, solicitar_prestamo,
)
from Presentacion.sesion import CLAVE_SESION


CLIENTE = 'cliente-local-pruebas'
CORREO = 'prueba@unab.edu.pe'
SUB = 'identidad-local'


def control(pagina, clase, **propiedades):
    return next(e for e in reversed(list(pagina.elements.values())) if isinstance(e, clase)
                and all(e.props.get(k) == v for k, v in propiedades.items()))


def emitir(elemento, tipo, args=None):
    evento = next(e for e in elemento._event_listeners.values() if e.type == tipo)
    elemento._handle_event({'listener_id': evento.id, 'args': args})


class RepositorioSimulado:
    def __init__(self):
        self.accesos = []
        self.usuarios = {}

    def registrar_acceso_google(self, *, correo, google_sub, **afirmaciones):
        self.accesos.append(dict(correo=correo, google_sub=google_sub, **afirmaciones))
        if not self.usuarios:
            self.usuarios[1] = {
                'id_usuario': 1, 'correo_institucional': correo, 'google_sub': google_sub,
                'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
                'rol': 'USUARIO', 'perfil_completo': False,
            }
        return dict(self.usuarios[1])

    def obtener_por_id(self, identificador):
        fila = self.usuarios.get(identificador)
        return dict(fila) if fila else None

    def listar_tipos_usuario(self):
        return [{'id_tipo_usuario': 1, 'nombre_tipo': 'ESTUDIANTE'}]

    def listar_escuelas(self):
        return [{'id_escuela': 1, 'nombre_escuela': 'Escuela de prueba'}]

    def completar_perfil(self, *, actor, **datos):
        fila = self.usuarios[actor.id_usuario]
        fila.update(datos, perfil_completo=True)
        return dict(fila)

    def actualizar_telefono(self, *, actor, telefono):
        fila = self.usuarios[actor.id_usuario]
        fila['telefono'] = telefono
        return dict(fila)


class GoogleOAuthTests(TestCase):
    @classmethod
    def setUpClass(cls):
        # Una sola instancia ASGI para todas las sesiones de navegador de esta clase.
        cls.temporal = TemporaryDirectory()
        cls.addClassCleanup(cls.temporal.cleanup)
        cls.storage = patch.object(Storage, 'path', Path(cls.temporal.name))
        cls.storage.start()
        cls.addClassCleanup(cls.storage.stop)
        cls.runner = asyncio.Runner()
        cls.addClassCleanup(cls.runner.close)
        cls.firma = RSAKey.generate_key(parameters={'kid': 'pruebas'})
        cls.firma_ajena = RSAKey.generate_key(parameters={'kid': 'pruebas'})
        with patch.dict(os.environ, {
            'NICEGUI_USER_SIMULATION': 'true',
            'GOOGLE_CLIENT_ID': CLIENTE,
            'GOOGLE_CLIENT_SECRET': 'secreto-ficticio',
            'GOOGLE_REDIRECT_URI': 'http://localhost:8080/auth/callback',
        }):
            obtener_oauth.cache_clear()
            cls.oauth = obtener_oauth()
            cls.addClassCleanup(obtener_oauth.cache_clear)
            cls.oauth.google.server_metadata.update({
                '_loaded_at': 1,
                'issuer': 'https://accounts.google.com',
                'authorization_endpoint': 'https://google.example/authorize',
                'token_endpoint': 'https://google.example/token',
                'id_token_signing_alg_values_supported': ['RS256'],
                'jwks': {'keys': [cls.firma.as_dict(private=False)]},
            })
            ui.run(show=False, reload=False, storage_secret='cookie-local-de-pruebas-sin-datos-reales')
        cls.lifespan = app.router.lifespan_context(app)
        cls.runner.run(cls.lifespan.__aenter__())

    @classmethod
    def tearDownClass(cls):
        cls.runner.run(cls.lifespan.__aexit__(None, None, None))

    def setUp(self):
        ejecutar_javascript = Client.run_javascript

        def simular_javascript(cliente, codigo, *args, **kwargs):
            if '__IS_DRAWER_OPEN__' in codigo:
                # Estas pruebas ASGI simulan una sesión de escritorio sin compositor.
                return asyncio.sleep(0, result=True)
            return ejecutar_javascript(cliente, codigo, *args, **kwargs)

        self.enterContext(patch.object(Client, 'run_javascript', simular_javascript))
        self.repositorio = RepositorioSimulado()
        self.enterContext(patch.object(inicio, 'RepositorioUsuariosMySQL', return_value=self.repositorio))
        self.enterContext(patch.object(registro_inicial, 'RepositorioUsuariosMySQL', return_value=self.repositorio))
        self.enterContext(patch('Presentacion.sesion.RepositorioUsuariosMySQL', return_value=self.repositorio))
        self.enterContext(patch.object(mi_perfil, 'RepositorioUsuariosMySQL', return_value=self.repositorio))
        self.enterContext(patch('infraestructura.autenticacion.google_oauth.obtener_oauth', return_value=self.oauth))
        self.enterContext(patch.dict(os.environ, {'GOOGLE_REDIRECT_URI': 'http://localhost:8080/auth/callback'}))
        self.canje = self.enterContext(patch.object(self.oauth.google, 'fetch_access_token', new_callable=AsyncMock))
        self.cliente = httpx2.AsyncClient(transport=httpx2.ASGITransport(app), base_url='http://localhost:8080')
        self.addCleanup(lambda: self.runner.run(self.cliente.aclose()))

    def pedir(self, ruta, **kwargs):
        return self.runner.run(self.cliente.get(ruta, **kwargs))

    def iniciar(self):
        respuesta = self.pedir('/login')
        self.assertEqual(respuesta.status_code, 302)
        consulta = {k: v[0] for k, v in parse_qs(urlsplit(respuesta.headers['location']).query).items()}
        self.assertEqual(consulta['prompt'], 'select_account')
        self.assertNotIn('hd', consulta)
        self.assertEqual(consulta['code_challenge_method'], 'S256')
        self.assertTrue(consulta['nonce'])
        return consulta

    def token(self, consulta, *, omitir=None, firma=None, **cambios):
        ahora = int(time())
        claims = {
            'iss': 'https://accounts.google.com', 'aud': CLIENTE, 'sub': SUB,
            'iat': ahora - 60, 'exp': ahora + 300, 'nonce': consulta['nonce'],
            'email': CORREO, 'email_verified': True, 'hd': 'unab.edu.pe',
            'name': 'Usuario de prueba',
        }
        claims.update(cambios)
        if omitir:
            del claims[omitir]
        return jwt.encode({'alg': 'RS256', 'kid': 'pruebas'}, claims, firma or self.firma)

    def retorno(self, consulta, **kwargs):
        self.canje.return_value = {'access_token': 'local', 'id_token': self.token(consulta, **kwargs)}
        return self.pedir('/auth/callback', params={'state': consulta['state'], 'code': 'local'})

    def assert_redirect(self, respuesta, destino):
        self.assertEqual((respuesta.status_code, respuesta.headers.get('location')), (303, destino))

    def test_workspace_verificado_y_registro_inicial(self):
        consulta = self.iniciar()
        self.assert_redirect(self.retorno(consulta), '/usuario/registro')
        self.assertTrue(self.canje.await_args.kwargs['code_verifier'])
        self.assertEqual(self.repositorio.accesos, [{
            'correo': CORREO, 'google_sub': SUB,
            'correo_verificado': True,
        }])
        self.assert_redirect(self.pedir('/usuario/inicio'), '/usuario/registro')
        self.assert_redirect(self.pedir('/admin/dashboard'), '/')
        respuesta = self.pedir('/usuario/registro')
        self.assertEqual(respuesta.status_code, 200)
        for etiqueta in ('COMPLETAR PERFIL', 'Salir', 'Cambiar de cuenta', 'Revisar datos', 'Guardar perfil'):
            self.assertIn(etiqueta, respuesta.text)

    def test_correo_unab_sin_hd_lleva_a_registro_o_inicio_segun_el_perfil(self):
        self.assert_redirect(self.retorno(self.iniciar(), omitir='hd'), '/usuario/registro')
        self.assertEqual(self.pedir('/usuario/registro').status_code, 200)
        self.repositorio.usuarios[1]['perfil_completo'] = True
        self.assert_redirect(self.retorno(self.iniciar(), omitir='hd'), '/usuario/inicio')
        self.assertIn('DISPONIBILIDAD DIARIA', self.pedir('/usuario/inicio').text)

    def test_correo_unab_verificado_se_acepta_con_otro_hd(self):
        self.assert_redirect(
            self.retorno(self.iniciar(), hd='otrauniversidad.edu.pe'), '/usuario/registro'
        )
        self.assertEqual(len(self.repositorio.accesos), 1)

    def test_login_local_usa_host_del_callback(self):
        self.assert_redirect(self.pedir('http://127.0.0.1:8080/login'), 'http://localhost:8080/login')
        self.iniciar()

    def test_rechaza_dominios_y_claims_fuera_de_politica_sin_insertar(self):
        variantes = [
            {'email': f'prueba@{dominio}'}
            for dominio in ('gmail.com', 'outlook.com', 'otrauniversidad.edu.pe',
                            'unab.edu.pe.ejemplo.com', 'falso-unab.edu.pe', 'sub.unab.edu.pe')
        ] + [
            {'email_verified': False}, {'email_verified': 'true'},
            {'sub': ' '},
        ]
        for cambio in variantes:
            with self.subTest(cambio=cambio):
                self.assert_redirect(self.retorno(self.iniciar(), **cambio), '/error-dominio')
                self.assert_redirect(self.pedir('/usuario/registro'), '/')
                self.assert_redirect(self.pedir('/admin/dashboard'), '/')
                self.assertEqual(self.repositorio.accesos, [])

    def test_rechaza_firma_emisor_audiencia_expiracion_y_nonce_sin_insertar(self):
        for nombre, cambio in {
            'firma': {'firma': self.firma_ajena},
            'audiencia': {'aud': 'otro-cliente', 'azp': CLIENTE},
            'emisor': {'iss': 'https://otro.example'},
            'expiracion': {'exp': int(time()) - 30},
            'nonce': {'nonce': 'distinto'},
            'sin_nonce': {'omitir': 'nonce'},
            'sub_invalido': {'sub': 123},
        }.items():
            with self.subTest(caso=nombre):
                self.assert_redirect(self.retorno(self.iniciar(), **cambio), '/error-acceso?motivo=google')
                self.assertEqual(self.repositorio.accesos, [])

    def test_userinfo_sin_id_token_no_autentica(self):
        consulta = self.iniciar()
        self.canje.return_value = {'userinfo': {'email': CORREO, 'sub': SUB, 'hd': 'unab.edu.pe'}}
        self.assert_redirect(
            self.pedir('/auth/callback', params={'state': consulta['state'], 'code': 'local'}),
            '/error-acceso?motivo=google',
        )
        self.assertEqual(self.repositorio.accesos, [])

    def test_sesion_antigua_se_descarta_sin_consultar_ni_insertar(self):
        previa = set(app.storage._users)
        self.pedir('/')
        identificador, = set(app.storage._users) - previa
        almacenamiento = app.storage._users[identificador]
        for correo in ('anterior@gmail.com', CORREO):
            with self.subTest(correo=correo):
                almacenamiento.update(id_usuario=1, google_sub=SUB, correo=correo, admin_autenticado=True)
                destino = '/' if correo == CORREO else '/error-dominio'
                with patch.object(self.repositorio, 'obtener_por_id') as consultar:
                    self.assert_redirect(self.pedir('/admin/dashboard'), destino)
                    consultar.assert_not_called()
                self.assertEqual(dict(almacenamiento), {})
                self.assertEqual(self.repositorio.accesos, [])

    def test_cambio_de_cuenta_revoca_sesion_y_acepta_solo_el_estado_nuevo(self):
        anterior = self.iniciar()
        self.assert_redirect(self.retorno(anterior), '/usuario/registro')
        cookie_anterior = self.cliente.cookies.get('session')
        self.assert_redirect(self.pedir('/logout?cambiar=true'), '/login')
        nuevo = self.iniciar()
        self.assertNotEqual(anterior['state'], nuevo['state'])
        self.canje.reset_mock()
        error = '/error-acceso?motivo=google'
        self.assert_redirect(self.pedir('/auth/callback', params={'state': anterior['state']}), error)
        self.canje.assert_not_awaited()
        self.assertIn('Puedes volver a usar la misma cuenta.', self.pedir(error).text)
        self.assert_redirect(self.retorno(nuevo, email='otra@gmail.com'), '/error-dominio')
        self.assert_redirect(self.pedir('/usuario/registro'), '/')
        self.cliente.cookies.set('session', cookie_anterior, domain='localhost.local', path='/')
        self.assertEqual(self.cliente.cookies.get('session'), cookie_anterior)
        self.assert_redirect(self.pedir('/usuario/registro'), '/')
        self.assertEqual(len(self.repositorio.accesos), 1)

    def test_usuario_activo_deshabilitado_y_sesion_expirada(self):
        previa = set(app.storage._users)
        self.pedir('/')
        identificador, = set(app.storage._users) - previa
        almacenamiento = app.storage._users[identificador]
        for campo in ('usuario_activo', 'perfil_activo', 'rol_activo'):
            with self.subTest(campo=campo):
                self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
                self.repositorio.usuarios[1][campo] = False
                self.assert_redirect(self.pedir('/usuario/registro'), '/error-acceso')
                self.repositorio.usuarios[1][campo] = True
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        with patch('Presentacion.sesion.time', return_value=time() + 9 * 3600):
            self.assert_redirect(self.pedir('/usuario/registro'), '/')
        self.assertNotIn(CLAVE_SESION, almacenamiento)

    def test_administrador_preconfigurado_y_administrador_incompleto(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ADMINISTRADOR', 'perfil_completo': False,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/error-acceso')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        for pagina in ('dashboard', 'reservas', 'actividades', 'inventario',
                       'usuarios', 'prestamos', 'reportes', 'auditoria'):
            with self.subTest(pagina=pagina):
                self.assertEqual(self.pedir(f'/admin/{pagina}').status_code, 200)
        self.assert_redirect(self.pedir('/usuario/registro'), '/admin/dashboard')
        self.assert_redirect(self.pedir('/logout'), '/')
        self.assert_redirect(self.pedir('/admin/dashboard'), '/')
        self.assert_redirect(self.pedir('/admin-login'), '/login')
        self.assert_redirect(self.pedir('/vista-previa'), '/')

    def test_transaccion_bloqueada_se_muestra_y_permite_reintentar(self):
        destino = '/error-acceso?motivo=base-ocupada'
        with patch.object(self.repositorio, 'registrar_acceso_google',
                          side_effect=AccesoTemporalmenteBloqueado):
            self.assert_redirect(self.retorno(self.iniciar()), destino)
        self.assertIn('Otra transacción está bloqueando el acceso.', self.pedir(destino).text)
        self.assert_redirect(self.pedir('/usuario/registro'), '/')
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.assert_redirect(self.pedir('/logout'), '/')

    def test_misma_cuenta_puede_cambiar_de_usuario_a_admin_y_volver(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        navegador = User(self.cliente)
        pagina = self.runner.run(navegador.open('/usuario/inicio'))
        self.assert_redirect(self.pedir('/admin/dashboard'), '/')

        self.repositorio.usuarios[1]['rol'] = 'ADMINISTRADOR'
        self.assert_redirect(self.pedir('/admin/dashboard'), '/login')
        self.assertTrue(pagina.is_deleted)
        self.assert_redirect(self.pedir('/admin/dashboard'), '/')
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        panel = self.runner.run(navegador.open('/admin/dashboard'))

        self.repositorio.usuarios[1]['rol'] = 'USUARIO'
        self.assert_redirect(self.pedir('/admin/dashboard'), '/login')
        self.assertTrue(panel.is_deleted)
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/inicio')
        self.assert_redirect(self.pedir('/admin/dashboard'), '/')
        self.assertEqual({acceso['google_sub'] for acceso in self.repositorio.accesos}, {SUB})
        self.assertEqual(set(self.repositorio.usuarios), {1})
        self.assert_redirect(self.pedir('/logout'), '/')

    def test_guardado_de_registro_y_actualizacion_desde_nicegui(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')

        def elemento(pagina, clase, **propiedades):
            return next(e for e in pagina.elements.values() if isinstance(e, clase)
                        and all(e.props.get(k) == v for k, v in propiedades.items()))

        def pulsar(pagina, etiqueta, icono):
            boton = elemento(pagina, ui.button, label=etiqueta, icon=icono)
            evento = next(e for e in boton._event_listeners.values() if e.type == 'click')
            with pagina:
                boton._handle_event({'listener_id': evento.id, 'args': None})

        async def usar_formularios():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/registro')
            with pagina:
                for etiqueta, valor in {
                    'Nombres *': 'Nombre', 'Apellidos *': 'Apellido',
                    'DNI *': '12345678', 'Código institucional *': 'PRUEBA',
                }.items():
                    elemento(pagina, ui.input, label=etiqueta).set_value(valor)
                for selector in (e for e in pagina.elements.values() if isinstance(e, ui.select)):
                    selector.set_value(1)
            pulsar(pagina, 'Guardar perfil', 'save')
            await navegador.should_see('DISPONIBILIDAD DIARIA')
            self.assertTrue(self.repositorio.usuarios[1]['perfil_completo'])
            self.assertEqual(self.repositorio.usuarios[1]['rol'], 'USUARIO')

            pagina = await navegador.open('/usuario/perfil')
            with pagina:
                elemento(pagina, ui.input, label='Teléfono (opcional)').set_value('1234567')
            pulsar(pagina, 'Guardar cambios', 'visibility')
            pulsar(pagina, 'Guardar cambios', 'save')
            for _ in range(10):
                if self.repositorio.usuarios[1].get('telefono') == '1234567':
                    break
                await asyncio.sleep(0.05)
            self.assertEqual(self.repositorio.usuarios[1]['telefono'], '1234567')

        self.runner.run(usar_formularios())
        self.assert_redirect(self.pedir('/logout'), '/')


    def test_calendario_registra_una_vez_y_muestra_solo_la_reserva_propia(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        futuro = datetime.now(calendario.ZONA_PERU).date() + timedelta(days=1)
        if futuro.weekday() >= 5:
            futuro += timedelta(days=7 - futuro.weekday())
        codigo = 'RES-ABC123ABC123'
        reserva = {
            'codigo_reserva': codigo, 'estado_reserva': 'RESERVADA', 'fecha_uso': futuro.isoformat(),
            'hora_inicio': '09:00', 'hora_fin': '10:00',
        }
        agenda = {'libres': [{'inicio': '08:00', 'fin': '11:00', 'titulo': 'Horario libre'}], 'ocupados': []}
        repo = self.enterContext(patch.object(calendario, 'RepositorioProgramacionesMySQL')).return_value
        repo.obtener_agenda_semanal.return_value = {futuro.isoformat(): agenda}
        repo.obtener_agenda.return_value = agenda
        repo.buscar_horario_reservable.return_value = {'id_horario': 7}
        registrar = self.enterContext(patch.object(calendario, 'RegistrarReserva')).return_value.ejecutar
        registrar.return_value = reserva
        buscar = self.enterContext(patch.object(resumen_reserva, 'RepositorioReservasMySQL'))
        buscar = buscar.return_value.obtener_por_codigo
        buscar.return_value = reserva

        async def usar_calendario():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/calendario')

            def encontrar(clase, etiqueta):
                return next(e for e in pagina.elements.values()
                            if isinstance(e, clase) and e.props.get('label') == etiqueta)

            def pulsar(boton):
                evento = next(e for e in boton._event_listeners.values() if e.type == 'click')
                boton._handle_event({'listener_id': evento.id, 'args': None})

            with pagina:
                boton = encontrar(ui.button, 'Realizar Reserva')
                self.assertFalse(boton.enabled)
                for etiqueta, valor in {'Fecha': futuro.isoformat(),
                                        'Hora inicial': '09:00', 'Hora final': '10:00'}.items():
                    encontrar(ui.input, etiqueta).set_value(valor)
                pulsar(encontrar(ui.button, 'Ver disponibilidad'))
                self.assertTrue(boton.enabled)
                pulsar(boton)
                pulsar(boton)
            await navegador.should_see(content=codigo, retries=25)

        self.runner.run(usar_calendario())
        registrar.assert_called_once_with(id_usuario_sesion=1, fecha_uso=futuro,
                                          hora_inicio='09:00', hora_fin='10:00')
        buscar.assert_called_once_with(codigo, id_usuario=1)
        for pagina in ('mis-reservas', 'solicitar-prestamo', 'mis-prestamos'):
            with self.subTest(pagina=pagina):
                self.assertEqual(self.pedir(f'/usuario/{pagina}').status_code, 200)
        self.assert_redirect(self.pedir('/admin/prestamos'), '/')

    def test_publicacion_desde_actividades_usa_el_actor_administrativo(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ADMINISTRADOR', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'listar_horarios', return_value=[]))
        self.enterContext(patch.object(
            RepositorioProgramacionesMySQL, 'listar_periodos',
            return_value=[{'id_periodo': 5, 'nombre_periodo': 'Período de prueba'}],
        ))
        guardar = self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'guardar_programacion', return_value=17))
        hoy = datetime.now(calendario.ZONA_PERU).date()
        sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7 or 7)
        dia, domingo = sabado.isoformat(), (sabado + timedelta(days=1)).isoformat()

        async def publicar():
            navegador = User(self.cliente)
            pagina = await navegador.open('/admin/actividades?vista=listado&tipo=LIBRE')
            with pagina:
                emitir(control(pagina, ui.button, label='Nuevo horario'), 'click')
                dialogo = control(pagina, ui.dialog)
                control(pagina, ui.select, label='Período académico').set_value(5)
                control(pagina, ui.input, label='Fecha').set_value(dia)
                control(pagina, ui.input, label='Última fecha (opcional)').set_value(domingo)
                emitir(control(pagina, ui.button, label='Jornada completa'), 'click')
                emitir(control(pagina, ui.button, label='Agregar horario'), 'click')
                emitir(control(pagina, ui.button, label='Publicar horarios'), 'click')
            async with asyncio.timeout(3):
                while dialogo.value:
                    await asyncio.sleep(0.05)

        self.runner.run(publicar())
        guardar.assert_called_once_with(
            actor=1, tipo='LIBRE', id_periodo=5, nombre='Horario disponible',
            descripcion='', responsable=None, escuela=None,
            horarios=((dia, '07:00', '22:00'), (domingo, '07:00', '22:00')),
        )

    def test_reportes_refresca_la_consulta_activa_y_exige_aplicar_nuevos_filtros(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ASISTENTE', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        self.enterContext(patch.object(reportes_admin, 'obtener_periodos_academicos', return_value=[]))
        leer = self.enterContext(patch.object(reportes_admin, 'obtener_resultados'))
        filas = [dict(dia='Martes', reservas=1, horas=1)]
        leer.side_effect = [[], filas, filas]

        async def revisar():
            navegador = User(self.cliente)
            pagina = await navegador.open('/admin/reportes')
            with pagina:
                temporizador = control(pagina, ui.timer)
                self.assertEqual(temporizador.interval, 60)
                await temporizador.callback()
                leer.assert_not_called()
                self.assertIn('Pulsa Consultar', control(pagina, ui.table).props['no-data-label'])
                emitir(control(pagina, ui.button, label='Consultar'), 'click')

                async with asyncio.timeout(3):
                    while 'reservas finalizadas' not in control(pagina, ui.table).props['no-data-label']:
                        await asyncio.sleep(0.02)
                await temporizador.callback()
                async with asyncio.timeout(3):
                    while not control(pagina, ui.table).rows:
                        await asyncio.sleep(0.02)

                tabla = control(pagina, ui.table)
                self.assertEqual(tabla.rows[0]['reservas'], 1)
                await temporizador.callback()
                self.assertIs(control(pagina, ui.table), tabla)
                control(pagina, ui.select, label='Período').set_value('Mes')
                await temporizador.callback()
                self.assertEqual(leer.call_count, 3)

        self.runner.run(revisar())

    def test_dashboard_filtros_refrescan_periodo_y_alertas_abren_listas_filtradas(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ASISTENTE', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        periodo = self.enterContext(patch.object(dashboard_admin, 'datos_dashboard', return_value=(
            [], dict(total=0, vigentes=0, usuarios=0, ocupacion=None, minutos_utilizados=0,
                     minutos_habilitados=0, minutos_futuros=0), {},
            dict(total=0, con_reserva=0, sin_reserva=0, reservas_con_prestamo=0, pendientes=0),
        )))
        estado_actual = self.enterContext(patch.object(dashboard_admin, 'datos_operativos_dashboard', return_value=(
            dict(total=7, disponibles=6, prestadas=1, no_habilitadas=0),
            dict(pendientes=1, por_devolver=1, vencidos=1, por_confirmar=0),
        )))
        agenda = self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'obtener_agenda', return_value=None))
        repo = self.enterContext(patch.object(prestamos_admin, 'RepositorioImplementosMySQL')).return_value
        repo.listar_prestamos.return_value = [
            dict(id_operacion=4, estado_prestamo='PENDIENTE', fecha_devolucion_prevista='2026-01-01 08:00'),
            dict(id_operacion=5, estado_prestamo='ENTREGADO', fecha_devolucion_prevista='2026-01-01 08:00'),
            dict(id_operacion=6, estado_prestamo='ENTREGADO', fecha_devolucion_prevista=None),
        ]
        self.enterContext(patch.object(reservas_admin, 'mostrar_reservas', return_value=[]))

        async def navegar():
            navegador = User(self.cliente)
            pagina = await navegador.open('/admin/dashboard')
            await navegador.should_see(content='6 / 7')
            await navegador.should_see(content='No hay reservas en este período.')
            self.assertFalse(any(isinstance(e, ui.echart) for e in pagina.elements.values()))
            with pagina:
                control(pagina, ui.select, label='Período estadístico').set_value('Mes')
                control(pagina, ui.input, label='Fecha de la agenda').set_value('2026-12-10')
                self.assertEqual((periodo.call_count, estado_actual.call_count, agenda.call_count), (2, 1, 2))
                emitir(control(pagina, ui.button, **{'aria-label': 'Actualizar dashboard'}), 'click')
                self.assertEqual((periodo.call_count, estado_actual.call_count, agenda.call_count), (3, 2, 4))
                rutas = {e.props.get('href') for e in pagina.elements.values() if e.tag == 'a'}
            self.assertIn('/admin/prestamos?estado=VENCIDOS', rutas)
            self.assertIn('/admin/reservas?filtro=asistencia', rutas)
            pagina = await navegador.open('/admin/prestamos?estado=VENCIDOS')
            self.assertEqual([p['id_operacion'] for p in control(pagina, ui.table).rows], [5])
            pagina = await navegador.open('/admin/reservas?filtro=asistencia')
            self.assertEqual(control(pagina, ui.select, label='Estado').value, reservas_admin.POR_CONFIRMAR)

        self.runner.run(navegar())

    def test_calendario_administrativo_filtra_sin_recargar_y_abre_reserva_de_sabado(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ASISTENTE', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        hoy = datetime.now(calendario.ZONA_PERU).date()
        sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7 or 7)
        libre = dict(id_horario=8, id_periodo=5, inicio='08:00', fin='12:00', titulo='Horario de sábado')
        reserva = dict(inicio='11:00', fin='11:30', tipo='RESERVA', codigo_reserva='RES-PRUEBA', id_periodo=5)
        agendas = {sabado.isoformat(): dict(libres=[libre], ocupados=[reserva])}
        leer = self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'obtener_agendas', return_value=agendas))
        self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'listar_periodos', return_value=[
            {'id_periodo': 5, 'nombre_periodo': 'Período de prueba'},
        ]))
        horario = dict(id_horario=8, id_programacion=17, id_periodo=5, nombre_periodo='Período de prueba',
                       nombre_escuela=None, nombre_programacion='Horario de sábado', nombre_tipo='LIBRE',
                       permite_reserva=True, hora_inicio='08:00', hora_fin='12:00', fecha_uso=sabado.isoformat())
        self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'listar_horarios', return_value=[horario]))
        self.enterContext(patch.object(reservas_admin.RepositorioUsuariosMySQL, 'listar_usuarios', return_value=[
            dict(id_usuario=7, nombres='Persona', apellidos='Prueba', rol='USUARIO', tipo_usuario='DOCENTE',
                 usuario_activo=True, perfil_activo=True, rol_activo=True, perfil_completo=True),
        ]))
        self.enterContext(patch.object(reservas_admin.RepositorioReservasMySQL, 'consumo_semanal', return_value=0))
        guardar = self.enterContext(patch.object(reservas_admin.RepositorioReservasMySQL, 'registrar_reserva'))

        async def usar():
            navegador = User(self.cliente)
            pagina = await navegador.open(f'/admin/actividades?dia={sabado.isoformat()}')
            await navegador.should_see(content='Dom')
            with pagina:
                modo = control(pagina, ui.toggle)
                self.assertEqual(modo.value, 'Semana')
                control(pagina, ui.switch).set_value(False)
                self.assertEqual(leer.call_count, 1)
                modo.set_value('Mes')
                self.assertEqual(leer.call_count, 2)
                async def esperar_boton(prefijo):
                    async with asyncio.timeout(3):
                        while True:
                            boton = next((e for e in pagina.elements.values() if e.tag == 'button' and
                                          e.props.get('aria-label', '').startswith(prefijo)), None)
                            if boton:
                                return boton
                            await asyncio.sleep(0.02)

                emitir(await esperar_boton(f'{sabado:%d/%m/%Y} · '), 'click')
                self.assertEqual((modo.value, leer.call_count), ('Semana', 3))
                bloque = await esperar_boton('08:00–11:00 · Disponible')
                emitir(bloque, 'click')
                emitir(control(pagina, ui.button, label='Nueva reserva'), 'click')
                control(pagina, ui.select, label='Usuario registrado').set_value(7)
                self.assertEqual(control(pagina, ui.input, label='Fecha de uso').value, sabado.isoformat())
                self.assertEqual(control(pagina, ui.input, label='Hora inicial').value, '08:00')
                self.assertEqual(control(pagina, ui.input, label='Hora final').value, '10:00')
                dlg = control(pagina, ui.dialog)
                emitir(control(pagina, ui.button, label='Guardar'), 'click')
            async with asyncio.timeout(3):
                while dlg.value:
                    await asyncio.sleep(0.05)

        self.runner.run(usar())
        guardar.assert_called_once_with(id_usuario=7, id_admin_gestor=1, fecha_uso=sabado.isoformat(),
                                        hora_inicio='08:00', hora_fin='10:00')
        self.assertEqual(leer.call_count, 4)

    def test_desactivar_desde_listado_informa_del_bloqueo_antes_de_escribir(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ASISTENTE', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        fecha = datetime.now(calendario.ZONA_PERU).date() + timedelta(days=1)
        self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'listar_periodos', return_value=[]))
        self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'listar_horarios', return_value=[
            dict(id_horario=1, id_programacion=8, id_periodo=5, nombre_periodo='Período de prueba',
                 nombre_escuela=None, nombre_programacion='Horario libre', fecha_uso=fecha.isoformat(),
                 hora_inicio='07:00', hora_fin='12:00'),
        ]))
        leer = self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'reservas_que_impiden_desactivar',
                                            return_value=[dict(codigo_reserva='RES-VIGENTE', fecha_uso=fecha,
                                                               hora_inicio='08:00', hora_fin='10:00',
                                                               nombre_estado='RESERVADA')]))
        desactivar = self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'desactivar_programacion'))

        async def abrir():
            navegador = User(self.cliente)
            pagina = await navegador.open('/admin/actividades?vista=listado&tipo=LIBRE')
            with pagina:
                tabla = control(pagina, ui.table)
                emitir(tabla, 'selection', {'added': True, 'rows': [tabla.rows[0]], 'keys': [1]})
                emitir(control(pagina, ui.button, label='Desactivar'), 'click')
                self.assertFalse(control(pagina, ui.button, label='Desactivar').enabled)
            await navegador.should_see(content='RES-VIGENTE')
            self.assertTrue(any(e.props.get('href') == '/admin/reservas?codigo=RES-VIGENTE'
                                for e in pagina.elements.values()))

        self.runner.run(abrir())
        leer.assert_called_once_with(8)
        desactivar.assert_not_called()

    def test_calendario_previsualiza_lote_y_exige_recalcular_al_cambiar_jornada(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ASISTENTE', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        dia = datetime.now(calendario.ZONA_PERU).date() + timedelta(days=7)
        self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'listar_periodos', return_value=[
            dict(id_periodo=5, nombre_periodo='Período de prueba',
                 fecha_inicio=(dia - timedelta(days=6)).isoformat(), fecha_fin=(dia + timedelta(days=6)).isoformat()),
        ]))
        agenda = self.enterContext(patch.object(RepositorioProgramacionesMySQL, 'obtener_agendas', return_value={}))
        caso = self.enterContext(patch.object(horarios_libres_admin, 'PublicarHorariosLibres')).return_value
        propuesta = PropuestaHorariosLibres(5, ((dia, '07:00', '12:00'),))
        caso.previsualizar.return_value = propuesta

        async def publicar():
            navegador = User(self.cliente)
            pagina = await navegador.open(f'/admin/actividades?dia={dia.isoformat()}')
            with pagina:
                emitir(control(pagina, ui.button, label='Completar horarios libres'), 'click')
                boton = control(pagina, ui.button, label='Publicar horarios libres')
                vista_previa = control(pagina, ui.button, label='Vista previa')
                self.assertFalse(boton.enabled)
                emitir(vista_previa, 'click')
                await navegador.should_see(content='Franjas para publicar · 1')
                control(pagina, ui.input, label='Cierre').set_value('12:00')
                self.assertFalse(boton.enabled)
                caso.ejecutar.assert_not_called()
                emitir(vista_previa, 'click')
                await navegador.should_see(content='Franjas para publicar · 1')
                emitir(boton, 'click')
                async with asyncio.timeout(3):
                    while control(pagina, ui.dialog).value:
                        await asyncio.sleep(0.05)

        self.runner.run(publicar())
        caso.ejecutar.assert_called_once_with(id_usuario_sesion=1, propuesta=propuesta)
        self.assertEqual(agenda.call_count, 2)

    def test_solicitar_y_cancelar_prestamo_desde_portal_del_usuario(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        repo = self.enterContext(patch.object(solicitar_prestamo, 'RepositorioImplementosMySQL')).return_value
        self.enterContext(patch.object(mis_prestamos, 'RepositorioImplementosMySQL', return_value=repo))
        repo.listar_implementos.return_value = [
            {'id_implemento': 8, 'nombre_implemento': 'Balón N. 1', 'nombre_categoria': 'Material',
             'disponibilidad': 'Disponible'},
            {'id_implemento': 9, 'nombre_implemento': 'Balón N. 2', 'nombre_categoria': 'Material',
             'disponibilidad': 'Disponible'},
        ]
        repo.listar_disponibles.return_value = repo.listar_implementos.return_value
        repo.listar_prestamos.return_value = [
            {'id_operacion': 12, 'estado_prestamo': 'PENDIENTE', 'total_implementos': 2},
        ]
        repo.reservas_elegibles.return_value = []
        repo.solicitar.return_value = 12
        dia = (datetime.now(calendario.ZONA_PERU).date() + timedelta(days=1)).isoformat()
        inicio_turno, fin_turno = f'{dia}T08:00', f'{dia}T09:00'

        async def solicitar_y_cancelar():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/solicitar-prestamo')
            with pagina:
                modalidad = control(pagina, ui.select, label='Modalidad')
                motivo = control(pagina, ui.textarea, label='Motivo del préstamo sin reserva *')
                self.assertEqual(modalidad.value, 'Con reserva')
                self.assertFalse(motivo.visible)
                modalidad.set_value('Sin reserva')
                self.assertTrue(motivo.visible)
                emitir(control(pagina, ui.button, icon='add'), 'click')
                emitir(control(pagina, ui.button, icon='add'), 'click')
            await navegador.should_see(content='2 seleccionados')
            with pagina:
                self.assertFalse(control(pagina, ui.button, icon='add').enabled)
                control(pagina, ui.input, label='Fecha y hora de recojo').set_value(inicio_turno)
                control(pagina, ui.input, label='Devolución prevista').set_value(fin_turno)
                motivo.set_value('  ')
                emitir(control(pagina, ui.button, label='Solicitar préstamo'), 'click')
                self.assertFalse(any(isinstance(e, ui.dialog) and e.value for e in pagina.elements.values()))
                repo.solicitar.assert_not_called()
                motivo.set_value('  El polideportivo está en mantenimiento.  ')
                emitir(control(pagina, ui.button, label='Solicitar préstamo'), 'click')
                await navegador.should_see(content='El polideportivo está en mantenimiento.')
                emitir(control(pagina, ui.button, label='Confirmar solicitud'), 'click')
            await navegador.should_see(content='Cancelar solicitud', retries=25)
            pagina = navegador.client
            with pagina:
                tabla = control(pagina, ui.table)
                emitir(tabla, 'selection', {'added': True, 'rows': [tabla.rows[0]], 'keys': [12]})
                emitir(control(pagina, ui.button, label='Cancelar solicitud'), 'click')
                emitir(control(pagina, ui.button, label='Confirmar cancelación'), 'click')
            async with asyncio.timeout(3):
                while tabla.rows:
                    await asyncio.sleep(0.05)

        self.runner.run(solicitar_y_cancelar())
        repo.solicitar.assert_called_once_with(actor=1, grupos={('Material', 'Balón'): 2},
                                              inicio=inicio_turno, fin=fin_turno, id_reserva=None,
                                              observacion='El polideportivo está en mantenimiento.')
        repo.listar_prestamos.assert_called_once_with(1)
        repo.cambiar_estado.assert_called_once_with(actor=1, operacion=12, destino='CANCELADO')

    def test_solicitud_abierta_desde_reserva_preselecciona_turno_y_guarda_vinculo(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        dia = (datetime.now(calendario.ZONA_PERU).date() + timedelta(days=2)).isoformat()
        registro = {
            'id_reserva': 37, 'codigo_reserva': 'RES-ABC123ABC123', 'fecha_uso': dia,
            'estado_reserva': 'RESERVADA', 'hora_inicio': '08:00', 'hora_fin': '09:00',
        }
        self.enterContext(patch.object(mis_reservas.RepositorioReservasMySQL, 'listar_por_usuario',
                                       return_value=[registro]))
        repo = self.enterContext(patch.object(solicitar_prestamo, 'RepositorioImplementosMySQL')).return_value
        repo.reservas_elegibles.return_value = [registro]
        repo.listar_categorias.return_value = []
        repo.listar_implementos.return_value = repo.listar_disponibles.return_value = [
            {'id_implemento': 8, 'nombre_implemento': 'Balón N. 1', 'nombre_categoria': 'Material',
             'disponibilidad': 'Disponible'},
        ]
        repo.solicitar.return_value = 100
        self.enterContext(patch.object(mis_prestamos.RepositorioImplementosMySQL, 'listar_prestamos', return_value=[]))

        async def solicitar():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/mis-reservas')
            with pagina:
                tabla = control(pagina, ui.table)
                emitir(tabla, 'selection', {'added': True, 'rows': [tabla.rows[0]], 'keys': [37]})
                emitir(control(pagina, ui.button, label='Solicitar implementos'), 'click')
            await navegador.should_see(content='DATOS DEL PRÉSTAMO', retries=25)
            with navegador.client as pagina:
                self.assertEqual(control(pagina, ui.select, label='Reserva vigente').value, 37)
                self.assertEqual(control(pagina, ui.input, label='Fecha y hora de recojo').value, f'{dia}T08:00')
                self.assertEqual(control(pagina, ui.input, label='Devolución prevista').value, f'{dia}T09:00')
                emitir(control(pagina, ui.button, icon='add'), 'click')
                emitir(control(pagina, ui.button, label='Solicitar préstamo'), 'click')
                emitir(control(pagina, ui.button, label='Confirmar solicitud'), 'click')
            await navegador.should_see(content='Ver detalle', retries=25)

        self.runner.run(solicitar())
        repo.reservas_elegibles.assert_called_once_with(1)
        repo.solicitar.assert_called_once_with(actor=1, grupos={('Material', 'Balón'): 1},
                                              inicio=f'{dia}T08:00', fin=f'{dia}T09:00', id_reserva=37, observacion=None)

    def test_agenda_diaria_en_fecha_elegida_y_fin_de_semana(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        hoy = datetime.now(calendario.ZONA_PERU).date()
        lunes = hoy + timedelta(days=7 - hoy.weekday())
        sabado = lunes + timedelta(days=5)
        agenda = {'libres': [{'inicio': '08:00', 'fin': '11:00', 'titulo': 'DEMO V9 - Horarios libres'}],
                  'ocupados': [{'inicio': '11:30', 'fin': '15:00', 'titulo': 'DEMO V9 - Taller UNAB',
                                'tipo': 'TALLER DEPORTIVO'}]}
        diario = self.enterContext(patch.object(inicio_usuario, 'RepositorioProgramacionesMySQL')).return_value
        diario.obtener_agenda.side_effect = lambda dia: agenda if dia == lunes else None
        semanal = self.enterContext(patch.object(calendario, 'RepositorioProgramacionesMySQL')).return_value
        semanal.obtener_agenda_semanal.return_value = {lunes.isoformat(): agenda, sabado.isoformat(): agenda}
        agregar = self.enterContext(patch.object(calendario, 'RegistrarReserva'))
        pagina_inicial = self.pedir('/usuario/calendario', params={'dia': lunes.isoformat()})
        self.assertIn('Taller UNAB', pagina_inicial.text)
        self.assertNotIn('DEMO V9', pagina_inicial.text)
        self.assertEqual(self.pedir('/assets/logo-unab.png').status_code, 200)

        async def usar_agendas():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/inicio')
            await navegador.should_see(content='No hay horarios publicados para esta fecha.')
            with pagina:
                control(pagina, ui.input, label='Fecha de disponibilidad').set_value(lunes.isoformat())
            await navegador.should_see(content='11:30–15:00 · Taller UNAB')
            pagina = await navegador.open('/usuario/calendario?dia=' + lunes.isoformat())
            await navegador.should_see(content='Taller UNAB')
            with pagina:
                for etiqueta, valor in (('Fecha', sabado.isoformat()), ('Hora inicial', '08:00'), ('Hora final', '09:00')):
                    control(pagina, ui.input, label=etiqueta).set_value(valor)
                emitir(control(pagina, ui.button, label='Ver disponibilidad'), 'click')
                self.assertFalse(control(pagina, ui.button, label='Realizar Reserva').enabled)
            await navegador.should_see(content='Las reservas de fin de semana requieren gestión administrativa.')

        self.runner.run(usar_agendas())
        diario.obtener_agenda.assert_any_call(lunes)
        semanal.buscar_horario_reservable.assert_not_called()
        agregar.assert_not_called()

    def test_historial_reserva_solo_detalle_y_comprobante_del_titular(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        repo = self.enterContext(patch.object(mis_reservas, 'RepositorioReservasMySQL')).return_value
        historica = {'id_reserva': 27, 'codigo_reserva': 'RES-HIST', 'fecha_uso': '2026-11-11',
                     'hora_inicio': '09:00', 'hora_fin': '10:00', 'estado_reserva': 'CANCELADA',
                     'nombres': 'Titular', 'apellidos': 'Prueba'}
        vigente = dict(historica, id_reserva=28, codigo_reserva='RES-VIG',
                       fecha_uso=(datetime.now(calendario.ZONA_PERU).date() + timedelta(days=3)).isoformat(),
                       estado_reserva='RESERVADA')
        repo.listar_por_usuario.return_value = [vigente, historica]
        repo.obtener_por_codigo.return_value = historica
        pdf = self.enterContext(patch.object(mis_reservas, 'descargar_comprobante'))

        async def usar_historial():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/mis-reservas')
            with pagina:
                tabla = control(pagina, ui.table)
                self.assertEqual([r['codigo'] for r in tabla.rows], ['RES-VIG'])
                control(pagina, ui.toggle).set_value('Historial')
                self.assertEqual([r['codigo'] for r in tabla.rows], ['RES-HIST'])
                self.assertFalse(control(pagina, ui.button, label='Confirmar asistencia').visible)
                self.assertFalse(control(pagina, ui.button, label='Cancelar reserva').visible)
                emitir(tabla, 'selection', {'added': True, 'rows': [tabla.rows[0]], 'keys': [27]})
                emitir(control(pagina, ui.button, label='Descargar comprobante'), 'click')

        self.runner.run(usar_historial())
        repo.obtener_por_codigo.assert_called_once_with('RES-HIST', id_usuario=1)
        pdf.assert_called_once_with(historica)

    def test_historial_prestamo_devuelto_emite_comprobante_real(self):
        self.assert_redirect(self.retorno(self.iniciar()), '/usuario/registro')
        self.repositorio.usuarios[1]['perfil_completo'] = True
        repo = self.enterContext(patch.object(mis_prestamos, 'RepositorioImplementosMySQL')).return_value
        devuelto = {'id_operacion': 12, 'estado_prestamo': 'DEVUELTO', 'total_implementos': 1}
        detalle = {'id_implemento': 15, 'nombre_categoria': 'Balones', 'nombre_implemento': 'Balón N. 1',
                   'codigo_patrimonial': 'PAT-15', 'movimiento': 'ENTRADA'}
        repo.listar_prestamos.return_value = [devuelto, dict(devuelto, id_operacion=13, estado_prestamo='PENDIENTE')]
        repo.obtener_prestamo.return_value = devuelto
        repo.detalle_prestamo.return_value = [detalle]
        pdf = self.enterContext(patch.object(mis_prestamos, 'descargar_comprobante_prestamo'))

        async def usar_historial():
            navegador = User(self.cliente)
            pagina = await navegador.open('/usuario/mis-prestamos')
            with pagina:
                tabla = control(pagina, ui.table)
                self.assertEqual([r['id_operacion'] for r in tabla.rows], [13])
                control(pagina, ui.toggle).set_value('Historial')
                self.assertEqual([r['id_operacion'] for r in tabla.rows], [12])
                self.assertFalse(control(pagina, ui.button, label='Cancelar solicitud').visible)
                emitir(tabla, 'selection', {'added': True, 'rows': [tabla.rows[0]], 'keys': [12]})
                emitir(control(pagina, ui.button, label='Descargar comprobante'), 'click')

        self.runner.run(usar_historial())
        repo.obtener_prestamo.assert_called_once_with(12, id_usuario=1)
        repo.detalle_prestamo.assert_called_once_with(12, id_usuario=1)
        pdf.assert_called_once_with(devuelto, [detalle])

    def test_asistente_confirma_codigos_en_entrega_y_devolucion(self):
        self.repositorio.usuarios[1] = {
            'id_usuario': 1, 'correo_institucional': CORREO, 'google_sub': SUB,
            'usuario_activo': True, 'perfil_activo': True, 'rol_activo': True,
            'rol': 'ASISTENTE', 'perfil_completo': True,
        }
        self.assert_redirect(self.retorno(self.iniciar()), '/admin/dashboard')
        repo = self.enterContext(patch.object(prestamos_admin, 'RepositorioImplementosMySQL')).return_value
        prestamo = {'id_operacion': 12, 'estado_prestamo': 'PENDIENTE',
                    'fecha_inicio_prevista': '2026-12-10 08:00', 'fecha_devolucion_prevista': '2026-12-10 10:00',
                    'implementos': 1, 'solicitante': 'Usuario Prueba', 'id_reserva': None,
                    'observacion': 'Entrenamiento en un espacio alternativo.'}
        unidad = {'id_implemento': 8, 'nombre_categoria': 'Balones', 'nombre_implemento': 'Balón N. 2',
                  'codigo_patrimonial': 'PAT-8', 'movimiento': 'SALIDA'}
        repo.listar_prestamos.side_effect = lambda: [dict(prestamo)]
        repo.listar_disponibles.return_value = [unidad]
        repo.detalle_prestamo.side_effect = lambda _: (
            [dict(unidad, id_implemento=7, codigo_patrimonial='PAT-7', movimiento=None)]
            if prestamo['estado_prestamo'] == 'PENDIENTE' else [unidad]
        )
        repo.cambiar_estado.side_effect = lambda **datos: prestamo.update(estado_prestamo=datos['destino'])

        async def cambiar_estado():
            navegador = User(self.cliente)
            pagina = await navegador.open('/admin/prestamos')
            tabla = control(pagina, ui.table)
            for accion, select, confirmacion, estado in (
                ('Entregar', 'Códigos a entregar', 'Confirmar entrega', 'ENTREGADO'),
                ('Devolver', 'Códigos recibidos en la devolución', 'Confirmar devolución', 'DEVUELTO'),
            ):
                with pagina:
                    emitir(tabla, 'selection', {'added': True, 'rows': [tabla.rows[0]], 'keys': [12]})
                    emitir(control(pagina, ui.button, label=accion), 'click')
                    if accion == 'Entregar':
                        await navegador.should_see(content='Entrenamiento en un espacio alternativo.')
                    boton = control(pagina, ui.button, label=confirmacion)
                    self.assertFalse(boton.enabled)
                    control(pagina, ui.select, label=select).set_value([8])
                    self.assertTrue(boton.enabled)
                    emitir(boton, 'click')
                async with asyncio.timeout(3):
                    while tabla.rows[0]['estado_prestamo'] != estado:
                        await asyncio.sleep(0.05)

        self.runner.run(cambiar_estado())
        self.assertEqual(
            [(c.kwargs['actor'], c.kwargs['destino'], c.kwargs['unidades'], c.kwargs['administrativo'])
             for c in repo.cambiar_estado.call_args_list],
            [(1, 'ENTREGADO', (8,), True), (1, 'DEVUELTO', (8,), True)],
        )

    def test_el_temporizador_del_servidor_ejecuta_ambos_casos_de_estado(self):
        modulo = 'aplicacion.casos_uso.reservas.actualizar_estados'
        conexion = MagicMock()
        cursor = conexion.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        self.enterContext(patch(modulo + '.obtener_conexion', return_value=conexion))
        repo = self.enterContext(patch(modulo + '.RepositorioReservasMySQL')).return_value
        repo.listar_transiciones_vencidas.return_value = [
            {'codigo_reserva': 'RES-ASISTENCIA', 'nombre_estado': 'RESERVADA'},
            {'codigo_reserva': 'RES-FIN', 'nombre_estado': 'CONFIRMADA'},
        ]

        async def verificar_temporizador():
            timer = inicio.programar_cierre_reservas(0.05)
            try:
                async with asyncio.timeout(3):
                    while cursor.execute.call_count < 2:
                        await asyncio.sleep(0.01)
            finally:
                timer.cancel()
        self.runner.run(verificar_temporizador())
        repo.marcar_inasistencia.assert_called_with(codigo_reserva='RES-ASISTENCIA')
        repo.finalizar_reserva.assert_called_with(codigo_reserva='RES-FIN')
        self.assertIn('RELEASE_LOCK', cursor.execute.call_args.args[0])
