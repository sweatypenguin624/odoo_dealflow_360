# 20. Important Design Patterns

The architecture of DealFlow360 relies heavily on two specific software design patterns to maintain clean code and prevent the "Fat Controller" anti-pattern.

## 1. The Hexagonal Architecture / Service Layer Pattern
**Why it's used**: In many FastAPI apps, business logic gets tangled inside the router (the `@app.post` function), mixed with database queries and HTTP exception handling.
**How it's implemented**: 
DealFlow360 strictly isolates business logic into `app/services/` (The Engines). 
The Router's *only* job is:
1. Receive Request.
2. Load Data from DB.
3. Pass Data to Engine.
4. Save Engine's Output to DB.
5. Return Response.

Because the Engines don't know about FastAPI or SQLAlchemy, they can be tested instantly and reused in CLI scripts if needed.

## 2. Dependency Injection
**Why it's used**: Database session management can cause memory leaks if connections aren't closed properly.
**How it's implemented**: 
FastAPI's `Depends(get_db)` is used in every router endpoint. 
The `get_db` function yields a `SessionLocal`, allowing the router to use it. Once the HTTP response is sent to the client, the `finally: db.close()` block in the dependency executes, safely returning the connection to the pool. This ensures that even if an engine crashes, the database connection is gracefully closed.
