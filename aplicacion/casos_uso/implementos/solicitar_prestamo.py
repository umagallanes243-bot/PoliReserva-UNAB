"""Solicita un préstamo propio o registra una solicitud administrativa para un usuario."""

from datetime import datetime

from infraestructura.persistencia.implementos_mysql import ErrorImplemento, RepositorioImplementosMySQL


class SolicitarPrestamo:
    def __init__(self, repositorio: RepositorioImplementosMySQL | None = None):
        self.repositorio = repositorio if repositorio is not None else RepositorioImplementosMySQL()

    def ejecutar(self, *, id_usuario_sesion: int, inicio: datetime | str, fin: datetime | str,
                 grupos: dict[tuple[str, str], int], id_reserva: int | None = None,
                 observacion: str | None = None) -> int:
        return self.repositorio.solicitar(
            actor=id_usuario_sesion, inicio=inicio, fin=fin, grupos=grupos,
            id_reserva=id_reserva, observacion=observacion,
        )

    def ejecutar_para_usuario(
        self, *, id_usuario_sesion: int, id_usuario: int, unidades: tuple[int, ...],
        inicio: datetime | str, fin: datetime | str, observacion: str | None = None,
        id_reserva: int | None = None,
    ) -> int:
        if id_usuario is None:
            raise ErrorImplemento('Selecciona un usuario.')
        return self.repositorio.solicitar(
            actor=id_usuario_sesion, id_usuario=id_usuario, unidades=unidades,
            inicio=inicio, fin=fin, observacion=observacion, id_reserva=id_reserva,
        )
