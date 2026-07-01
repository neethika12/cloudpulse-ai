from pydantic import BaseModel


class AccountOut(BaseModel):
    id: int
    name: str
    provider: str
    aws_account_id: str

    class Config:
        from_attributes = True
