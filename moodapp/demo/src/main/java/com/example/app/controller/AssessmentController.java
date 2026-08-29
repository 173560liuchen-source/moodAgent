package com.example.app.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.app.entity.AssessmentAiReport;
import com.example.app.entity.AssessmentRecord;
import com.example.app.entity.User;
import com.example.app.service.AssessmentRecordService;
import com.example.app.service.AssessmentService;
import com.example.app.service.UserService;
import java.io.PrintStream;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping({"/assessment"})
public class AssessmentController {
    @Autowired
    private AssessmentRecordService assessmentRecordService;
    @Autowired
    private UserService userService;
    @Autowired
    private AssessmentService assessmentService;

    public AssessmentController() {
    }

    @GetMapping({"/questions"})
    public Map<String, Object> getQuestions(@RequestParam(required = false,defaultValue = "20") Integer count) {
        Map<String, Object> result = new HashMap();

        try {
            Map<String, Object> questions = this.assessmentService.generateQuestions(count);
            result.put("code", 200);
            result.put("message", "获取成功");
            result.put("data", questions);
            return result;
        } catch (Exception var4) {
            var4.printStackTrace();
            result.put("code", 500);
            result.put("message", "获取题目失败: " + var4.getMessage());
            return result;
        }
    }

    @PostMapping({"/submit"})
    public Map<String, Object> submit(@RequestBody Map<String, Object> map, HttpServletRequest request) {
        try {
            List<Integer> answers = (List)map.get("answers");
            Long userId = AuthenticatedUser.requireId(request);
            if (answers != null) {
                if (answers.size() != 20 || answers.stream().anyMatch(value -> value == null || value < 1 || value > 4)) {
                    Map<String, Object> error = new HashMap();
                    error.put("code", 400);
                    error.put("message", "SDS测评必须完成20道题，每题答案应为1至4分");
                    return error;
                }
                LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper();
                wrapper.eq(User::getId, userId);
                User user = this.userService.selectOne(wrapper);
                if (user == null) {
                    Map<String, Object> error = new HashMap();
                    error.put("code", 404);
                    error.put("message", "用户不存在");
                    return error;
                } else {
                    int[] reverseScoredItems = new int[]{2, 5, 6, 11, 12, 14, 16, 17, 18, 20};
                    int score = 0;
                    for (int index = 0; index < answers.size(); index++) {
                        int itemNumber = index + 1;
                        int answer = answers.get(index);
                        boolean reverse = false;
                        for (int reverseItem : reverseScoredItems) {
                            if (reverseItem == itemNumber) {
                                reverse = true;
                                break;
                            }
                        }
                        score += reverse ? 5 - answer : answer;
                    }
                    int standardScore = (int)Math.round((double)score * 1.25);
                    String level;
                    String suggest;
                    if (standardScore < 53) {
                        level = "正常范围";
                        suggest = "目前结果处于正常范围，可以继续保持规律作息并关注情绪变化。";
                    } else if (standardScore < 63) {
                        level = "轻度抑郁情绪";
                        suggest = "建议适当放松、保持规律作息，并在情绪持续困扰时寻求专业支持。";
                    } else if (standardScore < 73) {
                        level = "中度抑郁情绪";
                        suggest = "建议尽快与心理咨询师或精神心理科专业人员沟通并接受进一步评估。";
                    } else {
                        level = "重度抑郁情绪";
                        suggest = "建议尽快寻求精神心理科专业评估；如出现伤害自己的想法，请立即联系可信赖的人并寻求紧急帮助。";
                    }

                    AssessmentRecord record = new AssessmentRecord();
                    record.setUserId(user.getId());
                    record.setScaleType("SDS");
                    record.setScore(score);
                    record.setResult(level);
                    record.setSuggestion(suggest);
                    record.setCreateTime(LocalDateTime.now());
                    this.assessmentRecordService.saveRecord(record);
                    PrintStream var10000 = System.out;
                    Long var10001 = user.getId();
                    var10000.println("测评记录保存成功: userId=" + var10001 + ", score=" + score);
                    if (user.getOpenid() != null) {
                        this.userService.updateAssessmentScore(user.getOpenid(), standardScore);
                    }
                    Map<String, Object> res = new HashMap();
                    res.put("score", standardScore);
                    res.put("rawScore", score);
                    res.put("standardScore", standardScore);
                    res.put("minRawScore", 20);
                    res.put("maxRawScore", 80);
                    res.put("minStandardScore", 25);
                    res.put("maxStandardScore", 100);
                    res.put("scaleType", "SDS");
                    res.put("screeningOnly", true);
                    res.put("level", level);
                    res.put("suggestion", suggest);
                    res.put("recordId", record.getId());
                    Map<String, Object> success = new HashMap();
                    success.put("code", 200);
                    success.put("message", "提交成功");
                    success.put("data", res);
                    return success;
                }
            } else {
                Map<String, Object> error = new HashMap();
                error.put("code", 400);
                error.put("message", "参数不完整");
                return error;
            }
        } catch (Exception var13) {
            var13.printStackTrace();
            Map<String, Object> error = new HashMap();
            error.put("code", 500);
            error.put("message", "提交失败：" + var13.getMessage());
            return error;
        }
    }

    private Long toLong(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return Long.valueOf(value.toString());
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    @PostMapping({"/analyze"})
    public Map<String, Object> analyze(@RequestBody Map<String, Object> params) {
        Map<String, Object> result = new HashMap();

        try {
            String openid = (String)params.get("openid");
            Integer score = (Integer)params.get("score");
            String level = (String)params.get("level");
            List<Integer> answers = (List)params.get("answers");
            if (openid != null && score != null) {
                AssessmentAiReport report = this.assessmentService.generateAIReport(openid, score, level, answers);
                Map<String, Object> reportMap = new HashMap();
                reportMap.put("id", report.getId());
                reportMap.put("score", report.getScore());
                reportMap.put("level", report.getLevel());
                reportMap.put("summary", report.getSummary());
                reportMap.put("emotionalAnalysis", report.getEmotionalAnalysis());
                reportMap.put("physicalSymptoms", report.getPhysicalSymptoms());
                reportMap.put("cognitiveStatus", report.getCognitiveStatus());
                reportMap.put("suggestions", report.getSuggestions());
                if (report.getCreatedAt() != null) {
                    reportMap.put("createdAt", report.getCreatedAt().toString());
                }

                result.put("code", 200);
                result.put("message", "分析完成");
                result.put("data", reportMap);
                return result;
            } else {
                result.put("code", 400);
                result.put("message", "参数不完整");
                return result;
            }
        } catch (Exception var9) {
            var9.printStackTrace();
            result.put("code", 500);
            result.put("message", "分析失败: " + var9.getMessage());
            return result;
        }
    }

    @GetMapping({"/history/{openid}"})
    public Map<String, Object> getHistory(@PathVariable String openid) {
        HashMap result;
        try {
            User user = this.userService.findByOpenid(openid);
            if (user == null) {
                result = new HashMap();
                result.put("code", 404);
                result.put("message", "用户不存在");
                return result;
            } else {
                result = new HashMap();
                result.put("code", 200);
                result.put("message", "获取成功");
                result.put("data", (Object)null);
                return result;
            }
        } catch (Exception var4) {
            var4.printStackTrace();
            result = new HashMap();
            result.put("code", 500);
            result.put("message", "获取历史失败：" + var4.getMessage());
            return result;
        }
    }
}
