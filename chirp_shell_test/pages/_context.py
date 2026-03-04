def context(request) -> dict:
    return {"current_path": request.path}
