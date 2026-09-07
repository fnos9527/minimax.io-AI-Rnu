import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

# 从 GitHub Secrets 获取环境变量
EMAIL = os.environ.get('MINIMAX_EMAIL')
PASSWORD = os.environ.get('MINIMAX_PASSWORD')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

def send_telegram_msg(text):
    """发送 Telegram 通知"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 TG 机器人，跳过发送通知")
        return
    
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"发送 TG 通知失败: {e}")

def main():
    with sync_playwright() as p:
        # 启动浏览器 (GitHub Actions 环境下必须用无头模式)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            print("🚀 开始执行 Minimax 自动签到任务...")
            
            # 1. 访问首页 (会自动转跳到你提供的登录授权链接)
            page.goto("https://agent.minimax.io/")
            page.wait_for_load_state('networkidle')
            
            # 2. 判断是否在登录页面并输入账号
            if "login" in page.url:
                print("🔑 正在输入账号信息...")
                # 输入邮箱
                page.get_by_placeholder("Enter your email").fill(EMAIL)
                
                # 勾选协议条款 (根据你的截图定位)
                page.locator("text=I have read and agree to the").click()
                time.sleep(1)
                
                # 点击 Continue
                page.get_by_role("button", name="Continue").click()
                time.sleep(3) # 等待动画转跳
                
                # 3. 输入密码
                print("🔑 正在输入密码...")
                page.get_by_placeholder("Enter your password").fill(PASSWORD)
                page.get_by_role("button", name="Continue").click()
                
                # 等待登录完成并转跳回主控制台
                page.wait_for_url("https://agent.minimax.io/**", timeout=30000)
                page.wait_for_load_state('networkidle')
                print("✅ 登录成功！")
            
            # 4. 寻找签到小部件并提取信息
            time.sleep(5) # 给主页加载小组件一点时间
            print("🔍 正在查找签到按钮...")
            
            # 匹配包含 "Check in for" 字样的按钮 (对应截图里的 Check in for ⊕400)
            checkin_btn = page.locator('button:has-text("Check in for")')
            
            if checkin_btn.is_visible():
                btn_text = checkin_btn.inner_text() # 获取按钮上的文字
                
                # 提取数字 (领取的积分数量)
                points = re.search(r'\d+', btn_text)
                points_val = points.group() if points else "未知"
                
                # 点击领取
                checkin_btn.click()
                time.sleep(3)
                
                msg = f"🎉 <b>Minimax 签到成功</b>\n\n💰 <b>获得积分:</b> {points_val}\n⏰ <b>状态:</b> 今日已完成领取"
                print(msg)
                send_telegram_msg(msg)
            else:
                # 如果找不到按钮，可能今天已经签过了，或者页面还没加载全
                print("⚠️ 未找到签到按钮，可能今日已签到，或者请检查网页 UI 是否变更。")
                send_telegram_msg("⚠️ <b>Minimax 签到异常</b>\n未找到签到按钮，可能是今天已经签到过了。")

        except Exception as e:
            error_msg = f"❌ <b>Minimax 签到失败</b>\n\n错误信息:\n<code>{str(e)}</code>"
            print(error_msg)
            send_telegram_msg(error_msg)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
