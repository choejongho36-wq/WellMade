package com.kdt.wellmade.domain.chat;

/**
 * 대화 이력을 서버(DB)가 갖게 되면서, 클라이언트는 매번 전체 배열이 아니라 새로 보낸 메시지 하나만 보내면 됨.
 *
 * followUpId는 "버튼 -> 봇이 되묻기 -> 사용자 답" 흐름(운동 추천)에서 어떤 되묻기에 대한 답인지 알린다.
 * 예전엔 프론트가 앞의 두 말풍선을 자기만 그리고 서버엔 감싼 문장("운동을 추천받고 싶어요. 원하는 조건: 하체")만
 * 보내서, 새로고침하면 앞 두 말풍선이 사라지고 사용자 말풍선도 감싼 문장으로 바뀌어 보였다.
 * 이제 감싸기와 이력 저장을 서버가 하고(ChatService.FOLLOW_UPS), message에는 사용자가 실제로 친 말만 담는다.
 * null이면 그냥 일반 대화.
 */
public record ChatRequest(String message, String followUpId) {
}
