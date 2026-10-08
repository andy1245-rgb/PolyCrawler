# Account Types

**Source:** spec.md §3

---

Polymarket users arrive through different paths. The same protocols apply; how early we see them varies.

| Type | Description | Detection timing |
|------|-------------|------------------|
| **Deposit wallet** | Direct deposit from parent. Fastest to detect. | Immediate on fund tx |
| **Safe** | Smart contract wallet. Requires event parsing. | On deploy + fund |
| **Proxy** | Intermediate deployer contract. Needs hop tracing. | After funding chain resolved |

All types are stored in `accounts.account_type` with values: `deposit_wallet`, `safe`, `proxy`, or `unknown`.
