package com.kdt.wellmade.global.admin;

import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

/**
 * 관리자 로그인 무차별 대입(brute-force) 방어 — loginId당 실패 횟수를 메모리에 세다가
 * 임곗값을 넘으면 일정 시간 잠근다. 서버 재시작 시 초기화되는 1차 방어선 수준의 단순
 * 구현이다 — 운영 규모가 커지면 Redis 등 외부 저장소 기반으로 옮겨야 한다(TODO).
 */
@Component
public class AdminLoginAttemptGuard {

    private static final int MAX_ATTEMPTS = 5;
    private static final long LOCK_DURATION_MS = 15 * 60 * 1000L; // 15분

    private static final class State {
        int failCount;
        long lockedUntil;
    }

    private final ConcurrentHashMap<String, State> states = new ConcurrentHashMap<>();

    public boolean isLocked(String loginId) {
        State s = states.get(loginId);
        return s != null && s.lockedUntil > System.currentTimeMillis();
    }

    public synchronized void onFailure(String loginId) {
        State s = states.computeIfAbsent(loginId, id -> new State());
        s.failCount++;
        if (s.failCount >= MAX_ATTEMPTS) {
            s.lockedUntil = System.currentTimeMillis() + LOCK_DURATION_MS;
        }
    }

    public synchronized void onSuccess(String loginId) {
        states.remove(loginId);
    }
}
