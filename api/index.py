import os
import json
import requests
from fastapi import FastAPI, Request, Response, BackgroundTasks
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from concurrent.futures import ThreadPoolExecutor, as_completed

app = FastAPI()

DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY")
SWGOH_API_KEY = os.environ.get("SWGOH_API_KEY")

# GL base_id → 表示名（リリース新しい順）
GL_NAMES = {
    "GLHONDO": "Hondo",
    "GLAHSOKATANO": "Ahsoka",
    "JABBATHEHUTT": "Jabba",
    "GLLEIA": "Leia",
    "JEDIMASTERKENOBI": "JMK",
    "LORDVADER": "LV",
    "SITHPALPATINE": "SEE",
    "GRANDMASTERLUKE": "JML",
    "SUPREMELEADERKYLOREN": "SLKR",
    "GLREY": "Rey",
}

# ===== Discord署名検証 =====
def verify_discord_signature(request: Request, body: bytes):
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    if not signature or not timestamp:
        return False
    try:
        verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False

# ===== ギルドID抽出 =====
def extract_guild_id(input_str):
    input_str = input_str.strip().rstrip("/")
    if "swgoh.gg" in input_str:
        parts = input_str.split("/g/")
        if len(parts) > 1:
            return parts[1].split("/")[0]
    return input_str

# ===== SWGOH.gg API =====
def get_guild_data(guild_id):
    url = f"http://swgoh.gg/api/guild-profile/{guild_id}"
    headers = {
        "content-type": "application/json",
        "x-gg-bot-access": SWGOH_API_KEY
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"Error fetching guild data: {e}")
        return None

def get_player_data(ally_code):
    url = f"http://swgoh.gg/api/player/{ally_code}/"
    headers = {
        "content-type": "application/json",
        "x-gg-bot-access": SWGOH_API_KEY
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"Error fetching player data: {e}")
        return None

# ===== データ処理 =====
def process_member_data(member):
    ally_code = member.get("ally_code")
    if not ally_code:
        return {"success": False}

    player_data = get_player_data(ally_code)
    if not player_data:
        return {"success": False}

    result = {
        "success": True,
        "gl": 0,
        "levi": 0,
        "prof": 0,
        "exec": 0,
        "fdc_lv15": 0,
        "fdc_lv12": 0,
        "dc_lv9": 0,
        "arena": None,
        "ship": None,
        "gl_relics": {}
    }

    units = player_data.get("units", [])
    for unit in units:
        unit_data = unit.get("data", {})
        base_id = unit_data.get("base_id", "")

        if unit_data.get("is_galactic_legend", False):
            result["gl"] += 1
            relic_tier = unit_data.get("relic_tier", 0)
            result["gl_relics"][base_id] = relic_tier - 2

        if base_id == "CAPITALLEVIATHAN":
            result["levi"] = 1
        elif base_id == "CAPITALPROFUNDITY":
            result["prof"] = 1
        elif base_id == "CAPITALEXECUTOR":
            result["exec"] = 1

    datacrons = player_data.get("datacrons", [])
    for dc in datacrons:
        tier = dc.get("tier", 0)
        template = dc.get("template_base_id", "")
        is_focused = "focused" in template.lower()

        if tier >= 9:
            result["dc_lv9"] += 1
        if tier >= 12 and is_focused:
            result["fdc_lv12"] += 1
        if tier == 15 and is_focused:
            result["fdc_lv15"] += 1

    data_section = player_data.get("data", {})
    result["arena"] = data_section.get("arena_rank")
    result["ship"] = data_section.get("fleet_arena", {}).get("rank")

    return result

