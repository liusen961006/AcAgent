from fastapi import FastAPI, HTTPException
import uvicorn
import json
from pathlib import Path

app = FastAPI()
MSG_FILE = Path("messages.json")

@app.post("/send")
def send_message(data: dict):
    msg = {"from": data.get("from", "unknown"), "content": data.get("content", ""), "ts": time.time()}
    msgs = json.loads(MSG_FILE.read_text()) if MSG_FILE.exists() else []
    msgs.append(msg)
    MSG_FILE.write_text(json.dumps(msgs))
    return {"status": "ok"}

@app.get("/recv")
def recv_messages():
    if not MSG_FILE.exists():
        return []
    msgs = json.loads(MSG_FILE.read_text())
    MSG_FILE.unlink()  # clear after read
    return msgs

if __name__ == "__main__":
    import time
    uvicorn.run(app, host="0.0.0.0", port=8000)
