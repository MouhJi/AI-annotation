from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .auth import EmailInput, TokenInput

Role = Literal["owner", "admin", "annotator", "reviewer", "viewer"]
class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)

class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    @field_validator("name", "slug")
    @classmethod
    def not_null(cls, value):
        if value is None: raise ValueError("Name/slug cannot be null")
        return value

class RoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role

class InviteInput(EmailInput):
    role: Role

class DeleteWorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str

class AcceptInvitationInput(TokenInput): pass
