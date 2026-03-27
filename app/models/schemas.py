from pydantic import BaseModel, EmailStr, Field


# OAuth

class OAuthExchangeRequest(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str


class OAuthExchangeResponse(BaseModel):
    success: bool
    tenant_id: str
    message: str


# Health

class HealthResponse(BaseModel):
    status: str
    service: str


# Auth

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterResponse(BaseModel):
    success: bool
    user_id: str
    message: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    user_id: str
    email: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    access_token: str
    new_password: str = Field(min_length=8)


# Dashboard

class TenantResponse(BaseModel):
    id: str
    business_name: str
    email: str | None
    plan: str
    status: str
    created_at: str


class WhatsAppAccountResponse(BaseModel):
    id: str
    waba_id: str
    phone_number_id: str
    display_phone: str | None
    status: str
    created_at: str


class BotConfigResponse(BaseModel):
    id: str
    system_prompt: str
    welcome_message: str
    language: str
    ai_model: str


class BotConfigUpdateRequest(BaseModel):
    system_prompt: str | None = None
    welcome_message: str | None = None
    language: str | None = None
    ai_model: str | None = None


class MessageResponse(BaseModel):
    id: str
    user_phone: str
    direction: str
    content: str | None
    message_type: str
    created_at: str


class PaginatedMessages(BaseModel):
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int
