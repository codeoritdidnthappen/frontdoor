# frontdoor
Storefront accessibility

## Server

```
docker build -t frontdoor-server .
docker run --rm -p 8080:8080 -e PORT=8080 frontdoor-server
```

`GET /health` answers `{"status":"ok"}`. Storage credentials, if the process needs them, come
from the environment at run time — never from the image. See `data/STORAGE.md`.
