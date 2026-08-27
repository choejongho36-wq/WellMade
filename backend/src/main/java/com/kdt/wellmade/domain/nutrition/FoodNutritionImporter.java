package com.kdt.wellmade.domain.nutrition;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
 
import java.io.File;
import java.math.BigDecimal;
 
/**
 * 식약처 "전국통합식품영양성분정보(음식) 표준데이터" JSON을 DB에 일괄 적재하는 일회성 배치.
 *
 * *** 이건 상시 실행되는 컴포넌트가 아니라 "한 번 돌리고 마는" 초기화 스크립트입니다. ***
 * import.enabled=true 로 설정했을 때만 동작하고, 끝나면 다시 false로 돌려두세요.
 * (매 서버 기동마다 19,495건을 또 넣으면 중복이 쌓입니다.)
 *
 * application.yml:
 *   food-import:
 *     enabled: true
 *     file-path: /path/to/전국통합식품영양성분정보_음식_표준데이터.json
 */
@Component
public class FoodNutritionImporter implements CommandLineRunner {
 
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final boolean enabled;
    private final String filePath;
 
    public FoodNutritionImporter(
            JdbcTemplate jdbcTemplate,
            @Value("${food-import.enabled:false}") boolean enabled,
            @Value("${food-import.file-path:}") String filePath
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.enabled = enabled;
        this.filePath = filePath;
    }
 
    @Override
    public void run(String... args) throws Exception {
        if (!enabled) {
            return;
        }
        if (filePath == null || filePath.isBlank()) {
            System.out.println("[FoodNutritionImporter] food-import.file-path가 설정되지 않아 건너뜁니다.");
            return;
        }
 
        System.out.println("[FoodNutritionImporter] 적재 시작: " + filePath);
 
        JsonNode root = objectMapper.readTree(new File(filePath));
        JsonNode records = root.path("records");
 
        String sql = """
                INSERT INTO food_nutrition_reference
                (food_code, food_name, representative_food_name, data_type, food_category_large,
                 nutrition_basis_unit, calories, protein_g, fat_g, carbs_g, sodium_mg, sugar_g,
                 data_generation_method, source_name, food_weight_reference)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """;
 
        int batchSize = 500;
        int count = 0;
        java.util.List<Object[]> batch = new java.util.ArrayList<>();
 
        for (JsonNode record : records) {
            batch.add(new Object[]{
                    text(record, "식품코드"),
                    text(record, "식품명"),
                    text(record, "대표식품명"),
                    text(record, "데이터구분명"),
                    text(record, "식품대분류명"),
                    text(record, "영양성분함량기준량"),
                    decimal(record, "에너지(kcal)"),
                    decimal(record, "단백질(g)"),
                    decimal(record, "지방(g)"),
                    decimal(record, "탄수화물(g)"),
                    decimal(record, "나트륨(mg)"),
                    decimal(record, "당류(g)"),
                    text(record, "데이터생성방법명"),
                    text(record, "출처명"),
                    text(record, "식품중량"),
            });
            count++;
 
            if (batch.size() >= batchSize) {
                jdbcTemplate.batchUpdate(sql, batch);
                batch.clear();
                System.out.println("[FoodNutritionImporter] " + count + "건 적재 완료...");
            }
        }
        if (!batch.isEmpty()) {
            jdbcTemplate.batchUpdate(sql, batch);
        }
 
        System.out.println("[FoodNutritionImporter] 총 " + count + "건 적재 완료. "
                + "application.yml에서 food-import.enabled를 false로 되돌리세요.");
    }
 
    private String text(JsonNode record, String field) {
        String value = record.path(field).asText("");
        return value.isBlank() ? null : value;
    }
 
    private BigDecimal decimal(JsonNode record, String field) {
        String value = record.path(field).asText("");
        if (value.isBlank()) {
            return null; // 원본에 빈 문자열인 경우가 많음 (예: 지방(g)이 비어있는 레코드)
        }
        try {
            return new BigDecimal(value);
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
 