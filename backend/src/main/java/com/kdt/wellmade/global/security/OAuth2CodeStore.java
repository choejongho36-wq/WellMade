package com.kdt.wellmade.global.security;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class OAuth2CodeStore {
    private static final long EXPIRE_SECONDS = 60;
    private record Entry(Long userId, Instant expiresAt) {}
    private final Map<String, Entry> store = new ConcurrentHashMap<>();

    public String issue(Long userId) {
        String code = UUID.randomUUID().toString();
        Entry entry = new Entry(userId, Instant.now().plusSeconds(EXPIRE_SECONDS));
        store.put(code, entry);
        return code;
    }
    public Long consume(String code) {
        if (code == null) return null;
        Entry entry = store.remove(code);
        if (entry == null) return null;
        if (Instant.now().isAfter(entry.expiresAt())) return null;
        return entry.userId();
    }
    
}
