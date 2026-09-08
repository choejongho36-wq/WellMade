package com.kdt.wellmade.domain.calendar;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.net.URI;
import java.time.Duration;
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

    /**
     * 캐시 유효 기간. 예전엔 만료 없이 들고 있었는데, 임시공휴일이 새로 지정돼도 서버를 껐다
     * 켜기 전까지 반영이 안 됐다(API로 옮긴 이유가 바로 그거였음). 하루 호출 한도가 있는 API라
     * 매번 부를 수도 없으니 반나절로 절충한다.
     */
    private static final Duration CACHE_TTL = Duration.ofHours(12);

    private final String serviceKey;
    private final RestClient holidayRestClient;
    private final ObjectMapper objectMapper;

    /** 월별 조회 결과 캐시. 실패는 넣지 않는다 - 넣으면 한 번 타임아웃 난 달이 계속 비어 보인다. */
    private final Map<String, CachedHolidays> cache = new ConcurrentHashMap<>();

    private record CachedHolidays(Map<String, String> value, long expiresAt) {
        boolean isFresh() {
            return System.currentTimeMillis() < expiresAt;
        }
    }

    public HolidayService(
            @Value("${data-go-kr.holiday-service-key:}") String serviceKey,
            RestClient holidayRestClient,
            ObjectMapper objectMapper
    ) {
        this.serviceKey = serviceKey;
        this.holidayRestClient = holidayRestClient;
        this.objectMapper = objectMapper;
    }

    /**
     * 그 해/월의 공휴일 목록. key="yyyy-MM-dd", value=공휴일 이름. 실패하거나 키 미설정이면 빈 맵.
     *
     * 캐시는 결과만 담고 HTTP 호출은 밖에서 한다 - computeIfAbsent 안에서 블로킹 호출을 돌리면
     * 그 동안 같은 버킷의 다른 달 조회까지 같이 막힌다.
     */
    public Map<String, String> getHolidays(int year, int month) {
        String key = year + "-" + month;
        CachedHolidays cached = cache.get(key);
        if (cached != null && cached.isFresh()) {
            return cached.value();
        }

        Map<String, String> fetched = fetchHolidays(year, month);
        if (fetched == null) {
            // 호출 실패. 캐시하지 않으므로 다음 요청에서 다시 시도한다.
            // 만료된 값이라도 갖고 있으면 그걸 쓴다 - 빈 달력보다 어제 값이 낫다.
            return cached != null ? cached.value() : Map.of();
        }
        cache.put(key, new CachedHolidays(fetched, System.currentTimeMillis() + CACHE_TTL.toMillis()));
        return fetched;
    }

    /** 조회 결과, 실패면 null (빈 맵은 "그 달에 공휴일이 없음"이라는 정상 응답이라 구분해야 함) */
    private Map<String, String> fetchHolidays(int year, int month) {
        if (serviceKey == null || serviceKey.isBlank()) {
            // 키가 없는 건 일시적 실패가 아니므로 빈 결과로 캐시해둔다(매 요청 경고가 찍히지 않게)
            log.warn("data-go-kr.holiday-service-key가 설정되지 않아 공휴일 조회를 건너뜁니다.");
            return Map.of();
        }

        // 공공데이터포털 서비스키는 발급받을 때 이미 URL 인코딩된 문자열이라, UriComponentsBuilder에
        // 넘기면 %가 다시 인코딩돼서(이중 인코딩) 인증 실패가 남. URI.create()로 완성된 문자열을
        // 그대로 URI로 만들어서 재인코딩을 우회함.
        String url = ENDPOINT
                + "?serviceKey=" + serviceKey
                + "&solYear=" + year
                + "&solMonth=" + String.format("%02d", month)
                + "&_type=json"
                + "&numOfRows=50";

        try {
            return parseResponse(holidayRestClient.get().uri(URI.create(url)).retrieve().body(String.class));
        } catch (Exception e) {
            // 예외 메시지와 스택트레이스에는 요청 URL이 통째로 들어있고, 그 URL엔 serviceKey가
            // 박혀 있다. 로그에 키가 남지 않도록 예외 종류만 남긴다.
            log.warn("공휴일 API 호출 실패 (year={}, month={}): {}", year, month, e.getClass().getSimpleName());
            return null;
        }
    }

    /**
     * 특일 정보 응답을 날짜->이름 맵으로. 공공데이터포털 응답은 항목 수에 따라 모양이 달라진다
     * (없음 / 객체 하나 / 배열)는 점이 함정이라 세 경우를 모두 받아준다.
     */
    Map<String, String> parseResponse(String body) throws Exception {
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
