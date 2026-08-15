import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { gunzip } from "node:zlib";
import { promisify } from "node:util";

import { archiveJson } from "../src/archive.mjs";

const gunzipAsync = promisify(gunzip);

test("archives the exact UTF-8 input bytes as gzip", async (t) => {
  const directory = await mkdtemp(path.join(tmpdir(), "archive-cli-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const input = path.join(directory, "input.json");
  const output = path.join(directory, "output.json.gz");
  const source = Buffer.from('{"greeting":"你好","items":[1,2,3]}\n', "utf8");
  await writeFile(input, source);

  await archiveJson(input, output);

  const restored = await gunzipAsync(await readFile(output));
  assert.deepEqual(restored, source);
});

test("preserves a destination write failure", async (t) => {
  const directory = await mkdtemp(path.join(tmpdir(), "archive-cli-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const input = path.join(directory, "input.json");
  const missingParent = path.join(directory, "missing", "output.json.gz");
  await writeFile(input, Buffer.from("{}\n", "utf8"));

  await assert.rejects(
    archiveJson(input, missingParent),
    (error) => error && error.code === "ENOENT",
  );
});

