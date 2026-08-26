package com.kdt.wellmade.domain.nutrition;


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