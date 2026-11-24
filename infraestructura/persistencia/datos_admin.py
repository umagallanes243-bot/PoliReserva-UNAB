# infraestructura/persistencia/datos_admin.py


datos_reservas = [
    {'id': 1, 'documento': '60936636', 'cod_estudiante': '20231045', 'solicitante': 'Charly Dorca', 'cod_reserva': 'RES-001', 'fecha': '04/11/2026', 'estado': 'Confirmada'},
    {'id': 2, 'documento': '12345678', 'cod_estudiante': '20231089', 'solicitante': 'Ulices Magallanes', 'cod_reserva': 'RES-002', 'fecha': '04/11/2026', 'estado': 'Pendiente'},
    {'id': 3, 'documento': '87654321', 'cod_estudiante': '20231102', 'solicitante': 'Rodrigo Cadillo', 'cod_reserva': 'RES-003', 'fecha': '03/11/2026', 'estado': 'Confirmada'},
    {'id': 4, 'documento': '14725836', 'cod_estudiante': '20231150', 'solicitante': 'Lorenzo Oyola', 'cod_reserva': 'RES-004', 'fecha': '03/11/2026', 'estado': 'Cancelada'},
]

datos_talleres = [
    {'id': 1, 'nombre': 'Taller de Futbol', 'tipo': 'Deporte', 'fecha': '13/11/2026', 'horario': '11:00AM', 'estado': 'CONFIRMADO'},
    {'id': 2, 'nombre': 'Taller de Danza', 'tipo': 'Arte y Cultura', 'fecha': '13/11/2026', 'horario': '12:00PM', 'estado': 'CONFIRMADO'},
    {'id': 3, 'nombre': 'Taller de Danza', 'tipo': 'Arte y Cultura', 'fecha': '13/11/2026', 'horario': '13:00PM', 'estado': 'CONFIRMADO'},
    {'id': 4, 'nombre': 'Taller de Voley', 'tipo': 'Deporte', 'fecha': '13/11/2026', 'horario': '14:00PM', 'estado': 'CONFIRMADO'},
]

datos_eventos = [
    {'id': 1, 'nombre': 'Concurso Danza', 'tipo': 'Recreación', 'escuela': 'Ing. Sistemas', 'fecha': '13/11/2026', 'horario': '11:00AM', 'estado': 'CONFIRMADO'},
    {'id': 2, 'nombre': 'Interciclos', 'tipo': 'Recreación y Bienestar', 'escuela': 'Todas las escuelas', 'fecha': '13/11/2026', 'horario': '12:00PM', 'estado': 'CONFIRMADO'},
    {'id': 3, 'nombre': 'Gymkana', 'tipo': 'Recreación', 'escuela': 'Administración', 'fecha': '13/11/2026', 'horario': '13:00PM', 'estado': 'CONFIRMADO'},
    {'id': 4, 'nombre': 'Premiacion Deportiva', 'tipo': 'Ceremonias', 'escuela': 'General', 'fecha': '13/11/2026', 'horario': '14:00PM', 'estado': 'CONFIRMADO'},
]

datos_inventario = [
    {'id': 1, 'nombre': 'Balón de fútbol', 'categoria': 'Deporte', 'cantidad': 15, 'descripcion': 'Balones de entrenamiento'},
    {'id': 2, 'nombre': 'Balón de básquet', 'categoria': 'Deporte', 'cantidad': 12, 'descripcion': 'Para competencia'},
    {'id': 3, 'nombre': 'Balón de vóley', 'categoria': 'Deporte', 'cantidad': 10, 'descripcion': 'Oficiales Mikasa'},
    {'id': 4, 'nombre': 'Red de vóley', 'categoria': 'Deporte', 'cantidad': 4, 'descripcion': 'Malla con cable de acero'},
    {'id': 5, 'nombre': 'Conos', 'categoria': 'Deporte', 'cantidad': 18, 'descripcion': 'Conos de PVC'},
    {'id': 6, 'nombre': 'Camisetas', 'categoria': 'Deporte', 'cantidad': 20, 'descripcion': 'Color verde, talla L'},
]