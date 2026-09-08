package com.kdt.wellmade.domain.mapage;

public enum Goal {
    LOSE("체중감량"),
    GAIN("근성장(벌크업)"),
    MAINTAIN("체형 유지/건강관리");

    // 화면·LLM 프롬프트에 그대로 쓰는 한국어 이름. 예전엔 ChatService와 ChatToolExecutor가
    // 같은 Map을 각자 들고 "서로 같은 값 유지"라고 주석으로만 묶여 있었다 - 라벨은 목표의
    // 속성이므로 enum이 직접 갖고 있는 게 어긋날 여지가 없다.
    private final String label;

    Goal(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }
}
