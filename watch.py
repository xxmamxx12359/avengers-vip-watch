import json, os, time
import requests
from bs4 import BeautifulSoup

BASE = "https://egy.voxcinemas.com"
SHOWTIMES = BASE + "/showtimes?c=city-centre-alexandria&c=mall-of-egypt&m=avengers-doomsday&m=avengers-doomsday-infinity-vision"
TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = "state.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "en",
}

def notify(title, msg, click):
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=msg.encode("utf-8"),
        headers={"Title": title, "Priority": "5", "Tags": "rotating_light", "Click": click},
        timeout=15,
    )

def get(s, url):
    last = None
    for attempt in range(3):
        try:
            return s.get(url, timeout=60)
        except requests.RequestException as e:
            last = e
            print(f"attempt {attempt + 1} failed: {type(e).__name__}")
            time.sleep(10)
    raise last

def open_sessions(s):
    soup = BeautifulSoup(get(s, SHOWTIMES).text, "html.parser")
    ids = []
    for el in soup.select("[data-id]"):
        sp = el if "showtime" in el.get("class", []) else el.select_one("span.action.showtime")
        if sp is None or "unavailable" in sp.get("class", []):
            continue
        ids.append(el["data-id"])
    return sorted(set(ids))

def free_premium_seats(s, sid):
    soup = BeautifulSoup(get(s, f"{BASE}/booking/{sid}").text, "html.parser")
    free = []
    for td in soup.select("td.seat.premium"):
        if "sold" in td.get("class", []):
            continue
        inp = td.find("input", attrs={"name": "seat"})
        if inp and not inp.has_attr("disabled"):
            free.append(inp.get("data-label", "?"))
    return set(free)

def main():
    s = requests.Session()
    s.headers.update(HEADERS)
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}

    try:
        sessions = open_sessions(s)
    except Exception as e:
        print(f"Site not reachable this run, will retry in 5 minutes: {e}")
        return

    for sid in sessions:
        try:
            free = free_premium_seats(s, sid)
        except Exception as e:
            print(f"{sid}: error {e}")
            continue
        prev = set(state.get(sid, []))
        new = free - prev
        if new:
            notify("VIP seat available!", f"{sid}: {', '.join(sorted(new))}", f"{BASE}/booking/{sid}")
        state[sid] = sorted(free)

    json.dump(state, open(STATE_FILE, "w"), indent=1)
    print(f"Checked {len(sessions)} open session(s).")

if __name__ == "__main__":
    main()
