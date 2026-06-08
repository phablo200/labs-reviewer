# Authentication Token Integration

## Objective

Protect the Labs Reviewer FastAPI endpoints with bearer-token authentication issued by the Node.js Auth Backend at `/home/danii/myProjects/auth-service`, while keeping the Python service prepared to swap token verification strategies later.

The implementation should receive `Authorization: Bearer <token>`, validate the token using the Auth Backend signing configuration, map the claims into an internal `AuthenticatedUser`, and make that user available to route handlers.

## Background

The research note in `.workspace/auth-integration-research.md` recommends an OAuth-style resource-server architecture with local JWT validation. At the code level, the recommended pattern is the Strategy Pattern behind a `TokenVerifier` contract.

Current Labs Reviewer behavior:

- `main.py` registers CORS, `RequiredHeadersMiddleware`, and the Labs/output routers.
- `core/` holds shared cross-cutting configuration and middleware.
- `labs/router.py` exposes `/labs/review`, `/outputs/makdown`, and `/outputs/pdf` without authentication.
- `.env.example` did not previously include auth verification settings.

Current Auth Backend behavior confirmed from `/home/danii/myProjects/auth-service`:

- Public envs include `JWT_SECRET` and `JWT_EXPIRES_IN`.
- `AuthService.createAuthResponse` signs JWTs with `jsonwebtoken`.
- The token is signed with `process.env.JWT_SECRET`.
- No issuer, audience, public key, or JWKS env is currently defined in the Auth Backend.
- With `jsonwebtoken`, the shared-secret signing algorithm is `HS256` by default unless changed.
- Token claims currently include:

```text
sub
email
profile_id
application_id
```

- The Labs Login application id is seeded as:

```text
00000000-0000-0000-0000-000000000002
```

`.env.example` in this repo now includes:

```text
AUTH_TOKEN_VERIFIER=jwt
AUTH_JWT_SECRET=
AUTH_JWT_PUBLIC_KEY=
AUTH_JWT_ALGORITHM=HS256
AUTH_JWT_ISSUER=
AUTH_JWT_AUDIENCE=
AUTH_JWKS_URL=
AUTH_EXPECTED_APPLICATION_ID=00000000-0000-0000-0000-000000000002
```

`AUTH_JWT_SECRET` should match the Auth Backend `JWT_SECRET`.

## Resolved Decisions

- All `/outputs/*` endpoints must require authentication because generated files will become user-scoped in future versions.
- Invalid, missing, expired, malformed, or untrusted tokens should return `401`.
- Tokens with a valid signature but a mismatched `application_id` should return `403`.
- The Auth Backend will not add `iss` or `aud` claims for this version, so issuer/audience validation is deferred.
- `profile_id` remains an identity claim for now. It should not be mapped to roles or permissions in this version.

## Scope

### In Scope

- Add an auth package under `core/auth/`.
- Define `AuthenticatedUser` in `core/auth/schemas.py`.
- Define a provider-agnostic `TokenVerifier` contract.
- Implement `JwtTokenVerifier` for local JWT verification using shared-secret `HS256`.
- Add FastAPI dependencies for extracting bearer tokens and resolving the current user.
- Wire protected routes to require an authenticated user.
- Add auth settings to `core/config.py`.
- Add the JWT dependency to `requirements.txt`.
- Add tests for valid tokens, missing tokens, invalid tokens, expired tokens, malformed claims, and wrong `application_id`.

### Out of Scope

- Changing the Auth Backend token issuer or login flow.
- Adding remote token introspection.
- Adding JWKS/public-key validation in the first implementation.
- Adding roles/permissions enforcement.
- Adding issuer/audience validation.
- Adding frontend storage or login behavior.
- Persisting users in the Labs Reviewer database.

## Proposed Approach

Implement a small auth layer in `core/auth/`:

```text
core/auth/
  __init__.py
  schemas.py
  token_verifier.py
  jwt_token_verifier.py
  dependencies.py
```

### Data Contract

Use `schemas.py`, not `models.py`, because `AuthenticatedUser` is an application data contract derived from token claims, not an ORM/database model.

```python
class AuthenticatedUser(BaseModel):
    id: str
    email: str
    profile_id: str
    application_id: str
```

Future optional fields can include `roles` and `permissions`, but the current Auth Backend does not issue those claims.

### Strategy Contract

Create `TokenVerifier` as the stable contract:

```python
class TokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedUser:
        ...
```

Create `JwtTokenVerifier` as the first concrete strategy:

- verifies the token signature with `AUTH_JWT_SECRET`
- uses `AUTH_JWT_ALGORITHM`, defaulting to `HS256`
- validates expiration
- validates required claims: `sub`, `email`, `profile_id`, `application_id`
- rejects tokens where `application_id` does not match `AUTH_EXPECTED_APPLICATION_ID`
- maps claims into `AuthenticatedUser`

Use `pyjwt` for JWT decoding and verification. Add it to `requirements.txt`.

The verifier should distinguish authentication failures from authorization failures:

- invalid token, expired token, missing token, invalid signature, or malformed claims: `401`
- valid token from the wrong `application_id`: `403`

### FastAPI Dependency

Create `get_current_user` in `core/auth/dependencies.py`:

- read `Authorization: Bearer <token>` with `HTTPBearer(auto_error=False)`
- return `401` for missing or invalid tokens
- return `403` for tokens whose `application_id` does not match `AUTH_EXPECTED_APPLICATION_ID`
- return `AuthenticatedUser` for valid tokens

