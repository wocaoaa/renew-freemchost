import os
import sys
from datetime import datetime
import json
import requests

# ==================== 🔧 核心配置区 ====================
LOGIN_URL = "https://laehfeigoiycigkfknfn.supabase.co/auth/v1/token?grant_type=password"
EMAIL = os.getenv("MY_EMAIL")
PASSWORD = os.getenv("MY_PASSWORD")
SUPABASE_ANON_KEY = os.getenv("ANON_KEY")

RENEW_ACTION_URL = "https://new.freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"
RENEW_DETAIL_URL = "https://new.freemchost.com/_serverFn/c3a45c08362f2f613bbb6d511a3733a9e85e561709d48bec9280e82a4aa4f47d"

SERVER_ID = "2f6dad40-16e6-450a-951d-1af84993cb9d"
SCKEY = os.getenv("SCKEY")

if not all([EMAIL, PASSWORD, SUPABASE_ANON_KEY]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 🛑 错误: 未能在环境中检测到必要的凭证 (MY_EMAIL, MY_PASSWORD 或 ANON_KEY)。")
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
    """【精密修复版】完美穿透 TSS 套娃结构，精准提取续期时间"""
    action_info = {"expires_at": None, "status_code": "0"}
    try:
        outer_p = res_json.get("p", {})
        outer_keys = outer_p.get("k", [])
        outer_values = outer_p.get("v", [])

        # 1. 提取错误状态
        if "error" in outer_keys:
            err_idx = outer_keys.index("error")
            if err_idx < len(outer_values):
                # 兼容数字(n)或状态(s)或直接取值
                val_node = outer_values[err_idx]
                action_info["status_code"] = str(val_node.get("s", val_node.get("n", "0")))

        # 2. 深度穿透提取到期时间
        if "result" in outer_keys:
            res_idx = outer_keys.index("result")
            if res_idx < len(outer_values):
                # 进入 result 节点
                result_p = outer_values[res_idx].get("p", {})
                res_keys = result_p.get("k", [])
                res_values = result_p.get("v", [])
                
                # 关键：2026最新结构中，核心数据被移动到了 'server' 键内
                if "server" in res_keys:
                    srv_idx = res_keys.index("server")
                    if srv_idx < len(res_values):
                        # 进入 server 节点
                        server_p = res_values[srv_idx].get("p", {})
                        srv_keys = server_p.get("k", [])
                        srv_values = server_p.get("v", [])
                        
                        # 精准捕获 expires_at
                        if "expires_at" in srv_keys:
                            exp_idx = srv_keys.index("expires_at")
                            if exp_idx < len(srv_values):
                                raw_time = srv_values[exp_idx].get("s")
                                if raw_time:
                                    # 格式化一下时间，让日志和通知更好看
                                    try:
                                        dt = datetime.strptime(raw_time.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                                        action_info["expires_at"] = dt.strftime("%Y-%m-%d %H:%M:%S") + " (UTC)"
                                    except Exception:
                                        action_info["expires_at"] = raw_time

    except Exception as e:
        log(f"💥 解析续期动作响应异常: {e}")
    return action_info

def parse_detail_response(res_json):
    """解析【接口 B】返回的完整数据包"""
    info = {"name": "未知", "status": "未知"}
    try:
        outer_v = res_json.get("p", {}).get("v", [])
        if not outer_v: return info
        mid_v = outer_v[0].get("p", {}).get("v", [])
        if not mid_v: return info

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
    log("🔑 正在尝试模拟登录以获取个人 Token...")
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "apikey": SUPABASE_ANON_KEY,
        "authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "origin": "https://new.freemchost.com",
        "referer": "https://new.freemchost.com/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }
    payload = {"email": EMAIL, "password": PASSWORD, "gotrue_meta_security": {}}
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

    token = get_new_token()
    if not token:
        log("🛑 未能取得有效 Token，流程被迫中断。")
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

    # 2. 发送【接口 A】请求
    log("⚡ 步骤 1/2: 正在向后端发送续期指令...")
    expires_at = None
    
    try:
        action_res = requests.post(RENEW_ACTION_URL, headers=base_headers, json=renew_payload, timeout=15)
        if action_res.status_code == 200:
            action_info = parse_action_response(action_res.json())
            expires_at = action_info["expires_at"]
            
            log("   📥 [接口A 返回快照] ----------------------------")
            log(f"   错误状态码 (Error Code)    : {action_info['status_code']}")
            log(f"   捕获新到期时间 (Expires At): {expires_at}")
            log("   ------------------------------------------------")
        else:
            log(f"❌ 续期动作请求失败，状态码: {action_res.status_code}")
            sys.exit(1)
    except Exception as e:
        log(f"💥 续期动作接口引发异常: {e}")
        sys.exit(1)

    # 如果此时依然没有拿到到期时间，说明结构又变了，安全阻断
    if not expires_at:
        log("🛑 接口 A 解析完全失败，未提取出新到期日期，流程中断。")
        sys.exit(1)

    # 3. 发送【接口 B】请求
    log("🔍 步骤 2/2: 续期指令已生效，正在拉取最终服务器完整状态确认...")
    server_name = "未知"
    server_status = "未知"
    try:
        detail_res = requests.post(RENEW_DETAIL_URL, headers=base_headers, json=renew_payload, timeout=15)
        if detail_res.status_code == 200:
            server_info = parse_detail_response(detail_res.json())
            server_name = server_info["name"]
            server_status = server_info["status"]
    except Exception as e:
        log(f"⚠️ 刷新最终详情时发生非致命异常: {e}")

    # 4. 打印完美闭环结果
    log("🎉【全链路全自动续期成功】-----------------------")
    log(f" 服务器名称: {server_name}")
    log(f" 当前状态  : {server_status}")
    log(f" 新到期时间: {expires_at}")
    log("--------------------------------------------------")
    
    notify(
        "FreeMCHost 自动续期成功", 
        f"服务器 [{server_name}] 续期成功！\n"
        f"运行状态：{server_status}\n"
        f"新到期时间：{expires_at}"
    )

if __name__ == "__main__":
    run_auto_renew()
