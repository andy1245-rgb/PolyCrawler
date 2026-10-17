# Relay v2 sunset — migration plan

Research doc for surviving the retirement of `GET https://api.relay.link/requests/v2` (deprecated 22 Jul 2026, rate-limit step-down from 1 Sep 2026, **retired 24 Nov 2026**). Relay's own in-band notice, present in every cached v2 response since 22 Jul:

```json
"deprecatedAt": "2026-07-22T00:00:00Z", "throttledFrom": "2026-09-01T00:00:00Z", "sunsetAt": "2026-11-24T00:00:00Z",
"successor": "https://api.relay.link/requests/v3",
"migrationGuide": "https://docs.relay.link/references/api/api_guides/migrating-to-requests-v3"
```

After the sunset, discovery must still resolve, for a POLYGON deposit tx paid out by a bridge-solver hub:

- **(a)** the requesting origin wallet + origin chain (v2 `?hash=` call, step 3 of SPEC.md §5), and
- **(b)** every historic request that origin wallet sent whose payout landed on Polygon (v2 `?user=` paging, the sibling list, step 3 of SPEC.md §5).

Written from the repo cache (`data/raw/relay/`, 356 files) plus live probes against candidate replacements (curl/python, no v2 quota spent). No code changed.

**Verdict first:** first choice is **Relay v3 with a self-serve `x-api-key`** — the v3 surface covers both (a) and (b) including the non-EVM origins, but the keyless-requests visibility claim could not be fully confirmed without creating the key; one curl confirms it. Fallback is the **on-chain trail on the origin chains** — exact for both new deposits and wallet history on EVM chains, heuristic on the payout side, and blind for Solana/Tron/Bitcoin origins (~10% of the universe). Everything else is dead.

---

## 1. Current v2 usage inventory (everything that breaks)

Every v2 touchpoint in the repo, from grep:

| Location | What it does | Breaks on 24 Nov |
|---|---|---|
| `src/polycrawler/discovery/engine.py:614` | `relayApi = "https://api.relay.link/requests/v2"` (with `relayPageCap = 50`, `relayUserPageCap = 40`, `polygonChainId = 137`) | route gone |
| `engine.py:1787 fetchRelayHashes` | `GET /requests/v2?hash=<payoutTxHash>` for each sampled hub payout + each traced account's earliest large hub deposit; `fetchMany` in chunks of 10; cache `data/raw/relay/hash_<tx>.json` | 404 |
| `engine.py:1813 fetchRelayUsers` | `GET /requests/v2?user=<wallet>&limit=&continuation=` paged up to 40 pages per origin wallet; cache `user_<wallet>_<cursor>.json` | 404 |
| `engine.py:1681 parseRelayRequest` | consumes `item.user`, `item.recipient`, `item.status`, `item.createdAt`, `data.inTxs[0]` (`chainId`, `hash`, `timestamp`), `data.outTxs[0]` (`chainId`, `hash`, `timestamp`, `block`), `data.metadata.currencyIn/currencyOut` (`amountUsd`; `currency.chainId` fallback via `_chainOf`) | response shape (see §2a) |
| `engine.py:1713 parseRelayPage` | `payload.requests[]`, `payload.continuation`, `rateLimitMessage(payload)` | same, key-wise identical in v3 |
| `engine.py:1729 polygonPayout` | filter `destinationChainId == 137 and recipient and status == "success"` | fine once fields parse |
| `engine.py:1735 matchPayout` | row whose `payoutTxHash` or `inTxHash` equals the deposit tx; single-row fallback | fine |
| `engine.py:~1979 linkOrigins` | `HttpSession(hostRates={"api.relay.link": relayRequestsPerSec, ...})`, hub probing (`sampleOtherHubs` → `fetchRelayHashes`), stats counters `relayCalls/relayCacheHits/relayRateLimits/relaySeconds` | host still valid for v3 |
| `src/polycrawler/discovery/funding.py` | `0xd216153c06e857cd7f72665e0af1d7d82172f494` labelled `relayHub` inside `polymarketContracts` (Polygon-side Transfer exclusion) + `ALCHEMY_API_KEY` solver-payout confirm in `confirmSolverPayout` (`engine.py`) | unaffected (on-chain, not the API) |
| `src/polycrawler/config.py:52-53` | `relayRequestsPerSec: float = 1.0`, `relayPageLimit: int = 50` | can be widened for v3 |
| `configs/base.yaml`, `insiderCases.yaml`, `oosExpansionDiscover.yaml` | mirror the two keys, plus `bridgeHubs: ["0xf70da97812cb96acdf810712aa562db8dfa3dbef"]` (the Relay solver) | bump rate |
| `src/polycrawler/cli.py:136-137` | prints relay call/cache/rateLimit stats | field names survive |
| `SPEC.md` §5 step 3 | documented semantics | rewrite |
| `data/raw/relay/` | 356 responses, 12 MB, `hash_*` and `user_*` — frozen ground truth for comparison | stays |

