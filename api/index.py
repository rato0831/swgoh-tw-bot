import os
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

app = FastAPI()

DISCORD_PUBLIC_KEY = os.environ.get('DISCORD_PUBLIC_KEY')
verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))

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
                # swgoh.gg APIテスト
                url = f"https://swgoh.gg/api/guild/{own_guild}/"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    guild_data = response.json()
                    message = f"✅ 自ギルド: {guild_data.get('data', {}).get('name', 'unknown')}\nGP: {guild_data.get('data', {}).get('galactic_power', 'unknown')}"
                else:
                    message = f"❌ 失敗\nStatus: {response.status_code}"
                    
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