def analyze_guild(guild_id):
    guild_data = get_guild_data(guild_id)
    if not guild_data:
        return None

    guild_name = guild_data.get("data", {}).get("name", "???")
    members = guild_data.get("data", {}).get("members", [])

    total_gp = sum(m.get("galactic_power", 0) for m in members)
    member_count = len(members)
    avg_gp = total_gp // member_count if member_count > 0 else 0

    leagues = {"Kyber": 0, "Aurodium": 0, "Chromium": 0, "Bronzium": 0, "Carbonite": 0}
    for m in members:
        league = m.get("league_name", "")
        if league in leagues:
            leagues[league] += 1

    gp_10m_plus = sum(1 for m in members if m.get("galactic_power", 0) >= 10_000_000)
    gp_8m_to_10m = sum(1 for m in members if 8_000_000 <= m.get("galactic_power", 0) < 10_000_000)

    gl_total = 0
    gl_r10_total = 0
    gl_r9_total = 0
    levi_count = 0
    prof_count = 0
    exec_count = 0
    fdc_lv15 = 0
    fdc_lv12 = 0
    dc_lv9 = 0
    arena_ranks = []
    ship_ranks = []
    success_count = 0
    gl_relic_dist = {base_id: {"r10": 0, "r9": 0} for base_id in GL_NAMES}

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_member_data, m): m for m in members}

        for future in as_completed(futures):
            result = future.result()
            if result.get("success"):
                success_count += 1
                gl_total += result["gl"]
                levi_count += result["levi"]
                prof_count += result["prof"]
                exec_count += result["exec"]
                fdc_lv15 += result["fdc_lv15"]
                fdc_lv12 += result["fdc_lv12"]
                dc_lv9 += result["dc_lv9"]

                if result["arena"]:
                    arena_ranks.append(result["arena"])
                if result["ship"]:
                    ship_ranks.append(result["ship"])

                for base_id, r_level in result["gl_relics"].items():
                    if base_id in gl_relic_dist:
                        if r_level >= 10:
                            gl_relic_dist[base_id]["r10"] += 1
                            gl_r10_total += 1
                        elif r_level == 9:
                            gl_relic_dist[base_id]["r9"] += 1
                            gl_r9_total += 1

    avg_arena = sum(arena_ranks) // len(arena_ranks) if arena_ranks else 0
    avg_ship = sum(ship_ranks) // len(ship_ranks) if ship_ranks else 0
    avg_gl = gl_total / member_count if member_count > 0 else 0

    return {
        "name": guild_name,
        "total_gp": total_gp,
        "member_count": member_count,
        "avg_gp": avg_gp,
        "leagues": leagues,
        "gp_10m_plus": gp_10m_plus,
        "gp_8m_to_10m": gp_8m_to_10m,
        "gl_total": gl_total,
        "gl_r10_total": gl_r10_total,
        "gl_r9_total": gl_r9_total,
        "avg_gl": avg_gl,
        "levi_count": levi_count,
        "prof_count": prof_count,
        "exec_count": exec_count,
        "fdc_lv15": fdc_lv15,
        "fdc_lv12": fdc_lv12,
        "dc_lv9": dc_lv9,
        "avg_arena": avg_arena,
        "avg_ship": avg_ship,
        "success_count": success_count,
        "gl_relic_dist": gl_relic_dist
    }

# ===== フォーマット =====
def format_gp(gp):
    """GPを3桁+M形式でフォーマット（例: 467M, _10M）"""
    return f"{gp // 1_000_000}M".rjust(4)

def row(own_val, opp_val, label, width=3):
    """数値 vs 数値 : ラベル の形式で1行生成"""
    own_str = str(own_val).rjust(width)
    opp_str = str(opp_val).rjust(width)
    return f"  {own_str} vs {opp_str}: {label}\n"

