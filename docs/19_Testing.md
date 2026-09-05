# 19. Testing

DealFlow360 utilizes `pytest` as its testing framework, located in `backend/tests/`. 

## Testing Strategy
The testing strategy is heavily influenced by the separation of the "Engines" from the "Routers".

### 1. Engine Tests (Unit Testing)
Files like `test_risk_engine.py` and `test_billing_engine.py` are pure unit tests.
- **What is tested**: Business logic boundaries, edge cases, math calculations.
- **Mocking**: None. Because the engines ingest standard Python `dataclasses` (like `LineInput` or `SubscriptionState`), the tests simply instantiate these classes with hardcoded values and assert the math on the output. There is no database setup required, making these tests blazing fast.

### 2. API Tests (Integration Testing)
Files like `test_billing_api.py` test the FastApi endpoints.
- **What is tested**: HTTP response codes, database persistence, state transitions.
- **Mocking**: The database session is overridden. A temporary SQLite database (often in-memory or a test file) is spun up. The tests use FastAPI's `TestClient` to send actual JSON payloads to the router, verify the `200 OK` response, and then query the test database to ensure the `AuditLog` and `Quote` tables were updated correctly.

## Missing Coverage
The Machine Learning pipeline (`upsell_cross_sell/`) currently lacks automated unit tests. The data building process is complex and would benefit from a test suite ensuring that Pandas transformations do not silently leak future data into historical states.
