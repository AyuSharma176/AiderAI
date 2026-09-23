import base64
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Query
from fastapi.responses import RedirectResponse

app = FastAPI(title="SupportAI fake Gmail")


def encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


@app.get("/oauth/authorize")
async def authorize(redirect_uri: str, state: str):
    query = urlencode({"code": "integration-code", "state": state})
    return RedirectResponse(f"{redirect_uri}?{query}")


@app.post("/oauth/token")
async def token(grant_type: str = Form(...)):
    if grant_type == "authorization_code":
        return {
            "access_token": "integration-access",
            "refresh_token": "integration-refresh",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
            "token_type": "Bearer",
        }
    return {"access_token": "integration-access", "expires_in": 3600, "token_type": "Bearer"}


@app.post("/oauth/revoke")
async def revoke():
    return {}


@app.get("/gmail/users/me/profile")
async def profile():
    return {"emailAddress": "orders@example.com", "historyId": "100"}


@app.get("/gmail/users/me/messages")
async def messages(q: str = Query(""), pageToken: str | None = None):
    del q, pageToken
    return {"messages": [{"id": "amazon-1"}, {"id": "flipkart-1"}], "historyId": "101"}


@app.get("/gmail/users/me/messages/{message_id}")
async def message(message_id: str):
    if message_id == "amazon-1":
        sender = "updates@amazon.in"
        subject = "Shipped 402-0000000-0000000"
        text = "Order # 402-0000000-0000000 Item: USB-C charger (Qty: 1)"
    else:
        sender = "updates@flipkart.com"
        subject = "Delivered OD000000000000000000"
        text = "Order ID: OD000000000000000000 Item: Wireless mouse (Qty: 1) delivered"
    return {
        "id": message_id,
        "historyId": "101",
        "internalDate": "1789898400000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": encoded(text)},
        },
    }


@app.get("/gmail/users/me/history")
async def history(startHistoryId: str):
    return {"history": [], "historyId": startHistoryId}
