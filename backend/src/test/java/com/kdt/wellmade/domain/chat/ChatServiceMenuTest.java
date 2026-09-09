package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 메뉴 경로는 기록이 없을 때 LLM을 아예 부르지 않고 도구가 준 문구를 그대로 사용자에게 보여준다.
 * 그 판정이 틀리면 (a) 빈 결과인데 LLM이 불려서 지어내거나 (b) 값이 있는데 note를 답으로 내보낸다.
 */
class ChatServiceMenuTest {

    private final ChatService service = new ChatService(null, null, null, null, null, null, null, new ObjectMapper());

    @Test
    void emptyMealsReturnsUserFacingNote() {
        String result = """
                {"date":"2026-08-31","meals":[],"note":"2026-08-31에 기록된 식사가 없어요.",\
                "instruction":"없다고만 답하고 식단을 지어내지 마세요."}""";
        // 모델에게만 필요한 instruction이 사용자에게 새어나가면 안 된다
        assertEquals("2026-08-31에 기록된 식사가 없어요.", service.emptyResultMessage(result));
    }

    @Test
    void errorIsShownAsIs() {
        String result = "{\"error\":\"인바디 정보가 없어서 목표 섭취량을 계산할 수 없어요.\"}";
        assertEquals("인바디 정보가 없어서 목표 섭취량을 계산할 수 없어요.", service.emptyResultMessage(result));
    }

    @Test
    void resultWithDataFallsThroughToLlm() {
        String result = """
                {"date":"2026-08-31","meals":[{"mealType":"아침","menuName":"계란","kcal":150}],\
                "totalKcal":"150kcal"}""";
        assertNull(service.emptyResultMessage(result));
    }

    /**
     * 인바디가 1건뿐이면 추세를 말할 수 없다. 모델에게 맡기면 "최근 몇 번의 측정 결과는 변함이
     * 없네요"처럼 비교를 지어내므로(실측 8/8), 메뉴 경로에서는 note를 그대로 답으로 쓴다.
     */
    @Test
    void singleInbodyRecordAnswersWithoutLlm() {
        String result = """
                {"records":[{"date":"2026-08-28","weightKg":76.5}],"recordCount":1,\
                "note":"인바디 기록이 1건뿐이라 체중 추세는 아직 알 수 없어요. 최근 측정값은 76.5kg입니다."}""";
        assertEquals("인바디 기록이 1건뿐이라 체중 추세는 아직 알 수 없어요. 최근 측정값은 76.5kg입니다.",
                service.emptyResultMessage(result));
    }

    /** 2건 이상이면 추세를 말할 수 있으므로 LLM이 문장으로 옮긴다 */
    @Test
    void multipleInbodyRecordsFallThroughToLlm() {
        String result = """
                {"records":[{"date":"2026-07-01","weightKg":78.2},{"date":"2026-08-01","weightKg":76.5}],\
                "recordCount":2,"weightChange":"-1.7kg (78.2kg -> 76.5kg)"}""";
        assertNull(service.emptyResultMessage(result));
    }

    @Test
    void malformedResultFallsThroughInsteadOfCrashing() {
        assertNull(service.emptyResultMessage("보통은 JSON이지만 아닐 수도 있다"));
    }

    /**
     * note는 두 뜻으로 쓰인다 - 운동 추천에서는 후보가 있을 때의 부연이기도 하다. 후보가 있으면
     * note가 붙어 있어도 데이터가 있는 것이다. 이 판정이 틀리면 후보를 버리고 안내문만 답이 된다.
     */
    @Test
    void recommendationWithCandidatesIsNotEmptyEvenWithNote() {
        String result = """
                {"body_part_ko":"어깨","candidates":[{"name":"덤벨 숄더 프레스","sets_reps":"3세트 x 12회"}],\
                "note":"이 부위는 기구 없이 하는 동작이 많지 않아 장비 조건을 넓혀서 골랐어요."}""";
        assertNull(service.emptyResultMessage(result));
    }

    @Test
    void recommendationWithoutCandidatesShowsTheNote() {
        String result = """
                {"body_part":"","matched":0,"candidates":[],"note":"어느 부위 운동인지 알려주시면 추천해드릴게요."}""";
        assertEquals("어느 부위 운동인지 알려주시면 추천해드릴게요.", service.emptyResultMessage(result));
    }

    @Test
    void foundExerciseDetailIsNotEmpty() {
        String result = """
                {"found":true,"name":"덤벨 런지","instructions_ko":"양손에 덤벨을 들고 한 발을 앞으로 내딛습니다."}""";
        assertNull(service.emptyResultMessage(result));
    }

    @Test
    void missingExerciseDetailShowsTheNote() {
        String result = """
                {"found":false,"note":"어떤 운동인지 찾지 못했어요. 추천해드린 목록에 있는 이름으로 물어봐 주세요."}""";
        assertEquals("어떤 운동인지 찾지 못했어요. 추천해드린 목록에 있는 이름으로 물어봐 주세요.",
                service.emptyResultMessage(result));
    }
}
