# frontdoor
Storefront accessibility

## Server

```
docker build -t frontdoor-server .
docker run --rm -p 8080:8080 -e PORT=8080 frontdoor-server
```

For local development only. The Demo Day laptop fallback must **pull** the deployed image rather
than build one — a local build is a different image from the same source, which is what D-016's
step 3 exists to rule out. See `docs/server-deploy.md`.

`GET /health` answers `{"status":"ok"}`. Storage credentials, if the process needs them, come
from the environment at run time — never from the image. See `data/STORAGE.md`.
