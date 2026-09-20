import os
import re
import traceback
import requests
from playwright.sync_api import sync_playwright

EMAIL = os.environ.get('MINIMAX_EMAIL')
PASSWORD = os.environ.get('MINIMAX_PASSWORD')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

MAX_ROUNDS = 3
POLL_INTERVAL_MS = 5000
POLLS_PER_ROUND = 4  # 4 * 5s = 20s 每轮


def send_telegram_msg(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass


def extract_points(text):
    """从按钮文案中提取积分数字，支持带千分位逗号，如 '1,000' -> '1000'"""
    match = re.search(r'[\d,]+', text)
    if not match:
        return "未知"
    return match.group().replace(',', '')


def nuke_ad_modal_only(page):
    """
    精准清除 'Try it now' 那种带明确按钮文案的广告弹窗。
    这里是唯一保留的"主动删 DOM"操作，因为它用具体的按钮文字精确匹配，
    误删真正业务面板（比如签到面板）的概率极低。
    """
    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const tryBtn = btns.find(b => b.innerText && b.innerText.includes('Try it now'));
        if (tryBtn) {
            const modal = tryBtn.closest('div[class*="modal"], div[class*="dialog"], div[role="dialog"]');
            if (modal) modal.remove();
        }
    }''')


# 说明：原来这里还有 nuke_generic_overlays_safe() 和 dismiss_blocking_dialogs()
# 两个函数，它们会用 [class*="mask"] / [class*="overlay"] / div[role="dialog"]
# 这种非常宽泛的选择器去批量删除元素。
#
# 问题在于：很多前端组件库（Ant Design / MUI 等）的正常业务弹层
# （比如签到面板本身如果是用 Drawer/Modal/Dialog 组件渲染的）
# 也会用到 mask / overlay / role="dialog" 这些通用类名或属性，
# 并不是只有广告弹窗才用。白名单关键词判断又依赖 innerText，
# 如果面板还在异步加载、文字还没渲染出来，也会被误判为"不受保护"而删除。
#
# 这就导致真正的签到面板可能在还没来得及显示签到按钮之前，
# 就被这两个"清理函数"连同外层容器一起删掉了，
# 于是无论怎么轮询等待，都再也等不到签到按钮。
#
# 因此这两个函数已被移除调用（保留精确匹配的 nuke_ad_modal_only 即可），
# 页面结构不再被脚本主动破坏。


def try_close_obvious_ad_by_click(page):
    """
    不删除任何 DOM，只是尝试"点击"明显的广告关闭按钮（× / Close / 关闭 / Got it 等），
    这类关闭按钮通常只会隐藏广告本身，不会误伤其他元素。
    找不到就直接跳过，不做任何破坏性操作。
    """
    try:
        page.evaluate('''() => {
            const candidates = Array.from(document.querySelectorAll(
                'button, [role="button"], span, div'
            )).filter(el => {
                const t = (el.innerText || '').trim();
                return t === '×' || t === 'X' || t.toLowerCase() === 'close' ||
                       t.toLowerCase() === 'got it' || t.toLowerCase() === 'dismiss';
            });
            // 只点最上层（z-index 最高）附近、明显是关闭按钮的第一个，避免乱点
            if (candidates.length > 0) {
                candidates[0].click();
            }
        }''')
    except:
        pass


def do_login(page):
    """执行一次完整的登录流程（只在第 1 轮调用一次）"""
    print("🌐 正在访问主页 https://agent.minimax.io/ ...")
    page.goto("https://agent.minimax.io/")
    page.wait_for_timeout(6000)

    # 保留原始页面截图，方便排查签到面板到底长什么样、是否真的被挡住
    page.screenshot(path="debug_raw_page_before_cleanup.png")

    print("🛡️ 仅清理明确的广告弹窗（不再批量删除遮罩/对话框）...")
    nuke_ad_modal_only(page)
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
    status: "found" / "already_done" / "not_loaded"

    注意：轮询过程中不再做任何"批量删除遮罩/对话框"的操作，
    只做精确匹配的广告清理，避免误删签到面板本身。
    """
    checkin_btn = None
    panel_seen = False

    for i in range(POLLS_PER_ROUND):
        page.wait_for_timeout(POLL_INTERVAL_MS)

        nuke_ad_modal_only(page)

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

    if not panel_seen:
        panel_seen = check_panel_loaded(page)

    if panel_seen:
        return "already_done", None

    return "not_loaded", None


def click_checkin_and_verify(page, checkin_btn, round_no):
    """
    点击签到按钮，并在点击后验证是否真正生效。
    如果点击被拦截（说明上面确实盖了一层东西），优先尝试"点击关闭按钮"
    而不是删除 DOM；实在不行再用 force 点击兜底，绝不主动删除元素。
    返回 (success: bool, points_val: str)
    """
    btn_text_before = checkin_btn.inner_text().strip()
    points_val = extract_points(btn_text_before)

    print(f"👆 [第 {round_no} 轮] 找到签到按钮 [{btn_text_before}]，准备点击...")

    clicked_normally = False
    try:
        checkin_btn.scroll_into_view_if_needed(timeout=5000)
        checkin_btn.hover(timeout=5000)
        page.wait_for_timeout(300)
        checkin_btn.click(timeout=5000)
        clicked_normally = True
    except Exception as e:
        print(f"⚠️ 正常点击失败 ({str(e)[:200]})，尝试点掉明显的广告关闭按钮后重试...")
        try_close_obvious_ad_by_click(page)
        page.wait_for_timeout(500)
        try:
            checkin_btn.click(timeout=5000)
            clicked_normally = True
        except Exception as e2:
            print(f"⚠️ 再次点击仍失败 ({str(e2)[:200]})，改用 force 点击兜底...")

    if not clicked_normally:
        try:
            checkin_btn.click(force=True, timeout=5000)
        except Exception as e:
            print(f"❌ force 点击也失败: {str(e)[:200]}")

    # 等待页面响应，然后截图确认（不再做批量清理）
    page.wait_for_timeout(3000)
    nuke_ad_modal_only(page)
    page.wait_for_timeout(2000)
    page.screenshot(path=f"after_click_round{round_no}.png")

    # 验证：重新查找按钮，如果文案和点击前完全一样，说明点击大概率没生效
    btn_after = page.locator('button:has-text("Check in for")').first
    still_same = False
    if btn_after.is_visible():
        try:
            btn_text_after = btn_after.inner_text().strip()
            if btn_text_after == btn_text_before:
                still_same = True
        except:
            pass

    success = not still_same
    if not success:
        print(f"⚠️ [第 {round_no} 轮] 点击后按钮文案未发生变化，判定点击未真正生效。")
    else:
        print(f"✅ [第 {round_no} 轮] 点击后按钮状态已变化，判定签到成功。")

    return success, points_val


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        click_attempted_but_failed = False

        try:
            for round_no in range(1, MAX_ROUNDS + 1):
                print(f"🚀 ===== 第 {round_no} 轮开始 =====")

                if round_no == 1:
                    do_login(page)
                else:
                    print("🔄 不重新登录，直接刷新签到页面...")
                    page.reload()
                    page.wait_for_timeout(6000)
                    nuke_ad_modal_only(page)
                    page.wait_for_timeout(1000)

                status, checkin_btn = poll_for_checkin_button(page, round_no)

                if status == "found":
                    success, points_val = click_checkin_and_verify(page, checkin_btn, round_no)

                    if success:
                        msg = (
                            f"🎉 <b>Minimax 签到成功</b>\n\n"
                            f"💰 <b>获得积分:</b> {points_val}\n"
                            f"🔁 <b>轮次:</b> 第 {round_no} 轮\n"
                            f"⏰ <b>状态:</b> 今日已完成领取"
                        )
                        print(msg)
                        send_telegram_msg(msg)
                        return
                    else:
                        click_attempted_but_failed = True
                        if round_no < MAX_ROUNDS:
                            print("➡️ 点击未生效，进入下一轮刷新重试...")
                        continue

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

            print("❌ 已重试 3 轮，均未能确认签到成功。")
            if click_attempted_but_failed:
                msg = (
                    f"⚠️ <b>Minimax 签到异常</b>\n\n"
                    f"已连续尝试 {MAX_ROUNDS} 轮，虽然找到了签到按钮并尝试点击，"
                    f"但点击后按钮状态始终没有变化，判定签到未真正生效。\n"
                    f"请去 Actions 下载 after_click_roundN.png 截图查看详情，"
                    f"也可以手动登录网站确认积分是否已到账。"
                )
            else:
                msg = (
                    f"⚠️ <b>Minimax 签到异常</b>\n\n"
                    f"已连续尝试 {MAX_ROUNDS} 轮，签到面板始终未能加载出来。\n"
                    f"可能原因:\n"
                    f"1. 网站页面结构发生变化\n"
                    f"2. 登录状态异常\n"
                    f"3. 网络异常\n"
                    f"请去 Actions 下载各轮次截图（尤其是 debug_raw_page_before_cleanup.png）查看详情。"
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
