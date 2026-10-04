package ru.meditron.routing.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Component;
import ru.meditron.routing.dictionary.DictionaryService;
import ru.meditron.routing.domain.Finding;
import ru.meditron.routing.domain.FindingLevel;

/**
 * Правила бэкенда поверх rules словаря (блок backend и flags в findings-dictionary.yaml):
 *  - флаги SYSTEM_UNKNOWN / SYSTEM_CONVERTED для TI-RADS;
 *  - MINOR: пациент младше 18 лет -> детский специалист по тому же правилу;
 *  - объединение гинекологических находок одного протокола в блок оперирующего гинеколога.
 */
@Component
public class RoutingAdjustments {

    static final String OPERATING_GYNECOLOGIST = "Оперирующий гинеколог";
    static final String GYNECOLOGIST = "Гинеколог";

    private final DictionaryService dictionary;

    public RoutingAdjustments(DictionaryService dictionary) {
        this.dictionary = dictionary;
    }

    /** Флаги бэкенда по атрибутам находки. */
    public void addSystemFlags(Finding f) {
        Object system = f.getAttributes() == null ? null : f.getAttributes().get("tiradsSystem");
        if (system == null) {
            return;
        }
        String s = String.valueOf(system).toUpperCase(Locale.ROOT);
        if ("UNKNOWN".equals(s)) {
            addFlag(f, "SYSTEM_UNKNOWN", "Система TI-RADS не указана — трактуется как EU-TIRADS");
        } else if ("ACR".equals(s) || "KWAK".equals(s)) {
            Object raw = f.getAttributes().get("tiradsRaw");
            addFlag(f, "SYSTEM_CONVERTED", "Категория " + (raw == null ? "" : raw + " ") + "по системе " + s
                    + " переведена в EU-TIRADS " + f.getAttributes().get("tirads"));
        }
    }

    /** MINOR: специалист заменяется на детского, правило и срок те же. */
    public void applyMinor(Finding f, Integer age) {
        if (age == null || age >= 18) {
            return;
        }
        f.setTargetSpecialty(pediatric(f.getTargetSpecialty()));
        addFlag(f, "MINOR", "Пациент младше 18 лет — направление к детскому специалисту");
    }

    static String pediatric(String specialty) {
        if (specialty == null || specialty.isBlank() || specialty.toLowerCase(Locale.ROOT).contains("детск")
                || specialty.startsWith("Координатор")) {
            return specialty;
        }
        String duty = "Дежурный ";
        if (specialty.startsWith(duty)) {
            return duty + "детский " + specialty.substring(duty.length());
        }
        return "Детский " + Character.toLowerCase(specialty.charAt(0)) + specialty.substring(1);
    }

    /**
     * Если хотя бы одна находка протокола идёт к оперирующему гинекологу, остальные гинекологические находки
     * (к гинекологу; кроме гинеколога-эндокринолога, онкогинеколога и экстренных) идут в тот же блок.
     * Срок блока — по самой срочной находке, шаблон — от самой срочной находки оперирующего гинеколога.
     */
    public void mergeGynecology(List<Finding> protocolFindings) {
        List<Finding> anchors = new ArrayList<>();
        List<Finding> others = new ArrayList<>();
        for (Finding f : protocolFindings) {
            if (f.getLevel() == FindingLevel.EMERGENCY || f.getTargetSpecialty() == null) {
                continue;
            }
            String sp = f.getTargetSpecialty().replaceFirst("^Детский ", "").trim();
            if (sp.equalsIgnoreCase(OPERATING_GYNECOLOGIST) || sp.equalsIgnoreCase("оперирующий гинеколог")) {
                anchors.add(f);
            } else if (sp.equalsIgnoreCase(GYNECOLOGIST)) {
                others.add(f);
            }
        }
        if (anchors.isEmpty() || (others.isEmpty() && anchors.size() < 2)) {
            return;    // объединять нечего
        }
        Finding lead = anchors.get(0);
        for (Finding a : anchors) {
            if (days(a) < days(lead)) {
                lead = a;
            }
        }
        int blockDays = days(lead);
        for (Finding o : others) {
            blockDays = Math.min(blockDays, days(o));
        }
        String specialty = lead.getTargetSpecialty();
        for (Finding o : others) {
            o.setTargetSpecialty(specialty);
            o.setRouteTemplateCode(lead.getRouteTemplateCode());
            o.setMatchedRule(o.getMatchedRule() + " + backend.mergeRules[gynecology]");
            addFlag(o, "MERGED_GYNECOLOGY", "Объединено с блоком оперирующего гинеколога (" + lead.getName() + ")");
        }
        // Срок всего блока — по самой срочной находке (в том числе когда все находки уже у оперирующего гинеколога).
        List<Finding> block = new ArrayList<>(anchors);
        block.addAll(others);
        for (Finding f : block) {
            if (f.getTargetDays() == null || f.getTargetDays() > blockDays) {
                f.setTargetDays(blockDays);
                if (!others.contains(f)) {
                    f.setMatchedRule(f.getMatchedRule() + " + backend.mergeRules[gynecology]");
                    addFlag(f, "MERGED_GYNECOLOGY", "Срок выровнен по самой срочной находке блока оперирующего гинеколога: "
                            + blockDays + " дн.");
                }
            }
        }
    }

    private int days(Finding f) {
        return f.getTargetDays() == null ? Integer.MAX_VALUE : f.getTargetDays();
    }

    void addFlag(Finding f, String code, String note) {
        if (f.getFlags() == null) {
            f.setFlags(new ArrayList<>());
        }
        boolean exists = f.getFlags().stream().anyMatch(m -> code.equals(m.get("code")));
        if (exists) {
            return;
        }
        Map<String, Object> flag = new LinkedHashMap<>();
        flag.put("code", code);
        dictionary.flag(code).ifPresent(d -> flag.put("name", d.path("name").asText()));
        flag.put("note", note);
        flag.put("setBy", "BACKEND");
        f.getFlags().add(flag);
    }
}
