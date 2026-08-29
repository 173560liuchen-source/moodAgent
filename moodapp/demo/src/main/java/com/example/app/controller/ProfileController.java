package com.example.app.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.app.dto.ApiResponse;
import com.example.app.dto.ProfileDTO;
import com.example.app.entity.PsychologicalProfile;
import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.service.ProfileService;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;

//用户画像控制器
@Slf4j
@RestController
@RequestMapping("/profile")
public class ProfileController {

    @Resource
    private ProfileService profileService;

    @Autowired
    private  UserMapper userMapper;

    @PostMapping("/generate")
    public Map<String, Object> generate(@RequestBody Map<String, String> body, HttpServletRequest request){
        User currentUser = userMapper.selectById(AuthenticatedUser.requireId(request));
        String openid = currentUser == null ? null : currentUser.getOpenid();
        log.info("【生成画像】收到请求，openid: {}", openid);

        Map<String, Object> result = new HashMap();
        try{
            profileService.generateProfile(openid);

            result.put("code",200);
            result.put("message","生成成功");
        }catch (Exception e){
            log.error("【生成画像】失败，openid: {}, 错误: {}", openid, e.getMessage(), e);
            e.printStackTrace();
            result.put("code",500);
            result.put("message","生成失败: " + e.getMessage());
        }
        return result;
    }

    @GetMapping("/latest")
    public Map<String, Object> latest(@RequestParam(required = false) String openid, HttpServletRequest request){

        User currentUser = userMapper.selectById(AuthenticatedUser.requireId(request));
        openid = currentUser == null ? null : currentUser.getOpenid();

        Map<String, Object> result = new HashMap();

        result.put("code",200);
        result.put("message","success");
        result.put("profile", profileService.getLatest(openid));

        return result;
    }

    @GetMapping("/history")
    public ApiResponse<ProfileDTO> history(@RequestParam(required = false) Long userId, HttpServletRequest request){

        userId = AuthenticatedUser.requireId(request);

        if ( userId == null){
            return ApiResponse.error("openid不能为空");
        }

        //根据openid 查询用户
        User user = userMapper.selectById(userId);

        if (user == null){
            return ApiResponse.error("用户不存在");
        }

       PsychologicalProfile profile = profileService.selectByUserId( userId);

        if (profile == null){
            return ApiResponse.error("暂无风险报告");
        }

        ProfileDTO profileDTO = new ProfileDTO();

        profileDTO.setAnxietyTrait(profile.getAnxietyTrait());
        profileDTO.setStressTrait(profile.getStressTrait());
        profileDTO.setEmotionTrait(profile.getEmotionTrait());
        profileDTO.setRiskTrait(profile.getRiskTrait());
        profileDTO.setSummary(profile.getSummary());


        return ApiResponse.success(profileDTO);
    }
}
