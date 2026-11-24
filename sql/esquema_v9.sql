-- PoliReserva UNAB V9. Estructura MySQL 8.0 sin datos.
-- Ejecutar con un esquema vacío seleccionado.

CREATE TABLE `tb_categorias_implementos` (
  `id_categoria` int NOT NULL AUTO_INCREMENT,
  `nombre_categoria` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_categoria`),
  UNIQUE KEY `nombre_categoria` (`nombre_categoria`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_escuelas` (
  `id_escuela` int NOT NULL AUTO_INCREMENT,
  `nombre_escuela` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sigla` varchar(15) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_escuela`),
  UNIQUE KEY `nombre_escuela` (`nombre_escuela`),
  UNIQUE KEY `sigla` (`sigla`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_estados_prestamo` (
  `id_estado_prestamo` int NOT NULL AUTO_INCREMENT,
  `nombre_estado` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_estado_prestamo`),
  UNIQUE KEY `nombre_estado` (`nombre_estado`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_estados_reserva` (
  `id_estado_reserva` int NOT NULL AUTO_INCREMENT,
  `nombre_estado` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bloquea_horario` bit(1) NOT NULL DEFAULT b'0',
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_estado_reserva`),
  UNIQUE KEY `nombre_estado` (`nombre_estado`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_periodos_academicos` (
  `id_periodo` int NOT NULL AUTO_INCREMENT,
  `nombre_periodo` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `fecha_inicio` date NOT NULL,
  `fecha_fin` date NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_periodo`),
  UNIQUE KEY `nombre_periodo` (`nombre_periodo`),
  CONSTRAINT `chk_periodo_fechas` CHECK ((`fecha_inicio` <= `fecha_fin`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_roles` (
  `id_rol` int NOT NULL AUTO_INCREMENT,
  `nombre_rol` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `descripcion` varchar(150) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_rol`),
  UNIQUE KEY `nombre_rol` (`nombre_rol`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_tipos_accion` (
  `id_tipo_accion` int NOT NULL AUTO_INCREMENT,
  `nombre_accion` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_tipo_accion`),
  UNIQUE KEY `nombre_accion` (`nombre_accion`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_tipos_movimiento` (
  `id_tipo_movimiento` int NOT NULL AUTO_INCREMENT,
  `nombre_tipo` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `factor_movimiento` smallint NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_tipo_movimiento`),
  UNIQUE KEY `nombre_tipo` (`nombre_tipo`),
  UNIQUE KEY `factor_movimiento` (`factor_movimiento`),
  CONSTRAINT `chk_tipo_movimiento_factor` CHECK ((`factor_movimiento` in (-(1),1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_tipos_operacion` (
  `id_tipo_operacion` int NOT NULL AUTO_INCREMENT,
  `nombre_tipo` varchar(45) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id_tipo_operacion`),
  UNIQUE KEY `nombre_tipo` (`nombre_tipo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_tipos_programacion` (
  `id_tipo_programacion` int NOT NULL AUTO_INCREMENT,
  `nombre_tipo` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `permite_reserva` bit(1) NOT NULL DEFAULT b'0',
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_tipo_programacion`),
  UNIQUE KEY `nombre_tipo` (`nombre_tipo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_tipos_usuarios` (
  `id_tipo_usuario` int NOT NULL AUTO_INCREMENT,
  `nombre_tipo` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_tipo_usuario`),
  UNIQUE KEY `nombre_tipo` (`nombre_tipo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_implementos` (
  `id_implemento` int NOT NULL AUTO_INCREMENT,
  `id_categoria` int NOT NULL,
  `codigo_patrimonial` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `nombre_implemento` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `descripcion` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `apto_prestamo` bit(1) NOT NULL DEFAULT b'1',
  `fecha_registro` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_implemento`),
  UNIQUE KEY `codigo_patrimonial` (`codigo_patrimonial`),
  KEY `fk_implemento_categoria` (`id_categoria`),
  CONSTRAINT `fk_implemento_categoria` FOREIGN KEY (`id_categoria`) REFERENCES `tb_categorias_implementos` (`id_categoria`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_usuarios` (
  `id_usuario` int NOT NULL AUTO_INCREMENT,
  `id_tipo_usuario` int DEFAULT NULL,
  `id_escuela` int DEFAULT NULL,
  `google_sub` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `codigo_institucional` varchar(25) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dni` char(8) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `nombres` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `apellidos` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correo_institucional` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `telefono` varchar(15) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fecha_registro` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `perfil_completo` bit(1) NOT NULL DEFAULT b'0',
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_usuario`),
  UNIQUE KEY `correo_institucional` (`correo_institucional`),
  UNIQUE KEY `google_sub` (`google_sub`),
  UNIQUE KEY `codigo_institucional` (`codigo_institucional`),
  UNIQUE KEY `dni` (`dni`),
  KEY `fk_usuario_tipo` (`id_tipo_usuario`),
  KEY `fk_usuario_escuela` (`id_escuela`),
  CONSTRAINT `fk_usuario_escuela` FOREIGN KEY (`id_escuela`) REFERENCES `tb_escuelas` (`id_escuela`),
  CONSTRAINT `fk_usuario_tipo` FOREIGN KEY (`id_tipo_usuario`) REFERENCES `tb_tipos_usuarios` (`id_tipo_usuario`),
  CONSTRAINT `chk_usuario_correo_unab` CHECK ((`correo_institucional` like _utf8mb4'%@unab.edu.pe')),
  CONSTRAINT `chk_usuario_dni` CHECK (((`dni` is null) or regexp_like(`dni`,_utf8mb4'^[0-9]{8}$')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_auditoria` (
  `id_auditoria` int NOT NULL AUTO_INCREMENT,
  `id_usuario_actor` int DEFAULT NULL,
  `id_tipo_accion` int NOT NULL,
  `tabla_afectada` varchar(70) COLLATE utf8mb4_unicode_ci NOT NULL,
  `id_registro_afectado` int NOT NULL,
  `detalle_cambio` json DEFAULT NULL,
  `fecha_operacion` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id_auditoria`),
  KEY `fk_auditoria_tipo` (`id_tipo_accion`),
  KEY `idx_auditoria_registro` (`tabla_afectada`,`id_registro_afectado`),
  KEY `idx_auditoria_fecha` (`fecha_operacion`),
  KEY `fk_auditoria_usuario_actor` (`id_usuario_actor`),
  CONSTRAINT `fk_auditoria_tipo` FOREIGN KEY (`id_tipo_accion`) REFERENCES `tb_tipos_accion` (`id_tipo_accion`),
  CONSTRAINT `fk_auditoria_usuario_actor` FOREIGN KEY (`id_usuario_actor`) REFERENCES `tb_usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_perfiles` (
  `id_perfil` int NOT NULL AUTO_INCREMENT,
  `id_usuario` int NOT NULL,
  `id_rol` int NOT NULL,
  `ultimo_acceso` datetime DEFAULT NULL,
  `fecha_creacion` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_perfil`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  KEY `fk_perfil_rol` (`id_rol`),
  CONSTRAINT `fk_perfil_rol` FOREIGN KEY (`id_rol`) REFERENCES `tb_roles` (`id_rol`),
  CONSTRAINT `fk_perfil_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `tb_usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_programaciones` (
  `id_programacion` int NOT NULL AUTO_INCREMENT,
  `id_periodo` int NOT NULL,
  `id_tipo_programacion` int NOT NULL,
  `id_escuela` int DEFAULT NULL,
  `id_admin_registra` int NOT NULL,
  `nombre_programacion` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `descripcion` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `responsable` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `fecha_registro` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_programacion`),
  KEY `fk_programacion_periodo` (`id_periodo`),
  KEY `fk_programacion_tipo` (`id_tipo_programacion`),
  KEY `fk_programacion_escuela` (`id_escuela`),
  KEY `fk_programacion_admin_registra` (`id_admin_registra`),
  CONSTRAINT `fk_programacion_admin_registra` FOREIGN KEY (`id_admin_registra`) REFERENCES `tb_usuarios` (`id_usuario`),
  CONSTRAINT `fk_programacion_escuela` FOREIGN KEY (`id_escuela`) REFERENCES `tb_escuelas` (`id_escuela`),
  CONSTRAINT `fk_programacion_periodo` FOREIGN KEY (`id_periodo`) REFERENCES `tb_periodos_academicos` (`id_periodo`),
  CONSTRAINT `fk_programacion_tipo` FOREIGN KEY (`id_tipo_programacion`) REFERENCES `tb_tipos_programacion` (`id_tipo_programacion`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_horarios_programados` (
  `id_horario` int NOT NULL AUTO_INCREMENT,
  `id_programacion` int NOT NULL,
  `fecha_uso` date NOT NULL,
  `hora_inicio` time NOT NULL,
  `hora_fin` time NOT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_horario`),
  KEY `fk_horario_programacion` (`id_programacion`),
  KEY `idx_horarios_fecha` (`fecha_uso`,`hora_inicio`,`hora_fin`),
  CONSTRAINT `fk_horario_programacion` FOREIGN KEY (`id_programacion`) REFERENCES `tb_programaciones` (`id_programacion`),
  CONSTRAINT `chk_horario_rango` CHECK ((`hora_inicio` < `hora_fin`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_reservas` (
  `id_reserva` int NOT NULL AUTO_INCREMENT,
  `id_usuario` int NOT NULL,
  `id_admin_gestor` int DEFAULT NULL,
  `id_horario` int NOT NULL,
  `id_estado_reserva` int NOT NULL,
  `codigo_reserva` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `hora_inicio` time NOT NULL,
  `hora_fin` time NOT NULL,
  `fecha_solicitud` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `fecha_actualizacion_estado` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_reserva`),
  UNIQUE KEY `codigo_reserva` (`codigo_reserva`),
  KEY `fk_reserva_estado` (`id_estado_reserva`),
  KEY `idx_reserva_horario_estado` (`id_horario`,`id_estado_reserva`,`estado`),
  KEY `fk_reserva_usuario` (`id_usuario`),
  KEY `fk_reserva_admin_gestor` (`id_admin_gestor`),
  CONSTRAINT `fk_reserva_admin_gestor` FOREIGN KEY (`id_admin_gestor`) REFERENCES `tb_usuarios` (`id_usuario`),
  CONSTRAINT `fk_reserva_estado` FOREIGN KEY (`id_estado_reserva`) REFERENCES `tb_estados_reserva` (`id_estado_reserva`),
  CONSTRAINT `fk_reserva_horario` FOREIGN KEY (`id_horario`) REFERENCES `tb_horarios_programados` (`id_horario`),
  CONSTRAINT `fk_reserva_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `tb_usuarios` (`id_usuario`),
  CONSTRAINT `chk_reserva_max_2_horas` CHECK (((time_to_sec(`hora_fin`) - time_to_sec(`hora_inicio`)) between 1 and 7200)),
  CONSTRAINT `chk_reserva_orden_fechas` CHECK ((`fecha_actualizacion_estado` >= `fecha_solicitud`)),
  CONSTRAINT `chk_reserva_rango` CHECK ((`hora_inicio` < `hora_fin`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_operaciones_implementos` (
  `id_operacion` int NOT NULL AUTO_INCREMENT,
  `id_tipo_operacion` int NOT NULL,
  `id_estado_prestamo` int DEFAULT NULL,
  `id_usuario` int DEFAULT NULL,
  `fecha_solicitud` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `fecha_inicio_prevista` datetime DEFAULT NULL,
  `fecha_entrega` datetime DEFAULT NULL,
  `fecha_devolucion_prevista` datetime DEFAULT NULL,
  `observacion` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  `id_reserva` int DEFAULT NULL,
  PRIMARY KEY (`id_operacion`),
  KEY `fk_operacion_tipo` (`id_tipo_operacion`),
  KEY `fk_operacion_estado_prestamo` (`id_estado_prestamo`),
  KEY `fk_operacion_usuario` (`id_usuario`),
  KEY `fk_operacion_reserva` (`id_reserva`),
  CONSTRAINT `fk_operacion_estado_prestamo` FOREIGN KEY (`id_estado_prestamo`) REFERENCES `tb_estados_prestamo` (`id_estado_prestamo`),
  CONSTRAINT `fk_operacion_reserva` FOREIGN KEY (`id_reserva`) REFERENCES `tb_reservas` (`id_reserva`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_operacion_tipo` FOREIGN KEY (`id_tipo_operacion`) REFERENCES `tb_tipos_operacion` (`id_tipo_operacion`),
  CONSTRAINT `fk_operacion_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `tb_usuarios` (`id_usuario`),
  CONSTRAINT `chk_operacion_fechas` CHECK (((`fecha_inicio_prevista` is null) or (`fecha_devolucion_prevista` is null) or (`fecha_inicio_prevista` < `fecha_devolucion_prevista`))),
  CONSTRAINT `chk_operacion_orden_entrega` CHECK (((`fecha_entrega` is null) or (`fecha_entrega` >= `fecha_solicitud`))),
  CONSTRAINT `chk_operacion_orden_inicio` CHECK (((`fecha_inicio_prevista` is null) or (`fecha_inicio_prevista` >= `fecha_solicitud`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `tb_detalle_operacion` (
  `id_detalle_operacion` int NOT NULL AUTO_INCREMENT,
  `id_operacion` int NOT NULL,
  `id_implemento` int NOT NULL,
  `id_tipo_movimiento` int NOT NULL,
  `id_admin_movimiento` int DEFAULT NULL,
  `fecha_movimiento` datetime DEFAULT NULL,
  `condicion_fisica` varchar(150) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `observacion` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `estado` bit(1) NOT NULL DEFAULT b'1',
  PRIMARY KEY (`id_detalle_operacion`),
  UNIQUE KEY `uq_detalle_operacion_unidad_tipo` (`id_operacion`,`id_implemento`,`id_tipo_movimiento`),
  KEY `fk_detalle_op_tipo` (`id_tipo_movimiento`),
  KEY `idx_detalle_implemento_fecha` (`id_implemento`,`fecha_movimiento`,`id_detalle_operacion`),
  KEY `fk_detalle_operacion_admin` (`id_admin_movimiento`),
  CONSTRAINT `fk_detalle_op_implemento` FOREIGN KEY (`id_implemento`) REFERENCES `tb_implementos` (`id_implemento`),
  CONSTRAINT `fk_detalle_op_operacion` FOREIGN KEY (`id_operacion`) REFERENCES `tb_operaciones_implementos` (`id_operacion`),
  CONSTRAINT `fk_detalle_op_tipo` FOREIGN KEY (`id_tipo_movimiento`) REFERENCES `tb_tipos_movimiento` (`id_tipo_movimiento`),
  CONSTRAINT `fk_detalle_operacion_admin` FOREIGN KEY (`id_admin_movimiento`) REFERENCES `tb_usuarios` (`id_usuario`),
  CONSTRAINT `chk_detalle_movimiento_responsable` CHECK ((((`fecha_movimiento` is null) and (`id_admin_movimiento` is null)) or ((`fecha_movimiento` is not null) and (`id_admin_movimiento` is not null)))),
  CONSTRAINT `chk_responsable_movimiento` CHECK (((`fecha_movimiento` is null) or (`id_admin_movimiento` is not null)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
