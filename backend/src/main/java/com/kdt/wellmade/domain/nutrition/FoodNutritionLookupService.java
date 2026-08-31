package com.kdt.wellmade.domain.nutrition;

import java.util.List;

public interface FoodNutritionLookupService {

    /**
     * 사용자가 그램/ml 수를 직접 말한 경우(예: "닭가슴살 200g") - 그 값 그대로 계산.
     * @param foodName 조회할 음식명 (검색용으로 정규화된 이름)
     * @param amountG  섭취량(그램)
     * @return 계산된 영양정보, 못 찾으면 null
     */
    NutritionInfo lookup(String foodName, double amountG);

    /**
     * 사용자가 인분수/개수만 말한 경우(예: "김치찌개 1인분", "사과 1개") - DB의 1인분 기준중량
     * (food_weight_reference)에 인분수를 곱해서 그램으로 환산. 매칭된 행에 중량이 없으면 같은 음식의
     * 다른 행에서 중량이 적힌 걸 찾아 쓰고, 그것도 없으면 영양성분 기준량(100g/100ml)으로 일단 기록한
     * 뒤 weightEstimated=true로 표시함 - 기록 자체를 실패시키지 않고, 사용자가 그램 수를 고칠 수 있게.
     *
     * @param foodName 조회할 음식명 (검색용으로 정규화된 이름)
     * @param servings 인분수/개수 (기본 1)
     * @return 계산된 영양정보, 음식 자체를 못 찾으면 null
     */
    NutritionInfo lookupByServings(String foodName, double servings);

    /**
     * 매칭이 불확실할 때(MatchTier.FUZZY) 사용자에게 보여줄 후보 음식명 목록.
     * @param foodName 검색어
     * @param limit    최대 후보 개수
     */
    List<String> suggestCandidates(String foodName, int limit);

    record NutritionInfo(
            String foodName,
            double calories,
            double proteinG,
            double carbsG,
            double fatG,
            double amountG,          // 실제 계산에 쓰인 최종 그램수 (인분수 기반이면 환산된 값)
            MatchTier matchTier,     // 몇 단계에서 매칭됐는지 - 프론트 신뢰도 배지용
            boolean weightEstimated  // DB에 1인분 중량이 없어 100g 기준으로 넣은 값인지 (수정 유도용)
    ) {}

    /** DB 매칭 신뢰도 단계. 프론트가 이 값에 따라 배지/후보 UI를 다르게 보여줌 */
    enum MatchTier {
        EXACT_PRODUCT,   // 구체적 제품명(food_name) 정확일치 - 가장 신뢰도 높음
        EXACT_CATEGORY,  // 대표식품명(카테고리) 정확일치
        FUZZY            // LIKE 폴백 - 엉뚱한 항목일 수 있어서 사용자 확인 필요
    }
}
