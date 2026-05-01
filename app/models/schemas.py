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
    requires_manager_setup: bool = True


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
    media: list[dict] | None = None
    agent_mode: str | None = None


class PaginatedMessages(BaseModel):
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int


class DeleteAccountResponse(BaseModel):
    success: bool
    message: str


class AdminPhonesResponse(BaseModel):
    """List of phone numbers (digits only, no '+') that may talk to the manager agent."""
    phones: list[str]


class AdminPhonesUpdateRequest(BaseModel):
    """Replace the full admin-phone list. Server normalizes each entry to digits only."""
    phones: list[str] = Field(default_factory=list, max_length=10)


# Business info / products


class BusinessInfoResponse(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    hours: str = ""
    address: str = ""
    payment_methods: str = ""


class BusinessInfoUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)
    hours: str | None = Field(None, max_length=500)
    address: str | None = Field(None, max_length=500)
    payment_methods: str | None = Field(None, max_length=500)


class ProductResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    price: float | None = None
    available: bool = True


class ProductCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    price: float | None = Field(default=None, ge=0)
    available: bool = True


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    price: float | None = Field(None, ge=0)
    available: bool | None = None
