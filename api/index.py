import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

app = FastAPI()

DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY')
verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))

def format_number(num):
    """数値を見やすくフォーマット（例: 4670000 → 467M）"""
    if num >= 1000000:
        return f"{num / 1000000:.0f}M"
    elif num >= 1000:
        return f"{num / 1000:.0f}K"
    return str(num)

def get_mock_guild_data(guild_id):
    """モックデータを返す（API承認後、ここを実データ取得に差し替え）"""
    if "test1" in guild_id.lower() or "zvca" in guild_id.lower():
        return {
            "name": "職人魂",
            "gp": 467000000,
            "member_count": 46,
            "gl_count": 243,
            "leviathan": 14,
            "profundity": 15,
            "executor": 26,
            "avg_skill": 2323,
            "avg_arena": 272,
            "avg_ship": 68,
            "datacron_15": 13,
            "datacron_12": 18,
            "datacron_9": 81,
            "kyber": 6,
            "aurodium": 8,
            "gp_10m_plus": 27,
            "gp_8m_10m": 11
        }
    else:
        return {
            "name": "相手ギルド",
            "gp": 438000000,
            "member_count": 49,
            "gl_count": 247,
            "leviathan": 13,
            "profundity": 22,
            "executor": 40,
            "avg_skill": 2362,
            "avg_arena": 227,
            "avg_ship": 68,
            "datacron_15": 9,
            "datacron_12": 11,
            "datacron_9": 105,
            "kyber": 7,
            "aurodium": 9,
            "gp_10m_plus": 16,
            "gp_8m_10m": 18
        }

def compare_guilds(own_data, opponent_data):
    """2つのギルドを比較してフォーマットされた文字列を返す"""
    output = f"【TW戦力比較】{own_data['name']} vs {opponent_data['name']}\n\n"
    output += "━━━━━━━━━━━━━━━━━━━━\n"
    output += "総合戦力\n"
    output += f"  GP: {format_number(own_data['gp'])} vs {format_number(opponent_data['gp'])}\n"
    output += f"  メンバー数: {own_data['member_count']}人 vs {opponent_data['member_count']}人\n"
    output += f"  GL総数: {own_data['gl_count']} vs {opponent_data['gl_count']}\n\n"
    
    output += "艦船戦力\n"
    output += f"  Leviathan: {own_data['leviathan']} vs {opponent_data['leviathan']}\n"
    output += f"  Profundity: {own_data['profundity']} vs {opponent_data['profundity']}\n"
    output += f"  Executor: {own_data['executor']} vs {opponent_data['executor']}\n\n"
    
    output += "平均値\n"
    output += f"  スキルレート: {own_data['avg_skill']:,} vs {opponent_data['avg_skill']:,}\n"
    output += f"  アリーナランク: {own_data['avg_arena']}位 vs {opponent_data['avg_arena']}位\n"
    output += f"  シップランク: {own_data['avg_ship']}位 vs {opponent_data['avg_ship']}位\n\n"
    
    output += "データクロン\n"
    output += f"  Lv15: {own_data['datacron_15']}人 vs {opponent_data['datacron_15']}人\n"
    output += f"  Lv12: {own_data['datacron_12']}人 vs {opponent_data['datacron_12']}人\n"
    output += f"  Lv9: {own_data['datacron_9']}個 vs {opponent_data['datacron_9']}個\n\n"
    
    output += "個人ランク\n"
    output += f"  カイバー: {own_data['kyber']}人 vs {opponent_data['kyber']}人\n"
    output += f"  オーロジウム: {own_data['aurodium']}人 vs {opponent_data['aurodium']}人\n\n"
    
    output += "GP分布\n"
    output += f"  1000万超: {own_data['gp_10m_plus']}人 vs {opponent_data['gp_10m_plus']}人\n"
    output += f"  800-1000万: {own_data['gp_8m_10m']}人 vs {opponent_data['gp_8m_10m']}人\n"
    output += "━━━━━━━━━━━━━━━━━━━━\n"
    output += "\n※ モックデータで動作確認中（API承認後、実データに切り替わります）"
    
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
            
            try:
                # モックデータ取得（API承認後、ここを実装に差し替え）
                own_data = get_mock_guild_data(own_guild)
                opponent_data = get_mock_guild_data(opponent_guild)
                
                # 比較結果をフォーマット
                message = compare_guilds(own_data, opponent_data)
                
            except Exception as e:
                message = f"❌ エラー発生: {str(e)}"
            
            return JSONResponse(content={
                "type": 4, 
                "data": {
                    "content": message,
                    "flags": 64
                }
            })

    return JSONResponse(content={"message": "Unhandled interaction type"})
