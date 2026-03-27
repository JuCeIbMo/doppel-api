# Doppel — Contexto completo para Claude Code

## Qué es este documento

Este documento contiene TODO el contexto que necesitas para implementar la integración de WhatsApp Embedded Signup en la plataforma Doppel. Léelo completo antes de escribir una sola línea de código.

---

## Resumen del proyecto

**Doppel** es un SaaS que permite a negocios conectar su WhatsApp Business a un sistema de automatización con IA. Los negocios (tenants) se onboardean a través de un flujo llamado "Embedded Signup" de Meta/Facebook, que es un popup OAuth donde autorizan a Doppel a gestionar su WhatsApp vía Cloud API.

## Infraestructura existente

- **Dominio:** `doppel.lat` (funcionando con HTTPS)
- **Frontend:** Next.js, ya desplegado en Dokploy en la VPS
- **Backend:** Aún no existe — crear con FastAPI (Python)
- **Base de datos:** Supabase (proyecto por crear)
- **VPS:** Hetzner con Dokploy para orquestación de containers
- **Subdominios planeados:**
  - `doppel.lat` → Frontend (Next.js)
  - `api.doppel.lat` → Backend (FastAPI) — por crear

## Variables de entorno que el usuario proporcionará

El usuario debe configurar manualmente en Meta developers.facebook.com primero. Las instrucciones están en la sección "PASOS MANUALES" más abajo. Los valores se obtienen de ahí:

```env
# Meta App (de developers.facebook.com → App Doppel → Settings → Basic)
META_APP_ID=<857809177275175>
META_APP_SECRET=<2ef82595b82bab7f6e3c3009e1ebb9fb>
META_CONFIG_ID=<el usuario te lo dará>
META_VERIFY_TOKEN=doppel_wh_verify_2026
META_API_VERSION=v21.0

# Supabase
SUPABASE_URL=<el usuario te lo dará>
SUPABASE_SERVICE_KEY=<el usuario te lo dará>

# Anthropic (para el bot de IA — fase posterior)
ANTHROPIC_API_KEY=<el usuario te lo dará>

# Seguridad
ENCRYPTION_KEY=<generar una clave aleatoria de 32 bytes en hex>
```

---

## PASOS MANUALES — El usuario debe hacer esto ANTES de que el código funcione

### Paso 1: Obtener App ID y App Secret

1. Ir a https://developers.facebook.com
2. Seleccionar la app "Doppel"
3. Ir a Settings → Basic
4. Copiar **App ID** y **App Secret** (click "Show")
5. En esa misma página, configurar:
   - Privacy Policy URL: `https://doppel.lat/privacidad`
   - Terms of Service URL: `https://doppel.lat/terminos`
   - Data Deletion Instructions URL: `https://doppel.lat/eliminar-datos`
   - App Domains: `doppel.lat`
   - App Icon: subir logo de Doppel

### Paso 2: Agregar producto "Facebook Login for Business"

1. En el dashboard de la app → Add Product
2. Seleccionar "Facebook Login for Business"
3. Ir a Facebook Login for Business → Settings
4. En Client OAuth Settings:
   - Valid OAuth Redirect URIs: `https://doppel.lat/auth/callback`
   - Allowed Domains for the JavaScript SDK: `https://doppel.lat`
   - Login with JavaScript SDK: Yes
   - Enforce HTTPS: Yes
5. Click Save Changes

### Paso 3: Crear Login Configuration (obtener config_id)

1. Ir a Facebook Login for Business → Configurations
2. Click "Create configuration"
3. Nombre: "Doppel WhatsApp Signup"
4. Login variation: "WhatsApp Embedded Signup"
5. Products: seleccionar "WhatsApp Cloud API"
6. Token expiration: "Never"
7. Assets: seleccionar "WhatsApp accounts"
8. Permissions: marcar `whatsapp_business_management` y `whatsapp_business_messaging`
9. Click Create
10. **Copiar el Configuration ID** que aparece — este es el `META_CONFIG_ID`

### Paso 4: Configurar Webhook

1. En la app de Meta → sección WhatsApp → Configuration
2. Callback URL: `https://api.doppel.lat/webhook/whatsapp`
3. Verify Token: `doppel_wh_verify_2026` (debe coincidir con META_VERIFY_TOKEN)
4. Suscribirse a: `messages`
5. **IMPORTANTE:** El backend debe estar corriendo y respondiendo al GET del webhook ANTES de que Meta acepte verificar la URL

