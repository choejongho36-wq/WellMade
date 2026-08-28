-- JPA 엔티티가 아니라 raw SQL(JdbcTemplate)로 다루는 테이블들.
-- Hibernate ddl-auto가 안 건드리므로 여기서 직접 생성한다.
-- spring.sql.init.mode=always 로 매 기동 실행되니 전부 IF NOT EXISTS.
-- users FK는 일부러 안 건다 - 탈퇴 시 UserService.withdraw()가 순서대로 직접 지운다.

CREATE TABLE IF NOT EXISTS diet_meals (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     BIGINT       NOT NULL,
    logged_date DATE         NOT NULL,
    meal_type   VARCHAR(20)  NOT NULL,
    menu_name   VARCHAR(255),
    raw_message TEXT,
    kcal        BIGINT,
    protein_g   DOUBLE,
    carbs_g     DOUBLE,
    fat_g       DOUBLE,
    food_items  JSON,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_diet_meals_user_date (user_id, logged_date)
);

CREATE TABLE IF NOT EXISTS user_food_alias (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id            BIGINT       NOT NULL,
    search_term        VARCHAR(255) NOT NULL,
    resolved_food_name VARCHAR(255) NOT NULL,
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_food_alias (user_id, search_term)
);

CREATE TABLE IF NOT EXISTS food_nutrition_reference (
    id                       BIGINT AUTO_INCREMENT PRIMARY KEY,
    food_code                VARCHAR(50),
    food_name                VARCHAR(255),
    representative_food_name  VARCHAR(255),
    data_type                VARCHAR(50),
    food_category_large       VARCHAR(100),
    nutrition_basis_unit      VARCHAR(50),
    calories                  DECIMAL(10,2),
    protein_g                 DECIMAL(10,2),
    fat_g                     DECIMAL(10,2),
    carbs_g                   DECIMAL(10,2),
    sodium_mg                 DECIMAL(10,2),
    sugar_g                   DECIMAL(10,2),
    data_generation_method    VARCHAR(50),
    source_name               VARCHAR(255),
    food_weight_reference     VARCHAR(100),
    INDEX idx_fnr_food_name (food_name),
    INDEX idx_fnr_rep_name (representative_food_name)
);
