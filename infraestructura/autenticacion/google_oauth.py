# infraestructura/autenticacion/google_oauth.py
"""Autenticación institucional con Google mediante OpenID Connect.

Este módulo no guarda usuarios en MySQL, no crea sesiones de NiceGUI
ni decide roles. Esas responsabilidades corresponden a otras capas.
"""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from authlib.integrations.starlette_client import OAuth, OAuthError
from authlib.oidc.core import UserInfo
from dotenv import load_dotenv
from fastapi import Request
from joserfc.errors import ClaimError, JoseError

from dominio.reglas.usuarios import validar_identidad_google


RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ_PROYECTO / '.env')


class ErrorAutenticacionGoogle(Exception):
    """La cuenta de Google no cumple los requisitos institucionales."""


def url_retorno() -> str:
    """Usa una URL fija registrada en Google Cloud, nunca el Host recibido."""
    url = os.getenv(
        'GOOGLE_REDIRECT_URI', 'http://localhost:8080/auth/callback'
    ).strip()
    parsed = urlparse(url)
    local = parsed.hostname in {'localhost', '127.0.0.1'}
    if (
        (parsed.scheme != 'https' and not (local and parsed.scheme == 'http'))
        or not parsed.netloc
        or parsed.path != '/auth/callback'
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment or parsed.query
    ):
        raise RuntimeError('GOOGLE_REDIRECT_URI no es una URL de retorno válida.')
    return url


@lru_cache(maxsize=1)
def obtener_oauth() -> OAuth:
    """Configura Google una sola vez, al utilizarlo por primera vez."""
    client_id = os.getenv('GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '').strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            'Configura GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET en .env.'
        )

    oauth = OAuth()
    oauth.register(
        name='google',
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=(
            'https://accounts.google.com/.well-known/openid-configuration'
        ),
        client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'},
    )
    return oauth


async def iniciar_sesion_google(request: Request, *, estado: str):
    """Inicia OAuth; Authlib protege el retorno con state/nonce."""
    google = obtener_oauth().google
    return await google.authorize_redirect(
        request,
        url_retorno(),
        state=estado,
        prompt='select_account',
    )


async def obtener_identidad_google(request: Request) -> dict:
    """Obtiene exclusivamente los claims OIDC validados por Authlib.

    Se debe invocar desde /auth/callback tras el retorno de Google.
    No aceptar correo, sub ni email_verified enviados por formularios.
    """
    try:
        google = obtener_oauth().google
        token = await google.authorize_access_token(
            request,
            claims_options={
                'iss': {'values': ['https://accounts.google.com', 'accounts.google.com']},
                'aud': {'essential': True, 'value': google.client_id},
            },
            leeway=0,
        )
    except OAuthError as exc:
        codigo = exc.error if exc.error in {
            'access_denied', 'invalid_client', 'invalid_grant',
            'mismatching_state', 'temporarily_unavailable',
        } else type(exc).__name__
        raise ErrorAutenticacionGoogle(f'El canje OAuth de Google falló ({codigo}).') from exc
    except JoseError as exc:
        detalle = type(exc).__name__
        if isinstance(exc, ClaimError) and exc.claim in {
            'iss', 'sub', 'aud', 'azp', 'iat', 'nbf', 'exp', 'nonce', 'at_hash', 'amr', 'auth_time',
        }:
            detalle = f'{detalle}, campo {exc.claim}'
        raise ErrorAutenticacionGoogle(f'El ID token de Google no pasó la validación ({detalle}).') from exc

    info = token.get('userinfo')
    # Authlib crea UserInfo al validar el ID token contra el nonce del state.
    if not token.get('id_token') or not isinstance(info, UserInfo):
        raise ErrorAutenticacionGoogle('Google no proporcionó identidad verificada.')
    identidad = validar_identidad_google(
        correo=info.get('email'),
        google_sub=info.get('sub'),
        correo_verificado=info.get('email_verified'),
    )
    return {
        'correo': identidad['correo'],
        'google_sub': identidad['google_sub'],
        'correo_verificado': True,
        'nombre': str(info.get('name') or '').strip(),
        'foto': str(info.get('picture') or '').strip(),
    }
