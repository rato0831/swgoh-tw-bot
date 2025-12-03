import os
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

app = FastAPI()

DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY')
SWGOH_API_KEY = os.environ.get('SWGOH_API_KEY')
verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))

def format_number(num):
    """数値を見やすくフォーマット（例: 4670000 → 467M）"""
    if num >= 1000000:
        return f"{num / 1000000:.0f}M"
    elif num >= 1000:
        return f"{num / 1000:.0f}K"
    return str(num)

def get_guild_data(guild_id):
    """swgoh.gg APIから実データ取得"""
    url = f"http://swgoh.gg/api/guild-profile/{guild_id}"
    headers = {
        "content-type": "application/json",
        "x-gg-bot-access": SWGOH_API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        data = response.json()
        guild_info = data.get('data', {})
        
        # 基本情報
        result = {
            "name": guild_info.get('name', 'Unknown'),
            "gp": guild_info.get('galactic_power', 0),
            "member_count": guild_info.get('member_count', 0),
        }
        
        # メンバー情報を集計
        members = guild_info.get('members', [])
        
        # リーグ別カウント
        league_counts = {}
        for member in members:
            league = member.get('league_id', 'UNKNOWN')
            league_counts[league] = league_counts.get(league, 0) + 1
        
        result['kyber'] = league_counts.get('KYBER', 0)
        result['aurodium'] = league_counts.get('AURODIUM', 0)
        result['chromium'] = league_counts.get('CHROMIUM', 0)
        
        # GP分布
        gp_10m_plus = 0
        gp_8m_10m = 0
        total_gp = 0
        
        for member in members:
            gp = member.get('galactic_power', 0)
            total_gp += gp
            if gp >= 10000000:
                gp_10m_plus += 1
            elif gp >= 8000000:
                gp_8m_10m += 1
        
        result['gp_10m_plus'] = gp_10m_plus
        result['gp_8m_10m'] = gp_8m_10m
        result['avg_gp'] = total_gp // len(members) if members else 0
        
        return result
        
    except Exception as e:
        print(f"Error fetching guild data: {str(e)}")
        return None

def compare_guilds(own_data, opponent_data):
    """2つのギルドを比較してフォーマットされた文字列を返す"""
    output = f"【TW戦力比較】{own_data['name']} vs {opponent_data['name']}\n\n"
    output += "━━━━━━━━━━━━━━━━━━━━\n"
    output += "総合戦力\n"
    output += f"  GP: {format_number(own_data['gp'])} vs {format_number(opponent_data['gp'])}\n"
    output += f"  メンバー数: {own_data['member_count']}人 vs {opponent_data['member_count']}人\n"
    output += f"  平均GP: {format_number(own_data['avg_gp'])} vs {format_number(opponent_data['avg_gp'])}\n\n"
    
    output += "個人ランク\n"
    output += f"  カイバー: {own_data['kyber']}人 vs {opponent_data['kyber']}人\n"
    output += f"  オーロジウム: {own_data['aurodium']}人 vs {opponent_data['aurodium']}人\n"
    output += f"  クロミウム: {own_data['chromium']}人 vs {opponent_data['chromium']}人\n\n"
    
    output += "GP分布\n"
    output += f"  1000万超: {own_data['gp_10m_plus']}人 vs {opponent_data['gp_10m_plus']}人\n"
    output += f"  800-1000万: {own_data['gp_8m_10m']}人 vs {opponent_data['gp_8m_10m']}人\n"
    output += "━━━━━━━━━━━━━━━━━━━━\n"
    
    return output

@app.post("/api")
async def interactions(request: Request):
    signature = request.headers.get('X-Signature-Ed25519')
    timestamp = request.headers.get('X-Signature-Timestamp')
    body = await request.body()

    if signature is None or timestamp is None:
        raise HTTPException(status_code=401, detail="Missing signature headers")

    try:
        verify_key.verify(f'{timestamp}{body.decode("utf-8")}'.encode(), bytes.fromhex(signature))
    except BadSignatureError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()

    # Discord PING
    if data.get('type') == 1:
        return JSONResponse(content={"type": 1})

    # コマンド実行
    if data.get('type') == 2:
        command_name = data['data']['name']
        
        # /ping コマンド
        if command_name == 'ping':
            return JSONResponse(content={"type": 4, "data": {"content": "Pong!"}})
        
        # /twcompare コマンド
        if command_name == 'twcompare':
            options = data['data']['options']
            own_guild = next(opt['value'] for opt in options if opt['name'] == 'own_guild')
            opponent_guild = next(opt['value'] for opt in options if opt['name'] == 'opponent_guild')
            
            # データ取得
            own_data = get_guild_data(own_guild)
            opponent_data = get_guild_data(opponent_guild)
            
            if not own_data or not opponent_data:
                message = "❌ ギルドデータの取得に失敗しました。ギルドIDを確認してください。"
            else:
                message = compare_guilds(own_data, opponent_data)
            
            return JSONResponse(content={
                "type": 4, 
                "data": {
                    "content": message,
                    "flags": 64
                }
            })

    return JSONResponse(content={"message": "Unhandled interaction type"})