### Paso 5: Crear proyecto en Supabase

1. Ir a https://supabase.com → crear proyecto nuevo "doppel"
2. Región: us-east-1
3. Copiar la URL del proyecto y la Service Role Key
4. Ejecutar el SQL de migración (proporcionado más abajo)

---

## IMPLEMENTACIÓN — Lo que Claude Code debe construir

### A) Frontend — Componentes Next.js

#### A.1 — Componente de Embedded Signup (`/app/conectar/page.tsx`)

Página que carga el Facebook JavaScript SDK y presenta un botón para iniciar el flujo de Embedded Signup. Al completarse, envía los datos al backend.

**Lógica del componente:**

```typescript
// 1. Cargar Facebook SDK al montar el componente
// El SDK se carga desde https://connect.facebook.net/en_US/sdk.js
// Se inicializa con:
window.fbAsyncInit = function() {
  FB.init({
    appId: process.env.NEXT_PUBLIC_META_APP_ID,
    autoLogAppEvents: true,
    xfbml: true,
    version: 'v21.0'
  });
};

// 2. Event listener para capturar datos del flujo (waba_id, phone_number_id)
const sessionInfoListener = (event) => {
  if (event.origin !== "https://www.facebook.com") return;
  try {
    const data = JSON.parse(event.data);
    if (data.type === "WA_EMBEDDED_SIGNUP") {
      if (data.event === "FINISH" || data.event === "FINISH_ONLY_WABA") {
        const { waba_id, phone_number_id } = data.data;
        // Guardar estos valores para enviar al backend
      }
    }
  } catch { /* non-JSON response, ignorar */ }
};
window.addEventListener("message", sessionInfoListener);

// 3. Función que se llama al click del botón
function launchEmbeddedSignup() {
  FB.login(
    function(response) {
      if (response.authResponse) {
        const code = response.authResponse.code;
        // Enviar code + waba_id + phone_number_id al backend
        // POST https://api.doppel.lat/oauth/exchange
        // Body: { code, waba_id, phone_number_id }
      }
    },
    {
      config_id: process.env.NEXT_PUBLIC_META_CONFIG_ID,
      response_type: 'code',
      override_default_response_type: true,
      extras: {
        setup: {},
        featureType: '',  // Vacío para Embedded Signup estándar
                          // Cambiar a 'whatsapp_business_app_onboarding' cuando tengamos Tech Provider
        sessionInfoVersion: '3',
      }
    }
  );
}
```

**Variables de entorno del frontend (en .env.local):**
```
NEXT_PUBLIC_META_APP_ID=<app_id>
NEXT_PUBLIC_META_CONFIG_ID=<config_id>
NEXT_PUBLIC_API_URL=https://api.doppel.lat
```

**UX del flujo:**
1. Usuario llega a `/conectar`
2. Ve un botón grande "Conecta tu WhatsApp Business"
3. Click → se abre popup de Facebook
4. En el popup: login con Facebook → seleccionar/crear WABA → verificar número
5. Popup se cierra → frontend muestra "¡Conectado!" o error
6. Frontend envió los datos al backend en background

**Tipo de SDK de Facebook:** NO usar npm package. Cargar el SDK via script tag dinámicamente al montar el componente. El SDK se carga así:

```javascript
(function(d, s, id) {
  var js, fjs = d.getElementsByTagName(s)[0];
  if (d.getElementById(id)) return;
  js = d.createElement(s); js.id = id;
  js.src = "https://connect.facebook.net/en_US/sdk.js";
  fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));
```

#### A.2 — Páginas legales

Crear tres páginas estáticas que Meta requiere. Deben estar accesibles públicamente:

- `/privacidad` — Política de privacidad
- `/terminos` — Términos de servicio
- `/eliminar-datos` — Instrucciones de eliminación de datos

**Contenido de la política de privacidad** (adaptar a español):
- Qué datos recopilamos: nombre del negocio, número de WhatsApp, mensajes procesados
- Para qué los usamos: proveer servicio de automatización de mensajería
- Con quién compartimos: Meta/WhatsApp como intermediario técnico
- Cómo los protegemos: encriptación en tránsito y en reposo
- Derechos del usuario: acceso, rectificación, eliminación
- Contacto: privacidad@doppel.lat
- Retención: datos se eliminan a los 90 días de cancelar el servicio

