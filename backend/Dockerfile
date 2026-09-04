# syntax=docker/dockerfile:1

# --- build ---
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app

# 의존성 레이어를 소스와 분리해서 캐시가 오래 유지되게 함
COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew --no-daemon dependencies || true

COPY src ./src
RUN ./gradlew --no-daemon clean bootJar -x test

# --- run ---
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/libs/*-SNAPSHOT.jar app.jar
EXPOSE 8080
# 서버(EC2)가 UTC라 "오늘"의 기준이 하루 밀리는 문제가 있었다. 날짜 경계가 걸리는 조회는
# AppTime(KST 고정)을 쓰지만, 엔티티의 createdAt 같은 LocalDateTime.now()는 JVM 기본
# 타임존을 그대로 타므로 여기서도 맞춰둔다 (MySQL은 compose에서 이미 +09:00).
ENV TZ=Asia/Seoul
ENTRYPOINT ["java", "-Duser.timezone=Asia/Seoul", "-jar", "app.jar"]
