package ru.meditron.routing.service;

import java.util.UUID;
import ru.meditron.routing.exception.NotFoundException;

public final class Ids {

    private Ids() {
    }

    public static UUID parse(String id, String what) {
        if (id == null) throw new NotFoundException(what + "_NOT_FOUND", "Идентификатор не указан");
        try {
            return UUID.fromString(id);
        } catch (IllegalArgumentException e) {
            throw new NotFoundException(what + "_NOT_FOUND", what + " " + id + " не найден");
        }
    }
}
