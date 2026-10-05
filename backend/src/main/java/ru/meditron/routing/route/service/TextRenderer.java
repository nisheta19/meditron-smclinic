package ru.meditron.routing.route.service;

import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Подстановка в шаблоны сообщений (раздел 6.6): {ключ} → значение, фрагмент [[…]] — только если
 * специалисту разрешён онлайн. Неизвестный ключ остаётся как есть, чтобы ошибку было видно в тексте.
 */
public final class TextRenderer {

    private static final Pattern ONLINE = Pattern.compile("\\[\\[(.*?)]]", Pattern.DOTALL);
    private static final Pattern KEY = Pattern.compile("\\{([A-Za-z]+)}");

    private TextRenderer() {
    }

    public static String render(String template, Map<String, String> values, boolean onlineAllowed) {
        if (template == null) {
            return null;
        }
        Matcher online = ONLINE.matcher(template);
        StringBuilder withOnline = new StringBuilder();
        while (online.find()) {
            online.appendReplacement(withOnline, Matcher.quoteReplacement(onlineAllowed ? online.group(1) : ""));
        }
        online.appendTail(withOnline);

        Matcher key = KEY.matcher(withOnline);
        StringBuilder out = new StringBuilder();
        while (key.find()) {
            String v = values.get(key.group(1));
            key.appendReplacement(out, Matcher.quoteReplacement(v != null ? v : key.group(0)));
        }
        key.appendTail(out);
        return out.toString().replaceAll(" {2,}", " ").replace(" ;", ";").trim();
    }
}
