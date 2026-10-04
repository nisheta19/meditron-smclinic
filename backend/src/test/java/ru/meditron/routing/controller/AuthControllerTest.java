package ru.meditron.routing.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import ru.meditron.routing.config.SecurityConfig;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.junit.jupiter.api.Assertions.*;

@WebMvcTest(AuthController.class)
@Import(SecurityConfig.class)
@TestPropertySource(properties = "auth.required=true")
class AuthControllerTest {
    @Autowired MockMvc mvc;

    @Test void anonymousAndClinicianApiRequireLogin() throws Exception {
        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/patients")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/auth/csrf")).andExpect(status().isOk()).andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test void rejectsMissingCsrfAndWrongPassword() throws Exception {
        mvc.perform(post("/api/auth/login").contentType("application/json").content("{\"login\":\"123\",\"password\":\"123\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(post(java.net.URI.create("/api/%61uth/login")).contentType("application/json").content("{\"login\":\"123\",\"password\":\"123\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/auth/login").with(csrf()).contentType("application/json").content("{\"login\":\"123\",\"password\":\"wrong\"}"))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.code").value("INVALID_CREDENTIALS"));
    }

    @Test void sessionRotatesAndLogoutRevokesIt() throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();
        mvc.perform(post("/api/auth/login").session(session).with(csrf()).contentType("application/json")
                .content("{\"login\":\"123\",\"password\":\"123\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.login").value("123"))
                .andExpect(jsonPath("$.password").doesNotExist());
        assertNotEquals(before, session.getId());
        mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isOk());
        mvc.perform(post("/api/auth/logout").session(session)).andExpect(status().isForbidden());
        mvc.perform(post("/api/auth/logout").session(session).with(csrf())).andExpect(status().isNoContent());
        assertTrue(session.isInvalid());
        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    }

    @Test void onlyOneAccountAndNoSelfRegistration() throws Exception {
        mvc.perform(post("/api/auth/login").with(csrf()).contentType("application/json").content("{\"login\":\"admin\",\"password\":\"123\"}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json").content("{}"))
                .andExpect(status().isNotFound());
    }
}
