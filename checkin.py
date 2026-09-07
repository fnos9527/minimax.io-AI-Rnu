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
        # 放大窗口分辨率，防止响应式布局导致按钮找不到
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            print("🚀 开始执行 Minimax 自动签到任务...")
            
            # 1. 访问首页并等待跳转
            print("🌐 正在访问 https://agent.minimax.io/ ...")
            # 移除导致超时的 networkidle，直接 goto
            page.goto("https://agent.minimax.io/")
            page.wait_for_timeout(5000) # 强制等待5秒，让网页完成重定向
            print(f"📌 当前页面 URL: {page.url}")

            # 2. 判断当前页面状态
            if "login" in page.url or "oauth2" in page.url:
                print("🔑 发现登录页，正在准备输入邮箱...")
                # 显式等待输入框加载
                page.wait_for_selector('input[placeholder="Enter your email"]', timeout=15000)
                page.get_by_placeholder("Enter your email").fill(EMAIL)
                
                print("✅ 勾选协议条款...")
                page.locator("text=I have read and agree to the").click()
                page.wait_for_timeout(1000) # 停顿1秒，让勾选状态生效
                
                print("🖱️ 点击 Continue...")
                page.get_by_role("button", name="Continue").click()
                page.wait_for_timeout(3000) # 等待页面过渡动画
                
                print("🔑 正在输入密码...")
                page.wait_for_selector('input[placeholder="Enter your password"]', timeout=15000)
                page.get_by_placeholder("Enter your password").fill(PASSWORD)
                
                print("🖱️ 点击 Continue (登录)...")
                page.get_by_role("button", name="Continue").click()
                
                print("⏳ 等待登录跳转回主页...")
                # 匹配跳回 agent.minimax.io 的 URL
                page.wait_for_url("**/agent.minimax.io/**", timeout=20000)
                print(f"✅ 登录成功！当前 URL: {page.url}")
            else:
                print("⚠️ 未检测到需要登录，尝试直接在当前页查找签到按钮...")

            # 3. 寻找签到小部件
            print("⏳ 正在等待主页数据加载 (等待 8 秒)...")
            page.wait_for_timeout(8000) 
            
            # 截取登录后/主页的状态
            page.screenshot(path="dashboard.png") 
            print("📸 已保存主页截图为 dashboard.png (可到 Actions 产物中查看)")
            
            print("🔍 正在查找签到按钮...")
            checkin_btn = page.locator('button:has-text("Check in for")')
            
            if checkin_btn.is_visible():
                btn_text = checkin_btn.inner_text()
                # 提取数字
                points = re.search(r'\d+', btn_text)
                points_val = points.group() if points else "未知"
                
                print(f"👆 找到签到按钮，准备点击...")
                checkin_btn.click()
                page.wait_for_timeout(3000) # 等待领取成功提示
                
                # 领取完再截个图
                page.screenshot(path="success.png")
                
                msg = f"🎉 <b>Minimax 签到成功</b>\n\n💰 <b>获得积分:</b> {points_val}\n⏰ <b>状态:</b> 今日已完成领取"
                print(msg)
                send_telegram_msg(msg)
            else:
                print("⚠️ 未找到签到按钮！")
                msg = "⚠️ <b>Minimax 签到异常</b>\n未找到签到按钮，可能是今天已经签到过，请去 Actions 下载截图查看情况。"
                send_telegram_msg(msg)

        except Exception as e:
            print(f"❌ 运行发生错误: {str(e)}")
            print(traceback.format_exc())
            # 发生异常时立刻截图保存“案发现场”
            print("📸 正在保存错误现场截图到 error.png...")
            page.screenshot(path="error.png")
            send_telegram_msg(f"❌ <b>Minimax 签到脚本崩溃</b>\n\n错误信息:\n<code>{str(e)}</code>")
            raise e # 将错误抛出，让 Github Actions 标记红叉
        finally:
            browser.close()

if __name__ == "__main__":
    main()
