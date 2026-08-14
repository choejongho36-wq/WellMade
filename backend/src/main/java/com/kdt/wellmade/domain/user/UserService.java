package com.kdt.wellmade.domain.user;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;

    @Transactional
    public User loginOrRegister(Provider provider, String providerId, String email){
        return userRepository.findByProviderAndProviderId(provider, providerId)
               .orElseGet(() -> userRepository.save(
                    User.builder()
                        .provider(provider)
                        .providerId(providerId)
                        .email(email)
                        .build()));
    }
    
}
