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

            # 2. 清理未登录状态下的广告弹窗
            print("🛡️ 正在执行 JS 移除广告弹窗和底层遮罩...")
            nuke_modals(page)
            page.wait_for_timeout(1000)

            # 3. 判断并点击登录
            email_input = page.locator('input[placeholder="Enter your email"]')
            if not email_input.is_visible():
                sign_in_btn = page.locator('text="Sign in"').first
                if sign_in_btn.is_visible():
                    print("👀 发现 [Sign in] 按钮，正在使用无视遮挡(force=True)进行强制点击...")
                    sign_in_btn.click(force=True) 
                    print("⏳ 等待跳转至登录页...")
                    try:
                        email_input.wait_for(state="visible", timeout=15000)
                    except:
                        pass
            
            # 4. 执行登录流程
            if email_input.is_visible():
                print("🔑 确认进入登录流程，正在输入邮箱...")
                email_input.fill(EMAIL)
                page.wait_for_timeout(500)
                
                print("✅ 正在强行勾选协议条款...")
                # 方案 A: 尝试用 Playwright 点击包含文字的标签 (取最后一个即可视元素)
                try:
                    page.locator('text=I have read and agree').last.click(force=True)
                except:
                    pass
                
                # 方案 B: 无论方案A成没成功，都注入 JS 执行降维打击，强制触发选中
                page.evaluate('''() => {
                    // 1. 找到该文字，并点击它的外层父容器(通常是包裹文字和小圆圈的 label/div)
                    const els = Array.from(document.querySelectorAll('*'));
                    const agreeEl = els.find(el => el.textContent && el.textContent.includes('I have read and agree'));
                    if (agreeEl && agreeEl.parentElement) {
                        agreeEl.parentElement.click();
                    }
                    // 2. 暴力寻找页面底层的 checkbox/radio 并修改状态为选中
                    const inputs = document.querySelectorAll('input[type="checkbox"], input[type="radio"]');
                    inputs.forEach(i => {
                        i.checked = true;
                        i.click();
                        i.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                }''')
                page.wait_for_timeout(1500) 
                
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

            # 5. 签到流程
            print("⏳ 正在等待主页数据及签到组件加载 (等待 10 秒)...")
            page.wait_for_timeout(10000) 
            
            print("🛡️ 再次清理可能弹出的登录后广告...")
            nuke_modals(page)
            page.wait_for_timeout(1000)
            
            page.screenshot(path="dashboard_cleaned.png") 
            print("📸 已保存清理后的主页截图为 dashboard_cleaned.png")
            
            print("🔍 正在查找签到按钮...")
            checkin_btn = page.locator('button:has-text("Check in for")').first
            
            if not checkin_btn.is_visible():
                print("⚠️ 签到面板未自动展开，正在使用 JS 遍历点击可能的小礼品盒...")
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
            
            if checkin_btn.is_visible():
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
                msg = "⚠️ <b>Minimax 签到异常</b>\n未找到签到面板。可能是:\n1. 今天已经签到过，按钮隐藏了\n2. 小礼品盒由于版本更新改了代码\n请去 Actions 下载截图 dashboard_cleaned.png 查看。"
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
