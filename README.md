\# PoliReserva UNAB



\## Descripción del proyecto



PoliReserva UNAB es un sistema web desarrollado para gestionar las reservas, programaciones y préstamos de implementos deportivos del polideportivo de la Universidad Nacional de Barranca.



El sistema busca optimizar los procesos administrativos, evitar conflictos de horarios, facilitar la consulta de disponibilidad y mejorar el control de los recursos deportivos.



\## Tecnologías utilizadas



\- Python 3.13

\- NiceGUI

\- MySQL

\- MySQL Connector/Python

\- Google Cloud

\- OAuth 2.0 y OpenID Connect

\- HTML, CSS y JavaScript

\- Visual Studio Code



\## Funcionalidades principales



\- Autenticación mediante correo institucional.

\- Consulta de disponibilidad del polideportivo.

\- Registro y cancelación de reservas.

\- Control de asistencia.

\- Control del límite semanal de reservas.

\- Gestión de períodos académicos.

\- Programación de talleres, eventos y mantenimientos.

\- Gestión de inventario deportivo.

\- Solicitudes de préstamos con reserva y sin reserva.

\- Control de entregas y devoluciones.

\- Dashboard administrativo.

\- Generación de reportes y comprobantes.

\- Auditoría de operaciones.



\## Arquitectura del sistema



El proyecto utiliza una arquitectura por capas que separa las responsabilidades de presentación, aplicación, dominio e infraestructura.



| Directorio | Responsabilidad |

|---|---|

| Presentacion | Interfaces web y componentes visuales. |

| aplicacion | Casos de uso y procesos del sistema. |

| dominio | Reglas y validaciones de negocio. |

| infraestructura | Persistencia, conexión MySQL y servicios externos. |

| sql | Scripts de base de datos. |

| tests | Pruebas del sistema. |



\## Roles del sistema



\- Usuario: estudiantes y docentes.

\- Asistente: gestión operativa del polideportivo.

\- Administrador: supervisión y administración del sistema.



\## Ejecución del proyecto



El sistema requiere Python, MySQL y una configuración autorizada de autenticación mediante Google.



Una vez instaladas las dependencias, configurada la base de datos y establecidas las variables de entorno necesarias, ejecutar:



```bash

python inicio.py

```



Dirección de acceso local:



http://localhost:8080



Por motivos de seguridad, las credenciales de conexión, las claves de autenticación y los datos privados no se incluyen en el repositorio.



\## Contexto académico



Proyecto desarrollado en el marco del curso de Ingeniería de Requerimientos.



Escuela Profesional de Ingeniería de Sistemas e Informática.



Universidad Nacional de Barranca — 2026.

