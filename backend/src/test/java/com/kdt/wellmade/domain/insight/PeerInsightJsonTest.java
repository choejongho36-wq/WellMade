package com.kdt.wellmade.domain.insight;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * 응답 본문이 Jackson 2 트리(JsonNode)로 나가면 안 된다는 것을 고정한다.
 *
 * Spring Boot 4.1의 응답 컨버터는 Jackson 3(tools.jackson)인데 코드가 쓰는 JsonNode는
 * Jackson 2(com.fasterxml.jackson)다. 서로 다른 라이브러리라 Jackson 3은 이 객체를 트리로
 * 알아보지 못하고 평범한 객체로 취급해서, 예외도 없이 내부 판별자만 담긴 JSON을 내보낸다.
 * 조용히 깨지는 종류라 눈으로는 못 잡는다 - 그래서 테스트로 박아둔다.
 */
class PeerInsightJsonTest {

    private final ObjectMapper jackson2 = new ObjectMapper();
    private final tools.jackson.databind.ObjectMapper jackson3 = new tools.jackson.databind.ObjectMapper();

    private ObjectNode sampleInsight() {
        ObjectNode node = jackson2.createObjectNode();
        node.put("category", "정상");
        node.put("percentile", 42);
        node.put("peer_mean", 23.1);
        return node;
    }

    /** 이게 실제로 났던 증상이다 - 값은 사라지고 isArray/isEmpty 같은 판별자만 나갔다 */
    @Test
    void jackson2TreeSerializedByJackson3LosesEverything() {
        String written = jackson3.writeValueAsString(sampleInsight());

        assertFalse(written.contains("category"), written);
        assertFalse(written.contains("정상"), written);
        assertTrue(written.contains("bigDecimal"), written);
    }

    /** 컨트롤러가 내보내는 형태(Map)는 어느 쪽 Jackson이 써도 결과가 같다 */
    @Test
    void mapConvertedFromTheTreeSurvivesJackson3() throws Exception {
        Map<String, Object> body = jackson2.convertValue(sampleInsight(), new TypeReference<Map<String, Object>>() {});

        String written = jackson3.writeValueAsString(body);

        assertTrue(written.contains("\"category\":\"정상\""), written);
        assertTrue(written.contains("\"percentile\":42"), written);
        assertTrue(written.contains("\"peer_mean\":23.1"), written);
        assertEquals(jackson2.writeValueAsString(body), written);
    }

    /** 중첩된 객체·배열도 그대로 살아남아야 한다(끼니별 비교 배열 등) */
    @Test
    void nestedStructuresSurviveToo() {
        ObjectNode node = sampleInsight();
        node.putObject("target").put("kcal", 2100);
        node.putArray("meals").add("아침").add("점심");

        Map<String, Object> body = jackson2.convertValue(node, new TypeReference<Map<String, Object>>() {});
        String written = jackson3.writeValueAsString(body);

        assertTrue(written.contains("\"kcal\":2100"), written);
        assertTrue(written.contains("[\"아침\",\"점심\"]"), written);
    }
}
