package ru.meditron.routing.route.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Serializes clinical writes in this small single-clinic service, including multiple JVMs. */
@Component
public class RouteWriteLock {
    private final JdbcTemplate jdbc;
    public RouteWriteLock(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public void acquire() {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("Clinical write lock requires a transaction");
        }
        jdbc.execute("select pg_advisory_xact_lock(726430105)");
    }
}
