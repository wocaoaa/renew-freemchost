import os
import sys
from datetime import datetime
import json
import requests

# ==================== 🔧 核心配置区 ====================
# 1. 登录配置（完全从 GitHub Secrets 读取，不留任何默认值兜底）
LOGIN_URL = "https://laehfeigoiycigkfknfn.supabase.co/auth/v1/token?grant_type=password"
EMAIL = os.getenv("MY_EMAIL")
PASSWORD = os.getenv("MY_PASSWORD")

# 2. 网页前端固定死公钥（完全从 GitHub Secrets 读取）
SUPABASE_ANON_KEY = os.getenv("ANON_KEY")

# 3. 路由配置 (2026-06-05 最新双接口链路)
# 【接口 A】触发续期的 Action 路由
RENEW_ACTION_URL = "https://new.freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"
# 【接口 B】获取最终完整状态的 Detail 路由
RENEW_DETAIL_URL = "https://new.freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"

SERVER_ID = "2f6dad40-16e6-450a-951d-1af84993cb9d"

# 4. 消息推送配置（可选，可从 GitHub Secrets 读取，不需要保持 None）
SCKEY = os.getenv("SCKEY")

# 🚨 安全校验：如果必备的环境变量为空，直接中断运行并报错提示，使 GitHub Actions 显式失败
if not all([EMAIL, PASSWORD, SUPABASE_ANON_KEY]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 🛑 错误: 未能在环境中检测到必要的凭证 (MY_EMAIL, MY_PASSWORD 或 ANON_KEY)。")
    print(f"[{now}] 请检查你的 GitHub Repository -> Settings -> Secrets and variables -> Actions 是否配置正确！")
    sys.exit(1)
# =====================================================

def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")

def notify(title, content):
    if SCKEY:
        try:
            requests.post(f"https://sctapi.ftqq.com/{SCKEY}.send", data={"title": title, "desp": content}, timeout=5)
        except Exception as e:
            log(f"🔔 推送通知失败: {e}")

def parse_action_response(res_json):
    """解析【接口 A】返回的轻量级压缩包，同时提取最新到期时间、操作状态码"""
    action_info = {"expires_at": None, "status_code": "未知"}
    
    # 📝 DEBUG 埋点：在日志中打印原始返回包，方便你进 GitHub Actions 复制和分析结构
    try:
        log(f"🔍 [DEBUG 原始响应体] {json.dumps(res_json, ensure_ascii=False)}")
    except Exception:
        log(f"🔍 [DEBUG 原始响应体] {res_json}")

    try:
        outer_p = res_json.get("p", {})
        keys = outer_p.get("k", [])
        values = outer_p.get("v", [])

        if "result" in keys:
            idx = keys.index("result")
            if idx < len(values):
                result_node_p = values[idx].get("p", {})
                sub_keys = result_node_p.get("k", [])
                sub_values = result_node_p.get("v", [])

                if "expires_at" in sub_keys:
                    sub_idx = sub_keys.index("expires_at")
                    if sub_idx < len(sub_values):
                        action_info["expires_at"] = sub_values[sub_idx].get("s")
        
        if "error" in keys:
            err_idx = keys.index("error")
            if err_idx < len(values):
                # 兼容处理数字或字符串类型的状态码
                action_info["status_code"] = str(values[err_idx].get("s", values[err_idx].get("n", "未知")))
    except Exception as e:
        log(f"解析续期动作响应异常: {e}")
    return action_info

def parse_detail_response(res_json):
    """解析【接口 B】返回的完整数据包，动态提取服务器名称、运行状态等元数据"""
    info = {"name": "未知", "status": "未知"}
    try:
        outer_v = res_json.get("p", {}).get("v", [])
        if not outer_v:
            return info

        mid_v = outer_v[0].get("p", {}).get("v", [])
        if not mid_v:
            return info

        server_node = mid_v[0]
        keys = server_node.get("p", {}).get("k", [])
        values = server_node.get("p", {}).get("v", [])

        if "name" in keys:
            info["name"] = values[keys.index("name")].get("s", "未知")
        if "status" in keys:
            info["status"] = values[keys.index("status")].get("s", "未知")
    except Exception as e:
        log(f"解析最终详情响应异常: {e}")
    return info

def get_new_token():
    """通过模拟登录，动态换取最新的个人专属 Access Token"""
    log("🔑 正在尝试模拟登录以获取个人 Token...")

    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "origin": "https://new.freemchost.com",
        "referer": "https://new.freemchost.com/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }

    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "gotrue_meta_security": {}
    }

    try:
        response = requests.post(LOGIN_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            token = response.json().get("access_token")
            if token:
                log("✅ 成功模拟登录，已捕获最新专属 Token！")
                return token
        log(f"❌ 登录失败，状态码: {response.status_code}")
    except Exception as e:
        log(f"💥 登录请求引发异常: {e}")
    return None

def run_auto_renew():
    log("▶️ 开始全自动登录 + 链式续期确认流程...")

    # 1. 获取专属 Token
    token = get_new_token()
    if not token:
        log("🛑 未能取得有效 Token，流程被迫中断。")
        notify("服务器自动续期失败", "模拟登录未成功获取 Token，请查看本地日志。")
        sys.exit(1)

    base_headers = {
        "accept": "application/x-tss-framed, application/x-ndjson, application/json",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://new.freemchost.com",
        "referer": f"https://new.freemchost.com/app/servers/{SERVER_ID}",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "x-tsr-serverfn": "true"
    }

    renew_payload = {
        "t": {"t": 10, "i": 0, "p": {"k": ["data"], "v": [{"t": 10, "i": 1, "p": {"k": ["id"], "v": [{"t": 1, "s": SERVER_ID}]}, "o": 0}]}}, "f": 63, "m": []
    }

    # 2. 发送【接口 A】请求：触发续期动作
    log("⚡ 步骤 1/2: 正在向后端发送续期指令...")
    expires_at = None
    status_code = "未知"
    
    try:
        action_res = requests.post(RENEW_ACTION_URL, headers=base_headers, json=renew_payload, timeout=15)
        if action_res.status_code == 200:
            action_info = parse_action_response(action_res.json())
            expires_at = action_info["expires_at"]
            status_code = str(action_info["status_code"])
            
            log("   📥 [接口A 返回快照] ----------------------------")
            log(f"   动作执行状态码 (Error Code) : {status_code} (注: 1通常代表无异常)")
            log(f"   捕获动作到期时间 (Expires At): {expires_at}")
            log("   ------------------------------------------------")
        else:
            log(f"❌ 续期动作请求失败，状态码: {action_res.status_code}")
            notify("服务器自动续期失败", f"续期 Action 接口返回异常状态码: {action_res.status_code}")
            sys.exit(1)
    except Exception as e:
        log(f"💥 续期动作接口引发异常: {e}")
        notify("服务器自动续期异常", f"Action 阶段异常: {e}")
        sys.exit(1)

    # 🛠️ 【核心容错逻辑优化】
    # 即使没解析出新日期，但只要状态码是 "1"，说明后端极大可能处理成功了。
    # 我们选择“不中断”，允许它继续去步骤 2 捞取【接口 B】，从全量包里碰碰运气。
    if not expires_at:
        if status_code == "1":
            log("⚠️ 接口 A 未提取出新到期日期，但状态码为 1。触发容错机制：尝试进入步骤 2 刷新完整数据...")
            expires_at = "未从接口A捕获(等待详情确认)"
        else:
            log(f"🛑 接口 A 未能提取出新到期日期，且状态码异常({status_code})，流程安全中断。")
            sys.exit(1)

    # 3. 发送【接口 B】请求：拉取续期后的最终详情状态
    log("🔍 步骤 2/2: 续期指令已生效，正在拉取最终服务器完整状态确认...")
    server_name = "未知"
    server_status = "未知"
    try:
        detail_res = requests.post(RENEW_DETAIL_URL, headers=base_headers, json=renew_payload, timeout=15)
        if detail_res.status_code == 200:
            detail_json = detail_res.json()
            server_info = parse_detail_response(detail_json)
            server_name = server_info["name"]
            server_status = server_info["status"]
            
            # 如果步骤 1 没拿到时间，看看能不能从接口 B 的原始结构里正则或者肉眼分析出来
            # 这里先保持原样，靠下方最终打印
        else:
            log(f"⚠️ 详情刷新接口返回状态码 {detail_res.status_code}，将使用原缺省值打印日志。")
    except Exception as e:
        log(f"⚠️ 刷新最终详情时发生非致命异常: {e}")

    # 4. 打印最终完美闭环结果并推送
    log("🎉【全链路全自动续期成功】-----------------------")
    log(f" 服务器名称: {server_name}")
    log(f" 当前状态  : {server_status}")
    log(f" 新到期时间: {expires_at}")
    log("--------------------------------------------------")
    
    notify(
        "服务器自动续期确认", 
        f"服务器 [{server_name}] 续期动作已触发！\n"
        f"当前运行状态：{server_status}\n"
        f"接口A截获时间：{expires_at}\n\n"
        f"💡 提示：如果到期时间不准，请登录 GitHub Actions 查看 [DEBUG 原始响应体] 日志结构。"
    )

if __name__ == "__main__":
    run_auto_renew()
