-- PoliReserva UNAB V9. Aplicar una vez sobre el esquema seleccionado.
-- Hacer un respaldo antes y verificar que id_reserva y fk_operacion_reserva no existan.
-- Compatible con el esquema previo y sus registros. MySQL confirma el DDL implícitamente.
ALTER TABLE tb_operaciones_implementos
    ADD COLUMN id_reserva INT NULL,
    ADD CONSTRAINT fk_operacion_reserva FOREIGN KEY (id_reserva)
        REFERENCES tb_reservas(id_reserva)
        ON DELETE RESTRICT ON UPDATE RESTRICT;
