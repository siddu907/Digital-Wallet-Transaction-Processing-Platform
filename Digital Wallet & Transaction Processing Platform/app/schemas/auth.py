from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=3, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = "Newpass@123"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


__all__ = ["PasswordChange", "RefreshRequest", "TokenPair", "UserLogin", "UserRegister"]
