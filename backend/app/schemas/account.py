from pydantic import BaseModel


class AccountOut(BaseModel):
    id: int
    name: str
    provider: str
    aws_account_id: str
    is_connected: bool
    aws_region: str | None = None

    class Config:
        from_attributes = True


class ConnectAwsRequest(BaseModel):
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"


class SyncResponse(BaseModel):
    synced_records: int
