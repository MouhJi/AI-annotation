from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
class EmailInput(StrictInput):
    email: EmailStr = Field(max_length=255)
    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().casefold() if isinstance(value, str) else value
class RegisterInput(EmailInput):
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=1024)
    @field_validator("full_name")
    @classmethod
    def name(cls, value):
        if not value.strip(): raise ValueError("Full name cannot be blank")
        return value.strip()
class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=1024)
class ProfileInput(StrictInput):
    full_name: str = Field(min_length=1, max_length=150)
    @field_validator("full_name")
    @classmethod
    def name(cls, value):
        if not value.strip(): raise ValueError("Full name cannot be blank")
        return value.strip()
class ChangePasswordInput(StrictInput):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)
class TokenInput(StrictInput):
    token: str = Field(min_length=20, max_length=256)
class ResetInput(TokenInput):
    new_password: str = Field(min_length=12, max_length=1024)
