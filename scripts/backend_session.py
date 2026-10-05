"""Cookie/CSRF authentication for the local demo CLI and verification tools."""
import os


def authenticate(client, base_url=None):
    base = str(base_url or client.base_url).rstrip('/')
    token = client.get(base + '/api/auth/csrf')
    token.raise_for_status()
    csrf = token.json()
    response = client.post(base + '/api/auth/login',
                           headers={csrf['headerName']: csrf['token']},
                           json={'login': os.getenv('AUTH_LOGIN', '123'),
                                 'password': os.getenv('AUTH_PASSWORD', '123')})
    response.raise_for_status()
    # Login rotates the session and invalidates the pre-login token.
    token = client.get(base + '/api/auth/csrf')
    token.raise_for_status()
    csrf = token.json()
    client.headers[csrf['headerName']] = csrf['token']
