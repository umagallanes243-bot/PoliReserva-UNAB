"""Exportaciones CSV y PDF para reportes y comprobantes."""

from collections import defaultdict
from csv import writer
from io import StringIO, BytesIO
from xml.sax.saxutils import escape

from nicegui import ui

from dominio.reglas.implementos import agrupar_unidades, nombre_tipo_implemento


def preparar_csv(columnas, filas):
    """CSV con encabezados legibles y valores seguros para hojas de cálculo."""
    contenido = StringIO()
    csv = writer(contenido)
    csv.writerow([etiqueta for _, etiqueta in columnas])
    for fila in filas:
        celdas = []
        for clave, _ in columnas:
            valor = str(fila.get(clave, '') if fila.get(clave) is not None else '')
            if valor.startswith(('=', '+', '-', '@', '\t', '\r')):
                valor = "'" + valor
            celdas.append(valor)
        csv.writerow(celdas)
    return contenido.getvalue().encode('utf-8-sig')


def preparar_pdf(titulo, columnas, filas, periodo_consultado, *, comprobante=False):
    """Genera un PDF del reporte consultado, con tabla y paginación."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer

    salida = BytesIO()
    doc = SimpleDocTemplate(
        salida, pagesize=landscape(A4),
        leftMargin=30, rightMargin=30, topMargin=34, bottomMargin=32,
    )
    titulo_style = ParagraphStyle(
        'titulo_reporte', fontName='Helvetica-Bold', fontSize=15,
        leading=19, textColor=colors.HexColor('#09234B'), spaceAfter=8,
    )
    subtitulo_style = ParagraphStyle(
        'subtitulo_reporte', fontName='Helvetica', fontSize=9,
        leading=13, textColor=colors.HexColor('#475569'),
    )
    encabezado_style = ParagraphStyle(
        'encabezado_reporte', fontName='Helvetica-Bold', fontSize=8,
        leading=10, textColor=colors.white,
    )
    celda_style = ParagraphStyle(
        'celda_reporte', fontName='Helvetica', fontSize=8,
        leading=11, textColor=colors.HexColor('#1F2937'),
    )

    encabezado = 'COMPROBANTE' if comprobante else 'REPORTES'
    elementos = [
        Paragraph(f'POLIRESERVA UNAB | {encabezado}', titulo_style),
        Paragraph(escape(str(titulo)), subtitulo_style),
    ]
    if comprobante:
        if periodo_consultado:
            elementos.append(Paragraph(escape(str(periodo_consultado)), subtitulo_style))
    else:
        elementos.extend([
            Paragraph('Período: ' + escape(str(periodo_consultado or 'Todo el historial')), subtitulo_style),
            Paragraph(f'Registros: {len(filas)}', subtitulo_style),
        ])
    elementos.append(Spacer(1, 14))
    datos = [[Paragraph(escape(etiqueta), encabezado_style)
              for _, etiqueta in columnas]]
    for fila in filas:
        datos.append([
            Paragraph(escape(str(fila.get(clave) if fila.get(clave) is not None else '')),
                      celda_style)
            for clave, _ in columnas
        ])

    ancho = landscape(A4)[0] - doc.leftMargin - doc.rightMargin
    tabla = Table(datos, colWidths=[ancho / len(columnas)] * len(columnas),
                  repeatRows=1, hAlign='LEFT')
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#164875')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#F3F5F8')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#09234B')),
    ]))
    elementos.append(tabla)

    def pie_pagina(canvas, documento):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#64748B'))
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(
            landscape(A4)[0] - 30, 18, f'Página {documento.page}'
        )
        canvas.restoreState()

    doc.build(elementos, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    return salida.getvalue()


def descargar_comprobante(reserva):
    columnas = [('codigo_reserva', 'CÓDIGO'), ('titular', 'TITULAR'), ('fecha_uso', 'FECHA'),
                ('hora_inicio', 'INICIO'), ('hora_fin', 'FIN'), ('estado_reserva', 'ESTADO')]
    codigo = reserva['codigo_reserva']
    titular = reserva.get('solicitante') or ' '.join(
        str(reserva.get(campo) or '') for campo in ('nombres', 'apellidos')
    ).strip()
    try:
        archivo = preparar_pdf(f'Reserva {codigo}', columnas, [dict(reserva, titular=titular)],
                               '', comprobante=True)
    except ImportError:
        ui.notify('La exportación PDF requiere ReportLab.', type='warning')
        return
    ui.download.content(archivo, f'{codigo}.pdf')


def descargar_comprobante_prestamo(prestamo, detalles):
    operacion = prestamo['id_operacion']
    estado = prestamo.get('estado_prestamo') or prestamo.get('nombre_estado') or ''
    entregados = defaultdict(list)
    for unidad in detalles:
        if unidad.get('movimiento') in ('ENTRADA', 'SALIDA'):
            tipo = nombre_tipo_implemento(unidad['nombre_implemento'])
            entregados[unidad['nombre_categoria'], tipo].append(unidad['codigo_patrimonial'])
    filas = [{'categoria': categoria, 'material': nombre, 'cantidad': cantidad,
              'unidades': ', '.join(sorted(entregados[categoria, nombre]))}
             for (categoria, nombre), cantidad in sorted(agrupar_unidades(detalles).items())]
    columnas = [('categoria', 'CATEGORÍA'), ('material', 'MATERIAL SOLICITADO'),
                ('cantidad', 'CANTIDAD'), ('unidades', 'UNIDADES ENTREGADAS')]
    resumen = ' · '.join(str(dato) for dato in (
        prestamo.get('solicitante'), estado, prestamo.get('fecha_solicitud'),
        prestamo.get('vinculo') or 'Sin reserva',
    ) if dato)
    try:
        archivo = preparar_pdf(f'Préstamo N.º {operacion}', columnas, filas, resumen, comprobante=True)
    except ImportError:
        ui.notify('La exportación PDF requiere ReportLab.', type='warning')
        return
    ui.download.content(archivo, f'prestamo-{operacion}.pdf')
