package ru.meditron.routing.route.service;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import ru.meditron.routing.route.domain.JournalEntry;
import ru.meditron.routing.route.repo.JournalRepository;

/** Журнал действий (раздел 13): одна запись — одно событие, записи только добавляются. */
@Service
public class JournalService {

    private final JournalRepository journal;
    private final TransactionTemplate independent;

    public JournalService(JournalRepository journal, PlatformTransactionManager txManager) {
        this.journal = journal;
        this.independent = new TransactionTemplate(txManager);
        this.independent.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public Builder entry(String actor, String action) {
        return new Builder(actor, action);
    }

    public final class Builder {
        private final JournalEntry e = new JournalEntry();

        private Builder(String actor, String action) {
            e.setActor(actor);
            e.setAction(action);
        }

        public Builder by(String name) { e.setActorName(name); return this; }
        public Builder basis(String basis) { e.setBasis(basis); return this; }
        public Builder patient(UUID id) { e.setPatientId(id); return this; }
        public Builder route(UUID id) { e.setRouteId(id); return this; }
        public Builder finding(UUID id) { e.setFindingId(id); return this; }
        public Builder task(UUID id) { e.setTaskId(id); return this; }
        public Builder escalation(UUID id) { e.setEscalationId(id); return this; }

        public Builder detail(String key, Object value) {
            if (e.getDetails() == null) {
                e.setDetails(new LinkedHashMap<>());
            }
            e.getDetails().put(key, value == null ? null : String.valueOf(value));
            return this;
        }

        public Builder details(Map<String, ?> values) {
            values.forEach(this::detail);
            return this;
        }

        public JournalEntry save() {
            return journal.save(e);
        }

        /** Запись, которая сохранится, даже если текущая транзакция откатится (отклонённое событие). */
        public JournalEntry saveIndependent() {
            return independent.execute(status -> journal.save(e));
        }
    }
}
