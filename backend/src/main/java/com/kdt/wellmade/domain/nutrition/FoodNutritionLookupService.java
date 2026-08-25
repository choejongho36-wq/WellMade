package com.kdt.wellmade.domain.nutrition;

/**
 * 영양성분 조회 인터페이스.
 * 지금은 MockFoodNutritionLookupService가 구현하고,
 * 식약처 API 승인 나면 FoodNutritionApiService(실제 구현체)로 교체.
 * 인터페이스가 같으니 이 부분을 쓰는 다른 코드는 수정할 필요 없음.
 */
public interface FoodNutritionLookupService {
 
    /** 
    @param foodName 조회할 음식명 (FoodParsingService가 정규화한 이름)
    @param amountG  섭취량(그램)
    @return 계산된 영양정보, 못 찾으면 null
    */
   
    NutritionInfo lookup(String foodName, double amountG);
 
    record NutritionInfo(
            String foodName,
            double calories,
            double proteinG,
            double carbsG,
            double fatG
    ) {}
}