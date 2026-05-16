# Asistpro Bridge — Temporary WhatsApp Integration

**Status:** Active on `feature/asistpro-n8n-bridge` branch
**Purpose:** Route incoming WhatsApp messages to n8n asistpro while asistpro does not yet have its own WhatsApp Business number.
**Owner:** @JuCeIbMo

---

## How It Works

doppel-api has a built-in "Nanobot Runtime" feature that, when `NANOBOT_RUNTIME_URL` is set, forwards all incoming WhatsApp messages to an external HTTP endpoint instead of using the local AI bot.

**Flow:**

```
WhatsApp → Meta → doppel-api webhook
    → POST {NANOBOT_RUNTIME_URL}/internal/whatsapp/turn (form-data)
    → n8n workflow processes message + calls asistpro-back
    → returns {"reply": "texto"}
    → doppel-api sends reply via Meta Cloud API → WhatsApp
```

The Meta integration is entirely unchanged. doppel-api still owns all communication with Meta.

---

## Enable the Bridge

In your production environment (or .env):

```
NANOBOT_RUNTIME_URL=https://n8n.doppel.lat/webhook/asistpro-bridge
NANOBOT_RUNTIME_TOKEN=
NANOBOT_RUNTIME_TIMEOUT_SECONDS=120
```

Restart the doppel-api process. All incoming messages will now be handled by n8n asistpro.

---

## Disable the Bridge (revert)

```
NANOBOT_RUNTIME_URL=
```

Restart the process. doppel-api returns to its default behavior.

---

## Protocol Reference

Request doppel-api to n8n:
```
POST .../internal/whatsapp/turn
Content-Type: multipart/form-data

tenant_id=<uuid>
mode=client|manager
sender_id=<phone>        (maps to X-External-User-Id in asistpro-back)
chat_id=<phone>
message_id=wamid.<hash>  (maps to Idempotency-Key for write actions)
content=<user message>
```

Response n8n to doppel-api:
```json
{"reply": "texto a enviar al usuario"}
```

If reply is empty/null, doppel-api sends nothing to the user (silent handling).

---

## When to Remove This

When asistpro has its own WhatsApp Business number:
1. Unset NANOBOT_RUNTIME_URL in doppel-api production
2. Delete or archive this branch (docs-only, no code to merge)
3. Disable or keep the n8n workflow "Asistpro WhatsApp Bridge"