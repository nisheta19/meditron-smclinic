package ru.meditron.routing.route.service;

import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.meditron.routing.exception.ConflictException;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.route.domain.StaffTask;
import ru.meditron.routing.route.repo.StaffTaskRepository;
import ru.meditron.routing.time.ModelTime;

/** Задачи персоналу (раздел 12). */
@Service
public class TaskService {
    @org.springframework.beans.factory.annotation.Autowired
    private ru.meditron.routing.route.service.RouteWriteLock writeLock;


    private final StaffTaskRepository tasks;
    private final JournalService journal;

    public TaskService(StaffTaskRepository tasks, JournalService journal) {
        this.tasks = tasks;
        this.journal = journal;
    }

    public StaffTask create(String type, String role, UUID patientId, UUID routeId, UUID escalationId,
                            String text, Duration dueIn, String basis) {
        StaffTask t = new StaffTask();
        t.setType(type);
        t.setRole(role);
        t.setPatientId(patientId);
        t.setRouteId(routeId);
        t.setEscalationId(escalationId);
        t.setText(text);
        t.setDueAt(dueIn == null ? null : ModelTime.now().plus(dueIn));
        StaffTask saved = tasks.save(t);
        journal.entry("SYSTEM", "TASK_CREATED").basis(basis).patient(patientId).route(routeId)
                .escalation(escalationId).task(saved.getId()).detail("type", type).detail("role", role).save();
        return saved;
    }

    public boolean existsForFinding(UUID findingId, String type) {
        return tasks.existsByFindingIdAndType(findingId, type);
    }

    public StaffTask createForFinding(String type, String role, UUID patientId, UUID findingId, String text, String basis) {
        StaffTask t = new StaffTask();
        t.setType(type);
        t.setRole(role);
        t.setPatientId(patientId);
        t.setFindingId(findingId);
        t.setText(text);
        StaffTask saved = tasks.save(t);
        journal.entry("SYSTEM", "TASK_CREATED").basis(basis).patient(patientId).finding(findingId)
                .task(saved.getId()).detail("type", type).detail("role", role).save();
        return saved;
    }

    /** Отменить открытые задачи маршрута (цепочка остановлена, маршрут закрыт). */
    public void cancelForRoute(UUID routeId, String basis, String... types) {
        List<String> only = List.of(types);
        for (StaffTask t : tasks.findByRouteIdAndStatus(routeId, StaffTask.Status.OPEN)) {
            if (!only.isEmpty() && !only.contains(t.getType())) {
                continue;
            }
            t.setStatus(StaffTask.Status.CANCELLED);
            t.setDoneAt(ModelTime.now());
            t.setComment(basis);
            journal.entry("SYSTEM", "TASK_CANCELLED").basis(basis).patient(t.getPatientId()).route(routeId)
                    .task(t.getId()).detail("type", t.getType()).save();
        }
    }

    public void cancelForEscalation(UUID escalationId, String basis) {
        for (StaffTask t : tasks.findByEscalationIdAndStatus(escalationId, StaffTask.Status.OPEN)) {
            t.setStatus(StaffTask.Status.CANCELLED);
            t.setDoneAt(ModelTime.now());
            t.setComment(basis);
        }
    }

    @Transactional
    public StaffTask done(String taskId, String by, String comment) {
        writeLock.acquire();
        StaffTask t = tasks.findById(ru.meditron.routing.service.Ids.parse(taskId, "RESOURCE"))
                .orElseThrow(() -> new NotFoundException("TASK_NOT_FOUND", "Задача " + taskId + " не найдена"));
        if (t.getStatus() != StaffTask.Status.OPEN) {
            throw new ConflictException("TASK_NOT_OPEN", "Задача уже закрыта");
        }
        t.setStatus(StaffTask.Status.DONE);
        t.setDoneBy(by);
        t.setDoneAt(ModelTime.now());
        t.setComment(comment);
        journal.entry(t.getRole(), "TASK_DONE").by(by).basis("Решение человека").patient(t.getPatientId())
                .route(t.getRouteId()).escalation(t.getEscalationId()).task(t.getId())
                .detail("type", t.getType()).detail("comment", comment).save();
        return t;
    }
}
