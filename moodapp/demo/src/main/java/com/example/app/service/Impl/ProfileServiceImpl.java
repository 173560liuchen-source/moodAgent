package com.example.app.service.Impl;

import com.example.app.entity.ChatRecord;
import com.example.app.entity.PsychologicalProfile;
import com.example.app.entity.User;
import com.example.app.mapper.ChatRecordMapper;
import com.example.app.mapper.ProfileMapper;
import com.example.app.mapper.UserMapper;
import com.example.app.service.ProfileService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Service
public class ProfileServiceImpl implements ProfileService {

    private static final int RECENT_CHAT_LIMIT = 30;

    @Resource
    private UserMapper userMapper;

    @Resource
    private ChatRecordMapper chatRecordMapper;

    @Resource
    private ProfileMapper profileMapper;

    @Override
    public void generateProfile(String openid) {
        User user = userMapper.selectByOpenid(openid);
        if (user == null) {
            throw new RuntimeException("用户不存在");
        }

        PsychologicalProfile latest = profileMapper.findLatest(user.getId());
        if (latest != null && latest.getSummary() != null && !latest.getSummary().isBlank()) {
            PsychologicalProfile snapshot = new PsychologicalProfile();
            snapshot.setUserId(user.getId());
            snapshot.setEmotionTrait(latest.getEmotionTrait());
            snapshot.setStressTrait(latest.getStressTrait());
            snapshot.setAnxietyTrait(latest.getAnxietyTrait());
            snapshot.setRiskTrait(latest.getRiskTrait());
            snapshot.setSummary("复用Python ProfileAgent最新画像快照：" + latest.getSummary());
            snapshot.setCreateTime(LocalDateTime.now());
            profileMapper.insert(snapshot);
            return;
        }

        List<ChatRecord> records = chatRecordMapper.findRecentByUserId(user.getId(), RECENT_CHAT_LIMIT);
        if (records == null || records.isEmpty()) {
            throw new RuntimeException("聊天记录不足，无法生成画像");
        }

        Collections.reverse(records);
        List<String> userTexts = new ArrayList<>();
        for (ChatRecord record : records) {
            if (record != null && "user".equals(record.getRole())
                    && record.getContent() != null && !record.getContent().isBlank()) {
                userTexts.add(record.getContent());
            }
        }

        if (userTexts.isEmpty()) {
            throw new RuntimeException("用户有效聊天记录不足，无法生成画像");
        }

        String joinedText = String.join("\n", userTexts);

        PsychologicalProfile profile = new PsychologicalProfile();
        profile.setUserId(user.getId());
        profile.setEmotionTrait(inferEmotionTrait(joinedText));
        profile.setStressTrait(inferStressTrait(joinedText));
        profile.setAnxietyTrait(inferCommunicationAndCoping(joinedText));
        profile.setRiskTrait(inferRiskTrait(joinedText));
        profile.setSummary(buildSummary(userTexts));
        profile.setCreateTime(LocalDateTime.now());

        profileMapper.insert(profile);
    }

    @Override
    public PsychologicalProfile getLatest(String openid) {
        User user = userMapper.selectByOpenid(openid);
        if (user == null) {
            throw new RuntimeException("用户不存在");
        }
        return profileMapper.findLatest(user.getId());
    }

    @Override
    public PsychologicalProfile selectByUserId(Long userId) {
        return profileMapper.selectByUserId(userId);
    }

    private String inferEmotionTrait(String text) {
        if (containsAny(text, "难过", "低落", "没意义", "撑不住", "崩溃")) {
            return "近期存在低落或无助表达；依据：最近聊天关键词命中";
        }
        if (containsAny(text, "焦虑", "担心", "害怕", "紧张")) {
            return "近期焦虑/担忧表达较明显；依据：最近聊天关键词命中";
        }
        if (containsAny(text, "压力", "累", "烦", "睡不好")) {
            return "近期压力和疲惫表达较明显；依据：最近聊天关键词命中";
        }
        return "近期未发现稳定负向情绪特征；依据：最近聊天记录";
    }

    private String inferStressTrait(String text) {
        List<String> sources = new ArrayList<>();
        if (containsAny(text, "学习", "考试", "作业", "成绩", "课程")) {
            sources.add("学业压力");
        }
        if (containsAny(text, "工作", "实习", "老板", "同事")) {
            sources.add("工作/实习压力");
        }
        if (containsAny(text, "朋友", "同学", "室友", "恋爱", "关系")) {
            sources.add("人际关系压力");
        }
        if (containsAny(text, "父母", "家庭", "家里")) {
            sources.add("家庭压力");
        }
        if (containsAny(text, "睡不着", "失眠", "睡不好", "熬夜")) {
            sources.add("睡眠问题");
        }
        if (sources.isEmpty()) {
            return "暂未识别出明确压力来源；依据：最近聊天记录";
        }
        return "主要压力来源：" + String.join("、", sources) + "；依据：最近聊天关键词命中";
    }

    private String inferCommunicationAndCoping(String text) {
        if (containsAny(text, "怎么办", "帮我", "建议", "分析")) {
            return "用户倾向于主动寻求建议和结构化分析；依据：最近聊天表达";
        }
        if (containsAny(text, "不想说", "没人懂", "不知道")) {
            return "用户可能更需要低压陪伴和开放式提问；依据：最近聊天表达";
        }
        return "沟通偏好证据不足，建议保持温和、简短、可选择的支持方式";
    }

    private String inferRiskTrait(String text) {
        if (containsAny(text, "自杀", "不想活", "结束生命", "伤害自己", "活着没意义")) {
            return "出现危机相关表达，需结合Python CrisisAgent结果人工复核；依据：最近聊天关键词命中";
        }
        if (containsAny(text, "没人帮", "没人管", "孤独", "一个人")) {
            return "支持资源表达偏弱，建议关注可联系的人和学校资源；依据：最近聊天关键词命中";
        }
        return "暂未发现明确高危画像特征；依据：最近聊天记录";
    }

    private String buildSummary(List<String> userTexts) {
        int count = userTexts.size();
        String latest = userTexts.get(userTexts.size() - 1);
        if (latest.length() > 120) {
            latest = latest.substring(0, 120);
        }
        return "本地画像兜底生成：基于最近" + count + "条用户消息；最新证据=\"" + latest + "\"；"
                + "说明：聊天主流程画像以Python ProfileAgent落库结果为准。";
    }

    private boolean containsAny(String text, String... keywords) {
        if (text == null || keywords == null) {
            return false;
        }
        for (String keyword : keywords) {
            if (text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }
}
