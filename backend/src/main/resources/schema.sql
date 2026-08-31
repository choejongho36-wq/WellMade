-- JPA 엔티티가 아니라 raw SQL(JdbcTemplate)로 다루는 테이블들.
-- Hibernate ddl-auto가 안 건드리므로 여기서 직접 생성한다.
-- spring.sql.init.mode=always 로 매 기동 실행되니 전부 IF NOT EXISTS.
--
-- 컬럼 정의는 개발 DB의 SHOW CREATE TABLE 과 맞췄다.
-- FK(diet_meals -> users / diet_plans)는 일부러 안 건다 - schema.sql은 Hibernate보다
-- 먼저 실행돼서 users 테이블이 아직 없을 수 있고, 탈퇴 시 UserService.withdraw()가
-- 순서대로 직접 지우므로 cascade가 필요 없다.

CREATE TABLE IF NOT EXISTS diet_meals (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    user_id      BIGINT,
    logged_date  DATE,
    diet_plan_id BIGINT,                 -- 레거시(구 diet_plans 설계) - 현재 코드는 안 씀
    meal_type    VARCHAR(20)  NOT NULL,
    menu_name    VARCHAR(200) NOT NULL,
    raw_message  TEXT,
    kcal         INT,
    protein_g    DECIMAL(6,1),
    carbs_g      DECIMAL(6,1),
    fat_g        DECIMAL(6,1),
    food_items   JSON,
    nutrients    JSON,                    -- 레거시 - 현재 코드는 안 씀
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_diet_meals_user_date (user_id, logged_date)
);

CREATE TABLE IF NOT EXISTS user_food_alias (
    id                 BIGINT       NOT NULL AUTO_INCREMENT,
    user_id            BIGINT       NOT NULL,
    search_term        VARCHAR(255) NOT NULL,
    resolved_food_name VARCHAR(255) NOT NULL,
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_user_food_alias (user_id, search_term)
);

CREATE TABLE IF NOT EXISTS food_nutrition_reference (
    id                       BIGINT NOT NULL AUTO_INCREMENT,
    food_code                VARCHAR(50),
    food_name                VARCHAR(200),
    representative_food_name  VARCHAR(100),
    data_type                VARCHAR(20),
    food_category_large       VARCHAR(50),
    nutrition_basis_unit      VARCHAR(10),
    calories                  DECIMAL(8,2),
    protein_g                 DECIMAL(8,2),
    fat_g                     DECIMAL(8,2),
    carbs_g                   DECIMAL(8,2),
    sodium_mg                 DECIMAL(8,2),
    sugar_g                   DECIMAL(8,2),
    data_generation_method    VARCHAR(20),
    source_name               VARCHAR(50),
    food_weight_reference     VARCHAR(30),
    created_at                DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_representative_name (representative_food_name),
    KEY idx_food_name (food_name),
    KEY idx_data_type (data_type)
);
