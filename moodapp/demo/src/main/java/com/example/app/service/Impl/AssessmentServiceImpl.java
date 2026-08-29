package com.example.app.service.Impl;

import cn.hutool.json.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.app.entity.AssessmentAiReport;
import com.example.app.entity.User;
import com.example.app.mapper.AssessmentAiReportMapper;
import com.example.app.mapper.UserMapper;
import com.example.app.service.AssessmentService;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class AssessmentServiceImpl implements AssessmentService {
    @Autowired
    private AssessmentAiReportMapper aiReportMapper;
    @Autowired
    private UserMapper userMapper;
    @Autowired
    private PythonOrchestratorService pythonOrchestratorService;
    private static final String[][] DEFAULT_QUESTIONS = new String[][]{
            {"我感到情绪低落、沮丧", "情感状态", "false"},
            {"我在一天中早晨的状态最好", "情感状态", "true"},
            {"我容易哭泣或想哭", "情感状态", "false"},
            {"我夜间睡眠不好", "睡眠状况", "false"},
            {"我的食量和平时一样", "饮食状况", "true"},
            {"我仍然对亲密关系感兴趣", "兴趣状态", "true"},
            {"我发现自己的体重在下降", "躯体症状", "false"},
            {"我有便秘的困扰", "躯体症状", "false"},
            {"我的心跳比平时快", "躯体症状", "false"},
            {"我无缘无故感到疲劳", "精力状态", "false"},
            {"我的头脑和平时一样清楚", "认知功能", "true"},
            {"我做平常做的事情并不困难", "行为能力", "true"},
            {"我感到坐立不安，难以保持平静", "情绪调节", "false"},
            {"我对未来抱有希望", "认知状态", "true"},
            {"我比平时更容易烦躁", "情绪调节", "false"},
            {"我觉得作出决定是容易的", "认知功能", "true"},
            {"我觉得自己是有用并被需要的", "自我评价", "true"},
            {"我的生活很充实", "生活感受", "true"},
            {"我觉得如果自己不在了，别人会过得更好", "风险评估", "false"},
            {"我仍然喜欢平时感兴趣的事", "兴趣状态", "true"}
    };

    public AssessmentServiceImpl() {
    }

    public Map<String, Object> generateQuestions(int count) {
        Map<String, Object> result = this.generateFallbackQuestions(DEFAULT_QUESTIONS.length);
        result.put("source", "STANDARD");
        result.put("scoring", "20题，每题1至4分；积极表述题反向计分；标准分为原始分乘以1.25后取整");
        result.put("notice", "本量表用于心理状态筛查，不构成医学诊断");
        return result;
    }

    private List<Map<String, Object>> buildOptions() {
        List<Map<String, Object>> options = new ArrayList();
        options.add(this.createOption("没有或很少时间", 1));
        options.add(this.createOption("小部分时间", 2));
        options.add(this.createOption("相当多时间", 3));
        options.add(this.createOption("绝大部分或全部时间", 4));
        return options;
    }

    private Map<String, Object> createOption(String label, int value) {
        Map<String, Object> option = new HashMap();
        option.put("label", label);
        option.put("value", value);
        return option;
    }

    private Map<String, Object> generateFallbackQuestions(int count) {
        Map<String, Object> result = new HashMap();
        List<Map<String, Object>> questions = new ArrayList();
        int actualCount = Math.min(count, DEFAULT_QUESTIONS.length);

        for(int i = 0; i < actualCount; ++i) {
            Map<String, Object> question = new HashMap();
            question.put("title", DEFAULT_QUESTIONS[i][0]);
            question.put("dimension", DEFAULT_QUESTIONS[i][1]);
            question.put("reverseScored", Boolean.parseBoolean(DEFAULT_QUESTIONS[i][2]));
            questions.add(question);
        }

        result.put("type", "SDS");
        result.put("typeName", "抑郁自评量表(SDS)");
        result.put("dimension", "抑郁情绪");
        result.put("questionCount", questions.size());
        result.put("questions", questions);
        result.put("options", this.buildOptions());
        result.put("source", "DEFAULT");
        return result;
    }

    public AssessmentAiReport generateAIReport(String openid, Integer score, String level, List<Integer> answers) {
        LambdaQueryWrapper<User> userWrapper = new LambdaQueryWrapper();
        userWrapper.eq(User::getOpenid, openid);
        User user = (User)this.userMapper.selectOne(userWrapper);
        String aiResponse = this.callPythonAssessmentReport(score, level, answers);
        Map<String, Object> analysis = this.parseAIResponse(aiResponse, score, level);
        AssessmentAiReport report = new AssessmentAiReport();
        report.setOpenid(openid);
        report.setUserId(user != null ? user.getId() : null);
        report.setScore(score);
        report.setLevel(level);
        report.setEmotionalAnalysis((String)analysis.get("emotionalAnalysis"));
        report.setPhysicalSymptoms((String)analysis.get("physicalSymptoms"));
        report.setCognitiveStatus((String)analysis.get("cognitiveStatus"));
        report.setSuggestions((String)analysis.get("suggestions"));
        report.setSummary((String)analysis.get("summary"));
        report.setCreatedAt(LocalDateTime.now());
        this.aiReportMapper.insert(report);
        return report;
    }

    public List<AssessmentAiReport> getReportHistory(String openid) {
        LambdaQueryWrapper<AssessmentAiReport> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AssessmentAiReport::getOpenid, openid)
                .orderByDesc(AssessmentAiReport::getCreatedAt)
                .last("LIMIT 10");
        return this.aiReportMapper.selectList(wrapper);
    }

    public AssessmentAiReport getLatestReport(String openid) {
        LambdaQueryWrapper<AssessmentAiReport> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AssessmentAiReport::getOpenid, openid)
                .orderByDesc(AssessmentAiReport::getCreatedAt)
                .last("LIMIT 1");
        return this.aiReportMapper.selectOne(wrapper);
    }

    private String callPythonAssessmentReport(Integer score, String level, List<Integer> answers) {
        try {
            return this.pythonOrchestratorService
                    .generateAssessmentReport(score, level, answers)
                    .toJSONString();
        } catch (PythonOrchestratorService.PythonOrchestratorException ex) {
            System.err.println("Python 测评报告服务不可用，使用本地兜底报告: " + ex.getMessage());
            return this.getDefaultAnalysis(score, level);
        }
    }

    private Map<String, Object> parseAIResponse(String aiResponse, Integer score, String level) {
        Map<String, Object> result = new HashMap();

        try {
            String jsonStr = aiResponse.trim();
            if (jsonStr.contains("```json")) {
                jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
            }

            if (jsonStr.contains("```")) {
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }

            JSONObject json = new JSONObject(jsonStr.trim());
            ((Map)result).put("emotionalAnalysis", json.getStr("emotionalAnalysis"));
            ((Map)result).put("physicalSymptoms", json.getStr("physicalSymptoms"));
            ((Map)result).put("cognitiveStatus", json.getStr("cognitiveStatus"));
            ((Map)result).put("suggestions", json.getStr("suggestions"));
            ((Map)result).put("summary", json.getStr("summary"));
        } catch (Exception var7) {
            var7.printStackTrace();
            result = this.parseAIResponse(this.getDefaultAnalysis(score, level), score, level);
        }

        return (Map)result;
    }

    private String getDefaultAnalysis(Integer score, String level) {
        String emotional;
        String physical;
        String cognitive;
        String suggestions;
        String summary;
        if (!"无抑郁".equals(level) && !"正常".equals(level) && !"情绪状态正常".equals(level) && !"正常范围".equals(level)) {
            if (!"轻度抑郁".equals(level) && !"轻度抑郁倾向".equals(level) && !"轻度抑郁情绪".equals(level)) {
                if (!"中度抑郁".equals(level) && !"中度抑郁倾向".equals(level) && !"中度抑郁情绪".equals(level)) {
                    emotional = "情绪持续低落，可能伴有强烈的绝望感和无助感。需要立即寻求专业帮助。";
                    physical = "躯体症状严重，睡眠严重紊乱，食欲明显改变，精力极度不足。";
                    cognitive = "认知功能明显受损，可能出现注意力严重下降、无法做决定、自我否定严重等情况。";
                    suggestions = "请立即联系精神心理专业人员。若有伤害自己的想法或现实危险，请联系可信赖的人并寻求当地紧急援助。";
                    summary = "存在重度抑郁倾向，需要紧急专业医疗干预。";
                } else {
                    emotional = "情绪低落感明显，持续时间较长，可能伴有明显的无助感。建议考虑寻求专业帮助。";
                    physical = "躯体症状较明显，可能出现失眠或嗜睡、食欲改变、精力不足等情况。";
                    cognitive = "注意力难以集中，决策困难，自我评价偏低，可能出现消极思维模式。";
                    suggestions = "强烈建议寻求专业心理咨询师的帮助。可以先尝试心理疏导，如持续2-4周无改善，建议就医评估。";
                    summary = "存在中度抑郁倾向，需要专业干预和支持。";
                }
            } else {
                emotional = "情绪略显低落，可能存在一些消极思维，但仍在可控范围内。建议多关注自己的情绪变化。";
                physical = "可能出现轻度睡眠问题或食欲变化，身体时有疲惫感，但不影响日常生活。";
                cognitive = "注意力有所下降，做事动力略有减退，但仍能完成日常任务。";
                suggestions = "建议每天进行30分钟有氧运动，如散步、慢跑等。保持规律作息，多与朋友交流，必要时可寻求心理咨询。";
                summary = "存在轻度抑郁倾向，建议通过生活方式调整和心理疏导来改善。";
            }
        } else {
            emotional = "你的情绪状态总体稳定，能够正常面对生活中的各种情境。积极情绪和消极情绪的起伏在正常范围内。";
            physical = "躯体症状不明显，睡眠、食欲、体力等方面表现正常，身体状态良好。";
            cognitive = "思维清晰，注意力集中，能够正常处理日常事务，做决定时果断性良好。";
            suggestions = "继续保持规律作息和适度的运动习惯。可以尝试每天花10分钟进行正念冥想，有助于维持心理健康。";
            summary = "整体心理健康状况良好，继续保持现有的生活方式即可。";
        }

        return String.format("{\"emotionalAnalysis\":\"%s\",\"physicalSymptoms\":\"%s\",\"cognitiveStatus\":\"%s\",\"suggestions\":\"%s\",\"summary\":\"%s\"}", emotional, physical, cognitive, suggestions, summary);
    }
}
