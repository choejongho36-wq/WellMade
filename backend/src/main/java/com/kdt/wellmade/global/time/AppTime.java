package com.kdt.wellmade.global.time;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

/**
 * "오늘"의 기준 시각. 서비스 대상이 한국 사용자뿐이므로 KST로 고정한다.
 *
 * 예전엔 전부 {@code LocalDate.now()}(JVM 기본 타임존)를 썼는데, 배포 서버(EC2)가 UTC면
 * KST 00:00~09:00 사이에 "오늘 식단"이 어제 것으로 조회됐다. 식단 기록/조회/목표 계산이
 * 각각 다른 날짜를 볼 수 있는 문제라, 날짜 경계가 걸리는 곳은 전부 이 클래스를 통한다.
 *
 * JVM 기본 타임존도 Dockerfile에서 -Duser.timezone=Asia/Seoul 로 맞춰두었다
 * (엔티티의 createdAt 처럼 여기를 안 거치는 LocalDateTime.now() 때문).
 */
public final class AppTime {

    public static final ZoneId ZONE = ZoneId.of("Asia/Seoul");

    private AppTime() {
    }

    public static LocalDate today() {
        return LocalDate.now(ZONE);
    }

    public static LocalDateTime now() {
        return LocalDateTime.now(ZONE);
    }

    public static LocalTime nowTime() {
        return LocalTime.now(ZONE);
    }
}
