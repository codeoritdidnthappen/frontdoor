const KEY_PATTERN = /^(open|sealed)\/[A-Za-z0-9_.-]{1,128}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const CONFIGS = new WeakMap();

class RequestError extends Error {
  constructor(detail, status) {
    super(detail);
    this.status = status;
  }
}

function config(env) {
  const cached = CONFIGS.get(env);
  if (cached) return cached;
  const secret = env.FRONTDOOR_DEPTH_INGEST_KEY?.trim();
  if (!secret) throw new Error("FRONTDOOR_DEPTH_INGEST_KEY is not configured");
  if (typeof env.DEPTH_BUCKET?.put !== "function") {
    throw new Error("DEPTH_BUCKET R2 binding is not configured");
  }
  const parsed = { bucket: env.DEPTH_BUCKET, secret };
  CONFIGS.set(env, parsed);
  return parsed;
}

function json(detail, status, headers = {}) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

async function sameSecret(presented, expected) {
  const encoder = new TextEncoder();
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(presented)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const leftBytes = new Uint8Array(left);
  const rightBytes = new Uint8Array(right);
  let difference = presented.length ^ expected.length;
  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ rightBytes[index];
  }
  return difference === 0;
}

function parseUploadRequest(request) {
  const url = new URL(request.url);
  if (url.pathname !== "/depth" || url.searchParams.size !== 1) {
    throw new RequestError("invalid storage key", 400);
  }
  const key = url.searchParams.get("key") ?? "";
  if (!KEY_PATTERN.test(key) || key.includes("..")) {
    throw new RequestError("invalid storage key", 400);
  }
  const sha256 = request.headers.get("X-Frontdoor-SHA256") ?? "";
  if (!SHA256_PATTERN.test(sha256)) {
    throw new RequestError("invalid sha256", 400);
  }
  if (request.body === null) {
    throw new RequestError("missing body", 400);
  }
  return { body: request.body, key, sha256 };
}

export async function handle(request, env) {
  if (request.method !== "PUT") {
    return json("method not allowed", 405, { allow: "PUT" });
  }

  // Worker bindings arrive at the request boundary; cache their parsed form once per isolate.
  const configured = config(env);
  const presented = request.headers.get("X-Frontdoor-Depth-Key") ?? "";
  if (!(await sameSecret(presented, configured.secret))) {
    return json("depth ingest not authorised", 401);
  }

  let upload;
  try {
    upload = parseUploadRequest(request);
  } catch (error) {
    if (error instanceof RequestError) return json(error.message, error.status);
    throw error;
  }

  const stored = await configured.bucket.put(upload.key, upload.body, {
    onlyIf: { etagDoesNotMatch: "*" },
    sha256: upload.sha256,
    customMetadata: { sha256: upload.sha256 },
  });
  if (stored === null) {
    return json("object already exists", 409);
  }
  return new Response(JSON.stringify({ sha256: upload.sha256 }), {
    status: 201,
    headers: { "content-type": "application/json" },
  });
}

export default {
  fetch: handle,
};
