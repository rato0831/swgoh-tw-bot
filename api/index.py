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

def get_guild_data(guild_id):
    """ギルドの基本情報を取得"""
    url = f"http://swgoh.gg/api/guild-profile/{guild_id}"
    headers = {
        "content-type": "application/json",
        "x-gg-bot-access": SWGOH_API_KEY
    }
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code != 200:
        return None
    return response.json()

def get_player_data(ally_code):
    """プレイヤーの詳細情報を取得"""
    url = f"http://swgoh.gg/api/player/{ally_code}/"
    headers = {
        "content-type": "application/json",
        "x-gg-bot-access": SWGOH_API_KEY
    }
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code != 200:
        return None
    return response.json()

def analyze_guild(guild_id):
    """ギルド全体の統計を分析（並列処理版）"""
    guild_data = get_guild_data(guild_id)
    if not guild_data:
        return None
    
    guild_name = guild_data.get("data", {}).get("name", "???")
    members = guild_data.get("data", {}).get("members", [])
    
    # Phase 1データ（すぐ計算可能）
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
    
    # Phase 2: 並列でメンバー詳細取得
    gl_total = 0
    levi_count = 0
    prof_count = 0
    exec_count = 0
    fdc_lv15 = 0
    fdc_lv12 = 0
    dc_lv9 = 0
    arena_ranks = []
    ship_ranks = []
    success_count = 0
    failed_count = 0
    
    def process_member(member):
        """1メンバーの詳細データ取得"""
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
            "ship": None
        }
        
        # GL数
        units = player_data.get("units", [])
        for unit in units:
            if unit.get("data", {}).get("is_galactic_legend", False):
                result["gl"] += 1
            
            base_id = unit.get("data", {}).get("base_id", "")
            if base_id == "CAPITALLEVIATHAN":
                result["levi"] = 1
            elif base_id == "CAPITALPROFUNDITY":
                result["prof"] = 1
            elif base_id == "CAPITALEXECUTOR":
                result["exec"] = 1
        
        # データクロン（現在のtierでカウント）
        datacrons = player_data.get("datacrons", [])
        for dc in datacrons:
            tier = dc.get("tier", 0)
            template = dc.get("template_base_id", "")
            is_focused = "focused" in template.lower()
            
        # データクロン部分
        if tier >= 9:
            result["dc_lv9"] += 1
        if tier >= 12 and is_focused:
            result["fdc_lv12"] += 1
        if tier == 15 and is_focused:
            result["fdc_lv15"] += 1

        # ランク
        data_section = player_data.get("data", {})
        result["arena"] = data_section.get("arena_rank")
        result["ship"] = data_section.get("fleet_arena", {}).get("rank")
        
        return result
    
    # 並列処理実行（最大20スレッド）
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_member, m): m for m in members}
        
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
            else:
                failed_count += 1
    
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
        "failed_count": failed_count
    }

def format_gp(gp):
    """GPをM単位でフォーマット"""
    return f"{gp // 1_000_000}M"

def format_comparison(own, opp):
    """比較結果をフォーマット（Phase 2対応）"""
    result = f"【TW戦力比較】{own['name']} vs {opp['name']}\n\n"
    result += "━━━━━━━━━━━━━━━━━━━━\n"
    result += "総合戦力\n"
    result += f"  GP: {format_gp(own['total_gp'])} vs {format_gp(opp['total_gp'])}\n"
    result += f"  メンバー数: {own['member_count']}人 vs {opp['member_count']}人\n"
    result += f"  平均GP: {format_gp(own['avg_gp'])} vs {format_gp(opp['avg_gp'])}\n\n"
    
    result += "GL（Galactic Legend）\n"
    result += f"  合計: {own['gl_total']}体 vs {opp['gl_total']}体\n"
    result += f"  平均: {own['avg_gl']:.1f}体 vs {opp['avg_gl']:.1f}体\n\n"
    
    result += "主要艦船\n"
    result += f"  Leviathan: {own['levi_count']}隻 vs {opp['levi_count']}隻\n"
    result += f"  Profundity: {own['prof_count']}隻 vs {opp['prof_count']}隻\n"
    result += f"  Executor: {own['exec_count']}隻 vs {opp['exec_count']}隻\n\n"
    
    result += "平均値\n"
    result += f"  平均アリーナランク: {own['avg_arena']}位 vs {opp['avg_arena']}位\n"
    result += f"  平均シップランク: {own['avg_ship']}位 vs {opp['avg_ship']}位\n\n"
    
    result += "データクロン\n"
    result += f"  FDC Lv15: {own['fdc_lv15']}個 vs {opp['fdc_lv15']}個\n"
    result += f"  FDC Lv12: {own['fdc_lv12']}個 vs {opp['fdc_lv12']}個\n"
    result += f"  DC Lv9: {own['dc_lv9']}個 vs {opp['dc_lv9']}個\n\n"
    
    result += "個人ランク\n"
    result += f"  カイバー: {own['leagues']['Kyber']}人 vs {opp['leagues']['Kyber']}人\n"
    result += f"  オーロジウム: {own['leagues']['Aurodium']}人 vs {opp['leagues']['Aurodium']}人\n"
    result += f"  クロミウム: {own['leagues']['Chromium']}人 vs {opp['leagues']['Chromium']}人\n\n"
    
    result += "GP分布\n"
    result += f"  1000万超: {own['gp_10m_plus']}人 vs {opp['gp_10m_plus']}人\n"
    result += f"  800-1000万: {own['gp_8m_to_10m']}人 vs {opp['gp_8m_to_10m']}人\n"
    result += "━━━━━━━━━━━━━━━━━━━━\n"
    result += f"\nデータ取得状況: {own['success_count']}/{own['member_count']}人 vs {opp['success_count']}/{opp['member_count']}人\n"
    
    return result

def send_followup(webhook_url: str, content: str):
    """Webhook経由で結果送信"""
    try:
        response = requests.post(
            webhook_url,
            json={"content": content},
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send followup: {e}")

@app.post("/api")
async def interactions(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    if not verify_discord_signature(request, body):
        return Response(status_code=401, content="Invalid signature")
    
    data = json.loads(body)
    
    # PING
    if data.get("type") == 1:
        return {"type": 1}
    
    # Slash Command
    if data.get("type") == 2:
        command_name = data.get("data", {}).get("name")
        
        if command_name == "ping":
            return {
                "type": 4,
                "data": {"content": "Pong!"}
            }
        
        elif command_name == "twcompare":
            options = {opt["name"]: opt["value"] for opt in data.get("data", {}).get("options", [])}
            own_guild = options.get("own_guild")
            opp_guild = options.get("opponent_guild")
            
            if not own_guild or not opp_guild:
                return {
                    "type": 4,
                    "data": {"content": "エラー: ギルドIDが指定されていません", "flags": 64}
                }
            
            # Webhook URL生成
            app_id = data.get("application_id")
            token = data.get("token")
            webhook_url = f"https://discord.com/api/v10/webhooks/{app_id}/{token}"
            
            # バックグラウンドタスク登録
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
            
            # すぐに「処理中」を返す
            return {
                "type": 5,  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
                "data": {"flags": 64}  # Ephemeral
            }
    
    return {"type": 4, "data": {"content": "Unknown command"}}

@app.get("/api")
async def health_check():
    return {"status": "ok"}
