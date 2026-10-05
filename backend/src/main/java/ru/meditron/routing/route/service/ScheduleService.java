package ru.meditron.routing.route.service;

import java.nio.charset.StandardCharsets;
import java.time.DayOfWeek;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import ru.meditron.routing.exception.BadRequestException;
import ru.meditron.routing.exception.NotFoundException;
import ru.meditron.routing.route.config.RouteConfig;
import ru.meditron.routing.route.domain.PendingVisit;
import ru.meditron.routing.route.domain.Route;
import ru.meditron.routing.route.dto.RouteDtos.SlotDto;
import ru.meditron.routing.route.repo.RouteRepository;
import ru.meditron.routing.time.ModelTime;

/**
 * Заглушка расписания (раздел 11): детерминированные слоты от модельного времени, вымышленные врачи,
 * локации Текстильщики / Сенежская / ВДНХ и онлайн — только там, где разрешено. Слот кодируется в id,
 * поэтому хранить расписание не нужно.
 */
@Service
public class ScheduleService {

    private final RouteConfig config;
    private final RouteRepository routes;

    public ScheduleService(RouteConfig config, RouteRepository routes) {
        this.config = config;
        this.routes = routes;
    }

    public List<SlotDto> slots(String specialty, String kind, int limit) {
        if (limit < 1 || limit > 500 || !("ULTRASOUND".equals(kind) || "CONSULTATION".equals(kind)))
            throw new BadRequestException("INVALID_SCHEDULE_FILTER", "limit от 1 до 500; kind: ULTRASOUND или CONSULTATION");
        boolean ultrasound = "ULTRASOUND".equals(kind);
        if (!ultrasound && !config.hasSlots(specialty)) {
            return List.of();
        }
        boolean onlineOk = !ultrasound && config.onlineAllowed(specialty);
        List<String> locations = new ArrayList<>(config.strings("/schedule/locations"));
        List<String> doctors = ultrasound ? config.strings("/schedule/ultrasoundDoctors")
                : config.strings("/schedule/doctors/" + escape(specialty));
        if (doctors.isEmpty()) {
            doctors = List.of(config.text("/schedule/doctorFallback", "Врач клиники"));
        }
        LocalTime start = LocalTime.parse(config.text("/schedule/dayStart", "09:00"));
        LocalTime end = LocalTime.parse(config.text("/schedule/dayEnd", "19:00"));
        int step = config.integer("/schedule/stepMinutes", 90);
        int days = config.integer("/schedule/days", 5);

        List<SlotDto> out = new ArrayList<>();
        Instant now = ModelTime.now();
        LocalDate day = ModelTime.today();
        int workDays = 0;
        int i = 0;
        while (workDays < days && out.size() < limit) {
            if (day.getDayOfWeek() != DayOfWeek.SATURDAY && day.getDayOfWeek() != DayOfWeek.SUNDAY) {
                workDays++;
                for (LocalTime t = start; t.isBefore(end) && out.size() < limit; t = t.plusMinutes(step)) {
                    Instant at = ZonedDateTime.of(day, t, ModelTime.ZONE).toInstant();
                    if (at.isBefore(now.plusSeconds(3600))) {
                        continue;
                    }
                    boolean online = onlineOk && i % 3 == 0;
                    String location = online ? config.text("/schedule/onlineLabel", "онлайн") : locations.get(i % locations.size());
                    String doctor = doctors.get(i % doctors.size());
                    String sp = ultrasound ? "УЗИ" : specialty;
                    out.add(new SlotDto(encode(sp, kind, at, location, online, doctor), sp, kind, at, location, online, doctor));
                    i++;
                }
            }
            day = day.plusDays(1);
        }
        return out;
    }

    /** Слоты для маршрута: УЗИ при наблюдении, иначе — специалист маршрута. */
    public List<SlotDto> slotsForRoute(String routeId, int limit) {
        Route r = routes.findById(ru.meditron.routing.service.Ids.parse(routeId, "RESOURCE"))
                .orElseThrow(() -> new NotFoundException("ROUTE_NOT_FOUND", "Маршрут " + routeId + " не найден"));
        if (limit < 1 || limit > 500) throw new BadRequestException("INVALID_LIMIT", "limit от 1 до 500");
        if (!r.isOpen() || !RouteStateService.WAITING_FOR_BOOKING.contains(r.getStage())) return List.of();
        boolean us = r.getPendingVisit() == PendingVisit.ULTRASOUND;
        return slots(r.getSpecialty(), us ? "ULTRASOUND" : "CONSULTATION", 500).stream()
                .filter(s -> !s.online() || onlineAllowed(r, config)).limit(Math.max(0, Math.min(limit, 500))).toList();
    }

    public static boolean onlineAllowed(Route r, RouteConfig config) {
        return r.getPendingVisit() != PendingVisit.CONTROL && r.getPendingVisit() != PendingVisit.RESULT
                && r.getPendingVisit() != PendingVisit.ULTRASOUND && config.onlineAllowed(r.getSpecialty());
    }

    public SlotDto validateSlot(Route r, String id) {
        SlotDto slot = decode(id);
        boolean us = r.getPendingVisit() == PendingVisit.ULTRASOUND;
        if (!slot.specialty().equals(us ? "УЗИ" : r.getSpecialty())
                || !slot.kind().equals(us ? "ULTRASOUND" : "CONSULTATION")
                || !slot.dateTime().isAfter(ModelTime.now()) || slot.online() && !onlineAllowed(r, config))
            throw new BadRequestException("INVALID_SLOT", "Слот не соответствует маршруту");
        return slot;
    }

    public SlotDto decode(String slotId) {
        try {
            String[] p = new String(Base64.getUrlDecoder().decode(slotId), StandardCharsets.UTF_8).split("\\|", -1);
            if (p.length != 6 || !("true".equals(p[4]) || "false".equals(p[4])))
                throw new IllegalArgumentException("Invalid slot fields");
            return new SlotDto(slotId, p[0], p[1], Instant.parse(p[2]), p[3], Boolean.parseBoolean(p[4]), p[5]);
        } catch (RuntimeException e) {
            throw new BadRequestException("INVALID_SLOT", "Слот не распознан");
        }
    }

    private static String encode(String specialty, String kind, Instant at, String location, boolean online, String doctor) {
        String raw = String.join("|", specialty, kind, at.toString(), location, String.valueOf(online), doctor);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    /** JSON Pointer: «/» и «~» в имени специалиста. */
    private static String escape(String key) {
        return key.replace("~", "~0").replace("/", "~1");
    }
}
