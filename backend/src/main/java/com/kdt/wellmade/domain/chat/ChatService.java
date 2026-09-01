package com.kdt.wellmade.domain.chat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.kdt.wellmade.domain.inbody.InbodyRecord;
import com.kdt.wellmade.domain.inbody.InbodyService;
import com.kdt.wellmade.domain.mapage.Gender;
import com.kdt.wellmade.domain.mapage.Goal;
import com.kdt.wellmade.domain.mapage.UserProfile;
import com.kdt.wellmade.domain.mapage.UserProfileService;
import com.kdt.wellmade.domain.nutrition.MealLoggingService;
import com.kdt.wellmade.domain.nutrition.NutrientTarget;
import com.kdt.wellmade.domain.nutrition.NutrientTargetCalculator;
import com.kdt.wellmade.domain.user.User;
import com.kdt.wellmade.global.exception.ExternalServiceException;

/**
 * 로컬 Ollama(Qwen2.5-7B-Instruct)에 사용자의 goal/인바디 값을 시스템 프롬프트로 얹어 채팅을 중계하는 서비스.
 *
 * 대화 이력은 이제 DB(chat_messages)가 진실 소스임. 예전엔 프론트가 매 요청마다 전체 대화 배열을
 * 그대로 보내고 서버는 그걸 신뢰하는 구조였어서, role을 위조한 메시지를 끼워넣을 수 있었고
 * 새로고침하면 이력이 통째로 사라졌음. 이제 클라이언트는 새로 보낸 사용자 메시지 하나만 전달하고,
 * 서버가 최근 이력을 불러와 컨텍스트를 구성한 뒤 이번 턴(사용자+응답)을 저장함.
 *
 * 일반 채팅(reply)은 툴콜링을 지원함 - 모델이 "어제 뭐 먹었지?" 같은 질문에 스스로 get_meals_for_date
 * 도구를 호출해서 실제 DB 값을 확인한 뒤 답하게 함. 계산이 필요한 질문(목표 섭취량 등)도 마찬가지로
 * calculate_nutrient_target 도구가 계산한 결정론적 수치를 인용하게 하고, 모델이 암산하지 않게 함.
 * nutrientAdvice()는 원래도 계산을 서버가 다 해서 프롬프트에 박아넣는 방식이라 툴콜링이 필요 없어서 그대로 둠.
 */
