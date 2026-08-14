package com.kdt.wellmade.domain.mapage;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UserProfileUpdateRequest(
    @NotBlank @Size(max = 50) String name, 
    @Size(max = 500) String profileImageUrl, 
    Goal goal) {
}
