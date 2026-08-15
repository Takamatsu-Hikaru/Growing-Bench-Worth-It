import { readFile } from "node:fs/promises";

/**
 * Read one UTF-8 JSON file and write its gzip representation.
 *
 * @param {string} inputPath
 * @param {string} outputPath
 * @returns {Promise<void>}
 */
export async function archiveJson(inputPath, outputPath) {
  await readFile(inputPath);
  throw new Error("archiveJson is not implemented");
}

