import json, os, re, time
import requests
from bs4 import BeautifulSoup

BASE = "https://egy.voxcinemas.com"
SHOWTIMES = BASE + "/showtimes?c=city-centre-alexandria&c=mall-of-egypt&m=avengers-doomsday&m=avengers-doomsday-infinity-vision"
TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = "state.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Mobile Safari/537.36",
    "Accept-Language": "en",
}

def new_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def get(s, url):
    last = None
    for attempt in range(3):
        try:
            return s.get(url, timeout=30)
        except requests.RequestException as e:
            last = e
            print(f"  attempt {attempt + 1} failed: {type(e).__name__}")
            time.sleep(5)
    raise last

def notify(title, msg, click):
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=msg.encode("utf-8"),
        headers={"Title": title, "Priority": "5", "Tags": "rotating_light", "Click": click},
        timeout=15,
    )

def open_sessions():
    soup = BeautifulSoup(get(new_session(), SHOWTIMES).text, "html.parser")
    ids = []
    for el in soup.select("[data-id]"):
        sp = el if "showtime" in el.get("class", []) else el.select_one("span.action.showtime")
        if sp is None or "unavailable" in sp.get("class", []):
            continue
        ids.append(el["data-id"])
    return sorted(set(ids))

def seat_page(sid):
    s = new_session()
    r = get(s, f"{BASE}/booking/{sid}")
    m = re.search(r"/booking/([^/?#]+)", r.url)
    if not m or m.group(1) == sid:
        raise RuntimeError(f"no booking token (landed on {r.url})")
    tok = m.group(1)
    r = get(s, f"{BASE}/booking/{tok}/seats/fetch")
    if 'class="seat' in r.text:
        return r.text
    for _ in range(10):
        try:
            j = get(s, f"{BASE}/booking/{tok}/seats/processing?json=1").json()
            if j.get("data", {}).get("status") == 1:
                break
        except ValueError:
            pass
        time.sleep(1)
    return get(s, f"{BASE}/booking/{tok}/seats").text

def free_premium_seats(sid):
    soup = BeautifulSoup(seat_page(sid), "html.parser")
    cells = soup.select("td.seat.premium")
    if not soup.select("td.seat"):
        raise RuntimeError("seat map not found")
    free = []
    for td in cells:
        if "sold" in td.get("class", []):
            continue
        inp = td.find("input", attrs={"name": "seat"})
        if inp and not inp.has_attr("disabled"):
            free.append(inp.get("data-label", "?"))
    return set(free), len(cells)

def main():
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    try:
        sessions = open_sessions()
    except Exception as e:
        print(f"Showtimes page not reachable: {e}")
        return
    print(time.strftime("%H:%M:%S"), f"- {len(sessions)} open session(s)")
    for sid in sessions:
        try:
            free, total = free_premium_seats(sid)
        except Exception as e:
            print(f"  {sid}: error {e}")
            continue
        print(f"  {sid}: {len(free)}/{total} premium free")
        new = free - set(state.get(sid, []))
        if new:
            notify("VIP seat available!", f"{sid}: {', '.join(sorted(new))}", f"{BASE}/booking/{sid}")
        state[sid] = sorted(free)
        time.sleep(2)
    json.dump(state, open(STATE_FILE, "w"), indent=1)

if __name__ == "__main__":
    main()