**Contenido de términos de servicio:**
- Descripción del servicio
- Responsabilidades del usuario (no spam, cumplir políticas de WhatsApp)
- Limitaciones de responsabilidad
- Cancelación: el usuario puede desconectar en cualquier momento

**Contenido de eliminación de datos:**
- Enviar solicitud a privacidad@doppel.lat
- O usar el botón "Eliminar mis datos" en el dashboard (futuro)
- Plazo: 30 días hábiles
- Se eliminan: credenciales, mensajes, configuraciones del bot

#### A.3 — Estética

La estética del frontend debe ser inspirada en Apple: fondo oscuro (#0a0a0a o similar), tipografía grande y limpia, mucho espacio en blanco, animaciones suaves con Framer Motion, CTAs claros con hover effects sutiles. NO usar estética genérica de AI/SaaS. Piensa en apple.com pero para una plataforma de automatización de WhatsApp.

---

### B) Backend — FastAPI

#### B.0 — Estructura del proyecto

```
doppel-api/
├── app/
│   ├── main.py                 # FastAPI app, CORS, lifespan
│   ├── config.py               # Pydantic Settings (env vars)
│   ├── routers/
│   │   ├── oauth.py            # POST /oauth/exchange
│   │   ├── webhook.py          # GET + POST /webhook/whatsapp
│   │   └── health.py           # GET /health
│   ├── services/
│   │   ├── meta_api.py         # Llamadas a Graph API de Meta
│   │   └── supabase_client.py  # Cliente de Supabase
│   └── models/
│       └── schemas.py          # Pydantic models
├── requirements.txt
├── Dockerfile
└── .env.example
```

#### B.1 — GET /webhook/whatsapp (Verificación del webhook)

Meta envía un GET para verificar que tu webhook es real. Debes responder con el challenge.

```python
@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")
```

**CRÍTICO:** Este endpoint DEBE estar funcionando ANTES de que el usuario configure el webhook en Meta. Meta hace la verificación inmediatamente al guardar la URL.

#### B.2 — POST /oauth/exchange (Intercambio de token)

Este es el endpoint más importante. Recibe el `code` del frontend y lo intercambia por un access_token con Meta.

**Flujo completo:**

```
1. Recibir { code, waba_id, phone_number_id } del frontend
2. POST a https://graph.facebook.com/v21.0/oauth/access_token
   params: client_id=APP_ID, client_secret=APP_SECRET, code=code
   → Respuesta: { access_token: "..." }
3. Con el access_token, GET https://graph.facebook.com/v21.0/{waba_id}
   → Obtener nombre del negocio y detalles del WABA
4. POST https://graph.facebook.com/v21.0/{phone_number_id}/register
   headers: Authorization: Bearer {access_token}
   body: { messaging_product: "whatsapp", pin: "000000" }
   → Registrar el número para Cloud API
5. POST https://graph.facebook.com/v21.0/{waba_id}/subscribed_apps
   headers: Authorization: Bearer {access_token}
   → Suscribir tu app al WABA para recibir webhooks
6. Guardar en Supabase:
   - Crear tenant (business_name, etc)
   - Crear whatsapp_account (waba_id, phone_number_id, access_token encriptado)
   - Crear bot_config con defaults
7. Responder al frontend: { success: true, tenant_id, message: "WhatsApp conectado" }
```

**Manejo de errores:**
- Si el code es inválido → 400 "Invalid authorization code"
- Si Meta rechaza el token exchange → 502 "Meta API error"
- Si el registro del número falla → 502 con detalle del error de Meta
- Si Supabase falla → 500 "Database error"

#### B.3 — POST /webhook/whatsapp (Recibir mensajes)

Meta envía TODOS los mensajes de TODOS los tenants a esta URL. Tu backend rutea por `phone_number_id`.

```
1. Recibir payload de Meta
2. Extraer: phone_number_id del metadata, from (número del usuario), message
3. Buscar en whatsapp_accounts WHERE phone_number_id = X → obtener tenant_id y access_token
4. Si no existe → ignorar (log warning)
5. Guardar mensaje inbound en tabla messages
6. Cargar bot_config del tenant
7. [FASE POSTERIOR] Procesar con Anthropic SDK → generar respuesta
8. [FASE POSTERIOR] Enviar respuesta vía Graph API
9. [FASE POSTERIOR] Guardar mensaje outbound
10. Responder 200 OK a Meta (SIEMPRE, incluso si hay error interno — Meta reintenta si no recibe 200)
```

**Estructura del payload de Meta (simplificada):**
```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "WABA_ID",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {
          "display_phone_number": "...",
          "phone_number_id": "PHONE_NUMBER_ID"
        },
        "messages": [{
          "from": "USER_PHONE",
          "id": "MSG_ID",
          "timestamp": "...",
          "type": "text",
          "text": { "body": "Hola!" }
        }]
      },
      "field": "messages"
    }]
  }]
}
```

**IMPORTANTE:** Siempre responder 200 a Meta. Nunca devolver 4xx o 5xx en el webhook POST. Si algo falla, loggear el error pero responder 200.

#### B.4 — GET /health

```python
@router.get("/health")
async def health():
    return {"status": "ok", "service": "doppel-api"}
```

#### B.5 — CORS

Configurar CORS para permitir requests desde `doppel.lat`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://doppel.lat"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### B.6 — Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### B.7 — requirements.txt

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
httpx>=0.27.0
supabase>=2.0.0
pydantic-settings>=2.0.0
cryptography>=42.0.0
```

---

### C) Base de datos — Supabase SQL

```sql
-- Tenants (cada negocio conectado)
create table tenants (
  id uuid primary key default gen_random_uuid(),
  business_name text not null,
  email text,
  plan text default 'free',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Cuentas de WhatsApp vinculadas
create table whatsapp_accounts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  waba_id text not null,
  phone_number_id text not null,
  display_phone text,
  access_token text not null,
  token_type text default 'long_lived',
  token_expiry timestamptz,
  webhook_active boolean default true,
  status text default 'connected',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(waba_id, phone_number_id)
);

-- Configuración del bot por tenant
create table bot_configs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  system_prompt text default 'Eres un asistente amable que ayuda a los clientes.',
  welcome_message text default '¡Hola! ¿En qué puedo ayudarte?',
  language text default 'es',
  ai_model text default 'claude-sonnet',
  tools_enabled jsonb default '[]',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Mensajes
create table messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  wa_account_id uuid references whatsapp_accounts(id),
  user_phone text not null,
  direction text not null check (direction in ('inbound', 'outbound')),
  content text,
  message_type text default 'text',
  wa_message_id text,
  session_id text,
  created_at timestamptz default now()
);

