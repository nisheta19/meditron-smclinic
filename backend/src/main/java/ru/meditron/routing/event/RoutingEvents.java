package ru.meditron.routing.event;

import java.util.UUID;

/**
 * События, которыми существующий код (приём ML, действия с находками) сообщает модулю маршрутов
 * о переменах. Модуль маршрутов слушает их синхронно, в той же транзакции. Если модуль выключен
 * (routes.enabled=false), события просто никто не слушает — поведение старого кода не меняется.
 */
public final class RoutingEvents {

    private RoutingEvents() {
    }

    /** Принят протокол со статусом DONE и его находки сохранены. */
    public record ProtocolAccepted(UUID patientId, UUID protocolId) {
    }

    /** Версия протокола выведена из работы: аннулирована (ANNULLED) или заменена новой версией (CORRECTED). */
    public record ProtocolClosed(UUID patientId, UUID protocolId, Reason reason) {
        public enum Reason { ANNULLED, CORRECTED }
    }

    /** Координатор изменил находки пациента: подтвердил, отклонил, поправил, добавил или удалил. */
    public record FindingsChanged(UUID patientId) {
    }
}