What the v2 responses we consume look like (cache-verified): top-level `id / status / user / recipient / data.inTxs[] / data.outTxs[] / data.metadata.currencyIn|Out` and `continuation`. Call volume is small and cache-first: one `hash=` call per deposit, one user sweep per distinct origin wallet (page cap 40 × limit ≤ 50).

## 2. Candidates, verified live

### (a) Relay v3 + self-serve `x-api-key` — **REPLACES** (pending one confirmation call)

**Live checks performed** (2026-10-17):

- `GET /requests/v3` without the header → `400 {"message":"headers must have required property 'x-api-key'"}` — auth is a single opaque string in an `x-api-key` header.
- `GET /requests/v3 -H "x-api-key: bogus"` → `{"message":"Unauthorized: Check API Key"}` — keys are plain strings, nothing else to sign.
- Full OpenAPI (`docs.relay.link/references/api/get-requests.md`) and the migration guide, pulled raw.

**How to get the key.** Self-serve and free: Relay Dashboard (`dashboard.relay.link`) → API keys → Create key. No billing, no approval. Default rate limits per key: `/requests/v3` **200 requests/minute** (~3.3 rps, our current config is 1 rps), `limit` paginates up to **100** per page (v2 hard-capped 50); elevated limits (20 rps for `/requests/v3`) are on request via the dashboard support widget. `429` again has no `Retry-After`; same exponential-backoff pattern as today.

