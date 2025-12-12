// Configuración del frontend
// API_URL vacío = mismo servidor (para cuando Flask sirve el frontend)
const API_URL = '';

// Clave pública VAPID para Push Notifications
// IMPORTANTE: Genera tus propias claves ejecutando: python -c "from pywebpush import webpush; import py_vapid; vapid = py_vapid.Vapid(); vapid.generate_keys(); print('VAPID_PUBLIC_KEY=' + vapid.public_key.urlsafe_key().decode()); print('VAPID_PRIVATE_KEY=' + vapid.private_key.urlsafe_key().decode())"
// O usa el endpoint /generate-vapid-keys
const VAPID_PUBLIC_KEY = 'BElHmOcWrUdjXQ0c86HpWsPfUHoNbzBxpo8wSxEosDs-6Kzmn3o0HOki1TJywVquHMp9kPZrxcpneXfc58io2hs';
