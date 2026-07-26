"""Contrato del canal WhatsApp: qué puede *hacer* el número, además de hablar.

Paquete hoja a propósito: sólo depende de la stdlib y de pydantic, nunca de
`app.*` ni de la red. Eso mantiene a `ai_core` testeable sin mockear Meta. Quien
efectivamente ejecuta estas acciones es `app/services/whatsapp_sender.py`.
"""
