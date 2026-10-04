package ru.meditron.routing.config;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {
    @Bean
    UserDetailsService users(@Value("${auth.login:123}") String login, @Value("${auth.password:123}") String password) {
        return new InMemoryUserDetailsManager(User.withUsername(login)
                .password(new BCryptPasswordEncoder().encode(password)).roles("DOCTOR").build());
    }

    @Bean
    AuthenticationManager authenticationManager(UserDetailsService users) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(new BCryptPasswordEncoder());
        return new ProviderManager(provider);
    }

    @Bean
    HttpSessionSecurityContextRepository contextRepository() { return new HttpSessionSecurityContextRepository(); }

    @Bean
    HttpSessionCsrfTokenRepository csrfRepository() { return new HttpSessionCsrfTokenRepository(); }

    @Bean
    SecurityFilterChain security(HttpSecurity http, HttpSessionSecurityContextRepository contexts,
                                 HttpSessionCsrfTokenRepository csrf, @Value("${auth.required:false}") boolean required) throws Exception {
        http.cors(c -> {}).formLogin(AbstractHttpConfigurer::disable).httpBasic(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable).requestCache(AbstractHttpConfigurer::disable)
                .securityContext(c -> c.securityContextRepository(contexts))
                .csrf(c -> c.csrfTokenRepository(csrf).requireCsrfProtectionMatcher(request -> {
                    if (java.util.Set.of("GET", "HEAD", "OPTIONS", "TRACE").contains(request.getMethod())) return false;
                    String path = org.springframework.web.util.UrlPathHelper.defaultInstance.getPathWithinApplication(request);
                    return path.startsWith("/api/auth/") || required && clinicianPath(path);
                }))
                .authorizeHttpRequests(a -> {
                    a.requestMatchers("/api/auth/me").authenticated();
                    if (required) a.requestMatchers("/api/patients/**", "/api/findings/**", "/api/protocols/**").authenticated();
                    a.anyRequest().permitAll();
                })
                .exceptionHandling(e -> e
                        .authenticationEntryPoint((req, res, ex) -> error(res, 401, "UNAUTHORIZED", "Требуется вход"))
                        .accessDeniedHandler((req, res, ex) -> error(res, 403, "FORBIDDEN", "Недостаточно прав или неверный CSRF-токен")));
        return http.build();
    }

    private static boolean clinicianPath(String path) {
        return path.matches("/api/(patients|findings|protocols)(/.*)?");
    }

    public static void error(HttpServletResponse response, int status, String code, String message) throws java.io.IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":\"" + code + "\",\"message\":\"" + message + "\"}");
    }
}
