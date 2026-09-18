import os
import re
import traceback
import requests
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get('MINIMAX_EMAIL')
PASSWORD = os.environ.get('MINIMAX_PASSWORD')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

MAX_ROUNDS = 3          # 最多轮询/刷新的轮次
POLL_INTERVAL_MS = 5000  # 每轮内部检测按钮的间隔
POLLS_PER_ROUND = 4      # 每轮内部检测次数 (4 * 5s = 20s)


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


def do_login(page):
    """执行一次完整的登录流程（只在第 1 轮调用一次）"""
    print("🌐 正在访问主页 https://agent.minimax.io/ ...")
    page.goto("https://agent.minimax.io/")
    page.wait_for_timeout(6000)

    print("🛡️ 正在执行 JS 移除广告弹窗和底层遮罩...")
    nuke_modals(page)
    page.wait_for_timeout(1000)

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

    if email_input.is_visible():
        print("🔑 确认进入登录流程，正在输入邮箱...")
        email_input.fill(EMAIL)
        page.wait_for_timeout(1000)

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


def check_panel_loaded(page):
    """判断 Daily check-in 面板本身是否已经加载出来（不代表按钮存在）"""
    try:
        panel = page.locator('text="Daily check-in"').first
        return panel.is_visible()
    except:
        return False


def poll_for_checkin_button(page, round_no):
    """
    在当前页面轮询检测签到按钮。
    返回 (status, checkin_btn)
    status 取值: "found"（找到按钮，可点击）/ "already_done"（面板加载了但按钮不在，判定已签到）/ "not_loaded"（面板都没加载出来）
    """
    checkin_btn = None
    panel_seen = False

    for i in range(POLLS_PER_ROUND):
        page.wait_for_timeout(POLL_INTERVAL_MS)
        nuke_modals(page)

        btn = page.locator('button:has-text("Check in for")').first
        if btn.is_visible():
            checkin_btn = btn
            print(f"✅ [第 {round_no} 轮] 第 {i+1} 次检测到签到按钮")
            break

        if check_panel_loaded(page):
            panel_seen = True

        print(f"⌛ [第 {round_no} 轮] 第 {i+1}/{POLLS_PER_ROUND} 次未检测到签到按钮，继续等待...")

    page.screenshot(path=f"dashboard_round{round_no}.png")

    if checkin_btn is not None:
        return "found", checkin_btn

    # 按钮没找到，再确认一次面板是否已经加载（哪怕之前没抓到）
    if not panel_seen:
        panel_seen = check_panel_loaded(page)

    if panel_seen:
        # 面板已经渲染出来了，只是签到按钮不在 —— 大概率是已经签到过
        # （很可能是这一轮或之前某一轮的操作已经生效，只是没被脚本正确捕捉到）
        return "already_done", None

    return "not_loaded", None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        final_status = "not_loaded"

        try:
            for round_no in range(1, MAX_ROUNDS + 1):
                print(f"🚀 ===== 第 {round_no} 轮开始 =====")

                if round_no == 1:
                    do_login(page)
                else:
                    print("🔄 不重新登录，直接刷新签到页面...")
                    page.reload()
                    page.wait_for_timeout(6000)
                    nuke_modals(page)
                    page.wait_for_timeout(1000)

                status, checkin_btn = poll_for_checkin_button(page, round_no)
                final_status = status

                if status == "found":
                    btn_text = checkin_btn.inner_text()
                    points = re.search(r'\d+', btn_text)
                    points_val = points.group() if points else "未知"

                    print(f"👆 [第 {round_no} 轮] 找到签到按钮 [{btn_text}]，准备点击...")
                    checkin_btn.click(force=True)
                    page.wait_for_timeout(4000)
                    page.screenshot(path=f"success_round{round_no}.png")

                    msg = (
                        f"🎉 <b>Minimax 签到成功</b>\n\n"
                        f"💰 <b>获得积分:</b> {points_val}\n"
                        f"🔁 <b>轮次:</b> 第 {round_no} 轮\n"
                        f"⏰ <b>状态:</b> 今日已完成领取"
                    )
                    print(msg)
                    send_telegram_msg(msg)
                    return

                elif status == "already_done":
                    print(f"ℹ️ [第 {round_no} 轮] 签到面板已加载但未找到签到按钮，判定为今日已签到。")
                    page.screenshot(path=f"already_done_round{round_no}.png")

                    msg = (
                        f"✅ <b>Minimax 今日已签到</b>\n\n"
                        f"🔁 <b>确认轮次:</b> 第 {round_no} 轮\n"
                        f"ℹ️ <b>说明:</b> 签到面板已正常加载，但未找到可点击的签到按钮，"
                        f"大概率今天的积分已经领取过了。"
                    )
                    print(msg)
                    send_telegram_msg(msg)
                    return

                else:  # not_loaded
                    print(f"⚠️ [第 {round_no} 轮] 签到面板未能加载出来。")
                    if round_no < MAX_ROUNDS:
                        print("➡️ 准备进入下一轮，刷新页面重试...")
                    continue

            # 三轮都是 not_loaded，才算真正失败
            print("❌ 已重试 3 轮，签到面板始终未能加载。")
            msg = (
                f"⚠️ <b>Minimax 签到异常</b>\n\n"
                f"已连续尝试 {MAX_ROUNDS} 轮，签到面板始终未能加载出来。\n"
                f"可能原因:\n"
                f"1. 网站页面结构发生变化\n"
                f"2. 登录状态异常\n"
                f"3. 网络异常\n"
                f"请去 Actions 下载各轮次截图查看详情。"
            )
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
