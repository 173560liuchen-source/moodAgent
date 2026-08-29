package com.example.app.controller;

import com.example.app.entity.CounselingAppointment;
import com.example.app.entity.Hotline;
import com.example.app.mapper.CounselingAppointmentMapper;
import com.example.app.service.HotlineService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping({"/help"})
public class HelpController {
    @Resource
    private HotlineService hotlineService;
    @Resource
    private CounselingAppointmentMapper appointmentMapper;

    public HelpController() {
    }

    @GetMapping({"/hotline"})
    public List<Hotline> getHotline() {
        return this.hotlineService.selectList((Object)null);
    }

    @PostMapping({"/appoint"})
    public String appoint(@RequestBody CounselingAppointment appointment, HttpServletRequest request) {
        appointment.setUserId(AuthenticatedUser.requireId(request));
        this.appointmentMapper.insert(appointment);
        return "预约成功，等待审核";
    }
}
