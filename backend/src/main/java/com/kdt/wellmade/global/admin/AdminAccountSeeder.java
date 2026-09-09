package com.kdt.wellmade.global.admin;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * admin.seed.login-id / admin.seed.password(application-local.yml 등에 환경변수로 설정)가
 * 있고 admin_accounts 테이블이 비어 있으면 최초 관리자 계정을 하나 만들어준다. 이후엔 그 값을
 * 지워도 이미 만들어진 계정에는 영향 없다 - 매 기동마다 다시 만들거나 덮어쓰지 않는다.
 */
@Component
public class AdminAccountSeeder implements CommandLineRunner {

    private final AdminAccountRepository adminAccountRepository;
    private final PasswordEncoder passwordEncoder;
    private final String seedLoginId;
    private final String seedPassword;

    public AdminAccountSeeder(AdminAccountRepository adminAccountRepository,
                               PasswordEncoder passwordEncoder,
                               @Value("${admin.seed.login-id:}") String seedLoginId,
                               @Value("${admin.seed.password:}") String seedPassword) {
        this.adminAccountRepository = adminAccountRepository;
        this.passwordEncoder = passwordEncoder;
        this.seedLoginId = seedLoginId;
        this.seedPassword = seedPassword;
    }

    @Override
    public void run(String... args) {
        if (seedLoginId.isBlank() || seedPassword.isBlank()) {
            return;
        }
        if (adminAccountRepository.count() > 0) {
            return;
        }
        adminAccountRepository.save(AdminAccount.builder()
                .loginId(seedLoginId)
                .password(passwordEncoder.encode(seedPassword))
                .name("관리자")
                .build());
    }
}
