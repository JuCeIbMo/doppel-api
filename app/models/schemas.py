from pydantic import BaseModel, EmailStr, Field


# OAuth

class OAuthExchangeRequest(BaseModel):
    code: str
    waba_id: str
    phone_number_id: str | None = None
    is_coexistence: bool = False


class OAuthExchangeResponse(BaseModel):
    success: bool
    tenant_id: str
    message: str
    display_phone: str | None = None
    business_name: str | None = None


# Health

class HealthResponse(BaseModel):
    status: str
    service: str


# Auth

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None


class UserResponse(BaseModel):
    user_id: str
    email: str


class OTPSendRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    token: str = Field(min_length=6, max_length=6)


class TokenRefreshRequest(BaseModel):
    refresh_token: str


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
    bot_enabled: bool


class BotConfigUpdateRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000)
    welcome_message: str | None = Field(None, max_length=500)
    language: str | None = Field(None, max_length=10)
    ai_model: str | None = Field(None, max_length=50)
    bot_enabled: bool | None = None


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


class DeleteAccountResponse(BaseModel):
    success: bool
    message: str
