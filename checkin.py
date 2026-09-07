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
                
                print("✅ 正在强行勾选协议条款 (三管齐下)...")
                
                # 【杀招 A】：深度 DOM 遍历，精准找到最底层的文字节点并疯狂点击它和它周围的元素
                page.evaluate('''() => {
                    // 点击所有复选框语义元素
                    document.querySelectorAll('[role="checkbox"], [role="radio"]').forEach(el => el.click());
                    
                    // 寻找包含文本的最底层元素
                    const all = document.querySelectorAll('*');
                    for (let el of all) {
                        if (el.textContent && el.textContent.includes('I have read and agree')) {
                            // 确保它没有子元素也包含该文本，说明它是最底层的 span/label
                            let childMatch = Array.from(el.children).some(c => c.textContent && c.textContent.includes('I have read and agree'));
                            if (!childMatch) {
                                el.click(); // 点文字
                                if(el.parentElement) el.parentElement.click(); // 点父节点 label
                                if(el.previousElementSibling) el.previousElementSibling.click(); // 点可能存在的左侧小圆圈 div
                            }
                        }
                    }
                }''')
                page.wait_for_timeout(1000)
                
                # 【杀招 B】：Playwright 模拟真人鼠标，物理点击文字左侧偏 15 像素的地方（直击小圆圈心脏）
                try:
                    box = page.locator('text="I have read and agree"').first.bounding_box()
                    if box:
                        # 瞄准文字左侧 15px 的位置（圆圈所在处）进行两连击
                        page.mouse.click(box["x"] - 15, box["y"] + box["height"] / 2)
                        page.mouse.click(box["x"] - 5, box["y"] + box["height"] / 2)
                except Exception as e:
                    print(f"坐标点击偏移失败，跳过: {e}")

                page.wait_for_timeout(1000)
                
                # 留个案发现场，如果还是没勾上，这张图能让我们看清楚
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

            # 4. 签到流程
            print("⏳ 正在等待主页数据及签到组件加载 (等待 10 秒)...")
            page.wait_for_timeout(10000) 
            
            print("🛡️ 再次清理可能弹出的登录后广告...")
            nuke_modals(page)
            page.wait_for_timeout(1000)
            
            page.screenshot(path="dashboard_cleaned.png") 
            
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
                msg = "⚠️ <b>Minimax 签到异常</b>\n未找到签到面板。可能是:\n1. 今天已经签到过\n2. 小礼品盒被折叠\n请去 Actions 下载截图 dashboard_cleaned.png 查看。"
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
