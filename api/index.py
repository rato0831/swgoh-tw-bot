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

    if data.get('type') == 1:
        return JSONResponse(content={"type": 1})

    if data.get('type') == 2:
        if data['data']['name'] == 'ping':
            return JSONResponse(content={"type": 4, "data": {"content": "Pong!"}})

    return JSONResponse(content={"message": "Unhandled interaction type"})
