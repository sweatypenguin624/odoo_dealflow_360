# 9. Authentication and Authorization

## Current State
At present, the `odoo_dealflow_360` repository **does not implement user authentication or strict role-based access control (RBAC)** at the API layer. 

- There are no JWTs, session tokens, or OAuth flows implemented in the FastAPI routers.
- Endpoints like `POST /quotes/{quote_id}/submit` or `POST /quotes/{quote_id}/approval-action` assume the client is trusted. 
- The `ApprovalActionRequest` schema explicitly asks for an `actor: str` field from the client, meaning the client dictates *who* is performing the action, rather than deriving it from a secure token context.

## Business Logic Authorization (Implicit)
While API-level Auth is missing, **domain-level authorization logic** exists within the Quote workflow:
- The system dictates that only certain roles can approve certain quotes.
- `required_approval_level` can be `none`, `manager`, or `manager_then_finance`.
- `current_approval_step` tracks who currently holds the authority to approve the quote.
- However, because there is no API authentication, there is currently no cryptographically secure way to guarantee that the `actor` calling the endpoint is actually a `manager` or `finance` user. 

## Architectural Implications for Future Work
To secure this application for production, the following must be implemented:
1. **Authentication Middleware**: A JWT or Session validation layer in FastAPI (`fastapi.security`).
2. **Context Injection**: Extracting the `user_id` and `role` from the token and injecting it into the `db Session` or router dependencies.
3. **Role Validation**: Inside the `approval_action` endpoint, the system must assert that the authenticated user's role matches the `current_approval_step` of the quote.
