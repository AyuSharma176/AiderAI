from pydantic import BaseModel


class GoogleOAuthTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    scope: str
    token_type: str = "Bearer"

