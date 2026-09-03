import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, test } from "node:test";

import { handle } from "../src/index.js";

const SECRET = "test-depth-service-key";
const DIGEST = "a".repeat(64);
const EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

// The message R2 actually returns for a server-side digest rejection, error 10037.
function digestRejection() {
  return new Error(`put: The SHA-256 checksum you specified did not match what we received.
You provided a SHA-256 checksum with value: ${DIGEST}
Actual SHA-256 was: ${"b".repeat(64)} (10037)`);
}

class Bucket {
  constructor(existing = false) {
    this.objects = new Map(existing ? [["open/C-001", "original"]] : []);
    this.puts = [];
  }

  async put(key, body, options) {
    const value = await new Response(body).text();
    this.puts.push({ key, body: value, options });
    // Cloudflare R2 Workers API: put() returns null when an onlyIf precondition fails.
    // https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2putoptions
    if (this.objects.has(key) && options?.onlyIf?.etagDoesNotMatch === "*") return null;
    this.objects.set(key, value);
    return { key };
  }
}

function env(bucket = new Bucket()) {
  return { DEPTH_BUCKET: bucket, FRONTDOOR_DEPTH_INGEST_KEY: SECRET };
}

function request(path = "open/C-001", options = {}) {
  return new Request(`https://depth.example/depth?key=${encodeURIComponent(path)}`, {
    method: "PUT",
    body: "depth-bytes",
    headers: {
      "X-Frontdoor-Depth-Key": SECRET,
      "X-Frontdoor-SHA256": DIGEST,
      ...options.headers,
    },
  });
}

describe("depth ingest Worker", () => {
  test("AC-1 stores an authorised body at the canonical key", async () => {
    const bucket = new Bucket();
    const response = await handle(request(), env(bucket));

    assert.equal(response.status, 201);
    assert.deepEqual(bucket.puts[0], {
      key: "open/C-001",
      body: "depth-bytes",
      options: {
        onlyIf: { etagDoesNotMatch: "*" },
        sha256: DIGEST,
        customMetadata: { sha256: DIGEST },
      },
    });
  });

  test("AC-2 rejects a missing service credential without touching R2", async () => {
    const bucket = new Bucket();
    const response = await handle(request(undefined, { headers: { "X-Frontdoor-Depth-Key": "" } }), env(bucket));

    assert.equal(response.status, 401);
    assert.equal(bucket.puts.length, 0);
  });

  test("AC-3 rejects non-PUT methods without touching R2", async () => {
    const bucket = new Bucket();
    const response = await handle(new Request("https://depth.example/depth?key=open%2FC-001"), env(bucket));

    assert.equal(response.status, 405);
    assert.equal(response.headers.get("allow"), "PUT");
    assert.equal(bucket.puts.length, 0);
  });

  test("AC-4 rejects a non-canonical key without touching R2", async () => {
    const bucket = new Bucket();
    const response = await handle(request("open/bad..id"), env(bucket));

    assert.equal(response.status, 400);
    assert.equal(bucket.puts.length, 0);
  });

  test("AC-5 rejects a malformed digest without touching R2", async () => {
    const bucket = new Bucket();
    const response = await handle(request(undefined, { headers: { "X-Frontdoor-SHA256": "ABC" } }), env(bucket));

    assert.equal(response.status, 400);
    assert.equal(bucket.puts.length, 0);
  });

  test("AC-6 refuses to overwrite an existing object", async () => {
    const bucket = new Bucket(true);
    const response = await handle(request(), env(bucket));

    assert.equal(response.status, 409);
    assert.equal(bucket.puts.length, 1);
    assert.equal(bucket.objects.get("open/C-001"), "original");
  });

  test("AC-7 configuration uses an R2 binding without credential variables", async () => {
    const text = await readFile(new URL("../wrangler.jsonc", import.meta.url), "utf8");
    const config = JSON.parse(text);

    assert.deepEqual(config.r2_buckets, [
      { binding: "DEPTH_BUCKET", bucket_name: "frontdoor-depth" },
    ]);
    assert.doesNotMatch(text, /ACCESS_KEY|SECRET_KEY/);
  });

  test("TICK-254 answers a digest R2 refuses with 422, storing nothing", async () => {
    const bucket = new Bucket();
    bucket.put = async () => {
      throw digestRejection();
    };
    const response = await handle(request(), env(bucket));

    assert.equal(response.status, 422);
    assert.deepEqual(await response.json(), {
      detail: "body does not match the declared sha256",
    });
    assert.equal(bucket.objects.size, 0);
  });

  test("TICK-254 lets an R2 failure that is not a digest rejection propagate", async () => {
    const bucket = new Bucket();
    bucket.put = async () => {
      throw new Error("put: we encountered an internal error (10001)");
    };

    await assert.rejects(() => handle(request(), env(bucket)), /internal error/);
  });

  test("TICK-255 refuses an empty body without touching R2", async () => {
    const bucket = new Bucket();
    const response = await handle(
      request(undefined, { headers: { "X-Frontdoor-SHA256": EMPTY_SHA256 } }),
      env(bucket),
    );

    assert.equal(response.status, 400);
    assert.deepEqual(await response.json(), { detail: "empty body" });
    assert.equal(bucket.puts.length, 0);
  });
});
