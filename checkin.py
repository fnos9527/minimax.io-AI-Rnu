import os
import re
import requests
import traceback
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get('MINIMAX_EMAIL')
PASSWORD = os.environ.get('MINIMAX_PASSWORD')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

def send_telegram_msg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def nuke_modals(page):
    """暴力清除页面上的广告弹窗和所有隐形遮罩层"""
    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const tryBtn = btns.find(b => b.innerText && b.innerText.includes('Try it now'));
        if (tryBtn) {
            const modal = tryBtn.closest('div[class*="modal"], div[class*="dialog"], div[role="dialog"]');
            if (modal) modal.remove();
        }
        const badElements = [
            '[class*="mask"]', 
            '[class*="overlay"]', 
            '[class*="blanket"]', 
            '[data-connect-mobile-hint-dismiss-boundary]',
            'div[style*="z-index: 9999"]'
        ];
        document.querySelectorAll(badElements.join(', ')).forEach(m => m.remove());
    }''')

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            print("🚀 开始执行 Minimax 自动签到任务...")
            
            # 1. 访问首页
            print("🌐 正在访问主页 https://agent.minimax.io/ ...")
            page.goto("https://agent.minimax.io/")
            page.wait_for_timeout(6000)

            print("🛡️ 正在执行 JS 移除广告弹窗和底层遮罩...")
            nuke_modals(page)
            page.wait_for_timeout(1000)

            # 2. 判断并点击登录
            email_input = page.locator('input[placeholder="Enter your email"]')
            if not email_input.is_visible():
                sign_in_btn = page.locator('text="Sign in"').first
                if sign_in_btn.is_visible():
                    print("👀 发现 [Sign in] 按钮，正在强制点击...")
                    sign_in_btn.click(force=True) 
                    print("⏳ 等待跳转至登录页...")
                    try:
                        email_input.wait_for(state="visible", timeout=15000)
                    except:
                        pass
            
            # 3. 执行登录流程
            if email_input.is_visible():
                print("🔑 确认进入登录流程，正在输入邮箱...")
                email_input.fill(EMAIL)
                page.wait_for_timeout(1000)
                
                # 协议默认已勾选，这里仅做兜底尝试，不再等待坐标点击（避免浪费 30 秒）
                print("✅ 正在尝试勾选协议条款（兜底，若默认已勾选则跳过）...")
                page.evaluate('''() => {
                    document.querySelectorAll('[role="checkbox"], [role="radio"]').forEach(el => el.click());
                    const all = document.querySelectorAll('*');
                    for (let el of all) {
                        if (el.textContent && el.textContent.includes('I have read and agree')) {
                            let childMatch = Array.from(el.children).some(c => c.textContent && c.textContent.includes('I have read and agree'));
                            if (!childMatch) {
                                el.click();
                                if(el.parentElement) el.parentElement.click();
                                if(el.previousElementSibling) el.previousElementSibling.click();
                            }
                        }
                    }
                }''')
                page.wait_for_timeout(500)
                
                # 留个案发现场
                page.screenshot(path="debug_checkbox.png") 
                
                print("🖱️ 点击 Continue...")
                page.get_by_role("button", name="Continue", exact=True).click(force=True)
                
                print("🔑 正在等待并输入密码...")
                page.wait_for_selector('input[placeholder="Enter your password"]', timeout=15000)
                page.get_by_placeholder("Enter your password").fill(PASSWORD)
                page.wait_for_timeout(500)
                
                print("🖱️ 点击 Continue (登录)...")
                page.get_by_role("button", name="Continue", exact=True).click(force=True)
                
                print("⏳ 等待登录完毕并跳回主控制台 (超时设为 30 秒)...")
                page.wait_for_url("**/agent.minimax.io/**", timeout=30000)
                print(f"✅ 登录成功！当前 URL: {page.url}")
            else:
                print("✅ 未检测到邮箱输入框，假设当前已是登录状态...")

            # 4. 签到流程 —— 用轮询代替固定等待，最长等 40 秒，并支持刷新重试
            print("⏳ 正在轮询等待签到组件加载 (最长 40 秒)...")
            checkin_btn = None
            for i in range(8):  # 8 * 5s = 40s
                page.wait_for_timeout(5000)
                nuke_modals(page)  # 每一轮都清理一次新冒出来的弹窗/遮罩
                btn = page.locator('button:has-text("Check in for")').first
                if btn.is_visible():
                    checkin_btn = btn
                    print(f"✅ 第 {i+1} 次轮询检测到签到按钮")
                    break
                print(f"⌛ 第 {i+1}/8 次未检测到签到面板，继续等待...")

            page.screenshot(path="dashboard_cleaned.png")

            # 仍未找到就刷新页面重试一次
            if checkin_btn is None:
                print("🔄 40 秒内未出现签到面板，尝试刷新页面重试...")
                page.reload()
                page.wait_for_timeout(8000)
                nuke_modals(page)
                page.wait_for_timeout(2000)
                btn = page.locator('button:has-text("Check in for")').first
                if btn.is_visible():
                    checkin_btn = btn
                    print("✅ 刷新后检测到签到按钮")
                page.screenshot(path="dashboard_after_reload.png")

            if checkin_btn is None:
                print("⚠️ 刷新后依然未找到，使用 JS 遍历点击可能的小礼品盒（兜底）...")
                page.evaluate('''() => {
                    const allEls = document.querySelectorAll('*');
                    for(let el of allEls) {
                        if (el.className && typeof el.className === 'string') {
                            let c = el.className.toLowerCase();
                            if (c.includes('checkin') || c.includes('gift') || c.includes('reward')) {
                                el.click();
                            }
                        }
                    }
                }''')
                page.wait_for_timeout(3000)
                btn = page.locator('button:has-text("Check in for")').first
                if btn.is_visible():
                    checkin_btn = btn

            if checkin_btn is not None and checkin_btn.is_visible():
                btn_text = checkin_btn.inner_text()
                points = re.search(r'\d+', btn_text)
                points_val = points.group() if points else "未知"
                
                print(f"👆 找到签到按钮 [{btn_text}]，准备点击...")
                checkin_btn.click(force=True) 
                page.wait_for_timeout(4000) 
                
                page.screenshot(path="success.png")
                
                msg = f"🎉 <b>Minimax 签到成功</b>\n\n💰 <b>获得积分:</b> {points_val}\n⏰ <b>状态:</b> 今日已完成领取"
                print(msg)
                send_telegram_msg(msg)
            else:
                print("⚠️ 仍然未找到签到按钮！")
                msg = "⚠️ <b>Minimax 签到异常</b>\n未找到签到面板。可能是:\n1. 今天已经签到过\n2. 小礼品盒被折叠\n3. 页面加载异常\n请去 Actions 下载截图 dashboard_cleaned.png / dashboard_after_reload.png 查看。"
                send_telegram_msg(msg)

        except Exception as e:
            print(f"❌ 运行发生错误: {str(e)}")
            print(traceback.format_exc())
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
