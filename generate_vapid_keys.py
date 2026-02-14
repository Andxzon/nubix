#!/usr/bin/env python3
"""
Script para generar claves VAPID para Web Push Notifications.
Ejecuta este script una vez y copia las claves a tu archivo .env
"""

import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

def generate_vapid_keys():
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()
    
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    private_key_b64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
    
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    public_key_b64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')
    
    print("=" * 60)
    print("CLAVES VAPID GENERADAS")
    print("=" * 60)
    print("\nAgrega estas líneas a tu archivo .env:\n")
    print(f"VAPID_PUBLIC_KEY={public_key_b64}")
    print(f"VAPID_PRIVATE_KEY={private_key_b64}")
    print("\n" + "=" * 60)
    print("\nTambién actualiza VAPID_PUBLIC_KEY en js/config.js:")
    print(f"const VAPID_PUBLIC_KEY = '{public_key_b64}';")
    print("=" * 60)

if __name__ == '__main__':
    generate_vapid_keys()