@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    // Ollama에 보낼 컨텍스트로 불러올 최근 이력 개수. 매 턴 이만큼을 프리필하므로 응답 속도에 직결됨
    // (T4 기준 30개는 프리필만 10초 넘게 걸림). 6번 주고받은 맥락이면 대부분의 상담엔 충분함.
    private static final int CONTEXT_HISTORY_LIMIT = 8;
    // 이력 1건이 그대로 들어가면 컨텍스트를 다 잡아먹는다(사용자 메시지는 최대 2000자).
    // 맥락 유지에는 앞부분이면 충분하므로 잘라서 넣는다 - 화면에 보여주는 이력은 자르지 않음
    private static final int CONTEXT_MESSAGE_MAX_CHARS = 800;
    // 프론트에 "이전 대화 이어서 보기"용으로 내려줄 이력 개수
    private static final int DISPLAY_HISTORY_LIMIT = 100;
    private static final int MAX_CONTENT_LENGTH = 2000;
    // 1라운드 본문을 사용자에게 흘리기 전에 도구 호출 텍스트인지 판별할 만큼만 붙잡아두는 길이
    private static final int TOOLCALL_SNIFF_CHARS = 48;

    // 예전 프롬프트는 역할을 "식단과 운동을 추천하는 어시스턴트"로 정의해서, 모델이 묻지도 않은
    // 추천을 매번 덧붙였다("안녕" -> 하루 식단표). 또 기록이 없을 때 어떻게 답할지 정해두지 않아
    // 없는 식단을 지어내기도 했다. 그래서 역할을 "물어본 것에 답하는" 쪽으로 좁히고, 하지 말아야
    // 할 행동을 명시적으로 금지한다.
    private static final String SYSTEM_PROMPT = """
            당신은 사용자의 식단 기록과 인바디 수치를 확인해주는 헬스케어 어시스턴트입니다.
            의학적 진단은 하지 않고 생활습관 수준의 정보만 다룹니다.

            답변 규칙:
            1. 사용자가 물어본 것에만 답하세요. 묻지 않은 추천, 제안, 계획, 후속 질문을 덧붙이지 마세요.
            2. 식단이나 운동 추천은 사용자가 명시적으로 요청했을 때만 하세요.
            3. 답변은 2~4문장으로 짧게. 마크다운 헤더/표/목록/이모지 없이 대화체로 쓰세요.
            4. 반드시 한국어로만 답하세요. 다른 언어를 섞지 마세요.
            5. 직전에 한 답변을 다시 반복하지 마세요.
            6. 인사에는 한 문장으로 인사만 하세요. 무엇을 확인할지 되묻거나 제안하지 마세요.

            데이터 규칙:
            7. 식사 기록, 섭취량, 목표 섭취량, 인바디 수치는 절대 추측하거나 암산하지 말고,
               제공된 도구를 호출해 실제 값을 확인한 뒤 그 값을 인용해서 답하세요.
               "확인해볼게요", "불러오는 중입니다" 같은 예고만 쓰고 끝내지 말고 도구를 실제로 호출하세요.
            8. 도구 결과가 비어 있으면 "기록이 없다"고만 답하세요. 없는 기록을 지어내거나,
               대신 식단을 만들어 제안하지 마세요.
            9. 숫자를 직접 더하지 마세요. 합계는 도구가 돌려준 값(totalKcal, totalCalories 등)을
               그대로 인용하세요.
            """;

    private static final Map<Goal, String> GOAL_LABEL = Map.of(
            Goal.LOSE, "체중감량",
            Goal.GAIN, "근성장(벌크업)",
            Goal.MAINTAIN, "체형 유지/건강관리"
    );

    /** Ollama에 넘길 도구 스펙 (OpenAI function-calling 호환 형식). Qwen2.5-Instruct가 이 형식을 지원함. */
    private static final List<Map<String, Object>> TOOLS = List.of(
            toolDef(
                    "get_meals_for_date",
                    "특정 날짜에 사용자가 기록한 식사 목록(끼니 종류, 메뉴명, 칼로리)을 가져온다. "
                  + "'어제 뭐 먹었지', '오늘 아침에 뭐 먹었더라' 같은 질문에는 반드시 이 도구로 실제 기록을 "
                  + "확인하고 답할 것 - 절대 추측하지 말 것.",
                    Map.of("date", Map.of(
                            "type", "string",
                            "description", "조회할 날짜, yyyy-MM-dd 형식. '어제'/'오늘'처럼 상대적인 표현은 "
                                    + "시스템 프롬프트에 적힌 오늘 날짜를 기준으로 직접 계산해서 넣을 것."
                    )),
                    List.of("date")
            ),
            toolDef(
                    "get_daily_total",
                    "특정 날짜의 총 섭취 칼로리/단백질/탄수화물/지방 합계를 가져온다.",
                    Map.of("date", Map.of(
                            "type", "string",
                            "description", "조회할 날짜, yyyy-MM-dd 형식."
                    )),
                    List.of("date")
            ),
            toolDef(
                    "get_inbody_history",
                    "최근 인바디 측정 기록을 오래된 순으로 여러 건 가져온다(체중/골격근량/체지방률/BMI). "
                  + "'요즘 체중 변화 어때', '살 빠지고 있어?'처럼 추세를 물어볼 때 인바디 한 건(최신값)만으로 "
                  + "답하지 말고 이 도구로 여러 건을 확인할 것.",
                    Map.of("limit", Map.of(
                            "type", "integer",
                            "description", "가져올 기록 개수. 생략하면 5, 최대 10."
                    )),
                    List.of()
            ),
            toolDef(
                    "get_bmi_peer_comparison",
                    "사용자의 최근 BMI가 같은 성별·연령대(국민건강통계) 안에서 어디쯤인지 백분위와 비만도 "
                  + "분류를 가져온다. '내 BMI 또래보다 높아?', '남들이랑 비교하면 어때?'처럼 또래 비교를 "
                  + "물어볼 때 쓸 것 - 절대 추측하지 말 것.",
                    Map.of(),
                    List.of()
            ),
            toolDef(
                    "get_nutrition_peer_comparison",
                    "특정 날짜의 섭취량이 같은 성별·연령대 평균(국민건강통계) 대비 몇 %인지 가져온다. "
                  + "'또래보다 많이 먹었나', '남들 평균이랑 비교해줘' 같은 질문에 쓸 것. 목표 대비 비교는 "
                  + "calculate_nutrient_target이고, 이 도구는 또래 대비 비교라 서로 다르다.",
                    Map.of("date", Map.of(
                            "type", "string",
                            "description", "조회할 날짜, yyyy-MM-dd 형식. 생략하면 오늘."
                    )),
                    List.of()
            ),
            toolDef(
                    "calculate_nutrient_target",
                    "사용자의 목표와 최근 인바디 수치를 바탕으로 하루 목표 칼로리/단백질/탄수화물/지방을 "
                  + "계산한다. 목표 섭취량을 묻는 질문에는 반드시 이 도구로 계산된 값을 인용할 것 - 직접 "
                  + "암산하지 말 것.",
                    Map.of(),
                    List.of()
            )
    );

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final MealLoggingService mealLoggingService;
    private final ChatMessageRepository chatMessageRepository;
    private final NutrientTargetCalculator nutrientTargetCalculator;
    private final RestClient ollamaRestClient;
    private final RestClient aiRestClient;
    private final String model;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ChatService(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            ChatMessageRepository chatMessageRepository,
            NutrientTargetCalculator nutrientTargetCalculator,
            RestClient ollamaRestClient,
            RestClient aiRestClient,
            @Value("${ollama.model}") String model
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.chatMessageRepository = chatMessageRepository;
        this.nutrientTargetCalculator = nutrientTargetCalculator;
        this.ollamaRestClient = ollamaRestClient;
        this.aiRestClient = aiRestClient;
        this.model = model;
    }

    /**
     * 새 사용자 메시지 하나를 받아서, DB에 저장된 최근 이력 + 이번 메시지로 컨텍스트를 구성하고
     * 최종 답변을 토큰 단위로 {@code onDelta}에 흘려보낸다. 스트림이 끝나면 이번 턴을 저장한다.
     *
     * 도구 호출이 필요한 질문은 먼저 (비스트리밍) 도구를 해소한 뒤 최종 답변만 스트리밍한다.
     */
    public void replyStream(User user, String rawMessage, Consumer<String> onDelta) {
        String userMessage = validateAndTrim(rawMessage);

        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user)));
        for (ChatMessageEntity h : loadRecentHistory(user, CONTEXT_HISTORY_LIMIT)) {
            messages.add(new OllamaMessage(h.getRole(), truncateForContext(h.getContent()), null, null));
        }
        messages.add(OllamaMessage.user(userMessage));

        StringBuilder full = new StringBuilder();
        resolveToolsThenStream(user, messages, delta -> {
            full.append(delta);
            onDelta.accept(delta);
        });

        // 모델이 아무것도 내놓지 않는 경우가 드물게 있다(도구도 안 부르고 content도 비어서 옴).
        // 그대로 두면 화면에 빈 말풍선만 남고 이력에도 빈 답변이 저장되므로 안내 문구로 대체한다.
        if (full.isEmpty()) {
            String fallback = "답변을 만들지 못했어요. 조금 더 구체적으로 다시 물어봐 주세요.";
            full.append(fallback);
            onDelta.accept(fallback);
        }

        // Ollama 호출(느릴 수 있음)이 끝난 뒤에 저장함 - 트랜잭션을 외부 HTTP 호출 동안 붙잡고
        // 있지 않으려는 의도. 두 저장 사이에 실패가 나도 사용자 메시지 한 줄만 남는 정도라 치명적이지 않음.
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("user").content(userMessage).build());
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("assistant").content(full.toString()).build());
    }

    /**
     * 메뉴 버튼 하나가 서버에서 대신 호출할 도구. 사용자가 버튼으로 의도를 이미 골랐는데 그걸
     * 자연어 문장으로 바꿔 모델에게 던지고 모델이 다시 도구를 고르게 하면, 그 "고르기" 단계에서
     * 확률적으로 실패한다(툴콜을 텍스트로 흘리거나 아예 안 부름 - 실측됨). 메뉴에서는 그 단계를
     * 통째로 없앤다.
     *
     * userLabel은 이력에 남길 사용자 문장이다 - 프론트가 낙관적으로 먼저 그리는 말풍선
     * (ChatDrawer.jsx의 CHAT_MENU_ITEMS.send)과 문구를 맞춰야 새로고침 후에도 같아 보인다.
     */
    private record MenuTool(String userLabel, String toolName, Map<String, Object> arguments) {}

    private MenuTool menuTool(String menuId) {
        LocalDate today = LocalDate.now();
        return switch (menuId) {
            case "meals-today" -> new MenuTool(
                    "오늘 뭐 먹었지?", "get_meals_for_date", Map.of("date", today.toString()));
            case "meals-yesterday" -> new MenuTool(
                    "어제 먹은 거 보여줘", "get_meals_for_date", Map.of("date", today.minusDays(1).toString()));
            case "total-today" -> new MenuTool(
                    "오늘 총 섭취량 알려줘", "get_daily_total", Map.of("date", today.toString()));
            case "target" -> new MenuTool(
                    "내 목표 섭취량 알려줘", "calculate_nutrient_target", Map.of());
            case "inbody-trend" -> new MenuTool(
                    "요즘 체중 변화 어때?", "get_inbody_history", Map.of("limit", 5));
            default -> null;
        };
    }

    /**
     * 메뉴 버튼 답변. 서버가 도구를 직접 실행하고, LLM은 그 결과를 문장으로 옮기는 일만 한다.
     *
     * 기록이 없으면 LLM을 아예 부르지 않는다 - 지어낼 여지가 구조적으로 없어지고, 응답도 즉시 나간다.
     * (도구가 돌려주는 note/error는 그래서 사람이 읽는 문장으로 쓰고, 모델에게만 필요한 지시는
     * instruction 키로 따로 뺐다.)
     */
    public String menuReply(User user, Long userId, String menuId) {
        MenuTool menu = menuTool(menuId);
        if (menu == null) {
            throw new IllegalArgumentException("알 수 없는 메뉴입니다: " + menuId);
        }

        String toolResult = executeTool(user, menu.toolName(), menu.arguments());
        String reply = emptyResultMessage(toolResult);
        if (reply == null) {
            reply = phraseToolResult(user, menu, toolResult);
        }

        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("user").content(menu.userLabel()).build());
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("assistant").content(reply).build());
        return reply;
    }

    /** 도구 결과가 "데이터 없음"이면 사용자에게 그대로 보여줄 문구, 데이터가 있으면 null */
    String emptyResultMessage(String toolResult) {
        try {
            JsonNode node = objectMapper.readTree(toolResult);
            for (String key : new String[] {"error", "note"}) {
                JsonNode value = node.get(key);
                if (value != null && !value.asText("").isBlank()) {
                    return value.asText();
                }
            }
        } catch (Exception e) {
            log.warn("메뉴 도구 결과를 읽지 못함", e);
        }
        return null;
    }

    /**
     * 도구 결과를 문장으로만 옮기게 한다. 모델이 도구를 호출한 뒤와 똑같은 형태의 컨텍스트를
     * 만들어 주므로(assistant tool_calls + tool 결과), 일반 대화의 마지막 라운드와 같은 경로다.
     */
    private String phraseToolResult(User user, MenuTool menu, String toolResult) {
        String callId = "menu-" + menu.toolName();
        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user)));
        messages.add(OllamaMessage.user(menu.userLabel()));
        messages.add(new OllamaMessage("assistant", "", List.of(new OllamaMessage.ToolCall(
                callId, new OllamaMessage.FunctionCall(menu.toolName(), menu.arguments()))), null));
        messages.add(OllamaMessage.tool(toolResult, callId));

        String reply = chatCompletion(messages, false).content();
        return reply == null || reply.isBlank()
                ? "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
                : reply;
    }

    /**
     * 이 사용자의 대화 이력을 전부 지운다. 이력은 다음 답변의 컨텍스트로도 쓰이므로
     * (loadRecentHistory) 지우고 나면 말투/맥락까지 새 대화처럼 초기화된다.
     */
    @Transactional
    public void clearHistory(User user) {
        chatMessageRepository.deleteByUser(user);
    }

    /** 프론트에서 드로어를 열 때 "이전 대화 이어보기"용으로 내려줄 이력 (오래된 순) */
    public List<ChatHistoryItem> getHistory(User user) {
        return loadRecentHistory(user, DISPLAY_HISTORY_LIMIT).stream()
                .map(h -> new ChatHistoryItem(h.getRole(), h.getContent(), h.getCreatedAt()))
                .toList();
    }

    /** 최신순으로 limit건 가져온 뒤 시간순으로 뒤집어서 반환 */
    private List<ChatMessageEntity> loadRecentHistory(User user, int limit) {
        List<ChatMessageEntity> recentFirst =
                chatMessageRepository.findByUserOrderByCreatedAtDesc(user, PageRequest.of(0, limit));
        List<ChatMessageEntity> chronological = new ArrayList<>(recentFirst);
        Collections.reverse(chronological);
        return chronological;
    }

    /**
     * 컨텍스트에 넣을 이력 1건을 잘라낸다. num_ctx를 넘기면 Ollama가 앞쪽(=시스템 프롬프트)부터
     * 버리기 때문에, 대화가 길어지면 답변 규칙이 통째로 사라진다. 그걸 막기 위한 상한.
     */
    private String truncateForContext(String content) {
        if (content == null) {
            return "";
        }
        return content.length() <= CONTEXT_MESSAGE_MAX_CHARS
                ? content
                : content.substring(0, CONTEXT_MESSAGE_MAX_CHARS) + "...";
    }

    /** 빈 메시지 거부 + 길이 상한. 예전엔 클라이언트가 배열 통째로 보내서 role 위조가 가능했지만,
     *  이제 문자열 하나만 받으므로 검증할 것도 이 정도로 단순해짐. */
    private String validateAndTrim(String rawMessage) {
        if (rawMessage == null || rawMessage.isBlank()) {
            throw new IllegalArgumentException("메시지를 입력해주세요.");
        }
        String trimmed = rawMessage.trim();
        return trimmed.length() > MAX_CONTENT_LENGTH ? trimmed.substring(0, MAX_CONTENT_LENGTH) : trimmed;
    }

    /**
     * 1) tools를 포함해 스트리밍으로 호출한다. 도구를 안 부르는 질문(인사·잡담)이 대부분인데,
     *    예전엔 이 호출만 비스트리밍이라 그런 질문은 생성이 끝날 때까지 화면이 비어 있었다.
     * 2) 도구를 불렀으면 전부 실행해 결과를 이어붙이고, tools 없이 한 번 더 스트리밍한다.
     *
     * 모델이 본문을 조금 흘린 뒤에 도구를 부르는 경우(드묾)에는 그 앞부분이 화면에 남은 채
     * 최종 답변이 이어진다. 매 응답을 도구 호출 여부가 확정될 때까지 붙잡아두면 스트리밍을
     * 하는 의미가 없어지므로, 흔한 경우(도구 호출은 본문 없이 옴)를 우선했다.
     *
     * 순차적으로 여러 번 도구를 불러야 하는 질문은 지원하지 않는다(이 앱의 도구는 한 라운드에서
     * 병렬 호출로 충분함). tools를 뺀 마지막 호출이라 모델은 반드시 텍스트로 답한다.
     */
    private void resolveToolsThenStream(User user, List<OllamaMessage> messages, Consumer<String> onDelta) {
        // 1라운드 본문은 앞부분만 붙잡아두고 흘린다. Qwen이 도구 호출을 구조화된 tool_calls 대신
        // <tool_call>{"name":...} 텍스트로 흘리는 턴이 있는데(재현됨), 그대로 스트리밍하면 화면에
        // JSON이 뜬다. 도구를 부를지는 본문 앞부분만 보면 판별돼서, 홀드 비용은 몇 백 ms 수준이다.
        StringBuilder held = new StringBuilder();
        boolean[] releasedToUser = {false};
        StreamResult first = chatCompletionStream(messages, true, delta -> {
            if (releasedToUser[0]) {
                onDelta.accept(delta);
                return;
            }
            held.append(delta);
            if (held.length() >= TOOLCALL_SNIFF_CHARS && !looksLikeToolCallText(held.toString())) {
                releasedToUser[0] = true;
                onDelta.accept(held.toString());
            }
        });

        List<OllamaMessage.ToolCall> toolCalls = first.toolCalls().isEmpty()
                ? parseToolCallsFromText(first.content())
                : first.toolCalls();

        if (toolCalls.isEmpty()) {
            // 도구 없이 답한 턴(인사·잡담). 짧아서 아직 못 내보낸 앞부분을 마저 흘린다.
            if (!releasedToUser[0]) {
                onDelta.accept(held.toString());
            }
            return;
        }

        // 도구를 부르는 턴이면 홀드분(툴콜 텍스트나 "확인해볼게요" 예고)은 화면에도 컨텍스트에도 넣지 않는다.
        messages.add(new OllamaMessage("assistant", releasedToUser[0] ? first.content() : "", toolCalls, null));
        for (OllamaMessage.ToolCall call : toolCalls) {
            String result = executeTool(user, call.function().name(), call.function().arguments());
            messages.add(OllamaMessage.tool(result, call.id()));
        }

        chatCompletionStream(messages, false, onDelta);
    }

    /** 홀드 중인 본문이 모델이 텍스트로 흘린 도구 호출인지. 정상 답변이 이렇게 시작할 일은 없다. */
    boolean looksLikeToolCallText(String content) {
        return content.contains("<tool_call>") || content.contains("\"name\"");
    }

    /**
     * Ollama가 파싱하지 못하고 본문으로 흘려보낸 도구 호출을 회수한다. 앞뒤에 잡토큰(`leton`,
     * `</tool_call>`)이 붙어 나오므로 첫 '{'부터 마지막 '}'까지만 떼어 파싱한다.
     * 실패하면 빈 목록 - 그냥 도구 없이 답한 턴으로 처리된다.
     */
    List<OllamaMessage.ToolCall> parseToolCallsFromText(String content) {
        int start = content.indexOf('{');
        int end = content.lastIndexOf('}');
        if (start < 0 || end <= start) {
            return List.of();
        }
        try {
            JsonNode node = objectMapper.readTree(content.substring(start, end + 1));
            String name = node.path("name").asText("");
            if (name.isEmpty()) {
                return List.of();
            }
            Map<String, Object> arguments = objectMapper.convertValue(
                    node.path("arguments"), new TypeReference<Map<String, Object>>() {});
            log.warn("모델이 도구 호출을 본문 텍스트로 흘려서 회수함: {}", name);
            return List.of(new OllamaMessage.ToolCall(null, new OllamaMessage.FunctionCall(name, arguments)));
        } catch (Exception e) {
            return List.of();
        }
    }

    private String executeTool(User user, String name, Map<String, Object> arguments) {
        try {
            return switch (name) {
                case "get_meals_for_date" -> toolGetMealsForDate(user.getId(), arguments);
                case "get_daily_total" -> toolGetDailyTotal(user.getId(), arguments);
                case "get_inbody_history" -> toolGetInbodyHistory(user, arguments);
                case "get_bmi_peer_comparison" -> toolGetBmiPeerComparison(user);
                case "get_nutrition_peer_comparison" -> toolGetNutritionPeerComparison(user, user.getId(), arguments);
                case "calculate_nutrient_target" -> toolCalculateNutrientTarget(user);
                default -> toJson(Map.of("error", "알 수 없는 도구입니다: " + name));
            };
        } catch (Exception e) {
            log.error("도구 실행 실패: {}", name, e);
            return toJson(Map.of("error", "도구 실행 중 문제가 발생했어요."));
        }
    }

    private String toolGetMealsForDate(Long userId, Map<String, Object> args) {
        LocalDate date = parseDateArgOrToday(args);
        List<Map<String, Object>> meals = mealLoggingService.getMealsForDate(userId, date);

        List<Map<String, Object>> simplified = meals.stream()
                .map(m -> Map.<String, Object>of(
                        "mealType", String.valueOf(m.get("meal_type")),
                        "menuName", String.valueOf(m.get("menu_name")),
                        "kcal", m.get("kcal")
                ))
                .toList();

        if (simplified.isEmpty()) {
            // 빈 배열만 돌려주면 모델이 그걸 무시하고 식단을 지어낸다. 문장으로 못 박아준다
            return toJson(Map.of("date", date.toString(), "meals", List.of(),
                    "note", date + "에 기록된 식사가 없어요.",
                    "instruction", "없다고만 답하고 식단을 지어내지 마세요."));
        }
        // 합계를 같이 넘긴다 - 없으면 모델이 끼니별 칼로리를 직접 더하다 틀린다(실제로 재현됨).
        // 더할 일 자체를 없애는 게 프롬프트로 금지하는 것보다 확실하다
        long totalKcal = meals.stream()
                .map(m -> m.get("kcal"))
                .filter(Number.class::isInstance)
                .mapToLong(k -> ((Number) k).longValue())
                .sum();
        // 숫자로 주면 모델이 한국어로 읽어내다 표기를 섞어버리는 경우가 있어(실제로 재현됨),
        // 그대로 복사해 쓰면 되는 완성된 문자열로 넘긴다
        return toJson(Map.of("date", date.toString(), "meals", simplified,
                "totalKcal", String.format("%,dkcal", totalKcal)));
    }

    private String toolGetDailyTotal(Long userId, Map<String, Object> args) {
        LocalDate date = parseDateArgOrToday(args);
        MealLoggingService.DailyTotal total = mealLoggingService.getTotalForDate(userId, date);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("date", date.toString());
        result.put("totalCalories", total.totalCalories());
        result.put("totalProteinG", total.totalProteinG());
        result.put("totalCarbsG", total.totalCarbsG());
        result.put("totalFatG", total.totalFatG());
        result.put("mealCount", total.mealCount());
        if (total.mealCount() == 0) {
            result.put("note", date + "에 기록된 식사가 없어요.");
            result.put("instruction", "없다고만 답하고 수치를 지어내지 마세요.");
        }
        return toJson(result);
    }

    private String toolGetInbodyHistory(User user, Map<String, Object> args) {
        int limit = argInt(args, "limit", 5);
        List<InbodyRecord> history = inbodyService.getHistory(user, limit);

        if (history.isEmpty()) {
            return toJson(Map.of("records", List.of(), "note", "등록된 인바디 기록이 없어요."));
        }

        List<Map<String, Object>> records = history.stream()
                // 최신순으로 조회되므로, 추세를 시간 순서대로 읽기 쉽게 오래된 것부터 정렬해서 돌려줌
                .sorted(Comparator.comparing(InbodyRecord::getCreatedAt))
                .map(r -> {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("date", r.getCreatedAt().toLocalDate().toString());
                    m.put("weightKg", r.getWeightKg());
                    m.put("skeletalMuscleMassKg", r.getSkeletalMuscleMassKg());
                    m.put("bodyFatPercentage", r.getBodyFatPercentage());
                    m.put("bmi", r.getBmi());
                    return m;
                })
                .toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("records", records);
        // 개수를 명시하지 않으면 모델이 자기가 넘긴 limit(기본 5)을 결과 개수로 착각한다
        result.put("recordCount", records.size());

        Double first = history.get(history.size() - 1).getWeightKg();
        Double last = history.get(0).getWeightKg();
        if (records.size() == 1) {
            // 1건인데도 "최근 몇 번의 측정 결과는 변함이 없네요"처럼 비교를 지어낸다(실측 8/8).
            // 추세를 말할 수 없다는 걸 문장으로 못 박는다 - 메뉴 경로에서는 이 note가 LLM 없이 그대로 답이 된다.
            result.put("note", last == null
                    ? "인바디 기록이 1건뿐이라 체중 추세는 아직 알 수 없어요."
                    : "인바디 기록이 1건뿐이라 체중 추세는 아직 알 수 없어요. 최근 측정값은 " + last + "kg입니다.");
        } else if (first != null && last != null) {
            // 변화량을 안 주면 모델이 첫 값과 끝 값을 직접 빼서 답한다(실측됨). totalKcal을 미리 계산해
            // 넘기는 것과 같은 이유로, 뺄셈할 일 자체를 없앤다. 부호를 잘못 읽는 것도 막으려고
            // 그대로 복사해 쓰면 되는 완성된 문자열로 넘긴다.
            double change = last - first;
            result.put("weightChange", String.format("%s%.1fkg (%.1fkg -> %.1fkg)",
                    change > 0 ? "+" : "", change, first, last));
        }
        return toJson(result);
    }

    private String toolGetBmiPeerComparison(User user) {
        UserProfile profile = getProfileOrNull(user);
        String peerError = peerProfileError(profile);
        if (peerError != null) {
            return toJson(Map.of("error", peerError));
        }

        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getBmi() == null) {
            return toJson(Map.of("error", "인바디 기록이 없어서 또래 비교를 할 수 없어요."));
        }

        return callAiServer("/ai/inbody/bmi-insight", Map.of(
                "bmi", inbody.getBmi(),
                "gender", referenceGender(profile.getGender()),
                "birth_year", profile.getBirthYear()
        ), "category", "percentile", "peer_mean", "age_bracket", "message", "source");
    }

    private String toolGetNutritionPeerComparison(User user, Long userId, Map<String, Object> args) {
        UserProfile profile = getProfileOrNull(user);
        String peerError = peerProfileError(profile);
        if (peerError != null) {
            return toJson(Map.of("error", peerError));
        }

        LocalDate date = parseDateArgOrToday(args);
        MealLoggingService.DailyTotal total = mealLoggingService.getTotalForDate(userId, date);
        if (total.mealCount() == 0) {
            return toJson(Map.of("date", date.toString(),
                    "note", date + "에 기록된 식사가 없어서 또래 비교를 할 수 없어요.",
                    "instruction", "없다고만 답하고 수치를 지어내지 마세요."));
        }

        return callAiServer("/ai/nutrition/peer-compare", Map.of(
                "gender", referenceGender(profile.getGender()),
                "birth_year", profile.getBirthYear(),
                "energy_kcal", total.totalCalories(),
                "protein_g", total.totalProteinG(),
                "carbs_g", total.totalCarbsG(),
                "fat_g", total.totalFatG()
        ), "age_bracket", "message", "source");
    }

    /** 또래 비교는 성별×연령대 통계라 둘 중 하나만 없어도 비교 자체가 불가능하다. */
    private String peerProfileError(UserProfile profile) {
        if (profile == null || profile.getGender() == null || profile.getBirthYear() == null) {
            return "성별과 출생연도가 있어야 또래 비교를 할 수 있어요. 마이페이지에서 프로필을 먼저 채워주세요.";
        }
        return null;
    }

    /** 프로필의 MALE/FEMALE을 AI 서버 참조 통계 표기(M/F)로 (frontend/src/lib/aiApi.js와 같은 규칙) */
    private String referenceGender(Gender gender) {
        return gender == Gender.MALE ? "M" : "F";
    }

    /**
     * 또래 비교 계산을 담당하는 AI 서버(FastAPI)를 부르고, 응답에서 {@code keep}에 적힌 필드만 남긴다.
     * 응답 전체(끼니별 비교 배열 등)를 그대로 넘기면 같은 내용이 message와 중복돼 컨텍스트만 잡아먹는다.
     *
     * AI 서버는 평소 꺼져 있을 수 있고 또래 비교는 부가 정보라, 실패해도 대화 전체를 끊지 않고
     * 도구 결과를 error로 돌려준다 - 모델이 "지금은 확인이 안 된다"고 답하게 된다.
     */
    private String callAiServer(String path, Map<String, Object> body, String... keep) {
        JsonNode response;
        try {
            response = aiRestClient.post().uri(path).body(body).retrieve().body(JsonNode.class);
        } catch (RestClientException e) {
            log.info("AI 서버 또래 비교 호출 실패 ({}): {}", path, e.getMessage());
            return toJson(Map.of("error", "또래 비교 데이터를 지금 가져올 수 없어요."));
        }
        if (response == null) {
            return toJson(Map.of("error", "또래 비교 데이터를 지금 가져올 수 없어요."));
        }

        Map<String, Object> trimmed = new LinkedHashMap<>();
        for (String field : keep) {
            JsonNode value = response.get(field);
            if (value != null && !value.isNull()) {
                trimmed.put(field, objectMapper.convertValue(value, Object.class));
            }
        }
        return toJson(trimmed);
    }

    private String toolCalculateNutrientTarget(User user) {
        UserProfile profile = getProfileOrNull(user);
        if (profile == null || profile.getGoal() == null) {
            return toJson(Map.of("error", "목표가 설정되어 있지 않아요. 마이페이지에서 목표를 먼저 설정해야 계산할 수 있어요."));
        }

        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getWeightKg() == null) {
            return toJson(Map.of("error", "인바디 정보가 없어서 목표 섭취량을 계산할 수 없어요."));
        }

        NutrientTarget target = nutrientTargetCalculator.calculate(inbody, profile);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("goal", GOAL_LABEL.get(profile.getGoal()));
        result.put("targetKcal", Math.round(target.kcal()));
        result.put("targetProteinG", Math.round(target.proteinG()));
        result.put("targetCarbsG", Math.round(target.carbsG()));
        result.put("targetFatG", Math.round(target.fatG()));
        return toJson(result);
    }

    private LocalDate parseDateArgOrToday(Map<String, Object> args) {
        String raw = argString(args, "date", null);
        if (raw == null) {
            return LocalDate.now();
        }
        try {
            return LocalDate.parse(raw);
        } catch (Exception e) {
            // 모델이 날짜 형식을 잘못 넣으면(예: "어제"를 계산 안 하고 그대로 보냄) 오늘로 대체.
            // 여기서 예외를 던지면 도구 호출 자체가 실패해서 답변을 아예 못 받는 게 더 나쁨.
            log.warn("도구 호출의 date 인자를 파싱하지 못해 오늘 날짜로 대체함: {}", raw);
            return LocalDate.now();
        }
    }

    private String argString(Map<String, Object> args, String key, String defaultVal) {
        Object v = args == null ? null : args.get(key);
        return v != null ? String.valueOf(v) : defaultVal;
    }

    private int argInt(Map<String, Object> args, String key, int defaultVal) {
        Object v = args == null ? null : args.get(key);
        if (v instanceof Number n) return n.intValue();
        if (v instanceof String s) {
            try {
                return Integer.parseInt(s.trim());
            } catch (NumberFormatException e) {
                return defaultVal;
            }
        }
        return defaultVal;
    }

    /**
     * 인바디+목표로 계산한 목표 영양소와 오늘 실제 섭취량을 비교해서 LLM이 조언하게 함.
     * 계산(목표치 산출, 차이 비교)은 전부 결정론적 수식이고, LLM은 그 결과를 자연어로 풀어주는 역할만 함.
     * 필요한 데이터를 이미 프롬프트에 다 박아넣기 때문에 툴콜링은 쓰지 않음.
     */
    public String nutrientAdvice(User user, Long userId) {
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getWeightKg() == null) {
            return "인바디 정보가 없어서 분석할 수 없어요. 마이페이지에서 인바디를 먼저 등록해주세요.";
        }

        UserProfile profile = getProfileOrNull(user);
        if (profile == null || profile.getGoal() == null) {
            return "목표가 설정되어 있지 않아요. 마이페이지에서 목표(체중감량/근육증가/체중유지)를 먼저 설정해주세요.";
        }

        MealLoggingService.DailyTotal actual = mealLoggingService.getTotalForDate(userId, LocalDate.now());
        if (actual.mealCount() == 0) {
            return "오늘 기록된 식사가 아직 없어요. 식단을 기록하면 목표 대비 분석해드릴게요.";
        }

        Goal goal = profile.getGoal();
        NutrientTarget target = nutrientTargetCalculator.calculate(inbody, profile);

        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user) + "\n\n" + buildAdviceContext(goal, target, actual)));
        String userLabel = "오늘 내가 먹은 식단이 목표 대비 어떤지 분석해서 부족하거나 초과된 영양소를 짚어주고 조언해줘.";
        messages.add(OllamaMessage.user(userLabel));
        String reply = chatCompletion(messages, false).content();

        // 이 흐름도 같은 대화창(ChatDrawer)에 이어서 보여지므로, 새로고침 후에도 이어지도록 이력에 남김
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("user").content(userLabel).build());
        chatMessageRepository.save(ChatMessageEntity.builder().user(user).role("assistant").content(reply).build());

        return reply;
    }

    private Map<String, Object> buildRequestBody(List<OllamaMessage> messages, boolean includeTools, boolean stream) {
        Map<String, Object> requestBody = new LinkedHashMap<>();
        requestBody.put("model", model);
        requestBody.put("stream", stream);
        requestBody.put("messages", messages);
        // Ollama는 마지막 요청 후 5분이 지나면 모델(4.7GB)을 메모리에서 내린다. 챗봇은 띄엄띄엄
        // 쓰이므로 그대로 두면 사용자가 거의 매번 재적재(20초 안팎)를 기다리게 된다.
        // GPU 인스턴스 환경변수를 건드리지 않고 요청마다 상주 시간을 지정해 그 비용을 없앤다.
        requestBody.put("keep_alive", "24h");
        // temperature 미지정 시 Ollama 기본값(0.8)이 적용되던 걸 명시적으로 낮춤.
        // num_ctx: 시스템 프롬프트(약 1000토큰) + 툴 스키마(약 800) + 이력 8건 + 답변 384가
        // 4096을 넘길 수 있었다. 넘치면 Ollama가 앞쪽부터 버려서 시스템 프롬프트가 날아간다.
        // *** FoodParsingService와 값이 반드시 같아야 함 *** - 같은 모델을 쓰는데 num_ctx가
        // 다르면 Ollama가 요청마다 모델을 내렸다 다시 올린다(4.7GB 재적재 = 20초).
        // temperature 0.4에서는 모델이 도구를 부르는 대신 예고 문장만 쓰거나 tool_call을 텍스트로
        // 흘리는 턴이 나온다(재현: 12회 중 1회). 도구가 안 돌면 검증 없는 답이 그대로 나가고
        // 그게 이력에 남아 다음 턴부터 증폭되므로, 다양성보다 툴콜 신뢰도를 택한다.
        requestBody.put("options", Map.of(
                "temperature", 0.2,
                "num_ctx", 8192,
                "num_predict", 384
        ));
        if (includeTools) {
            requestBody.put("tools", TOOLS);
        }
        return requestBody;
    }

    private static final String AI_UNAVAILABLE_MSG = "AI 챗봇은 지금 준비 중이에요. 잠시 후 다시 시도해 주세요.";

    /**
     * Ollama 호출 실패를 사용자向 예외로 변환한다. Ollama(GPU 인스턴스)는 평소 꺼져 있는 게 정상이라,
     * 연결 자체가 안 되는 경우({@link ResourceAccessException} - ConnectException/타임아웃)는
     * 스택트레이스 없이 INFO로만 남긴다. 그 외(5xx 응답 등)만 ERROR.
     */
    private ExternalServiceException aiUnavailable(Exception e) {
        if (e instanceof ResourceAccessException) {
            log.info("Ollama에 연결할 수 없음 (GPU 인스턴스 중지 상태로 추정): {}", e.getMessage());
        } else {
            log.error("Ollama 호출 실패", e);
        }
        return new ExternalServiceException(AI_UNAVAILABLE_MSG, e);
    }

    private OllamaMessage chatCompletion(List<OllamaMessage> messages, boolean includeTools) {
        OllamaChatResponse response;
        try {
            response = ollamaRestClient.post()
                    .uri("/api/chat")
                    .body(buildRequestBody(messages, includeTools, false))
                    .retrieve()
                    .body(OllamaChatResponse.class);
        } catch (RestClientException e) {
            throw aiUnavailable(e);
        }

        if (response == null || response.message() == null) {
            log.error("Ollama 채팅 응답이 비어있습니다.");
            throw new ExternalServiceException(AI_UNAVAILABLE_MSG);
        }
        return response.message();
    }

    /** 스트리밍 한 번의 결과 - 흘려보낸 본문과, 모델이 요청한 도구 호출 목록 */
    private record StreamResult(String content, List<OllamaMessage.ToolCall> toolCalls) {}

    /**
     * Ollama /api/chat 를 stream 모드로 호출해서, 응답으로 오는 NDJSON 각 줄의
     * message.content 조각을 받는 대로 {@code onDelta}에 넘긴다.
     * tools를 포함해 호출한 경우 도중에 오는 message.tool_calls를 모아서 돌려준다.
     */
    private StreamResult chatCompletionStream(
            List<OllamaMessage> messages, boolean includeTools, Consumer<String> onDelta
    ) {
        StringBuilder content = new StringBuilder();
        List<OllamaMessage.ToolCall> toolCalls = new ArrayList<>();
        try {
            ollamaRestClient.post()
                    .uri("/api/chat")
                    .body(buildRequestBody(messages, includeTools, true))
                    .exchange((request, response) -> {
                        try (BufferedReader reader = new BufferedReader(
                                new InputStreamReader(response.getBody(), StandardCharsets.UTF_8))) {
                            String line;
                            while ((line = reader.readLine()) != null) {
                                if (line.isBlank()) {
                                    continue;
                                }
                                JsonNode node = objectMapper.readTree(line);
                                JsonNode message = node.path("message");

                                String delta = message.path("content").asText("");
                                if (!delta.isEmpty()) {
                                    content.append(delta);
                                    onDelta.accept(delta);
                                }
                                collectToolCalls(message, toolCalls);

                                if (node.path("done").asBoolean(false)) {
                                    break;
                                }
                            }
                        } catch (java.io.IOException e) {
                            throw new UncheckedIOException(e);
                        }
                        return null;
                    });
        } catch (RestClientException | UncheckedIOException e) {
            throw aiUnavailable(e);
        }
        return new StreamResult(content.toString(), toolCalls);
    }

    /** 스트림 조각에 들어있는 tool_calls를 자바 객체로 옮겨 담는다 (없으면 아무것도 안 함) */
    private void collectToolCalls(JsonNode message, List<OllamaMessage.ToolCall> into) {
        JsonNode calls = message.path("tool_calls");
        if (!calls.isArray()) {
            return;
        }
        for (JsonNode call : calls) {
            JsonNode function = call.path("function");
            Map<String, Object> arguments = objectMapper.convertValue(
                    function.path("arguments"), new TypeReference<Map<String, Object>>() {});
            into.add(new OllamaMessage.ToolCall(
                    call.path("id").asText(null),
                    new OllamaMessage.FunctionCall(function.path("name").asText(), arguments)
            ));
        }
    }

    private String buildAdviceContext(Goal goal, NutrientTarget target, MealLoggingService.DailyTotal actual) {
        return """
                [오늘 영양소 분석 요청 - 아래 수치는 이미 계산된 값이니 그대로 인용해서 설명할 것]
                목표: %s
                목표 섭취량 - 칼로리: %.0fkcal, 단백질: %.0fg, 탄수화물: %.0fg, 지방: %.0fg
                오늘 실제 섭취량 - 칼로리: %.0fkcal, 단백질: %.1fg, 탄수화물: %.1fg, 지방: %.1fg
                """.formatted(
                GOAL_LABEL.get(goal),
                target.kcal(), target.proteinG(), target.carbsG(), target.fatG(),
                actual.totalCalories(), actual.totalProteinG(), actual.totalCarbsG(), actual.totalFatG()
        );
    }

    private String buildSystemPrompt(User user) {
        UserProfile profile = getProfileOrNull(user);
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);

        StringBuilder sb = new StringBuilder(SYSTEM_PROMPT)
                .append("\n\n오늘 날짜: ").append(LocalDate.now())
                .append(" (사용자가 '어제', '이번 주'처럼 상대적으로 말하면 이 날짜를 기준으로 계산해서 도구를 호출할 것)");

        boolean hasGoal = profile != null && profile.getGoal() != null;
        if (!hasGoal && inbody == null) {
            return sb.toString();
        }

        sb.append("\n\n사용자 정보:");
        if (hasGoal) {
            sb.append("\n- 목표: ").append(GOAL_LABEL.get(profile.getGoal()));
        }
        // 체지방률 정상범위·권장 섭취량이 성별에 따라 다르므로 모델에게 같이 알려줌
        if (profile != null) {
            List<String> body = new ArrayList<>();
            if (profile.getGender() != null) body.add(profile.getGender() == Gender.MALE ? "남성" : "여성");
            if (profile.getHeightCm() != null) body.add("키 " + profile.getHeightCm() + "cm");
            if (profile.getBirthYear() != null) body.add("만 " + (LocalDate.now().getYear() - profile.getBirthYear()) + "세");
            if (!body.isEmpty()) {
                sb.append("\n- 신체 정보: ").append(String.join(", ", body));
            }
        }
        if (inbody != null) {
            List<String> parts = new ArrayList<>();
            if (inbody.getWeightKg() != null) parts.add("체중 " + inbody.getWeightKg() + "kg");
            if (inbody.getSkeletalMuscleMassKg() != null) parts.add("골격근량 " + inbody.getSkeletalMuscleMassKg() + "kg");
            if (inbody.getBodyFatPercentage() != null) parts.add("체지방률 " + inbody.getBodyFatPercentage() + "%");
            if (!parts.isEmpty()) {
                sb.append("\n- 최근 측정한 인바디 수치(1건, 추세는 get_inbody_history 도구로 확인): ").append(String.join(", ", parts));
            }
            if (inbody.getBasalMetabolicRateKcal() != null) {
                sb.append("\n- 기초대사량: ").append(inbody.getBasalMetabolicRateKcal()).append("kcal");
            }
        }
        return sb.toString();
    }

    private UserProfile getProfileOrNull(User user) {
        try {
            return userProfileService.getProfile(user);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            log.error("도구 결과 직렬화 실패", e);
            return "{\"error\": \"결과를 표현하는 중 문제가 발생했어요.\"}";
        }
    }

    private static Map<String, Object> toolDef(
            String name, String description, Map<String, Object> properties, List<String> required
    ) {
        Map<String, Object> parameters = new LinkedHashMap<>();
        parameters.put("type", "object");
        parameters.put("properties", properties);
        parameters.put("required", required);

        Map<String, Object> function = new LinkedHashMap<>();
        function.put("name", name);
        function.put("description", description);
        function.put("parameters", parameters);

        Map<String, Object> tool = new LinkedHashMap<>();
        tool.put("type", "function");
        tool.put("function", function);
        return tool;
    }

    private record OllamaChatResponse(OllamaMessage message) {
    }
}
