"""Indicador del límite semanal de reservas."""

from nicegui import ui

from dominio.reglas.reservas import LIMITE_SEMANAL_MINUTOS, minutos_disponibles


def _duracion(minutos):
    horas, resto = divmod(minutos, 60)
    return f'{horas} h {resto} min' if horas and resto else f'{horas} h' if horas else f'{resto} min'


class IndicadorCupoSemanal:
    def __init__(self):
        with ui.column().classes('w-full max-w-sm gap-1'):
            ui.label('Tiempo de reserva semanal').classes('text-xs font-semibold text-[#09234B]')
            self.texto = ui.label().classes('text-xs text-slate-600')
            self.barra = ui.linear_progress(value=0).props('rounded size=5px')
        self.actualizar(None)

    def actualizar(self, segundos, *, mensaje='No se pudo consultar el saldo semanal.'):
        self.barra.set_visibility(segundos is not None)
        if segundos is None:
            self.texto.set_text(mensaje)
            return
        usados = (segundos + 59) // 60
        limite = LIMITE_SEMANAL_MINUTOS
        self.texto.set_text(f'Límite {_duracion(limite)} · Utilizado {_duracion(usados)} · '
                            f'Disponible {_duracion(minutos_disponibles(segundos))}')
        self.barra.set_value(min(1, segundos / (limite * 60)))
