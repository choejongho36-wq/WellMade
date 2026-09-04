package com.kdt.wellmade.domain.chat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 추천 결과에 붙는 국민체력100 영상 버튼.
 *
 * 영상은 운동이 아니라 '동작'으로 이어지므로 서로 다른 운동이 같은 영상을 가리킬 수 있다
 * (잭 점프 / 스타 점프 -> 같은 점핑잭 영상). 그대로 두면 같은 버튼이 두 번 붙는다.
 */
class ChatToolExecutorVideoLinkTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    // videoLinks는 응답 JSON만 보므로 주입 대상이 필요 없다
    private final ChatToolExecutor executor =
            new ChatToolExecutor(null, null, null, null, null, new ObjectMapper(), null, null, null);

    private JsonNode response(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    @Test
    void sameVideoIsLinkedOnlyOnce() {
        JsonNode body = response("""
                {"candidates":[
                 {"name":"잭 점프","difficulty":"초급","related_video":
                  {"name":"점핑잭","level":"초급","place":"실내","video_url":"http://v/1.mp4"}},
                 {"name":"스타 점프","difficulty":"초급","related_video":
                  {"name":"점핑잭","level":"초급","place":"실내","video_url":"http://v/1.mp4"}}]}""");

        List<Map<String, String>> links = executor.videoLinks(body);

        assertEquals(1, links.size());
        assertEquals("http://v/1.mp4", links.get(0).get("url"));
    }

    /** 영상 데이터에 초급이 적어서 "초급 운동 ▶ (중급) 영상"이 자주 나온다 - 그 조합은 혼란만 준다 */
    @Test
    void videoLevelIsHiddenWhenItDiffersFromTheExercise() {
        JsonNode body = response("""
                {"candidates":[
                 {"name":"3/4 싯업","difficulty":"초급","related_video":
                  {"name":"윗몸 말아 올리기","level":"중급","place":"실내","tool":"매트","video_url":"http://v/2.mp4"}}]}""");

        String label = executor.videoLinks(body).get(0).get("label");

        assertFalse(label.contains("중급"), label);
        assertTrue(label.contains("실내") && label.contains("매트"), label);
    }

    @Test
    void matchingLevelIsShown() {
        JsonNode body = response("""
                {"candidates":[
                 {"name":"닐링 푸시업","difficulty":"초급","related_video":
                  {"name":"팔 굽혀 펴기","level":"초급","place":"실내","video_url":"http://v/3.mp4"}}]}""");

        assertTrue(executor.videoLinks(body).get(0).get("label").contains("초급"));
    }

    @Test
    void candidatesWithoutVideoAddNoLink() {
        JsonNode body = response("""
                {"candidates":[{"name":"덤벨 런지","difficulty":"초급","related_video":null}]}""");

        assertTrue(executor.videoLinks(body).isEmpty());
    }
}
