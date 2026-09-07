import os
import re
import time
import requests
import traceback
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get('MINIMAX_EMAIL')
PASSWORD = os.environ.get('MINIMAX_PASSWORD')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

def send_telegram_msg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置 TG 机器人，跳过发送通知")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"发送 TG 通知失败: {e}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 保持大分辨率
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            print("🚀 开始执行 Minimax 自动签到任务...")
            
            # 1. 访问首页
            print("🌐 正在访问 https://agent.minimax.io/ ...")
            page.goto("https://agent.minimax.io/")
            page.wait_for_timeout(6000) # 等待页面和广告加载
            print(f"📌 当前页面 URL: {page.url}")

            # 【新增】尝试按 ESC 键关闭刚进网页时的 H3 活动广告弹窗
            print("🛡️ 尝试清理遮挡弹窗...")
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)

            # 【新增】判断主页是否有 Sign in 按钮（主动点击去登录）
            sign_in_btn = page.locator('text="Sign in"').first
            if sign_in_btn.is_visible():
                print("👀 发现 [Sign in] 按钮，说明在游客状态，正在点击进入登录页...")
                # force=True 表示无视弹窗遮挡，强制点击该按钮
                sign_in_btn.click(force=True)
                print("⏳ 等待页面跳转...")
                page.wait_for_timeout(4000)
                print(f"📌 跳转后的 URL: {page.url}")

            # 2. 判断是否进入了登录页面 (查找邮箱输入框)
            email_input = page.locator('input[placeholder="Enter your email"]')
            if email_input.is_visible() or "login" in page.url or "oauth2" in page.url:
                print("🔑 确认进入登录流程，正在输入邮箱...")
                email_input.wait_for(state="visible", timeout=10000)
                email_input.fill(EMAIL)
                
                print("✅ 勾选协议条款...")
                page.locator("text=I have read and agree to the").click()
                page.wait_for_timeout(1000) 
                
                print("🖱️ 点击 Continue...")
                page.get_by_role("button", name="Continue").click()
                page.wait_for_timeout(3000) 
                
                print("🔑 正在输入密码...")
                page.wait_for_selector('input[placeholder="Enter your password"]', timeout=15000)
                page.get_by_placeholder("Enter your password").fill(PASSWORD)
                
                print("🖱️ 点击 Continue (登录)...")
                page.get_by_role("button", name="Continue").click()
                
                print("⏳ 等待登录完毕并跳回主控制台 (超时设为30秒)...")
                page.wait_for_url("**/agent.minimax.io/**", timeout=30000)
                print(f"✅ 登录成功！当前 URL: {page.url}")
            else:
                print("✅ 未检测到登录框，假设当前已是登录状态...")

            # 3. 寻找签到小部件
            print("⏳ 正在等待主页数据及签到组件加载 (等待 10 秒)...")
            page.wait_for_timeout(10000) 
            
            # 【新增】登录进来后再次按 ESC，防止又有什么新人引导弹窗遮挡签到按钮
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
            
            page.screenshot(path="dashboard.png") 
            print("📸 已保存登录后主页截图为 dashboard.png")
            
            print("🔍 正在查找签到按钮...")
            checkin_btn = page.locator('button:has-text("Check in for")')
            
            if checkin_btn.is_visible():
                btn_text = checkin_btn.inner_text()
                # 提取数字
                points = re.search(r'\d+', btn_text)
                points_val = points.group() if points else "未知"
                
                print(f"👆 找到签到按钮，准备点击...")
                checkin_btn.click(force=True)
                page.wait_for_timeout(4000) # 等待领取成功的提示
                
                # 截取领取成功的图
                page.screenshot(path="success.png")
                
                msg = f"🎉 <b>Minimax 签到成功</b>\n\n💰 <b>获得积分:</b> {points_val}\n⏰ <b>状态:</b> 今日已完成领取"
                print(msg)
                send_telegram_msg(msg)
            else:
                print("⚠️ 未找到签到按钮！")
                msg = "⚠️ <b>Minimax 签到异常</b>\n未找到签到按钮，可能是今天已经签过，或者小礼品盒被折叠没有自动弹出来。请去 Actions 下载截图 dashboard.png 查看。"
                send_telegram_msg(msg)

        except Exception as e:
            print(f"❌ 运行发生错误: {str(e)}")
            print(traceback.format_exc())
            print("📸 正在保存错误现场截图到 error.png...")
            try:
                page.screenshot(path="error.png")
            except:
                pass
            send_telegram_msg(f"❌ <b>Minimax 签到脚本崩溃</b>\n\n错误信息:\n<code>{str(e)}</code>")
            raise e 
        finally:
            browser.close()

if __name__ == "__main__":
    main()
