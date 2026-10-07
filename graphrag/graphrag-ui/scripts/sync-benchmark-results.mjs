import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const sourceDirectory = fileURLToPath(new URL("../../results/public/", import.meta.url));
const outputDirectory = fileURLToPath(new URL("../public/benchmark-results/", import.meta.url));
const resultFiles = [
  "rag_results.json",
  "graphrag_results.json",
  "agentic_results.json",
];

await mkdir(outputDirectory, { recursive: true });

for (const fileName of resultFiles) {
  await copyFile(path.join(sourceDirectory, fileName), path.join(outputDirectory, fileName));
}

console.log(`Synchronized ${resultFiles.length} public benchmark result files.`);