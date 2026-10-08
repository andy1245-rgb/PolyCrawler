# Discovery steps 2–3 — funding and clusters

Ran on `configs/insiderCases.yaml` (`splitDate` 2026-03-01) after step 1. 236 suspicious accounts, plus the 2 labeled wallets that were not suspicious, so 238 accounts traced. Transfers before the split are the only ones used to link accounts. `pc2 discover` writes `data/funding.parquet`, `data/parents.parquet`, and `data/clusterAccounts.parquet`.

## Collateral and Polymarket contracts

Collateral that actually moves into these accounts:

| Token | Address | Rows kept |
|---|---|---:|
| USDC.e | `0x2791bca1f2de4661ed88a30c99a7a9449aa84174` | 4593 |
| pUSD | `0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb` | 2891 |
| native USDC | `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` | 62 |
| USDT (USDT0) | `0xc2132d05d31c914a87c6611c10748aeb04b58e8f` | 40 |

Every labeled insider deposit in this window is USDC.e. pUSD shows up as later collateral movement, not as the first funding of those wallets. Trades and redeems are dropped when the other side is a Polymarket contract: CTF exchange v1 `0x4bfb41d5…`, NegRisk exchange v1 `0xc5d563a3…`, NegRisk adapter `0xd91e80cf…`, conditional tokens `0x4d97dcd9…`, the proxy and safe factories, and the v2 exchange, router, position manager, and collateral ramp addresses. That filter removed 65,217 collateral transfers.

## What `0xf70da978…` is

Polygonscan labels `0xf70da97812cb96acdf810712aa562db8dfa3dbef` **Relay: Solver**. It is an EOA (no code) and a hub: 570 distinct collateral counterparties on its newest 1,000 token transfers, and it paid 211 of the 238 traced accounts. It fronts USDC.e from inventory. Around the fuego66, Lettucehead718, and suffix-295 deposits there is no inbound transfer of the same amount in the surrounding minute — the solver pays the Polymarket account, and the user's own deposit is not on this address.

## Hubs and clusters

20 hubs. The ones that touch the most traced accounts:

| Address | Counterparties in sample | Traced accounts | What it is |
|---|---:|---:|---|
| `0xf70da978…` | 570 | 211 | Relay solver |
| `0x4cd00e38…` | 681 | 98 | hub (the cluster parent also cashes out here) |
| `0xc2884805…` | 999 | 61 | hub, mostly dust |
| `0xf7cd89be…` | 237 | 39 | hub, mostly dust |
| `0xf5042e6f…` | 83 | 24 | USDC ↔ USDC.e swap router |

`0xf5042e6f…` is why the oldest page of a full transfer history is checked. Its newest 1,000 transfers have only 21 collateral counterparties, so a newest-page-only rule made it the parent of a fake 29-account cluster. The oldest page has 83. Swaps through that router are not a shared funder.

One real cluster:

| Parent | Suspicious | Accounts | Profit | First seen |
|---|---:|---:|---:|---|
| `0x0700cb9b2504c30c55273c323f67faaa23a3267b` | 4 | 5 | $168,600 | 2026-02-22 05:13 UTC |

The parent is a small contract. It sent each account $5 and then a round amount ($1,495, $2,495, $2,995, $2,995) on 22 Feb and 25 Feb. A second contract with the identical bytecode, `0x798c4246…`, paid the same four accounts again a few hours later ($1, then $1,499 / $2,500 / $2,999 / $2,207). The fifth account, `0xe23e6d6f…`, received $617 from the parent on 28 Mar, after the split. None of the nine labeled wallets are in this cluster. The parent's own USDC.e mostly arrived from the Relay solver; one early $216 came from `0x04ef39c0…`.

## Labeled wallets

| Wallet | Name | In a cluster | With |
|---|---|---|---|
| `0x6f536910…` | Lettucehead718 | no | — |
| `0xb390ae2c…` | suffix-295 | no | — |
| `0x1caa6a7a…` | Careless-Bug | no | — |
| `0xa4eb5222…` | Wet-Film | no | — |
| `0xca886a7e…` | Courteous-Epoch | no | — |
| `0x9c274a7d…` | Aware-Initialize | no | — |
| `0x09d3273f…` | fuego66 | no | — |
| `0x31a56e9e…` | Burdensome-Mix | no | — |
| `0xa72db174…` | Wee-Pseudoscience | no | — |

Lettucehead718, suffix-295, Careless-Bug, Wet-Film, and fuego66 are funded only by hubs (almost entirely the Relay solver), and before the split they have no cash-out to a non-hub address. Aware-Initialize, Burdensome-Mix, and Wee-Pseudoscience also share the solver, and the last two plus Aware share the USDC router `0xf5042e6f…`. That router link is the fake cluster above; it is not kept.

Bubblemaps' "funded through similar paths" matches the on-chain pattern and stops there. Lettucehead718 and suffix-295 were both created 22 Feb and both received ~$10 from the solver, then $16,302 and $14,224 about 40 minutes apart. The amounts are not the same, and the solver's books in those minutes show unrelated inflows, not one shared deposit. There is no second hop to take: the funder is a hub, and hopping through hubs is what creates the mega-cluster. Nothing in these transfers links the nine labeled wallets to each other once hubs and routers are removed.

## API

Etherscan v2, `chainid=137`, throttled at about 4 requests/second, every response cached under `data/raw/etherscan/`. The funding runs made 345 requests (342 on the first pass, 3 after the router fix, then a cache-only rerun). About 30 more requests were used by hand to identify the solver and to read its books around the insider deposits.
