import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import MessageRole, ProgramLevel, UserRole


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- sessions / auth ---
class SessionOut(ORM):
    session_id: uuid.UUID = Field(validation_alias="id")
    expires_at: datetime
    user_id: uuid.UUID | None = None


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=150)


class UserOut(ORM):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleUpdateIn(BaseModel):
    role: UserRole


# --- catalogue ---
class InstitutionOut(ORM):
    code: str
    name: str
    city: str | None


class RequirementIO(ORM):
    bac_sections: list[str] = []
    min_average: Decimal | None = None
    required_diploma: str | None = None
    notes: str | None = None


class FeeIO(ORM):
    academic_year: str
    fee_type: str
    amount: Decimal
    currency: str = "TND"
    is_official: bool = False


class ProgramBase(BaseModel):
    level: ProgramLevel
    name: str
    specialization: str | None = None
    duration_years: int | None = Field(default=None, ge=1, le=8)
    language: str | None = None
    description: str | None = None
    career_outcomes: list[str] = []
    bridges: list[str] = []
    source_url: str | None = None
    requirements: list[RequirementIO] = []
    fees: list[FeeIO] = []


class ProgramIn(ProgramBase):
    code: str = Field(min_length=2, max_length=40)
    institution_code: str


class ProgramOut(ProgramBase, ORM):
    code: str
    institution: InstitutionOut
    data_source: str
    last_synced_at: datetime | None
    updated_at: datetime


class ProgramSummary(ORM):
    code: str
    name: str
    level: ProgramLevel
    duration_years: int | None
    institution: InstitutionOut


# --- chat ---
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


class ChatOut(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    language: str


class ConversationOut(ORM):
    id: uuid.UUID
    title: str | None
    detected_language: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(ORM):
    id: uuid.UUID
    role: MessageRole
    content: str
    language: str | None
    created_at: datetime
