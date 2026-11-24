"""Heure de Guadeloupe : UTC-4 toute l'année (pas d'heure d'été). Une seule définition pour tout le code."""
from datetime import timedelta, timezone

TZ = timezone(timedelta(hours=-4))