-- Índices
create index idx_messages_tenant_phone on messages(tenant_id, user_phone);
create index idx_messages_session on messages(session_id);
create index idx_wa_accounts_tenant on whatsapp_accounts(tenant_id);
create index idx_wa_accounts_phone_id on whatsapp_accounts(phone_number_id);
```

---

### D) Orden de implementación

Claude Code debe implementar en este orden:

1. **Backend: health + webhook GET** → Deployar a api.doppel.lat → Verificar que responde
2. **Backend: oauth exchange endpoint** → La lógica de token exchange con Meta
3. **Backend: webhook POST** → Parsear mensajes entrantes (sin bot por ahora, solo loggear)
4. **Frontend: componente Embedded Signup** → Página /conectar con el botón
5. **Frontend: páginas legales** → /privacidad, /terminos, /eliminar-datos
6. **Supabase: ejecutar migración SQL**
7. **Integrar frontend → backend** → Que el botón envíe el code al backend

---

### E) Notas técnicas importantes

- **El App Secret NUNCA va en el frontend.** Solo vive en el backend como variable de entorno.
- **El webhook es UNO para todos los tenants.** Se rutea internamente por phone_number_id.
- **Siempre responder 200 al webhook POST de Meta**, incluso si hay errores internos.
- **Los access tokens de Meta son sensibles.** Encriptarlos antes de guardar en Supabase.
- **El frontend carga el SDK de Facebook via script tag dinámico**, no via npm.
- **CORS:** El backend debe permitir requests desde https://doppel.lat
- **Para Coexistence (futuro):** Solo cambiar `featureType: ''` a `featureType: 'whatsapp_business_app_onboarding'` en el componente de Embedded Signup. Requiere Tech Provider status.
