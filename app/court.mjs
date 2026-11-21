#!/usr/bin/env node
/**
 * OKX Price Court — read-only verifier CLI (genlayer-js).
 *
 * Independently reads verdicts from the OkxPriceCourt contract deployed on
 * GenLayer Studio Next (chainId 61997) by app/deploy_and_run.py:
 *
 *   npm install
 *   node court.mjs verify                 # both demo cases + court name
 *   node court.mjs get <case_id>          # one case as JSON
 *
 * Why read-only? Writes on Studio Next must use the newer tuple-form
 * addTransaction (payable, fees distribution from sim_getFeeConfig), which
 * the current genlayer-js release does not emit — its legacy addTransaction
 * reverts on this chain (deploy tx 0xd689fca6… proved it). Reads go through
 * gen_call and work fine, so this CLI is the independent verification path;
 * deploy_and_run.py is the write path.
 *
 * A key file is used only to derive the reader address for gen_call
 * (GENLAYER_KEY_FILE, default ~/.secrets/testnet-eoa/evm-key.txt). The key
 * is read locally and never printed; nothing is signed or sent.
 */
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createClient, createAccount, chains } from "genlayer-js";

const HERE = dirname(fileURLToPath(import.meta.url));
const DEPLOYMENT_PATH = join(HERE, "deployment.json");

// GenLayer Studio Next (the chain the Season 2 portal wizard runs on).
const studioNext = {
  ...chains.studionet,
  id: 61997,
  name: "GenLayer Studio Next",
  rpcUrls: { default: { http: ["https://studio-dev.genlayer.com/api"] } },
  blockExplorers: {
    default: { name: "GenLayer Explorer", url: "https://explorer-studio-dev.genlayer.com" },
  },
};

function loadClient() {
  const keyFile =
    process.env.GENLAYER_KEY_FILE || join(homedir(), ".secrets/testnet-eoa/evm-key.txt");
  const pk = readFileSync(keyFile, "utf8").trim();
  const account = createAccount(pk);
  return createClient({ chain: studioNext, account });
}

function loadDeployment() {
  if (!existsSync(DEPLOYMENT_PATH)) {
    throw new Error("no deployment.json — run app/deploy_and_run.py first");
  }
  return JSON.parse(readFileSync(DEPLOYMENT_PATH, "utf8"));
}

async function getCase(client, address, caseId) {
  const raw = await client.readContract({ address, functionName: "get_case", args: [caseId] });
  return JSON.parse(raw);
}

const cmd = process.argv[2];
const client = loadClient();
const deployment = loadDeployment();
const address = deployment.contractAddress;

if (cmd === "get") {
  console.log(JSON.stringify(await getCase(client, address, process.argv[3]), null, 2));
} else if (cmd === "verify") {
  const name = await client.readContract({ address, functionName: "get_court_name", args: [] });
  console.log("court:", name);
  console.log("contract:", address);
  console.log("explorer:", deployment.explorer);
  for (const id of ["case-001-btc-2026-11-19", "case-002-btc-2026-11-18"]) {
    const c = await getCase(client, address, id);
    console.log(`\n${id}`);
    console.log("  status: ", c.status);
    console.log("  close:  ", c.close, "USDT (OKX,", c.date + ")");
    console.log("  verdict:", c.verdict);
    console.log("  ruling: ", c.ruling);
  }
} else {
  console.log("usage: node court.mjs <verify|get <case_id>>");
  process.exit(1);
}
