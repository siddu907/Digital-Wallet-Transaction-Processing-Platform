from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.core.constants import Role


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class UserPatch(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=160)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email", "full_name", mode="before")
    @classmethod
    def reject_null_fields(cls, value):
        if value is None:
            raise ValueError("This field cannot be null.")
        return value


class RoleChange(BaseModel):
    role: str = Field(
        description="Role to assign: super_admin, admin, support_agent, or customer.",
        examples=["admin"],
        min_length=1,
    )

    model_config = ConfigDict(json_schema_extra={"example": {"role": "admin"}})


__all__ = ["RoleChange", "UserOut", "UserPatch"]
