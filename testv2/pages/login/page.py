from chirp import Request, Template


async def handler(request: Request):
    error = request.query.get("error", "")
    return Template("login/page.html", error="Invalid credentials" if error else "")
