package com.kdt.wellmade.domain.calendar;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 공공데이터포털 "한국천문연구원_특일 정보" API(getRestDeInfo)로 그 달의 공휴일을 조회하는 서비스.
 * 예전엔 Calendar.jsx(프론트)에 연도별로 하드코딩해뒀던 것 - 매년 새 연도를 손으로 추가해야
 * 했고, 지방선거일처럼 그때그때 새로 지정되는 임시공휴일도 반영이 안 됐음.
 *
 * 서비스 키는 공공데이터포털(data.go.kr)에서 "한국천문연구원_특일 정보" API를 활용신청하면
 * 발급됨 - data-go-kr.holiday-service-key(DATA_GO_KR_HOLIDAY_KEY 환경변수)로 주입. 키가
 * 없으면 기능만 조용히 꺼짐(빈 맵 반환) - 달력 자체는 계속 정상 동작해야 하므로.
 */
@Service
public class HolidayService {

    private static final Logger log = LoggerFactory.getLogger(HolidayService.class);

    private static final String ENDPOINT =
            "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo";

    private final String serviceKey;
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();

    // 월별 조회 결과 캐시 - 같은 달을 여러 번 조회해도 외부 API를 다시 호출하지 않음
    // (data.go.kr API는 보통 하루 호출 한도가 있음). 공휴일 지정은 서버를 껐다 켜기 전까지는
    // 안 바뀐다고 보고 만료 없이 그냥 들고 있음.
    private final Map<String, Map<String, String>> cache = new ConcurrentHashMap<>();

    public HolidayService(@Value("${data-go-kr.holiday-service-key:}") String serviceKey) {
        this.serviceKey = serviceKey;
    }

    /** 그 해/월의 공휴일 목록. key="yyyy-MM-dd", value=공휴일 이름. 실패하거나 키 미설정이면 빈 맵. */
    public Map<String, String> getHolidays(int year, int month) {
        return cache.computeIfAbsent(year + "-" + month, k -> fetchHolidays(year, month));
    }

    private Map<String, String> fetchHolidays(int year, int month) {
        if (serviceKey == null || serviceKey.isBlank()) {
            log.warn("data-go-kr.holiday-service-key가 설정되지 않아 공휴일 조회를 건너뜁니다.");
            return Map.of();
        }

        // 공공데이터포털 서비스키는 발급받을 때 이미 URL 인코딩된 문자열이라, RestTemplate의
        // UriComponentsBuilder에 넘기면 %가 다시 인코딩돼서(이중 인코딩) 인증 실패가 남.
        // URI.create()로 완성된 문자열을 그대로 URI로 만들어서 재인코딩을 우회함.
        String url = ENDPOINT
                + "?serviceKey=" + serviceKey
                + "&solYear=" + year
                + "&solMonth=" + String.format("%02d", month)
                + "&_type=json"
                + "&numOfRows=50";

        try {
            String body = restTemplate.getForObject(URI.create(url), String.class);
            return parseResponse(body);
        } catch (Exception e) {
            log.error("공휴일 API 호출 실패 (year={}, month={})", year, month, e);
            return Map.of();
        }
    }

    private Map<String, String> parseResponse(String body) throws Exception {
        JsonNode root = objectMapper.readTree(body);
        JsonNode itemNode = root.path("response").path("body").path("items").path("item");

        Map<String, String> result = new LinkedHashMap<>();
        if (itemNode.isMissingNode() || itemNode.isEmpty()) {
            return result; // 그 달에 공휴일이 하나도 없음 (정상)
        }

        // 항목이 하나뿐이면 배열이 아니라 객체 하나로 내려오는 공공데이터포털 특유의 응답이라 맞춰줌
        if (itemNode.isArray()) {
            itemNode.forEach(item -> putItem(result, item));
        } else {
            putItem(result, itemNode);
        }
        return result;
    }

    private void putItem(Map<String, String> result, JsonNode item) {
        String locdate = item.path("locdate").asText();
        if (locdate.length() != 8) return;
        String dateStr = locdate.substring(0, 4) + "-" + locdate.substring(4, 6) + "-" + locdate.substring(6, 8);
        result.put(dateStr, item.path("dateName").asText());
    }
}
