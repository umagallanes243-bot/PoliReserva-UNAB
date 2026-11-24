"""Consultas y agregaciones de informes a partir de los repositorios V9."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from dominio.reglas.agenda import (
    TIPOS_ACTIVIDAD, a_minutos, hhmm, intervalo_jornada, restar_intervalos, unir_intervalos,
)
from dominio.reglas.implementos import devolucion_vencida, nombre_tipo_implemento
from dominio.reglas.periodos import MESES, sumar_meses
from dominio.reglas.reservas import (
    APERTURA, CIERRE, ESTADOS_CONSUMEN_CUPO, ESTADOS_RESERVA, ZONA_PERU,
    acciones_reserva, inicio_semana, minutos_disponibles,
)
from infraestructura.persistencia.implementos_mysql import RepositorioImplementosMySQL
from infraestructura.persistencia.programaciones_mysql import RepositorioProgramacionesMySQL
from infraestructura.persistencia.reservas_mysql import RepositorioReservasMySQL


DIAS = ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo')


def _en_rango(valor, desde, hasta):
    dia = date.fromisoformat(str(valor)[:10])
    return (desde is None or dia >= desde) and (hasta is None or dia <= hasta)


def _contar(filas, campos, total):
    grupos = Counter(tuple((f.get(k) or '—') for k in campos) for f in filas)
    return [dict(zip(campos, claves), **{total: cantidad}) for claves, cantidad in grupos.most_common()]


def _capacidad_diaria(horarios):
    agendas = defaultdict(lambda: ([], []))
    for horario in horarios:
        libres, bloqueados = agendas[horario['fecha_uso']]
        intervalo = intervalo_jornada(horario['hora_inicio'], horario['hora_fin'])
        if intervalo:
            destino = libres if horario['nombre_tipo'] == 'LIBRE' and horario['permite_reserva'] else bloqueados
            destino.append(intervalo)
    return {dia: [tramo for a, b in unir_intervalos(libres) for tramo in restar_intervalos(a, b, bloqueados)]
            for dia, (libres, bloqueados) in agendas.items()}


def _minutos_usados(reservas, capacidad, desde_ahora=None):
    por_fecha = defaultdict(list)
    hoy = desde_ahora.date().isoformat() if desde_ahora else None
    for r in reservas:
        fecha = r['fecha_uso']
        intervalo = intervalo_jornada(r['hora_inicio'], r['hora_fin'])
        if not intervalo or fecha not in capacidad or (hoy and fecha < hoy):
            continue
        inicio, fin = intervalo
        if hoy and fecha == hoy:
            inicio = max(inicio, desde_ahora.hour * 60 + desde_ahora.minute)
        if inicio < fin:
            por_fecha[fecha].append((inicio, fin))
    usadas = {dia: unir_intervalos(intervalos) for dia, intervalos in por_fecha.items()}
    return {dia: sum(max(0, min(b, fin) - max(a, inicio))
                     for a, b in capacidad[dia] for inicio, fin in intervalos)
            for dia, intervalos in usadas.items()}


def _minutos_habilitados(intervalos):
    return sum(b - a for a, b in intervalos)


def minutos_ocupacion(reservas_finalizadas, horarios):
    """Minutos habilitados y usados por fecha en el único polideportivo."""
    capacidad = _capacidad_diaria(horarios)
    usadas = _minutos_usados(reservas_finalizadas, capacidad)
    return [(dia, _minutos_habilitados(intervalos), usadas.get(dia, 0))
            for dia, intervalos in sorted(capacidad.items())]


def _ocupacion(reservas, desde, hasta):
    horarios = RepositorioProgramacionesMySQL().listar_horarios(desde, hasta)
    return [{'fecha': dia, 'horas_habilitadas': round(capacidad / 60, 2),
             'horas_utilizadas': round(uso / 60, 2),
             'porcentaje': round(uso * 100 / capacidad, 2) if capacidad else 0}
            for dia, capacidad, uso in minutos_ocupacion(reservas, horarios)]


def _acciones(fila, ahora):
    return acciones_reserva(fila['estado_reserva'], fila['fecha_uso'], fila['hora_inicio'], fila['hora_fin'], ahora)


def _programaciones_por_tipo(horarios):
    return Counter(tipo for _, tipo in {
        (h['id_programacion'], h['nombre_tipo']) for h in horarios if h['nombre_tipo'] in TIPOS_ACTIVIDAD
    })


def datos_dashboard(desde, hasta, ahora):
    """Tres lecturas del período. Los indicadores actuales se consultan aparte."""
    reservas = RepositorioReservasMySQL().listar_resumen(desde, hasta)
    horarios = RepositorioProgramacionesMySQL().listar_horarios(desde, hasta)
    capacidad = _capacidad_diaria(horarios)
    habilitados = sum(map(_minutos_habilitados, capacidad.values()))
    usados = sum(_minutos_usados((r for r in reservas if r['estado_reserva'] == 'FINALIZADA'), capacidad).values())
    vigentes = [r for r in reservas if r['bloquea_horario'] and _acciones(r, ahora).vigente]
    futuros = sum(_minutos_usados(vigentes, capacidad, desde_ahora=ahora).values())
    estadisticas = {
        'total': len(reservas), 'usuarios': len({r['id_usuario'] for r in reservas}), 'vigentes': len(vigentes),
        'minutos_habilitados': habilitados, 'minutos_utilizados': usados, 'minutos_futuros': futuros,
        'ocupacion': round(usados * 100 / habilitados, 1) if habilitados else None,
    }
    prestamos = RepositorioImplementosMySQL().resumen_solicitudes(desde, hasta)
    return reservas, estadisticas, _programaciones_por_tipo(horarios), prestamos


def datos_operativos_dashboard(ahora):
    """Pendientes e inventario al momento de la consulta, sin filtro histórico."""
    repo = RepositorioImplementosMySQL()
    operacion = repo.resumen_prestamos_activos(ahora)
    hoy = ahora.date()
    reservas = RepositorioReservasMySQL().listar_resumen(hoy, hoy, estado='RESERVADA')
    operacion['por_confirmar'] = sum(r['bloquea_horario'] and _acciones(r, ahora).confirmar for r in reservas)
    return repo.resumen_inventario(), operacion


def tendencia_reservas(filas, desde, hasta, periodo):
    """Serie de todos los estados por fecha de uso y con granularidad acorde al rango."""
    if not filas:
        return [], []
    fechas = [date.fromisoformat(f['fecha_uso']) for f in filas]
    desde, hasta = desde or min(fechas), hasta or max(fechas)
    dias = (hasta - desde).days + 1
    if dias == 1:
        horas = [a_minutos(f['hora_inicio']) for f in filas]
        tramos = list(range(APERTURA, CIERRE, 120))
        conteos = Counter(max(0, min(len(tramos) - 1, (h - APERTURA) // 120)) for h in horas if h is not None)
        return ([f'{hhmm(h)}–{hhmm(min(h + 120, CIERRE))}' for h in tramos],
                [conteos[i] for i in range(len(tramos))])
    if dias > 1096 and periodo == 'Todo el historial':
        conteos = Counter(d.year for d in fechas)
        anios = range(desde.year, hasta.year + 1)
        return [str(y) for y in anios], [conteos[y] for y in anios]
    if periodo in ('Año', 'Período académico') or dias > 92:
        meses = (hasta.year - desde.year) * 12 + hasta.month - desde.month + 1
        inicios = [sumar_meses(desde.replace(day=1), i) for i in range(meses)]
        conteos = Counter(d.replace(day=1) for d in fechas)
        etiquetas = [f'{MESES[d.month - 1][:3]} {str(d.year)[2:]}' for d in inicios]
        return etiquetas, [conteos[d] for d in inicios]
    if dias > 14 or periodo == 'Mes':
        lunes = inicio_semana(desde)
        semanas = (hasta - lunes).days // 7 + 1
        inicios = [lunes + timedelta(weeks=i) for i in range(semanas)]
        conteos = Counter(inicio_semana(d) for d in fechas)
        return [max(d, desde).strftime('%d/%m') for d in inicios], [conteos[d] for d in inicios]
    inicios = [desde + timedelta(days=i) for i in range(dias)]
    conteos = Counter(fechas)
    return [d.strftime('%d/%m') for d in inicios], [conteos[d] for d in inicios]


def _cupos(filas):
    grupos = {}
    for f in filas:
        lunes = inicio_semana(date.fromisoformat(f['fecha']))
        clave = lunes, f['id_usuario']
        grupo = grupos.setdefault(clave, dict(
            semana=f'{lunes:%d/%m/%Y} – {lunes + timedelta(days=6):%d/%m/%Y}',
            codigo=f['codigo'], usuario=f['usuario'], reservas=0, segundos=0,
        ))
        grupo['reservas'] += 1
        if f['estado'] in ESTADOS_CONSUMEN_CUPO:
            grupo['segundos'] += f['duracion_segundos']
    return [dict(g, minutos=(g['segundos'] + 59) // 60, saldo=minutos_disponibles(g['segundos']))
            for _, g in sorted(grupos.items())]


def reporte_reservas(codigo, desde, hasta, criterio):
    if codigo == 'cupos':
        desde = inicio_semana(desde) if desde else None
        hasta = inicio_semana(hasta) + timedelta(days=6) if hasta else None
    filas = RepositorioReservasMySQL().listar_administracion(desde, hasta)
    for fila in filas:
        fila.update(fecha=fila['fecha_uso'], codigo=fila['codigo_institucional'],
                    usuario=' '.join(x for x in (fila['nombres'], fila['apellidos']) if x),
                    horario=f"{fila['hora_inicio']} – {fila['hora_fin']}", estado=fila['estado_reserva'])
    if codigo == 'historial':
        return [f for f in filas if f['codigo'] and f['codigo'].casefold() == criterio.casefold()]
    if codigo == 'cupos':
        return _cupos(filas)
    if codigo == 'estados':
        estados = Counter(f['estado'] for f in filas)
        return [dict(estado=e.capitalize(), reservas=estados[e]) for e in ESTADOS_RESERVA] if filas else []
    if codigo == 'por_fecha':
        conteos = Counter(f['fecha'] for f in filas)
        return [dict(fecha=d, reservas=n) for d, n in sorted(conteos.items())]
    if codigo == 'tipo_usuario':
        return _contar(filas, ('tipo_usuario',), 'reservas')
    if codigo == 'escuelas_reservas':
        return _contar(filas, ('escuela',), 'reservas')
    if codigo == 'horarios':
        return _contar((f for f in filas if f['estado'] != 'CANCELADA'), ('horario',), 'reservas')
    if codigo == 'incidencias':
        grupos = defaultdict(Counter)
        for f in filas:
            if f['estado'] in ('CANCELADA', 'INASISTENCIA'):
                grupos[f['fecha'][:7]][f['estado']] += 1
        return [dict(periodo=mes, cancelaciones=c['CANCELADA'], inasistencias=c['INASISTENCIA'])
                for mes, c in sorted(grupos.items())]

    finalizadas = [f for f in filas if f['estado'] == 'FINALIZADA']
    if codigo == 'ocupacion':
        return _ocupacion(finalizadas, desde, hasta)
    if codigo == 'escuelas':
        return _contar(finalizadas, ('escuela',), 'reservas')
    if codigo == 'usuarios':
        return _contar(finalizadas, ('codigo', 'usuario', 'escuela'), 'reservas')
    if codigo in ('dias', 'ciclos'):
        clave = 'dia' if codigo == 'dias' else 'periodo'
        grupos = defaultdict(list)
        for f in finalizadas:
            grupo = DIAS[date.fromisoformat(f['fecha']).weekday()] if codigo == 'dias' else f['periodo']
            grupos[grupo].append(f)
        claves = (d for d in DIAS if d in grupos) if codigo == 'dias' else sorted(grupos)
        return [{clave: k, 'reservas': len(grupos[k]),
                 'horas': round(sum(a_minutos(f['hora_fin']) - a_minutos(f['hora_inicio'])
                                    for f in grupos[k]) / 60, 2)}
                for k in claves]
    raise ValueError('Selecciona un reporte válido.')


def reporte_programaciones(codigo, desde, hasta, criterio):
    horarios = [h for h in RepositorioProgramacionesMySQL().listar_horarios(desde, hasta)
                if h['nombre_tipo'] in TIPOS_ACTIVIDAD]
    if codigo == 'jornadas':
        return [dict(h, horario=f"{h['hora_inicio']} – {h['hora_fin']}") for h in horarios]
    if codigo == 'horas':
        programaciones = _programaciones_por_tipo(horarios)
        jornadas, minutos = Counter(), Counter()
        for h in horarios:
            tipo = h['nombre_tipo']
            jornadas[tipo] += 1
            minutos[tipo] += a_minutos(h['hora_fin']) - a_minutos(h['hora_inicio'])
        return [dict(tipo=tipo.capitalize(), programaciones=programaciones[tipo],
                     jornadas=jornadas[tipo], horas=round(minutos[tipo] / 60, 2))
                for tipo in TIPOS_ACTIVIDAD if jornadas[tipo]]
    raise ValueError('Selecciona un reporte válido.')


def reporte_implementos(codigo, desde, hasta, criterio):
    repo = RepositorioImplementosMySQL()
    if codigo == 'modalidades':
        prestamos = repo.listar_prestamos(desde=desde, hasta=hasta)
        resultados = []
        for modalidad in ('Con reserva', 'Sin reserva'):
            filas = [p for p in prestamos if p['modalidad'] == modalidad]
            resultados.append(dict(modalidad=modalidad, operaciones=len(filas),
                                   reservas=len({p['id_reserva'] for p in filas if p['id_reserva'] is not None}),
                                   solicitadas=sum(p['total_implementos'] for p in filas),
                                   entregadas=sum(p['unidades_entregadas'] for p in filas)))
        return resultados
    if codigo == 'por_reserva':
        grupos = defaultdict(Counter)
        operaciones = defaultdict(set)
        for unidad in repo.unidades_prestamos(desde, hasta, solo_asociados=True):
            clave = (unidad['codigo_reserva'], unidad['nombre_categoria'],
                     nombre_tipo_implemento(unidad['nombre_implemento']))
            grupos[clave]['solicitadas'] += 1
            grupos[clave]['entregadas'] += unidad['entregada']
            operaciones[clave].add(unidad['id_operacion'])
        return [dict(reserva=reserva, categoria=categoria, material=material, **grupos[reserva, categoria, material],
                     operaciones=len(operaciones[reserva, categoria, material]))
                for reserva, categoria, material in sorted(grupos)]
    if codigo == 'inventario':
        grupos = defaultdict(Counter)
        for fila in repo.listar_implementos():
            clave = fila['nombre_categoria'], nombre_tipo_implemento(fila['nombre_implemento'])
            grupos[clave][fila['disponibilidad']] += 1
        return [dict(categoria=categoria, implemento=nombre, total=sum(c.values()), disponibles=c['Disponible'],
                     prestadas=c['Prestado'], no_habilitadas=c['No disponible'])
                for (categoria, nombre), c in sorted(grupos.items())]
    if codigo == 'solicitados':
        filas = (dict(u, implemento=nombre_tipo_implemento(u['nombre_implemento']), categoria=u['nombre_categoria'])
                 for u in repo.unidades_prestamos(desde, hasta))
        return _contar(filas, ('implemento', 'categoria'), 'solicitadas')
    if codigo == 'pendientes':
        return repo.listar_prestamos(desde=desde, hasta=hasta, estado='PENDIENTE')
    if codigo == 'atrasos':
        ahora = datetime.now(ZONA_PERU)
        resultados = []
        for p in repo.listar_prestamos(estado='ENTREGADO'):
            fecha = p['fecha_devolucion_prevista']
            if devolucion_vencida(fecha, ahora) and _en_rango(fecha, desde, hasta):
                resultados.append(dict(id_operacion=p['id_operacion'], usuario=p['solicitante'],
                                       fecha_prevista=fecha, dias_atraso=(ahora.date() - date.fromisoformat(fecha[:10])).days))
        return resultados
    if codigo in ('escuelas', 'usuarios'):
        vigentes = [dict(p, usuario=p['solicitante'], codigo=p['codigo_institucional'])
                    for p in repo.listar_prestamos(desde=desde, hasta=hasta) if p['nombre_estado'] in ('ENTREGADO', 'DEVUELTO')]
        return _contar(vigentes, ('escuela',) if codigo == 'escuelas' else ('codigo', 'usuario'), 'prestamos')

    movimientos = repo.listar_movimientos(desde, hasta)
    if codigo == 'historial':
        return [dict(m, fecha=m['fecha_movimiento'].isoformat(sep=' ', timespec='minutes'),
                     condicion=m['condicion_fisica'])
                for m in movimientos if m['codigo_patrimonial'].casefold() == criterio.casefold()]
    if codigo == 'implementos':
        salidas = [dict(m, implemento=nombre_tipo_implemento(m['nombre_implemento']), categoria=m['nombre_categoria'])
                   for m in movimientos if m['operacion'] == 'PRESTAMO' and m['movimiento'] == 'SALIDA']
        return _contar(salidas, ('implemento', 'categoria'), 'prestamos')
    if codigo in ('devoluciones', 'movimientos'):
        grupos = defaultdict(Counter)
        operaciones = defaultdict(set)
        for m in movimientos:
            mes = m['fecha_movimiento'].strftime('%Y-%m')
            if codigo == 'devoluciones' and m['operacion'] == 'PRESTAMO':
                grupos[mes][m['movimiento']] += 1
                operaciones[mes, m['movimiento']].add(m['id_operacion'])
            if codigo == 'movimientos' and m['operacion'] in ('ALTA', 'BAJA'):
                grupos[mes][m['operacion']] += 1
        if codigo == 'devoluciones':
            return [dict(periodo=mes, entregados=c['SALIDA'], devueltos=c['ENTRADA'],
                         prestamos_entregados=len(operaciones[mes, 'SALIDA']),
                         prestamos_devueltos=len(operaciones[mes, 'ENTRADA']))
                    for mes, c in sorted(grupos.items())]
        return [dict(periodo=mes, altas=c['ALTA'], bajas=c['BAJA']) for mes, c in sorted(grupos.items())]
    raise ValueError('Selecciona un reporte válido.')
