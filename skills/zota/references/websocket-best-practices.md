# ZOTA WebSocket / STOMP 配置最佳实践

> 适用版本：2026-08-02 | 涉及：zota-web (hawkbit-updater-ui) + zota-server WebSocket

---

## 一、架构概览

```
Browser (SockJS/STOMP)
  │  new SockJS('/ws/stomp')
  │  → GET /ws/stomp/info  (SockJS 握手)
  │  → GET /ws/stomp/.../websocket  (WebSocket 升级)
  │  → POST /ws/stomp/.../xhr_streaming  (长连接兜底)
  ▼
Volcengine APIG (:443, TLS 终结)
  │  location / → zota-web:80
  │  需要: loadbalancer-backend-protocol: http
  ▼
zota-web nginx (:80)
  │  location /ws/ → proxy_pass zota-server:8090/ws/
  │  关键: map $http_upgrade 不能对非 WebSocket 返回 close
  ▼
zota-server (:8090, Spring WebSocket)
  │  WebSocketBrokerConfig: /ws/stomp endpoint
  │  SimpleBroker: /topic prefix
```

---

## 二、nginx 配置（⚠️ 两个踩坑点）

### 2.1 map 块：非 WebSocket 请求不要 Connection: close

```nginx
# ❌ 错误 — SockJS xhr_streaming 会被强制断开
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;   # ← 导致 streaming transport 失败
}

# ✅ 正确 — 仅 WebSocket 升级时设置 Connection: Upgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      '';      # ← 空值 = 不覆盖，HTTP/1.1 默认 keep-alive
}
```

**原理**：SockJS 有四种传输方式，按优先级尝试：
1. WebSocket（需要 `Upgrade: websocket` header）
2. XHR streaming（长连接 POST，依赖 keep-alive）
3. XHR polling（短轮询，每个请求独立）
4. JSONP polling

如果 map 对非 WebSocket 请求返回 `close`，streaming transport 被杀死 → 只剩 polling → 延迟 8 秒。

### 2.2 worker_processes 放在主配置文件

```dockerfile
# ❌ 错误 — worker_processes 是 main 级指令，不能在 conf.d/ 里
# k8s/nginx.conf:
worker_processes 1;   # ← 放在 /etc/nginx/conf.d/default.conf 会导致 nginx 启动失败

# ✅ 正确 — 在 Dockerfile 中 sed 修改主配置
# Dockerfile:
RUN sed -i 's/worker_processes.*/worker_processes 1;/' /etc/nginx/nginx.conf
```

> `conf.d/` 下的文件被 include 在 `http {}` 块内，`worker_processes` 是 main 级指令，只能在 `/etc/nginx/nginx.conf` 顶层。

### 2.3 完整 /ws/ location 模板

```nginx
location /ws/ {
    proxy_pass http://zota-server.zota.svc:8090/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $proxy_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;   # WebSocket 长连接不超时
    proxy_send_timeout 300s;
    proxy_buffering off;       # WebSocket 禁用缓冲
}
```

---

## 三、APIG Ingress 注解（火山引擎）

```yaml
# ✅ 必要的 WebSocket 相关注解
ingress.vke.volcengine.com/loadbalancer-backend-protocol: http   # 告诉 APIG 后端是 HTTP
ingress.vke.volcengine.com/loadbalancer-pass-through: "false"    # L7 模式即可（不需要 true）

# ❌ 不需要的
# pass-through: "true"  # L4 透传会绕过 TLS 终结，反而不需要
```

> 对比 casdoor Ingress，关键差异是缺少 `loadbalancer-backend-protocol: http`。

---

## 四、排查流程

```bash
# 1. 验证后端 WebSocket 端点是否正常
kubectl -n zota port-forward svc/zota-server 8090:8090
curl http://localhost:8090/ws/stomp/info
# 预期: {"websocket":true,...}

# 2. 验证 nginx 配置已生效
kubectl -n zota exec deploy/zota-web -- grep "''" /etc/nginx/conf.d/default.conf
# 预期: ''      '';  (不是 close)

# 3. 验证 nginx 日志有 /ws/ 请求
kubectl -n zota logs -l app=zota-web | grep /ws/

# 4. 浏览器控制台检查
# 正确状态: WebSocket 指示灯绿色 CONNECTED
# 错误状态: "[WebSocket] STOMP unavailable, falling back to polling"
```

---

## 五、常见问题

| 现象 | 根因 | 修复 |
|------|------|------|
| "falling back to polling" | nginx map 返回 `close` | 改为 `'' '';` |
| nginx 启动失败: "worker_processes directive is not allowed here" | worker_processes 在 conf.d/ 里 | 移到 Dockerfile sed 主配置 |
| 完全没有 /ws/ 请求到 nginx | APIG 缺少 backend-protocol 注解 | 加 `loadbalancer-backend-protocol: http` |
| WebSocket 连上后频繁断开 | APIG 超时太短 | 加 `loadbalancer-timeout: 3600` |