Initial route integration should protect:

- `POST /labs/review`
- `GET /outputs/makdown`
- `GET /outputs/pdf`

Add the dependency at router level if all endpoints in a router must be protected, or at endpoint level if public endpoints are needed later.

### Configuration

Extend `core/config.py` settings:

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

For the first milestone, only `AUTH_TOKEN_VERIFIER`, `AUTH_JWT_SECRET`, `AUTH_JWT_ALGORITHM`, and `AUTH_EXPECTED_APPLICATION_ID` are required at runtime.

Keep the unused issuer, audience, public-key, and JWKS settings as future-compatible configuration, but do not enforce issuer/audience claims or implement public-key verification until needed.

## Milestones

1. Add configuration and dependency support.
   - Update `requirements.txt` with `pyjwt`.
   - Extend `core/config.py` with auth settings.
   - Confirm `.env.example` documents Auth Backend mapping.

2. Add auth package.
   - Implement `core/auth/schemas.py`.
   - Add `core/auth/token_verifier.py`.
   - Add `core/auth/jwt_token_verifier.py`.
   - Add `core/auth/dependencies.py`.

3. Protect routes.
   - Wire `get_current_user` into `labs/router.py`.
   - Keep existing response behavior unchanged for authenticated requests.
   - Return consistent `401` responses for missing/invalid tokens.
   - Return `403` for authenticated tokens from another `application_id`.

4. Add tests.
   - Add unit tests for `JwtTokenVerifier`.
   - Add route tests for missing, invalid, and valid bearer tokens.
   - Add config tests for default algorithm and expected application id.

5. Manual verification.
   - Use a token generated by Auth Backend login.
   - Call Labs Reviewer endpoints with and without `Authorization`.
   - Confirm wrong Auth Backend secret or wrong `application_id` is rejected.

## Edge Cases

- Missing `Authorization` header returns `401`.
- Non-bearer authorization scheme returns `401`.
- Empty bearer token returns `401`.
- Invalid signature returns `401`.
- Expired token returns `401`.
- Token signed with unsupported algorithm returns `401`.
- Missing `sub`, `email`, `profile_id`, or `application_id` returns `401`.
- Token for another Auth Backend application returns `403`.
- `AUTH_JWT_SECRET` missing in JWT mode should fail closed and return `500` or raise at startup, depending on the implementation decision.

## Acceptance Criteria

- [ ] `.env.example` includes the auth settings needed to validate Auth Backend JWTs.
- [ ] `AuthenticatedUser` is defined in `core/auth/schemas.py`.
- [ ] `TokenVerifier` defines the provider-agnostic verification contract.
- [ ] `JwtTokenVerifier` validates Auth Backend JWTs signed with the shared `JWT_SECRET`.
- [ ] Valid tokens expose `sub`, `email`, `profile_id`, and `application_id` as `AuthenticatedUser`.
- [ ] Tokens with a mismatched `application_id` are rejected with `403`.
- [ ] `/labs/review`, `/outputs/makdown`, and `/outputs/pdf` reject missing or invalid bearer tokens.
- [ ] `/outputs/makdown` and `/outputs/pdf` require authentication.
- [ ] Existing endpoint behavior is preserved for valid bearer tokens.
- [ ] Tests cover verifier behavior and protected route behavior.

## Test Plan

Unit:

- `JwtTokenVerifier.verify` returns `AuthenticatedUser` for a valid HS256 token.
- `JwtTokenVerifier.verify` rejects invalid signatures.
- `JwtTokenVerifier.verify` rejects expired tokens.
- `JwtTokenVerifier.verify` rejects tokens missing required claims.
- `JwtTokenVerifier.verify` rejects mismatched `application_id` as an authorization failure.
- Auth config defaults `AUTH_TOKEN_VERIFIER` to `jwt` and `AUTH_JWT_ALGORITHM` to `HS256`.

Integration:

- FastAPI route tests call protected endpoints without `Authorization` and receive `401`.
- FastAPI route tests call protected endpoints with malformed bearer tokens and receive `401`.
- FastAPI route tests call protected endpoints with a valid token for another `application_id` and receive `403`.
- FastAPI route tests call protected endpoints with valid tokens and receive the existing success response shape.

Manual verification:

- Start Auth Backend and Labs Reviewer locally.
- Sign in through Auth Backend using the Labs Login application id.
- Send the returned token to Labs Reviewer with `Authorization: Bearer <token>`.
- Confirm request success.
- Change `AUTH_JWT_SECRET` and confirm `401`.
- Send a valid token for another `application_id` and confirm `403`.

## Risks and Mitigations

- Risk: Auth Backend changes token claims.
  - Mitigation: keep claim mapping isolated in `JwtTokenVerifier` and cover required claims in tests.

- Risk: Auth Backend later switches from shared-secret JWTs to public/private keys.
  - Mitigation: keep `TokenVerifier` as a strategy contract and add a separate public-key/JWKS verifier.

- Risk: Missing `issuer` and `audience` validation weakens token scoping.
  - Mitigation: enforce `application_id` now and add issuer/audience validation in a future version once the Auth Backend emits those claims.

- Risk: Route protection may break existing local workflows.
  - Mitigation: document required auth envs and test both protected endpoint behavior and existing success response shape.

- Risk: Instantiating verifiers directly in route handlers creates coupling.
  - Mitigation: centralize verifier construction in `core/auth/dependencies.py` or a small factory function.

## Open Questions

- None for this version.
