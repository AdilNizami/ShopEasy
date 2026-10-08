from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


class AccessTokenResponse(BaseModel):
    access_token: str = Field(serialization_alias="accessToken")
    token_type: str = Field(default="Bearer", serialization_alias="tokenType")
    expires_in: int = Field(serialization_alias="expiresIn")
    user_id: UUID = Field(serialization_alias="userId")


class CurrentUserResponse(BaseModel):
    user_id: UUID = Field(serialization_alias="userId")
    username: str
    role: str
