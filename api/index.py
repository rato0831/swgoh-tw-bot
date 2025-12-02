import os
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
            
            # とりあえず受け取った値を表示
            message = f"受け取りました！\n自ギルド: {own_guild}\n相手ギルド: {opponent_guild}\n\n（データ取得処理は次のステップで実装します）"
            
            return JSONResponse(content={"type": 4, "data": {"content": message}})

    return JSONResponse(content={"message": "Unhandled interaction type"})