def format_comparison(own, opp):
    result = f"【TW戦力比較】{own['name']} vs {opp['name']}\n\n"
    result += "━━━━━━━━━━━━━━━━━━━━\n"

    # 総合戦力（GP=4, メンバー=2, 平均GP=4）
    result += "総合戦力\n"
    result += row(format_gp(own['total_gp']), format_gp(opp['total_gp']), "GP", width=4)
    result += row(own['member_count'], opp['member_count'], "メンバー数", width=2)
    result += row(format_gp(own['avg_gp']), format_gp(opp['avg_gp']), "平均GP", width=4)
    result += "\n"

    # GL（3桁、平均のみ特別）
    result += "GL（Galactic Legend）\n"
    result += row(own['gl_total'], opp['gl_total'], "合計", width=3)
    result += row(own['gl_r10_total'], opp['gl_r10_total'], "R10", width=3)
    result += row(own['gl_r9_total'], opp['gl_r9_total'], "R 9", width=3)
    result += row(f"{own['avg_gl']:.1f}", f"{opp['avg_gl']:.1f}", "平均", width=4)
    result += "\n"

    # GLレリック分布（2桁）
    result += "GLレリック分布\n"
    for base_id, name in GL_NAMES.items():
        od = own['gl_relic_dist'][base_id]
        op = opp['gl_relic_dist'][base_id]
        o_total = od['r10'] + od['r9']
        p_total = op['r10'] + op['r9']

        if o_total > 0 or p_total > 0:
            result += f"  {name}\n"
            result += row(o_total, p_total, "所持数", width=2)
            result += row(od['r10'], op['r10'], "R10", width=2)
            result += row(od['r9'], op['r9'], "R 9\n", width=2)
    result += "\n"

    # 主要艦船（2桁）
    result += "主要艦船\n"
    result += row(own['levi_count'], opp['levi_count'], "Leviathan", width=2)
    result += row(own['prof_count'], opp['prof_count'], "Profundity", width=2)
    result += row(own['exec_count'], opp['exec_count'], "Executor", width=2)
    result += "\n"

    # 平均値（3桁）
    result += "平均値\n"
    result += row(own['avg_arena'], opp['avg_arena'], "アリーナランク", width=3)
    result += row(own['avg_ship'], opp['avg_ship'], "シップランク", width=3)
    result += "\n"

    # データクロン（3桁）
    result += "データクロン\n"
    result += row(own['fdc_lv15'], opp['fdc_lv15'], "FDC Lv15", width=3)
    result += row(own['fdc_lv12'], opp['fdc_lv12'], "FDC Lv12", width=3)
    result += row(own['dc_lv9'], opp['dc_lv9'], "DC Lv9", width=3)
    result += "\n"

    # 個人ランク（2桁）
    result += "個人ランク\n"
    result += row(own['leagues']['Kyber'], opp['leagues']['Kyber'], "カイバー", width=2)
    result += row(own['leagues']['Aurodium'], opp['leagues']['Aurodium'], "オーロジウム", width=2)
    result += row(own['leagues']['Chromium'], opp['leagues']['Chromium'], "クロミウム", width=2)
    result += "\n"

    # GP分布（2桁）
    result += "GP分布\n"
    result += row(own['gp_10m_plus'], opp['gp_10m_plus'], "1000万超", width=2)
    result += row(own['gp_8m_to_10m'], opp['gp_8m_to_10m'], "800-1000万", width=2)
    result += "\n"

    result += "━━━━━━━━━━━━━━━━━━━━\n"
    result += f"データ取得: {own['success_count']}/{own['member_count']}人 vs {opp['success_count']}/{opp['member_count']}人\n"

    return result

def send_followup(webhook_url: str, content: str):
    try:
        response = requests.post(
            webhook_url,
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send followup: {e}")

# ===== FastAPIエンドポイント =====
@app.post("/api")
async def interactions(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    if not verify_discord_signature(request, body):
        return Response(status_code=401, content="Invalid signature")

    data = json.loads(body)

    if data.get("type") == 1:
        return {"type": 1}

    if data.get("type") == 2:
        command_name = data.get("data", {}).get("name")

        if command_name == "ping":
            return {"type": 4, "data": {"content": "Pong!"}}

        elif command_name == "twcompare":
            options = {opt["name"]: opt["value"] for opt in data.get("data", {}).get("options", [])}
            own_guild = extract_guild_id(options.get("own_guild", ""))
            opp_guild = extract_guild_id(options.get("opponent_guild", ""))

            if not own_guild or not opp_guild:
                return {"type": 4, "data": {"content": "エラー: ギルドIDが指定されていません"}}

            app_id = data.get("application_id")
            token = data.get("token")
            webhook_url = f"https://discord.com/api/v10/webhooks/{app_id}/{token}"

            def process_and_send():
                try:
                    own_data = analyze_guild(own_guild)
                    opp_data = analyze_guild(opp_guild)

                    if not own_data or not opp_data:
                        send_followup(webhook_url, "エラー: ギルドデータの取得に失敗しました")
                        return

                    comparison = format_comparison(own_data, opp_data)
                    send_followup(webhook_url, f"```\n{comparison}\n```")
                except Exception as e:
                    send_followup(webhook_url, f"エラーが発生しました: {str(e)}")

            background_tasks.add_task(process_and_send)
            return {"type": 5}

    return {"type": 4, "data": {"content": "Unknown command"}}

@app.get("/api")
async def health_check():
    return {"status": "ok"}
