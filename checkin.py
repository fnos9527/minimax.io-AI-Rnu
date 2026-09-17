import os
import re
import time
import traceback
import requests
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get('MINIMAX_EMAIL')
PASSWORD = os.environ.get('MINIMAX_PASSWORD')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

MAX_ATTEMPTS = 3


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


def try_checkin(attempt_no):
    """
    执行一次完整的「打开页面 -> 登录 -> 签到」流程。
    返回 True 表示本次成功领取到积分，False 表示本次未成功（会触发外层重试）。
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        try:
            print(f"🚀 [第 {attempt_no} 次尝试] 开始执行 Minimax 自动签到任务...")

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

                # 协议默认已勾选，这里仅做一次兜底点击，不再等待坐标点击
                print("✅ 正在尝试勾选协议条款（兜底）...")
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

                page.screenshot(path=f"debug_checkbox_attempt{attempt_no}.png")

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

            # 4. 签到流程 —— 轮询等待签到组件加载，最长 40 秒
            print("⏳ 正在轮询等待签到组件加载 (最长 40 秒)...")
            checkin_btn = None
            for i in range(8):  # 8 * 5s = 40s
                page.wait_for_timeout(5000)
                nuke_modals(page)
                btn = page.locator('button:has-text("Check in for")').first
                if btn.is_visible():
                    checkin_btn = btn
                    print(f"✅ 第 {i+1} 次轮询检测到签到按钮")
                    break
                print(f"⌛ 第 {i+1}/8 次未检测到签到面板，继续等待...")

            page.screenshot(path=f"dashboard_attempt{attempt_no}.png")

            # 仍未找到就刷新页面重试一次（同一次尝试内的小重试）
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
                page.screenshot(path=f"dashboard_attempt{attempt_no}_after_reload.png")

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

                page.screenshot(path=f"success_attempt{attempt_no}.png")

                msg = (
                    f"🎉 <b>Minimax 签到成功</b>\n\n"
                    f"💰 <b>获得积分:</b> {points_val}\n"
                    f"🔁 <b>尝试次数:</b> 第 {attempt_no} 次\n"
                    f"⏰ <b>状态:</b> 今日已完成领取"
                )
                print(msg)
                send_telegram_msg(msg)
                return True
            else:
                print(f"⚠️ [第 {attempt_no} 次尝试] 仍然未找到签到按钮！")
                return False

        except Exception as e:
            print(f"❌ [第 {attempt_no} 次尝试] 运行发生错误: {str(e)}")
            print(traceback.format_exc())
            try:
                page.screenshot(path=f"error_attempt{attempt_no}.png")
            except:
                pass
            return False
        finally:
            browser.close()


def main():
    for attempt_no in range(1, MAX_ATTEMPTS + 1):
        success = try_checkin(attempt_no)
        if success:
            print(f"✅ 第 {attempt_no} 次尝试成功领取积分，任务结束。")
            return

        if attempt_no < MAX_ATTEMPTS:
            print(f"⚠️ 第 {attempt_no} 次尝试未成功，等待 10 秒后从头重试...")
            time.sleep(10)
        else:
            print(f"❌ 已重试 {MAX_ATTEMPTS} 次，均未成功领取积分。")
            msg = (
                f"⚠️ <b>Minimax 签到失败</b>\n\n"
                f"已连续尝试 {MAX_ATTEMPTS} 次，均未能找到签到按钮或成功签到。\n"
                f"可能原因:\n"
                f"1. 今天已经签到过\n"
                f"2. 页面结构发生变化\n"
                f"3. 登录失败或网络异常\n"
                f"请去 Actions 下载各次尝试的截图查看详情。"
            )
            send_telegram_msg(msg)


if __name__ == "__main__":
    main()
