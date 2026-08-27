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
ENTRYPOINT ["java", "-jar", "app.jar"]
