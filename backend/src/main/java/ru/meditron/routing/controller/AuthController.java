package ru.meditron.routing.controller;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.*;
import ru.meditron.routing.config.SecurityConfig;

/** Единственный демонстрационный аккаунт; UI входа подключается отдельно. */
@RestController
@RequestMapping("/api/auth")
@Tag(name = "Auth", description = "Единственный тестовый аккаунт, cookie-сессия и CSRF; вход и выход через cookie-сессию")
public class AuthController {
    private final AuthenticationManager manager;
    private final HttpSessionSecurityContextRepository contexts;
    private final HttpSessionCsrfTokenRepository csrf;

    public AuthController(AuthenticationManager manager, HttpSessionSecurityContextRepository contexts, HttpSessionCsrfTokenRepository csrf) {
        this.manager = manager; this.contexts = contexts; this.csrf = csrf;
    }

    public record Login(@NotBlank @Size(max = 128) String login, @NotBlank @Size(max = 128) String password) {}
    public record Account(String login, List<String> roles) {}
    public record Csrf(String token, String headerName, String parameterName) {}

    @GetMapping("/csrf")
    public Csrf csrf(@Parameter(hidden = true) CsrfToken token) { return new Csrf(token.getToken(), token.getHeaderName(), token.getParameterName()); }

    @PostMapping("/login")
    public Account login(@Valid @RequestBody Login credentials, HttpServletRequest request, HttpServletResponse response) throws java.io.IOException {
        try {
            Authentication auth = manager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(credentials.login(), credentials.password()));
            new ChangeSessionIdAuthenticationStrategy().onAuthentication(auth, request, response);
            var context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(auth);
            SecurityContextHolder.setContext(context);
            contexts.saveContext(context, request, response);
            csrf.saveToken(null, request, response);
            return account(auth);
        } catch (AuthenticationException ex) {
            SecurityConfig.error(response, 401, "INVALID_CREDENTIALS", "Неверный логин или пароль");
            return null;
        }
    }

    @GetMapping("/me")
    public Account me(Authentication auth) { return account(auth); }

    @PostMapping("/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void logout(HttpServletRequest request, HttpServletResponse response, Authentication auth) {
        new SecurityContextLogoutHandler().logout(request, response, auth);
        response.addHeader("Set-Cookie", "JSESSIONID=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" + (request.isSecure() ? "; Secure" : ""));
    }

    private Account account(Authentication auth) {
        return new Account(auth.getName(), auth.getAuthorities().stream().map(a -> a.getAuthority().replace("ROLE_", "")).toList());
    }
}
