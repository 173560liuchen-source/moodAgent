package com.example.app.service.Impl;

import okhttp3.*;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.util.List;

public class OkHttpTimingListener extends EventListener {

    private long callStart;
    private long dnsStart;
    private long connectStart;
    private long secureConnectStart;

    @Override
    public void callStart(Call call) {
        callStart = System.currentTimeMillis();
    }

    @Override
    public void dnsStart(Call call, String domainName) {
        dnsStart = System.currentTimeMillis();
    }

    @Override
    public void dnsEnd(Call call, String domainName, List<InetAddress> inetAddressList) {
        System.out.println("[OkHttp] DNS解析: " + (System.currentTimeMillis() - dnsStart) + "ms");
    }

    @Override
    public void connectStart(Call call, InetSocketAddress inetSocketAddress, Proxy proxy) {
        connectStart = System.currentTimeMillis();
    }

    @Override
    public void secureConnectStart(Call call) {
        secureConnectStart = System.currentTimeMillis();
    }

    @Override
    public void secureConnectEnd(Call call, Handshake handshake) {
        System.out.println("[OkHttp] TLS握手: " + (System.currentTimeMillis() - secureConnectStart) + "ms");
    }

    @Override
    public void connectEnd(Call call, InetSocketAddress inetSocketAddress, Proxy proxy, Protocol protocol) {
        System.out.println("[OkHttp] TCP连接(含TLS): " + (System.currentTimeMillis() - connectStart) + "ms");
    }

    @Override
    public void responseHeadersEnd(Call call, Response response) {
        System.out.println("[OkHttp] 等待响应首字节(TTFB): " + (System.currentTimeMillis() - callStart) + "ms");
    }

    @Override
    public void callEnd(Call call) {
        System.out.println("[OkHttp] 请求总耗时: " + (System.currentTimeMillis() - callStart) + "ms");
    }

    @Override
    public void callFailed(Call call, IOException ioe) {
        System.out.println("[OkHttp] 请求失败, 耗时: " + (System.currentTimeMillis() - callStart) + "ms, 原因: " + ioe.getMessage());
    }
}
