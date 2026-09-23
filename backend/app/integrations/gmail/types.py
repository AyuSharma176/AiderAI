from pydantic import BaseModel


def _camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class GoogleOAuthTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    scope: str
    token_type: str = "Bearer"


class GmailHeader(BaseModel):
    name: str
    value: str


class GmailBody(BaseModel):
    data: str | None = None
    attachment_id: str | None = None


class GmailPayload(BaseModel):
    mime_type: str = ""
    filename: str = ""
    headers: list[GmailHeader] = []
    body: GmailBody = GmailBody()
    parts: list["GmailPayload"] = []

    model_config = {"populate_by_name": True, "alias_generator": lambda value: _camel(value)}


class GmailRawMessage(BaseModel):
    id: str
    history_id: str
    internal_date: str
    payload: GmailPayload

    model_config = {"populate_by_name": True, "alias_generator": lambda value: _camel(value)}


class GmailMessageRef(BaseModel):
    id: str


class GmailMessagePage(BaseModel):
    messages: list[GmailMessageRef] = []
    next_page_token: str | None = None
    history_id: str | None = None

    model_config = {"populate_by_name": True, "alias_generator": lambda value: _camel(value)}


class GmailHistoryMessage(BaseModel):
    message: GmailMessageRef


class GmailHistoryRecord(BaseModel):
    id: str
    messages_added: list[GmailHistoryMessage] = []

    model_config = {"populate_by_name": True, "alias_generator": lambda value: _camel(value)}


class GmailHistoryPage(BaseModel):
    history: list[GmailHistoryRecord] = []
    next_page_token: str | None = None
    history_id: str

    model_config = {"populate_by_name": True, "alias_generator": lambda value: _camel(value)}
