package com.example.app.service;

import com.example.app.entity.PsychologicalProfile;

public interface ProfileService {

    void generateProfile(String openid);

    PsychologicalProfile getLatest(String openid);

    PsychologicalProfile selectByUserId(Long userId);
}