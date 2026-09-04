package com.kdt.wellmade.domain.chat;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
import com.kdt.wellmade.global.time.AppTime;

/**
 * 사용자의 goal/인바디 값을 시스템 프롬프트로 얹어 로컬 Ollama 채팅을 중계한다.
 * Ollama 호출 자체는 {@link OllamaClient}, 툴콜링 도구 실행은 {@link ChatToolExecutor}에 있다.
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

    /**
     * 답변에 붙일 후속 행동. 프론트가 이 값을 보고 말풍선 아래에 버튼을 그린다.
     * 지금은 인바디 등록 유도 하나뿐이라 상수 하나로 둔다.
     */
    public static final String ACTION_REGISTER_INBODY = "register_inbody";

    /**
     * 인바디 기록이 있어야 답할 수 있는 도구들. 이걸 쓰려 했는데 기록이 없으면 "인바디가 없어서
     * 못 알려준다"로 대화가 끊기므로, 등록 화면으로 가는 버튼을 답변에 같이 실어 보낸다.
     */
    private static final Set<String> INBODY_TOOLS = Set.of(
            "get_inbody_history", "get_bmi_peer_comparison", "calculate_nutrient_target");

    // 예전 프롬프트는 역할을 "식단과 운동을 추천하는 어시스턴트"로 정의해서, 모델이 묻지도 않은
    // 추천을 매번 덧붙였다("안녕" -> 하루 식단표). 또 기록이 없을 때 어떻게 답할지 정해두지 않아
    // 없는 식단을 지어내기도 했다. 그래서 역할을 "물어본 것에 답하는" 쪽으로 좁히고, 하지 말아야
    // 할 행동을 명시적으로 금지한다.
    // 평가 하네스(ChatExerciseEvalTest)가 실제 프롬프트로 채점할 수 있게 패키지까지 열어둔다
    static final String SYSTEM_PROMPT = """
            당신은 사용자의 식단 기록과 인바디 수치를 확인해주는 헬스케어 어시스턴트입니다.
            의학적 진단은 하지 않고 생활습관 수준의 정보만 다룹니다.

            답변 규칙:
            1. 사용자가 물어본 것에만 답하세요. 묻지 않은 추천, 제안, 계획, 후속 질문을 덧붙이지 마세요.
            2. 식단이나 운동 추천은 사용자가 명시적으로 요청했을 때만 하세요.
            3. 답변은 2~4문장으로 짧게. 마크다운 헤더/표/목록/이모지 없이 대화체로 쓰세요.
               코드블록(```)이나 백틱으로 감싸지 마세요. 수치도 그냥 문장 안에 쓰세요.
            4. 반드시 한국어로만 답하세요. 영어 단어나 중국어·한자를 섞지 말고 문장 전체를 한국어로 쓰세요.
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
            10. 운동 추천은 이렇게 처리하세요.
                - 어느 부위를 원하는지 모를 때만 한 문장으로 물어보세요. 난이도는 묻지 마세요.
                - 부위가 정해지면 recommend_exercises 도구를 호출하고, candidates 에 들어 있는
                  운동을 전부 한국어로 추천하세요. 목록에 없는 운동은 지어내지 마세요.
                - 세트 수와 횟수는 직접 정하지 마세요. 각 운동의 sets_reps 값을 그대로 인용하세요.
                  (도구가 사용자의 목표에 맞춰 이미 계산한 값입니다.)
                - cautions 가 있으면 그 문장을 그대로 한 줄 덧붙이세요. 주의사항을 지어내지 마세요.
                - workout_note 가 있으면 그 내용을 한 문장으로 자연스럽게 전달하세요.
                - 운동 방법은 절대 지어내지 마세요. candidates 안의 instructions_ko 에 적힌
                  내용만 간추려 쓰세요. 추천할 때 각 운동의 수행 방법도 instructions_ko 를
                  근거로 한 문장씩 같이 알려주세요.
                - 영상 링크나 주소는 절대 쓰지 마세요. 영상은 화면이 알아서 버튼으로 보여줍니다.
                - 컨텍스트에 instructions_ko 가 없는 운동을 물으면 get_exercise_detail 도구를
                  부르고, 그래도 없으면 "그 운동은 설명해드릴 자료가 없다"고 답하세요.
            11. "또래", "평균", "남들과 비교" 같은 비교 질문은 get_bmi_peer_comparison 또는
                get_nutrition_peer_comparison 도구 결과만 인용하세요.
                - 아래 "사용자 정보"에 적힌 인바디 수치는 이 사용자 '본인' 값일 뿐 평균이 아닙니다.
                  그 값만 보고 "평균보다 높다/낮다"를 판단하지 마세요.
                - 도구를 부르지 않았거나 결과에 error가 있으면, 평균을 추측하지 말고
                  "지금은 또래 비교를 할 수 없다"고만 답하세요.
            """;

    private final UserProfileService userProfileService;
    private final InbodyService inbodyService;
    private final MealLoggingService mealLoggingService;
    private final ChatMessageRepository chatMessageRepository;
    private final NutrientTargetCalculator nutrientTargetCalculator;
    private final OllamaClient ollamaClient;
    private final ChatToolExecutor toolExecutor;
    private final ObjectMapper objectMapper;

    public ChatService(
            UserProfileService userProfileService,
            InbodyService inbodyService,
            MealLoggingService mealLoggingService,
            ChatMessageRepository chatMessageRepository,
            NutrientTargetCalculator nutrientTargetCalculator,
            OllamaClient ollamaClient,
            ChatToolExecutor toolExecutor,
            ObjectMapper objectMapper
    ) {
        this.userProfileService = userProfileService;
        this.inbodyService = inbodyService;
        this.mealLoggingService = mealLoggingService;
        this.chatMessageRepository = chatMessageRepository;
        this.nutrientTargetCalculator = nutrientTargetCalculator;
        this.ollamaClient = ollamaClient;
        this.toolExecutor = toolExecutor;
        this.objectMapper = objectMapper;
    }

    /**
     * 답변 본문 말고 화면에 같이 그릴 것들.
     *
     * action은 버튼 하나(예: 인바디 등록하러 가기), links는 도구가 실어 보낸 바깥 링크
     * (운동 추천의 국민체력100 영상)다. 링크는 모델을 통과시키지 않는다 - URL을 컨텍스트에
     * 넣으면 답변에 주소를 그대로 뱉거나 없는 주소를 지어낸다.
     */
    public record ReplyMeta(String action, List<Map<String, String>> links) {
        static ReplyMeta none() {
            return new ReplyMeta(null, List.of());
        }
    }

    /**
     * 스트리밍 답변을 받아가는 쪽(컨트롤러의 SSE). 토큰 조각과, 화면을 비우라는 신호를 받는다.
     */
    public interface ReplyStream {

        void delta(String text);

        /**
         * 도구를 부른 턴에서 최종 답변(2라운드) 스트리밍을 시작하기 직전에 한 번 온다.
         * 1라운드에서 이미 흘려보낸 조각("어깨 운동을 찾아볼게요" 같은 예고문이나 뒤늦게 섞여나온
         * 툴콜 텍스트)이 최종 답변 앞에 그대로 붙어 보이므로, 말풍선을 비우고 다시 그리라는 뜻.
         */
        void reset();
    }

    /**
     * "버튼 -> 봇이 되묻기 -> 사용자 답" 흐름. wrapPrefix를 붙인 문장은 모델에게만 가고,
     * 이력에는 사용자가 실제로 친 말이 남는다.
     */
    private record FollowUp(String userLabel, String question, String wrapPrefix) {
        String wrap(String answer) {
            return wrapPrefix + answer;
        }
    }

    /**
     * 되묻기 목록. 예전엔 이 세 말풍선이 전부 프론트에만 있었고 서버엔 감싼 문장 하나만 저장돼서,
     * 새로고침하면 앞 두 말풍선이 사라지고 사용자 말풍선은 감싼 문장으로 바뀌어 보였다.
     * 이제 감싸기와 저장을 서버가 한다 - 문구는 ChatDrawer.jsx의 CHAT_MENU_ITEMS와 맞춰야 함.
     */
    private static final Map<String, FollowUp> FOLLOW_UPS = Map.of(
            "exercise-recommend", new FollowUp(
                    "운동 추천받고 싶어요",
                    "어느 부위를 운동하고 싶으세요? 사용할 장비(맨몸, 덤벨 등)가 있으면 같이 알려주세요.",
                    "운동을 추천받고 싶어요. 원하는 조건: "));

    /**
     * 새 사용자 메시지 하나를 받아서, DB에 저장된 최근 이력 + 이번 메시지로 컨텍스트를 구성하고
     * 최종 답변을 토큰 단위로 {@code out}에 흘려보낸다.
     *
     * 도구 호출이 필요한 질문은 먼저 도구를 해소한 뒤 최종 답변을 다시 스트리밍한다.
     */
    public ReplyMeta replyStream(User user, String rawMessage, String followUpId, ReplyStream out) {
        String userMessage = validateAndTrim(rawMessage);
        FollowUp followUp = followUpId == null ? null : FOLLOW_UPS.get(followUpId);
        if (followUpId != null && followUp == null) {
            // 프론트가 새 되묻기를 추가했는데 서버가 아직 모르는 경우. 사용자의 답을 버릴 이유는
            // 없으므로 감싸지 않고 일반 대화로 처리한다.
            log.warn("모르는 followUpId라 일반 대화로 처리함: {}", followUpId);
        }

        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user)));
        for (ChatMessageEntity h : loadRecentHistory(user, CONTEXT_HISTORY_LIMIT)) {
            messages.add(new OllamaMessage(h.getRole(), truncateForContext(h.getContent()), null, null));
        }
        if (followUp != null) {
            messages.add(OllamaMessage.user(followUp.userLabel()));
            messages.add(OllamaMessage.assistant(followUp.question()));
        }
        messages.add(OllamaMessage.user(followUp == null ? userMessage : followUp.wrap(userMessage)));

        // 사용자 메시지는 스트리밍을 시작하기 '전에' 저장한다. 예전엔 두 저장이 모두 스트림 뒤에
        // 있었는데, 실제로 흔한 실패는 답변이 흘러가는 중에 사용자가 창을 닫는 것이다
        // (sendJson -> UncheckedIOException으로 여기를 빠져나감). 그러면 방금 보낸 질문까지
        // 통째로 사라져서, 다시 들어오면 대화가 없던 일이 됐다.
        if (followUp != null) {
            save(user, "user", followUp.userLabel());
            save(user, "assistant", followUp.question());
        }
        save(user, "user", userMessage);

        StringBuilder full = new StringBuilder();
        ReplyMeta meta;
        try {
            meta = resolveToolsThenStream(user, messages, new ReplyStream() {
                @Override
                public void delta(String text) {
                    full.append(text);
                    out.delta(text);
                }

                @Override
                public void reset() {
                    full.setLength(0);
                    out.reset();
                }
            });
        } catch (RuntimeException e) {
            // 만들다 만 답이라도 남긴다 - 아무것도 안 남기면 사용자 질문만 덩그러니 남는다.
            if (!full.isEmpty()) {
                save(user, "assistant", full + "\n\n(답변이 도중에 끊겼어요.)");
            }
            throw e;
        }

        // 모델이 아무것도 내놓지 않는 경우가 드물게 있다(도구도 안 부르고 content도 비어서 옴).
        // 텍스트로 샌 툴콜을 회수하지 못해 통째로 버린 턴도 여기로 온다.
        if (full.isEmpty()) {
            String fallback = "답변을 만들지 못했어요. 조금 더 구체적으로 다시 물어봐 주세요.";
            full.append(fallback);
            out.delta(fallback);
        }

        save(user, "assistant", full.toString());
        return meta;
    }

    private void save(User user, String role, String content) {
        chatMessageRepository.save(
                ChatMessageEntity.builder().user(user).role(role).content(content).build());
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
        LocalDate today = AppTime.today();
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
    public ChatResponse menuReply(User user, Long userId, String menuId) {
        MenuTool menu = menuTool(menuId);
        if (menu == null) {
            throw new IllegalArgumentException("알 수 없는 메뉴입니다: " + menuId);
        }

        String toolResult = toolExecutor.execute(user, menu.toolName(), menu.arguments()).json();
        String reply = emptyResultMessage(toolResult);
        if (reply == null) {
            reply = phraseToolResult(user, menu, toolResult);
        }

        save(user, "user", menu.userLabel());
        save(user, "assistant", reply);
        return new ChatResponse(reply, inbodyActionFor(user, List.of(menu.toolName())));
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
    private static final String NO_REPLY_FALLBACK = "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.";

    /**
     * Ollama가 content를 null이나 빈 문자열로 돌려주는 턴이 있다. 이력 컬럼은 nullable=false라
     * 그대로 저장하면 500이 나고, 저장이 되더라도 빈 말풍선만 남는다.
     */
    private String orFallback(String reply) {
        return reply == null || reply.isBlank() ? NO_REPLY_FALLBACK : reply;
    }

    private String phraseToolResult(User user, MenuTool menu, String toolResult) {
        String callId = "menu-" + menu.toolName();
        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user)));
        messages.add(OllamaMessage.user(menu.userLabel()));
        messages.add(new OllamaMessage("assistant", "", List.of(new OllamaMessage.ToolCall(
                callId, new OllamaMessage.FunctionCall(menu.toolName(), menu.arguments()))), null));
        messages.add(OllamaMessage.tool(toolResult, callId));

        return orFallback(ollamaClient.chatCompletion(messages, false).content());
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
    String validateAndTrim(String rawMessage) {
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
    ReplyMeta resolveToolsThenStream(User user, List<OllamaMessage> messages, ReplyStream out) {
        // 1라운드 본문은 앞부분만 붙잡아두고 흘린다. Qwen이 도구 호출을 구조화된 tool_calls 대신
        // <tool_call>{"name":...} 텍스트로 흘리는 턴이 있는데(재현됨), 그대로 스트리밍하면 화면에
        // JSON이 뜬다. 도구를 부를지는 본문 앞부분만 보면 판별돼서, 홀드 비용은 몇 백 ms 수준이다.
        StringBuilder held = new StringBuilder();
        boolean[] releasedToUser = {false};
        var first = ollamaClient.chatCompletionStream(messages, true, delta -> {
            if (releasedToUser[0]) {
                out.delta(delta);
                return;
            }
            held.append(delta);
            if (held.length() >= TOOLCALL_SNIFF_CHARS && !ToolCallTextParser.looksLikeToolCall(held.toString())) {
                releasedToUser[0] = true;
                out.delta(held.toString());
            }
        });

        List<OllamaMessage.ToolCall> toolCalls = first.toolCalls().isEmpty()
                ? ToolCallTextParser.parse(first.content())
                : first.toolCalls();

        if (toolCalls.isEmpty()) {
            if (releasedToUser[0]) {
                return ReplyMeta.none();
            }
            // 홀드를 푼 적이 없으면 held가 본문 전체다. 툴콜처럼 보여서 붙잡아둔 건데 회수까지
            // 실패했다면(도구 두 개를 텍스트로 흘려서 첫 '{'~마지막 '}' 사이에 JSON 두 덩어리가
            // 들어오는 경우 등) 그대로 내보내면 화면에 JSON이 뜬다. 붙잡아둔 이유가 "보여줄 게
            // 아니라서"였으니 여기서 버리고, 빈 답변으로 두면 replyStream이 폴백 문구로 대체한다.
            if (ToolCallTextParser.looksLikeToolCall(held.toString())) {
                log.warn("툴콜 텍스트로 보였지만 회수하지 못해 버림: {}", held);
                return ReplyMeta.none();
            }
            // 도구 없이 답한 턴(인사·잡담). 짧아서 아직 못 내보낸 앞부분을 마저 흘린다.
            out.delta(held.toString());
            return ReplyMeta.none();
        }

        // 1라운드에서 이미 흘려보낸 게 있으면(예고 문장 뒤에 툴콜을 이어붙이는 턴) 최종 답변 앞에
        // 그대로 남는다. 앞 48자만 보고 판별하는 구조라 이런 턴은 홀드로는 못 막으므로,
        // 2라운드를 시작하기 전에 말풍선을 비우라고 알린다.
        if (releasedToUser[0]) {
            out.reset();
        }

        // 도구를 부르는 턴이면 홀드분(툴콜 텍스트나 "확인해볼게요" 예고)은 화면에도 컨텍스트에도 넣지 않는다.
        messages.add(new OllamaMessage("assistant", releasedToUser[0] ? first.content() : "", toolCalls, null));
        List<Map<String, String>> links = new ArrayList<>();
        for (OllamaMessage.ToolCall call : toolCalls) {
            ChatToolExecutor.ToolResult result =
                    toolExecutor.execute(user, call.function().name(), call.function().arguments());
            links.addAll(result.links());
            messages.add(OllamaMessage.tool(result.json(), call.id()));
        }

        ollamaClient.chatCompletionStream(messages, false, out::delta);
        String action = inbodyActionFor(user, toolCalls.stream().map(c -> c.function().name()).toList());
        return new ReplyMeta(action, links);
    }

    /** 인바디가 필요한 도구를 쓰려 했는데 기록이 없으면 "등록하러 가기" 버튼을 붙이라고 알린다 */
    private String inbodyActionFor(User user, List<String> usedToolNames) {
        boolean needsInbody = usedToolNames.stream().anyMatch(INBODY_TOOLS::contains);
        return needsInbody && inbodyService.getLatest(user).isEmpty() ? ACTION_REGISTER_INBODY : null;
    }

    /**
     * 인바디+목표로 계산한 목표 영양소와 오늘 실제 섭취량을 비교해서 LLM이 조언하게 함.
     * 계산(목표치 산출, 차이 비교)은 전부 결정론적 수식이고, LLM은 그 결과를 자연어로 풀어주는 역할만 함.
     * 필요한 데이터를 이미 프롬프트에 다 박아넣기 때문에 툴콜링은 쓰지 않음.
     */
    public ChatResponse nutrientAdvice(User user, Long userId) {
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);
        if (inbody == null || inbody.getWeightKg() == null) {
            return new ChatResponse("인바디 정보가 없어서 분석할 수 없어요. 아래 버튼으로 인바디를 먼저 등록해주세요.",
                    ACTION_REGISTER_INBODY);
        }

        UserProfile profile = getProfileOrNull(user);
        if (profile == null || profile.getGoal() == null) {
            return ChatResponse.of("목표가 설정되어 있지 않아요. 마이페이지에서 목표(체중감량/근육증가/체중유지)를 먼저 설정해주세요.");
        }

        MealLoggingService.DailyTotal actual = mealLoggingService.getTotalForDate(userId, AppTime.today());
        if (actual.mealCount() == 0) {
            return ChatResponse.of("오늘 기록된 식사가 아직 없어요. 식단을 기록하면 목표 대비 분석해드릴게요.");
        }

        Goal goal = profile.getGoal();
        NutrientTarget target = nutrientTargetCalculator.calculate(inbody, profile);

        List<OllamaMessage> messages = new ArrayList<>();
        messages.add(OllamaMessage.system(buildSystemPrompt(user) + "\n\n" + buildAdviceContext(goal, target, actual)));
        String userLabel = "오늘 내가 먹은 식단이 목표 대비 어떤지 분석해서 부족하거나 초과된 영양소를 짚어주고 조언해줘.";
        messages.add(OllamaMessage.user(userLabel));
        String reply = orFallback(ollamaClient.chatCompletion(messages, false).content());

        // 이 흐름도 같은 대화창(ChatDrawer)에 이어서 보여지므로, 새로고침 후에도 이어지도록 이력에 남김
        save(user, "user", userLabel);
        save(user, "assistant", reply);

        return ChatResponse.of(reply);
    }

    private String buildAdviceContext(Goal goal, NutrientTarget target, MealLoggingService.DailyTotal actual) {
        return """
                [오늘 영양소 분석 요청 - 아래 수치는 이미 계산된 값이니 그대로 인용해서 설명할 것]
                목표: %s
                목표 섭취량 - 칼로리: %.0fkcal, 단백질: %.0fg, 탄수화물: %.0fg, 지방: %.0fg
                오늘 실제 섭취량 - 칼로리: %.0fkcal, 단백질: %.1fg, 탄수화물: %.1fg, 지방: %.1fg
                """.formatted(
                goal.label(),
                target.kcal(), target.proteinG(), target.carbsG(), target.fatG(),
                actual.totalCalories(), actual.totalProteinG(), actual.totalCarbsG(), actual.totalFatG()
        );
    }

    private String buildSystemPrompt(User user) {
        UserProfile profile = getProfileOrNull(user);
        InbodyRecord inbody = inbodyService.getLatest(user).orElse(null);

        StringBuilder sb = new StringBuilder(SYSTEM_PROMPT)
                .append("\n\n오늘 날짜: ").append(AppTime.today())
                .append(" (사용자가 '어제', '이번 주'처럼 상대적으로 말하면 이 날짜를 기준으로 계산해서 도구를 호출할 것)");

        boolean hasGoal = profile != null && profile.getGoal() != null;
        if (!hasGoal && inbody == null) {
            return sb.toString();
        }

        sb.append("\n\n사용자 정보:");
        if (hasGoal) {
            sb.append("\n- 목표: ").append(profile.getGoal().label());
        }
        // 체지방률 정상범위·권장 섭취량이 성별에 따라 다르므로 모델에게 같이 알려줌
        if (profile != null) {
            List<String> body = new ArrayList<>();
            if (profile.getGender() != null) body.add(profile.getGender() == Gender.MALE ? "남성" : "여성");
            if (profile.getHeightCm() != null) body.add("키 " + profile.getHeightCm() + "cm");
            if (profile.getBirthYear() != null) body.add("만 " + (AppTime.today().getYear() - profile.getBirthYear()) + "세");
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
}
