---
title: Routes
description: Route registration, methods, and path parameters
draft: false
weight: 10
lang: en
type: doc
tags: [routing, routes, decorators, path-params]
keywords: [route, decorator, methods, get, post, path, parameters, trie]
category: guide
---

## Route Registration

Register routes with the `@app.route()` decorator:

```python
@app.route("/")
def index():
    return "Hello, World!"

@app.route("/about")
def about():
    return Template("about.html")
```

Routes are registered during the setup phase. At freeze time, the route table compiles into an immutable trie-based structure for fast matching.

## HTTP Methods

By default, routes accept `GET` requests. Specify methods explicitly:

```python
@app.route("/users", methods=["GET"])
def list_users():
    return Template("users.html", users=get_all_users())

@app.route("/users", methods=["POST"])
async def create_user(request: Request):
    data = await request.json()
    user = create(data)
    return Response(body=b"Created").with_status(201)

@app.route("/users/{id:int}", methods=["GET", "DELETE"])
async def user(request: Request, id: int):
    if request.method == "DELETE":
        delete_user(id)
        return Response(body=b"Deleted")
    return Template("user.html", user=get_user(id))
```

If a request matches a path but not the method, Chirp returns `405 Method Not Allowed` with an `Allow` header listing the valid methods.

## Path Parameters

Dynamic segments are defined with curly braces:

```python
@app.route("/users/{id}")
def user(id: str):
    return f"User: {id}"
```

### Type Conversions

Add a type suffix to auto-convert parameters:

```python
@app.route("/users/{id:int}")
def user(id: int):          # id is an int, not a str
    return get_user(id)

@app.route("/price/{amount:float}")
def price(amount: float):   # amount is a float
    return f"${amount:.2f}"
```

Supported types:

| Type | Pattern | Example |
|------|---------|---------|
| `str` | (default) any non-`/` chars | `/users/{name}` |
| `int` | digits only | `/users/{id:int}` |
| `float` | digits with optional decimal | `/price/{amount:float}` |
| `path` | any chars including `/` | `/files/{filepath:path}` |

### Catch-All Routes

Use `{name:path}` to match the rest of the URL:

```python
@app.route("/files/{filepath:path}")
def serve_file(filepath: str):
    return send_file(filepath)  # filepath can contain slashes
```

## Handler Signature Introspection

Chirp inspects your handler's signature to inject the right arguments:

```python
# No arguments -- simplest case
@app.route("/")
def index():
    return "Hello"

# Request only
@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    return Template("search.html", q=q)

# Path parameters only
@app.route("/users/{id:int}")
def user(id: int):
    return get_user(id)

# Both
@app.route("/users/{id:int}/posts/{slug}")
def user_post(request: Request, id: int, slug: str):
    return Template("post.html", post=get_post(id, slug))
```

If the first parameter is typed as `Request`, Chirp injects the request. Path parameters are matched by name.

## Async Handlers

Handlers can be sync or async. Chirp handles both:

```python
@app.route("/sync")
def sync_handler():
    return "Sync"

@app.route("/async")
async def async_handler():
    data = await fetch_data()
    return Template("data.html", data=data)
```

Use async handlers when you need to `await` I/O (database queries, HTTP calls, file reads).

## Error Handlers

Register error handlers by status code or exception type:

```python
@app.error(404)
def not_found(request: Request):
    return Template("errors/404.html", path=request.path)

@app.error(500)
def server_error(request: Request, error: Exception):
    return Template("errors/500.html", error=str(error))

@app.error(ValidationError)
def validation_error(request: Request, error: ValidationError):
    return Response(str(error)).with_status(422)
```

Error handlers use the same return-value system as route handlers.

## Route Table Compilation

At freeze time, routes compile into a trie (prefix tree). Matching is O(path-segments), not O(total-routes). This means performance doesn't degrade as you add more routes.

The compiled route table is immutable. Under free-threading, all worker threads share it without synchronization.

## Next Steps

- [[docs/routing/request-response|Request & Response]] -- The immutable request and chainable response
- [[docs/middleware/overview|Middleware]] -- Intercept requests before they reach handlers
- [[docs/templates/fragments|Fragments]] -- Return fragments from route handlers
