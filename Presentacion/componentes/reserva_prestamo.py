"""Modalidad y selector de reservas para formularios de préstamo."""

from datetime import date, datetime

from mysql.connector import Error as ErrorMySQL
from nicegui import ui

from dominio.reglas.implementos import (
    MAX_OBSERVACION_PRESTAMO, fechas_sugeridas_prestamo, validar_motivo_sin_reserva,
)
from dominio.reglas.reservas import ZONA_PERU


CON_RESERVA = 'Con reserva'
SIN_RESERVA = 'Sin reserva'


class SelectorReservaPrestamo:
    def __init__(self, repo):
        self.repo = repo
        self.reservas = {}
        with ui.row().classes('w-full items-start gap-3 flex-wrap'):
            self.modalidad = ui.select([CON_RESERVA, SIN_RESERVA], value=CON_RESERVA,
                                      label='Modalidad').props('outlined dense').classes('min-w-36')
            self.turno = ui.select({}, label='Reserva vigente').props('outlined dense').classes('flex-1 min-w-64')
        self.aviso = ui.label().classes('text-xs text-slate-600')
        self.motivo = ui.textarea('Motivo del préstamo sin reserva *',
                                  placeholder='Ejemplo: el polideportivo está en mantenimiento') \
            .props(f'outlined rows=2 maxlength={MAX_OBSERVACION_PRESTAMO}').classes('w-full')
        self.modalidad.on_value_change(self._actualizar)
        self._actualizar()

    def _actualizar(self):
        vinculada = self.modalidad.value == CON_RESERVA
        self.turno.set_visibility(vinculada)
        self.aviso.set_visibility(vinculada and not self.reservas)
        self.motivo.set_visibility(not vinculada)

    def cargar(self, titular, preseleccion=None):
        mensaje = 'No hay reservas elegibles. Puedes elegir Sin reserva e indicar el motivo.'
        try:
            filas = self.repo.reservas_elegibles(titular) if titular is not None else []
        except ErrorMySQL:
            filas = []
            mensaje = 'No se pudieron consultar las reservas elegibles.'
        self.reservas = {r['id_reserva']: r for r in filas}
        self.aviso.set_text(mensaje if titular is not None else 'Selecciona primero al usuario solicitante.')
        self.turno.set_options({
            clave: (f"{r['codigo_reserva']} · {date.fromisoformat(r['fecha_uso']):%d/%m/%Y} · "
                    f"{r['hora_inicio']}–{r['hora_fin']} · {r['estado_reserva']}")
            for clave, r in self.reservas.items()
        }, value=preseleccion if preseleccion in self.reservas else None)
        if preseleccion is not None:
            self.modalidad.set_value(CON_RESERVA)
        self._actualizar()

    def conectar_fechas(self, recojo, devolucion):
        def completar():
            if (reserva := self.elegida()) is not None:
                ahora = datetime.now(ZONA_PERU).replace(tzinfo=None)
                inicio, fin = fechas_sugeridas_prestamo(reserva, ahora)
                recojo.set_value(inicio.isoformat(timespec='minutes') if inicio < fin else None)
                devolucion.set_value(fin.isoformat(timespec='minutes') if inicio < fin else None)
        self.turno.on_value_change(completar)
        self.modalidad.on_value_change(completar)
        completar()

    def elegida(self):
        return self.reservas.get(self.turno.value) if self.modalidad.value == CON_RESERVA else None

    def id_reserva(self):
        if self.modalidad.value == SIN_RESERVA:
            return None
        reserva = self.elegida()
        if reserva is None:
            raise ValueError('Selecciona una reserva vigente o elige Sin reserva.')
        return reserva['id_reserva']

    def motivo_sin_reserva(self):
        if self.modalidad.value == SIN_RESERVA:
            return validar_motivo_sin_reserva(self.motivo.value)
        return None

    @staticmethod
    def descripcion(registro):
        if not registro.get('codigo_reserva'):
            return SIN_RESERVA
        return (f"{registro['codigo_reserva']} · {registro['fecha_reserva']} · "
                f"{registro['hora_inicio_reserva']}–{registro['hora_fin_reserva']} · {registro['estado_reserva']}")
