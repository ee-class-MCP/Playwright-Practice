"""用 Playwright 無頭瀏覽器登入 ee-class，印出個人頁面（/dashboard）的內容。

第一次：python login.py --set-password   （帳密存進 Windows 認證管理員，不寫在程式裡）
之後：  python login.py
檢查：  python login.py --check           （不登入，只確認登入頁的欄位還找得到）
"""
import asyncio
import getpass
import sys
from pathlib import Path

import keyring
from playwright.async_api import async_playwright

BASE = "https://ncueeclass.ncu.edu.tw"
SERVICE = "ncueeclass"
# 學校登入失敗 5 次會鎖帳號：被拒一次就寫這個檔並停手，等人工確認密碼後才再試
LOGIN_LOCK = Path(__file__).parent / "LOGIN_FAILED"
HEADLESS = True  # 改成 False 可以看到瀏覽器視窗，方便除錯

ACCOUNT_INPUT = "#login_form input[name=account]"
PASSWORD_INPUT = "#login_form input[name=password]"
SUBMIT_BUTTON = "#login_form button[type=submit]"


def set_password():
    account = input("ee-class 帳號（學號）：").strip()
    password = getpass.getpass("密碼（輸入時不會顯示）：")
    if password != getpass.getpass("再輸入一次確認："):
        sys.exit("兩次密碼不同，沒有存檔")
    keyring.set_password(SERVICE, "account", account)
    keyring.set_password(SERVICE, account, password)
    LOGIN_LOCK.unlink(missing_ok=True)
    print("已存進 Windows 認證管理員")


def load_credentials():
    account = keyring.get_password(SERVICE, "account")
    if account is None:
        sys.exit("找不到帳密，請先執行：python login.py --set-password")
    password = keyring.get_password(SERVICE, account)
    if password is None:
        sys.exit("找不到密碼，請先執行：python login.py --set-password")
    return account, password


async def login(page, account, password):
    await page.goto(BASE + "/index/login")
    await page.fill(ACCOUNT_INPUT, account)
    await page.fill(PASSWORD_INPUT, password)
    await page.click(SUBMIT_BUTTON)

    # 已在別處登入時會跳出「是否要將其他裝置登出?」，按鈕有「登出所有裝置」和「保持登入」。
    # 只按「保持登入」，絕不按「登出所有裝置」。exact=True 避免選到「保持登入狀態」勾選框。
    keep_button = page.get_by_text("保持登入", exact=True)
    clicked_keep = False
    left_login_page = False
    for _ in range(30):  # 每 0.5 秒看一次，最多 15 秒
        await page.wait_for_timeout(500)
        if "/index/login" not in page.url:
            left_login_page = True
            break
        if not clicked_keep and await keep_button.is_visible():
            await keep_button.click()
            clicked_keep = True

    if not left_login_page:
        page_text = await page.locator("body").inner_text()
        LOGIN_LOCK.write_text(page.url + "\n\n" + page_text, "utf-8")
        raise RuntimeError("15 秒內沒離開登入頁，可能是帳密錯誤。"
                           "畫面文字已存進 LOGIN_FAILED，請把它貼給我，先不要重跑")

    await page.goto(BASE + "/dashboard")
    if await page.locator("#login_form").count() > 0:
        raise RuntimeError("登入後仍在登入頁，登入流程可能改版")


async def check_selectors(page):
    """不登入：確認登入頁上每個要用的欄位都恰好找到一個。"""
    await page.goto(BASE + "/index/login")
    for selector in [ACCOUNT_INPUT, PASSWORD_INPUT, SUBMIT_BUTTON]:
        count = await page.locator(selector).count()
        assert count == 1, f"{selector} 找到 {count} 個，登入頁可能改版"
    print("登入頁欄位檢查通過")


async def main():
    if "--set-password" in sys.argv:
        set_password()
        return
    checking = "--check" in sys.argv
    if not checking and LOGIN_LOCK.exists():
        sys.exit("上次登入被拒，為避免帳號被鎖已停止。確認密碼後執行：python login.py --set-password")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()
        try:
            if checking:
                await check_selectors(page)
                return
            account, password = load_credentials()
            await login(page, account, password)
            print("登入成功：", await page.title())
            text = await page.locator("body").inner_text()
            print(text[:1000])
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
