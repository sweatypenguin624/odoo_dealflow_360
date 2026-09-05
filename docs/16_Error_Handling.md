# 16. Error Handling

DealFlow360 uses a predictable error-handling model heavily reliant on FastAPI's native `HTTPException`.

## Validation Errors (422 Unprocessable Entity)
Because the API relies entirely on Pydantic models (e.g., `SubscribeRequest`), any malformed JSON, missing fields, or incorrect types (e.g., passing a string to an integer `quantity` field) are caught automatically by FastAPI. The system responds with a detailed `422` error before any business logic is executed.

## Business Rule Errors (400 Bad Request)
When a user attempts an invalid state transition, the router explicitly raises a `400` error.
Examples:
- Submitting a quote that is not in the `draft` state.
- Attempting to confirm a fulfillment plan for a quote that isn't `approved`.
- Trying to approve a quote when the action isn't one of (`approved`, `rejected`, `returned_for_revision`).

## Resource Not Found (404 Not Found)
When an ID is passed in the URL (e.g., `/quotes/999/submit`), the router immediately queries the database. If it returns `None`, a `404` is raised.

## Conflict Errors (409 Conflict)
Used specifically in the Fulfillment engine. When a user tries to `confirm_fulfillment`, the system locks the database rows for the required `Stock`. If the available quantity has dropped below what the fulfillment plan requires (due to another quote taking the stock in the interim), the transaction rolls back, and a `409` error is raised detailing the exact stock shortage.

## Error Propagation
Errors bubble up to the FastAPI router level. There are no global custom exception handlers intercepting standard errors. If a database disconnect or unexpected Python `ValueError` occurs, it results in a standard `500 Internal Server Error`.
