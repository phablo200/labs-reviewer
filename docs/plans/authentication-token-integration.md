# Authentication Token Integration Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/authentication-token-integration.md
```

This plan implements bearer-token authentication for Labs Reviewer using JWTs issued by the Auth Backend at:

```text
/home/danii/myProjects/auth-service
```

## Decisions To Preserve

- Protect `POST /labs/review`.
- Protect `GET /outputs/makdown`.
- Protect `GET /outputs/pdf`.
- Return `401` for missing, malformed, expired, invalid, or untrusted tokens.
- Return `403` for valid tokens whose `application_id` does not match `AUTH_EXPECTED_APPLICATION_ID`.
- Do not enforce `iss` or `aud` in this version.
- Treat `profile_id` as an identity claim only.
- Use `core/auth/schemas.py`, not `models.py`, for `AuthenticatedUser`.

## Phase 1: Dependency And Configuration

Files:

```text
requirements.txt
core/config.py
.env.example
```

Steps:

1. Add PyJWT to `requirements.txt`.
2. Extend `Settings` in `core/config.py` with:

```text
AUTH_TOKEN_VERIFIER
AUTH_JWT_SECRET
AUTH_JWT_PUBLIC_KEY
AUTH_JWT_ALGORITHM
AUTH_JWT_ISSUER
AUTH_JWT_AUDIENCE
AUTH_JWKS_URL
AUTH_EXPECTED_APPLICATION_ID
```

3. Keep `AUTH_JWT_ALGORITHM` defaulted to `HS256`.
4. Keep `AUTH_TOKEN_VERIFIER` defaulted to `jwt`.
5. Keep `AUTH_EXPECTED_APPLICATION_ID` defaulted to the Auth Backend Labs Login application id:

```text
00000000-0000-0000-0000-000000000002
```

6. Confirm `.env.example` includes the same settings and documents that `AUTH_JWT_SECRET` must match the Auth Backend `JWT_SECRET`.

Implementation note:

- `AUTH_JWT_PUBLIC_KEY`, `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, and `AUTH_JWKS_URL` are future-compatible settings only in this version.

## Phase 2: Auth Package

Files:

```text
core/auth/__init__.py
core/auth/schemas.py
core/auth/token_verifier.py
core/auth/jwt_token_verifier.py
core/auth/dependencies.py
```

Steps:

1. Create `core/auth/__init__.py`.
2. Define `AuthenticatedUser` in `core/auth/schemas.py`.

```python
class AuthenticatedUser(BaseModel):
    id: str
    email: str
    profile_id: str
    application_id: str
```

3. Define the Strategy contract in `core/auth/token_verifier.py`.

```python
class TokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedUser:
        ...
```

4. Implement `JwtTokenVerifier` in `core/auth/jwt_token_verifier.py`.
5. Validate:

- JWT signature
- expiration
- configured algorithm
- required claims: `sub`, `email`, `profile_id`, `application_id`
- expected `application_id`

6. Map valid claims into `AuthenticatedUser`:

```text
sub -> id
email -> email
profile_id -> profile_id
application_id -> application_id
```

7. Define clear internal exception types or error outcomes so the FastAPI dependency can map:

- token/authentication failures to `401`
- wrong `application_id` to `403`

## Phase 3: FastAPI Dependency

File:

```text
core/auth/dependencies.py
```

Steps:

1. Use `HTTPBearer(auto_error=False)` to extract the bearer token.
2. Implement `get_current_user`.
3. Return `401` when credentials are missing or invalid.
4. Return `403` when the token is valid but belongs to another `application_id`.
5. Return `AuthenticatedUser` when verification succeeds.
6. Instantiate the verifier centrally in this module or through a small factory function.

Recommended dependency shape:

```python
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    ...
```

## Phase 4: Protect Routes

File:

```text
labs/router.py
```

Steps:

1. Import `get_current_user`.
2. Require authentication on:

```text
POST /labs/review
GET /outputs/makdown
GET /outputs/pdf
```

3. Prefer router-level dependencies if every route in that router is protected.
4. Keep existing response payloads unchanged for valid authenticated requests.
5. Do not introduce roles, permissions, or user-scoped output filtering in this version.

Implementation note:

- User-scoped file generation is future work. This version only ensures the endpoints already require a valid user.

## Phase 5: Tests

New or updated test files:

```text
tests/test_auth_jwt_token_verifier.py
tests/test_auth_dependencies.py
tests/test_outputs_router.py
tests/test_service.py
```

Add focused tests for `JwtTokenVerifier`:

- accepts a valid HS256 token
- maps `sub`, `email`, `profile_id`, and `application_id`
- rejects invalid signatures
- rejects expired tokens
- rejects unsupported algorithms
- rejects missing required claims
- rejects wrong `application_id` as an authorization failure

Add route/dependency tests:

- missing `Authorization` returns `401`
- malformed bearer token returns `401`
- invalid signature returns `401`
- expired token returns `401`
- valid token with wrong `application_id` returns `403`
- valid token preserves existing `/labs/review` behavior
- valid token preserves existing `/outputs/makdown` response shape
- valid token preserves existing `/outputs/pdf` response shape

Add config tests:

- `AUTH_TOKEN_VERIFIER` defaults to `jwt`
- `AUTH_JWT_ALGORITHM` defaults to `HS256`
- `AUTH_EXPECTED_APPLICATION_ID` defaults to `00000000-0000-0000-0000-000000000002`

## Phase 6: Manual Verification

Prerequisites:

- Auth Backend running.
- Labs Reviewer running.
- `AUTH_JWT_SECRET` in Labs Reviewer matches `JWT_SECRET` in Auth Backend.

Steps:

1. Sign in through the Auth Backend using the Labs Login application id.
2. Capture the returned JWT.
3. Call `/labs/review` with:

```text
Authorization: Bearer <token>
```

4. Call `/outputs/makdown` with the same bearer token.
5. Call `/outputs/pdf` with the same bearer token.
6. Confirm each request succeeds with the existing response shape.
7. Remove the `Authorization` header and confirm `401`.
8. Change `AUTH_JWT_SECRET` and confirm `401`.
9. Send a valid token for another `application_id` and confirm `403`.

## Implementation Order

1. Add PyJWT and config fields.
2. Implement `AuthenticatedUser`.
3. Implement `TokenVerifier`.
4. Implement `JwtTokenVerifier`.
5. Implement `get_current_user`.
6. Protect routers.
7. Add unit tests.
8. Add route tests.
9. Run `pytest`.
10. Perform manual verification against the Auth Backend.

## Completion Checklist

- [ ] Auth envs documented in `.env.example`.
- [ ] PyJWT dependency added.
- [ ] Auth settings available through `core/config.py`.
- [ ] `core/auth/` package implemented.
- [ ] `AuthenticatedUser` defined in `schemas.py`.
- [ ] `TokenVerifier` strategy contract implemented.
- [ ] `JwtTokenVerifier` validates Auth Backend JWTs.
- [ ] Wrong `application_id` maps to `403`.
- [ ] Protected routes require bearer authentication.
- [ ] Tests cover verifier, dependency, and route behavior.
- [ ] `pytest` passes.
- [ ] Manual Auth Backend token verification succeeds.
