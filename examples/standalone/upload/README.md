# Upload

A photo gallery with multipart form uploads. It covers file validation, saving
uploads to disk, reading file metadata, and serving uploaded assets back through
`StaticFiles`.

## Run

```bash
pip install chirp[forms]
PYTHONPATH=src python examples/standalone/upload/app.py
```

## Test

```bash
pytest examples/standalone/upload/
```