**Scope — the load-bearing sentence.** The migration guide: *"v3 returns requests owned by your integrator, plus requests that were created **without an API key**"*; the endpoint spec repeats it: *"Requests are limited to the caller's integrator and requests without an API key."* Every request in our cache is keyless (`integrator: null` across all inspected responses — Polymarket's Relay flow runs keyless), so the whole universe we trace should be visible to any free key. **This is the one claim not yet live-verified** — creating the key is an interactive dashboard step, and the check is one curl (script in §5, run order 1).

**Call sequences.**

- (a) origin resolution — v3 `term`/targeted lookups replace `?hash=`: `GET /requests/v3?fillTxHash=<payoutTxHash>` (or `depositTxHash=` for the origin-side deposit leg; `term=<x>` fuzzy-matches request id, wallet, deposit address and *all* tx hashes). Returns the same logical record; renames: `hash` → `txHash` inside `data.inTxs[]/outTxs[]`, chain/amount data moved from `data.metadata.currencyIn/Out` to `data.route.quoted/actual .origin/destination .inputCurrency/outputCurrency` (each carries `currency.chainId`, `amountUsd`). `status`, `user`, `recipient`, `id`, `createdAt` survive at top level; `continuation` semantics unchanged.
- (b) sibling sweep — v3's `user=` filter is *narrower in the right way*: "matches requests where this address is the **sender or the deposit-address depositor**" (v2 also matched recipient; we only ever query origin wallets as senders, so nothing is lost). Server-side filters then shrink the sweep: `GET /requests/v3?user=<wallet>&destinationChainId=137&status=success&limit=100` — the 40-page × 50-row sweep becomes ~n/100 pages of already-Polygon rows. Optional `includeTotal=true` gives the exact match count for progress meters; `originChainId`, `depositAddress`, `startTimestamp`/`endTimestamp`/`startBlock`/`endBlock` also exist and compose.

**Example resolution** (from cache, ready to be replayed live once the key exists):

- payout `0x131e0ad577b73064a8ace3c4bb851d75aa031151b66343c43c197afacb16c0cb` (Polygon, block 83322963) → cached v2 answer: user `0xcd86a2bb349bc6e2fac056611fb743f1ddf03ad4`, origin chain 1, `inTxs[0].hash 0xbc17d7d8eba38153cec2236e6c5446372757dfd7ba59fff3ca41d68240dfab43` (14220 USDC at ts 1771765919), out 14214.31 USDC.e at ts 1771765954, recipient `0xB390Ae2cc3FD8cB2670A62129fAEb775FAee106c`, request id `0xaaa51201dc546f0f068d32fbb7cbd046010f971ef8911157be09902769d24a96`.
- Expected v3 equivalence: `?fillTxHash=0x131e0ad5…` → same user/inTx/chain triple under the renamed fields.

**Risk register:** (i) keyless visibility could be future-only or limited (not stated — confirm in run order 1); (ii) historical retention unspecified (v2 responses kept everything we've queried so far; assume same, but the §5 backfill script makes the point moot for the pre-sunset universe); (iii) response-shape change means `parseRelayRequest` needs the rename mapping, but the fields we need all exist.

### (b) `api.relay.pro` and other v2 mirrors — **DEAD**

`api.relay.pro` resolves (13.248.169.48 / 76.223.54.146) but the TLS connection opens and every request hangs to timeout; `relay.pro` itself is a parked "lander" page. No `apiv2.` / `api-v2.` hostnames exist in DNS. The legacy `GET /requests` (v1, unsuffixed) routes return `404 Route GET:/requests?...not found`. There is no mirror path that keeps v2 alive after 24 Nov.

### (c) The on-chain trail at source (EVM origin chains) — **PARTIAL** (exact for (b) on EVM; heuristic for (a); blind for Solana/Tron/Bitcoin)

The live contract work has three shapes, all verified against real receipts pulled via public RPCs and Etherscan V2:

**Shape 1 — gasless intent (ERC-4337 + EIP-7702), seen on Ethereum, BSC, OP, Base, Arbitrum.**

- `tx.from` is a **rotating Relay bundler** (`0x433700890211…`, `0x4337009be43c…`, `0x4337032d9c92…`, all 0x4337-vanity) — the user never appears in `tx.from`, so `txlist`-style sweeps miss these.
- `tx.to` = `0x4337084d9e255ff0702461cf8895ce9e3b5ff108` — a Relay-deployed EntryPoint-flavoured router: real ~43 KB contract on Ethereum/Polygon, elsewhere it operates as an **EIP-7702 delegated EOA** (64-byte delegation stub on BSC/OP/Base/Avalanche) that accepts `handleOps` (`0x765e827f`).
- Inside the receipt:
  - relay paymaster `0x888888888888ec68a58ab8094cc1ad20ba3d2402` emits `UserOperationSponsored(bytes32 userOpHash, address user, uint8, address, …)` — **`user` is topic-indexed** (verified: topic2 = the cached v2 `user` on the golden example).
  - an escrow/deposit contract emits an unindexed event whose data words are `(user, token, amount, intentId)` — `0x4cd00e387622c35bddb9b4c962c136462338bc31` on Arbitrum/BSC/Ethereum (17258-byte code on Ethereum + Polygon), a different escrow address on Base (`0xb92fe925dc43a0ec…`, event `0xafbab204e8…`). For Base the op wraps native ETH first (`0xe1fffcc492` = `deposit()` on WETH `0x4200…0006`) before the token leg, so token-contract filters alone miss native-ETH intents.
  - the token leg emits `Transfer(user → hub 0xf70da978… on that chain)` or `approve + transferFrom(user → escrow)`.
- **Mainnet variance:** for the golden example the Relay request id (`0xaaa51201…`) is embedded verbatim in the userOp calldata — and in the Polygon payout calldata. For Arbitrum/BSC-style escrow deposits the on-chain intent id (`0x1bcb017b…`-style) is *not* the Relay request id (`0x03a53377…`-style, verified mismatched on a second user), so the exact id-join only works for the mainnet-like gasless shape.

**Shape 2 — plain token transfer (no sponsor), seen on BSC/Arbitrum.** `tx.from` IS the user; `transfer(user → deposit address)` (`0xa9059cbb`). Fully visible to `tokentx`/`txlist` by address, no decoding needed.

**Shape 3 — depositAddress origin chains** (Arbitrum): `transfer(user → 0x4cd00e38… escrow)` with the Relay deposit-address model; the destination stays Relay-internal.

**(b)-replacement via this trail — verified with real resolutions matching cached v2 answers:**

| Chain call (single source) | Found | Matches cached v2 |
|---|---|---|
| Etherscan V2 `account.tokentx` chainid=1, address `0xcd86a2bb…` | 2 USDC out-transfers to `0xf70da978…`, incl. `0xbc17d7d8…` (14220 USDC, ts 1771765919) | ✅ user, origin chain 1, inTx hash, amount |
| Etherscan V2 `account.tokentx` chainid=42161, address `0x30419f31…` | inTx `0x4ad16b3a…`: USDC → `0x4cd00e38…` escrow, 7444 USDC, ts 1771927210 | ✅ user, origin 42161, inTx, amount; cached payout `0x8de33d74…` lands 6 s later |
| Base receipt of `0xd06b8f16…` (user `0x92e71460…`) | WETH wrap + USDC 6035 + event listing user | ✅ matches per-chain shape |

Timing for the join: deposit ts 1771765919 → payout ts 1771765954 (Δ35 s), and 1771927210 → 1771927216 (Δ6 s). Deposits pre-date payouts by seconds, always.

**(a)-replacement via this trail** — two options, both usable today:

1. **Exact for gasless/mainnet-shape intents:** parse the Relay requestId out of the *Polygon payout calldata* (verified: the `transferFrom(hub, recipient, …)` payload from executor `0xca7ded7e4f4ba8ab3b10009236ae6d1b95094589` ends with the raw request id, `0xaaa51201…` for the golden example), then match that id against a user's decoded origin calldata. Works because both sides embed the same id — but only for shape 1 on chains where Relay kept that embedding, so treat as opportunistic, not systematic.
2. **Heuristic join, everywhere:** pre-index origin-side intents (`(chain, user, token, amount, ts)` from the escrow/Transfer events above, one rolling getLogs sweep per chain), then join a hub payout `(recipient, amount, ts)` to a unique origin deposit within a ±60 s window. With insider-size deposits and the observed sub-minute latency, collisions are rare; ambiguous cases count as `unresolvedOrigins`. This is the funding-transfer matching logic already in the repo, applied one chain further back.

**Chain coverage through public/free infrastructure (live-verified matrix):**

| Chain | Etherscan V2 free key (`api.etherscan.io/v2`) | Public RPC (no key) |
|---|---|---|
| Ethereum (1) | proxy ✅ / `tokentx` ✅ | publicnode ✅ |
| Polygon (137) | proxy ✅ / `tokentx` ✅ | polygon-rpc ✅ |
| Arbitrum (42161) | proxy ✅ / `tokentx` ✅ | blastapi ✅ |
| BSC (56) | **free tier refuses** (`Free API access is not supported for this chain`) | bsc-dataseed ✅ |
| Base (8453) | refuses | blastapi ✅, meowrpc ✅ |
| OP (10) | refuses | mainnet.optimism.io ✅ |
| Avalanche (43114) | refuses | api.avax.network ✅ |

(Etherscan's paid tiers unlock the rest of the family; the free-key matrix was confirmed twice to be exactly {Ethereum, Polygon, Arbitrum} for both the `proxy` and `account` modules.) Note: free public RPCs are best-effort and cap getLogs ranges; for a durable implementation the repo's existing Alchemy infra (`AlchemyBook` batching + disk cache) extends to these hosts — needs one free Alchemy app per network (the current single key is Polygon-scoped and 403s on bnb/base/opt/arb/avax hosts; `solana` is also on Alchemy).

**Blind spots, quantified from the cache:** origin chains in the `hash_*` sample: 1 (72), 137 (54, same-chain swap via hub), Solana 792703809 (20), Tron 8253038 (15), BSC 56 (14), Base 8453 (13), Arbitrum 42161 (12), OP 10 (3), X-Layer 728126428 (4), plus singletons (143, …). User-page in-chains agree (~29% Solana/Tron over the keyless user sweeps). The on-chain trail covers EVM only — Solana/Tron/Bitcoin origins (~10–13% of today's resolves) become `unresolvedOrigins` under this fallback.

### (d) Other bridges (Across, …) used by Polymarket users — **DEAD as a v2 replacement**

Coverage scope is defined by `bridgeHubs` (Relay solver `0xf70da978…` + any hub whose sample payout resolves on Relay). Deposits that came in through Across or similar were never funnel inputs, so no v2-era row depends on them. If scope ever widens to an Across hub, the same escrow/event recipe applies (`FilledV3`-style fill events index depositor/recipient); noted for completeness, not planned, not built.

### (e) Polymarket proxy mint / USDC canonical path — **DEAD**

PolyProxy funding arrives through Polymarket's own contracts, which `funding.py` already excludes from funder analysis (`polymarketContracts`). Nothing in the Relay trail depends on it.

### (f) Third-party cross-chain indexers — **extra lanes, same info as (c)**

- **Etherscan V2, one key**: verified live matrix above. Free = {Ethereum, Polygon, Arbitrum} for raw JSON-RPC pass-through *and* the high-level `account` module; Base/BSC/OP/Avalanche behind a paid plan. Good enough-by-itself for {1,137,42161}; the bigger flows sit elsewhere.
- **Relay-native alternative hosts**: covered in (b) — dead.
- **Covalent / Moralis / SimpleHash / Ankr**: same data as (c) behind multi-chain APIs; free tiers are per-chain or thin, and each adds an auth dependency the existing etherscan/alchemy/stream plumbing does not have. Not probed (no keys); verdict: use only if Etherscan-paid + Alchemy both fail.

## 3. Ranked migration plan

**First choice — Relay v3 with a self-serve `x-api-key` (complexity: S).**

1. Create the key (interactive, dashboard.relay.link → API keys → Create key); put `RELAY_API_KEY` in `.env`.
2. Confirm keyless visibility with one call against the cached golden example (`?fillTxHash=0x131e0ad5…` → expect user `0xcd86a2bb…`, origin chain 1, inTx `0xbc17d7d8…`).
3. Swap the route: `relayApi` → `https://api.relay.link/requests/v3`; `fetchRelayHashes` param `hash=` → `fillTxHash=`; `fetchRelayUsers` becomes `user= + destinationChainId=137 + status=success + limit=min(relayPageLimit,100)` (server-side Polygon filter replaces the local `polygonPayout` pre-filter for paging, keep it as a post-check).
4. `parseRelayRequest`: rename `hash` → `txHash` in in/out tx entries; move `chainId`/`amountUsd` source from `data.metadata.currencyIn/Out` to `data.metadata.route*(.quoted|.actual)` — keep the `_chainOf` fallback order; everything else (`user`, `recipient`, `status`, `continuation`) is unchanged.
5. `HttpSession`/`JsonRequest` needs a per-host `headers` passthrough for `x-api-key`; host-rates key stays `api.relay.link`; bump `relayRequestsPerSec` default 1.0 → 3.0 (v3 default limit 200/min ≈ 3.3 rps).
6. Parse-shape guard: keep the v2 parser behind a config switch (`relayApiVersion: 2|3`) so the sunset site can be watched until Nov 24, then delete the v2 branch.
7. SPEC.md §5 step 3 rewrite (terminology: fillTxHash, x-api-key, 200/min, limit ≤ 100).

Files touched: `src/polycrawler/discovery/engine.py` (relayApi, fetchRelayHashes, fetchRelayUsers, parseRelayRequest/page), `src/polycrawler/http.py` (headers on `JsonRequest`), `src/polycrawler/config.py` + the three `configs/*.yaml`, `SPEC.md`. Est. ~150 line changes.

**Fallback — on-chain origin trail (complexity: M).** New module `src/polycrawler/discovery/originTrail.py`:

- per-chain descriptors: chainId, RPC (Alchemy app or public), USDC/USDT addresses, Relay escrow set (`0x4cd00e387622…`, Base `0xb92fe925…`, hub `0xf70da978…`), bundler/paymaster watchdogs;
- (b): per origin wallet, per chain, getLogs `Transfer(topic1=<user>)` alias escrow-filtered → decode op to extract `(user, chain, token, amount, userOp/tx, intentId)`; deposit tokens/native wraps covered by receipt scanning;
- (a): replay the hub payout's Raw calldata (grab requestId when embedded) + unique-window matching of `(amount, Δt)` against the per-user intent index;
- cache dir `data/raw/trail/`; reuses `HttpSession` (hostRates per RPC), etherscan-cache convention, and register the trail route as the fallback behind the v3 path (env-flag or key-absent).

Files touched: new module + `engine.linkOrigins` branch + `config.py` descriptor list + `.env`. Est. ~400–600 lines. **Accept the coverage loss for Solana/Tron/Bitcoin origins** (only v3 covers those).

**Optional layered third-party indexer purchases (S)** — only if Etherscan free + public RPC rate caps bite: Etherscan paid tier (unlocks 56/8453/10/43114 with one key) or extra Alchemy apps (also brings solana). Neither adds information (c) lacks.

**Backfill before the deadline (recommended, S).** One-off `scripts/research/relaySweep.py`: with v2 still alive, re-pull every origin wallet known to the labeled/crun caches at relaxed limiter (1 rps exists already in config) so `data/raw/relay/` becomes a frozen, complete pre-sunset ground truth; siblings today are already cached, so this is insurance against v3-side field surprises during the cutover.

## 4. Verification run order (after the key exists)

1. `curl -H "x-api-key: $KEY" "https://api.relay.link/requests/v3?fillTxHash=0x131e0ad577b73064a8ace3c4bb851d75aa031151b66343c43c197afacb16c0cb&limit=1"` — assert `user == 0xcd86a2bb…`, `data.inTxs[0].chainId == 1`, `data.outTxs[0].chainId == 137`, inTx hash `0xbc17d7d8…` (golden cache example).
2. `curl -H "x-api-key: $KEY" "https://api.relay.link/requests/v3?user=0xcd86a2bb349bc6e2fac056611fb743f1ddf03ad4&destinationChainId=137&status=success&limit=100"` — the same sweep as today's `user=` on that wallet; compare rows against the cached `user_0xcd86a2bb…_start.json` page set.
3. Repeat (1) for a non-EVM origin, e.g. payout `0x5e3cc012cb055ed7bae82a45b4fb052b789c336335e4ba9274a8eb52a0802ed8` (Solana-origin user `EdrUA7xfoRNxyuhsYP6HKNueBWem2R16mtcYbPiN2Caf`) — proves the non-EVM row survives v3.
4. Sanity-check 429 behaviour: burst to the limit, confirm backoff semantics match `rateLimitMessage()` (body-level `message` string, no `Retry-After`).

If (1) returns empty or omits our keyless rows → the scope claim fails → jump to the on-chain fallback and treat v3 as partial.

## 5. Takeaways

- Nothing about the *analysis* changes — only resolution plumbing. `firstBridgeDeposits`, `sampleOtherHubs`, `polygonPayout`, cluster logic are all untouched; the sunset removes ~two HTTP calls' worth of source data.
- v3 is feature-for-feature (functional superset: term search, server-side chain/status filters, includeTotal, 2× page size, same `continuation`), and needs no infra beyond a free key. The single open question is keyless-requests visibility; the on-chain fallback does not depend on it and works without any Relay-side change.
- The on-chain trail is permanently available (no sunset risk — it is just chains and contracts) at the price of per-chain plumbing and a residual join heuristic on the payout side.
- The non-EVM origins (Solana/Tron) are the one thing the on-chain fallback cannot cover — worth keeping the v3 key even if it only works partially.
- v2 quota discipline during the run-in was maintained: zero live v2 calls made producing this doc; all comparisons came from `data/raw/relay/` and the user-deprecation body that travels with every v2 response.
