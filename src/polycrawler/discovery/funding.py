import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import polars as pl

from polycrawler.fetch import alchemyUrl, loadApiKey
from polycrawler.http import HttpSession, cachePath, rateLimitMessage, redactSecrets, writeJson

etherscanApi = "https://api.etherscan.io/v2/api"
etherscanChainId = 137
etherscanPageSize = 1000
# Etherscan's result window stops at 10_000 rows (10 pages of 1000).
etherscanMaxPages = 10
alchemyHost = "polygon-mainnet.g.alchemy.com"
# Free-tier CU rejects a 100-call alchemy_getAssetTransfers batch. Start at 100
# and halve after a rate-limit body; 20-call batches return cleanly.
alchemyBatchStart = 100
alchemyPageCap = 40

collateralSymbols = {
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC.e",
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": "USDC",
    "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb": "pUSD",
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": "USDT0",
}
collateralTokens = frozenset(collateralSymbols)
collateralList = list(collateralSymbols)

# Trades and redeems move collateral through these. They are not funders.
polymarketContracts = {
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e": "ctfExchangeV1",
    "0xc5d563a36ae78145c45a50134d48a1215220f80a": "negRiskExchangeV1",
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296": "negRiskAdapter",
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045": "conditionalTokens",
    "0xab45c5a4b0c941a2f231c04c3f49182e1a254052": "proxyFactory",
    "0xaacfeea03eb1561c4e67d661e40682bd20e3541b": "safeFactory",
    "0xe111180000d2663c0091e4f400237545b87b996b": "ctfExchangeV2",
    "0xe2222d279d744050d28e00520010520000310f59": "negRiskExchangeV2",
    "0x006f54f7f9a22e0000cc2ab60031000000ae9fef": "positionManager",
    "0x12121212006e4cd160d18e3f00711da5c3372600": "routerV2",
    "0x1000008dd9001b968442c1000017eae6e0da00ba": "binaryModule",
    "0x200000900045e3b6259600682756002200028933": "negRiskModule",
    "0x30000034706c7d8e12009dab006be20000c031a8": "combinatorialModule",
    "0xe3333700ca9d93003f00f0f71f8515005f6c00aa": "exchangeV3",
    "0xa1200000d0002264c9a1698e001292d00e1b00af": "autoRedeemer",
    "0x93070a847efef7f70739046a929d47a521f5b8ee": "collateralOnramp",
    "0x2957922eb93258b93368531d39facca3b4dc5854": "collateralOfframp",
    "0xebc2459ec962869ca4c0bd1e06368272732bcb08": "permissionedRamp",
    "0xada100db00ca00073811820692005400218fce1f": "ctfCollateralAdapter",
    "0xada2005600dec949baf300f4c6120000bdb6eaab": "negRiskCtfCollateralAdapter",
    "0x00000000000fb5c9adea0298d729a0cb3823cc07": "depositWalletFactory",
    "0x7a18edfe055488a3128f01f563e5b479d92ffc3a": "depositWalletBeacon",
    "0xd216153c06e857cd7f72665e0af1d7d82172f494": "relayHub",
}


@dataclass(frozen=True)
class TransferRow:
    ts: int
    fromAddr: str
    toAddr: str
    amountUsd: float
    txHash: str


@dataclass
class EtherscanStats:
    fetched: int = 0
    cached: int = 0


@dataclass(frozen=True)
class HubInfo:
    address: str
    counterparties: int
    accounts: int


@dataclass
class FundingResult:
    traced: int
    hubs: list[HubInfo]
    clusters: int
    fetched: int
    cached: int
    collateralCounts: dict[str, int]
    otherTokens: list[tuple[str, int]]
    parents: pl.DataFrame
    members: pl.DataFrame
    fundingRows: int = 0
    skippedPolymarket: int = 0
    origins: int = 0
    originUsers: int = 0
    originChainText: str = ""
    unresolvedOrigins: int = 0
    siblings: int = 0
    siblingsOutside: int = 0
    siblingsAfterSplit: int = 0
    relayCalls: int = 0
    relayCacheHits: int = 0
    relayRateLimits: int = 0
    relaySeconds: float = 0.0
    bridgeHubs: list[str] = field(default_factory=list)
    alchemyBlock: int | None = None
    alchemyPayoutConfirmed: bool | None = None
    bridgeDeposits: int = 0
    coTradeEdges: int = 0
    alchemyCalls: int = 0
    alchemyCached: int = 0
    alchemySeconds: float = 0.0
    alchemyBatch: int = 0


def etherscanCacheKey(params: dict[str, Any]) -> str:
    action = str(params.get("action") or "call")
    address = str(params.get("address") or "none").lower()
    extra = [
        f"{key}-{params[key]}"
        for key in sorted(params)
        if key not in {"module", "action", "address"}
    ]
    tail = "_".join(extra)
    if len(tail) > 140:
        tail = hashlib.sha256(tail.encode()).hexdigest()[:20]
    return f"{action}_{address}_{tail}" if tail else f"{action}_{address}"


def payloadUsable(params: dict[str, Any], payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    if params.get("action") == "eth_getCode":
        return isinstance(result, str) and result.startswith("0x")
    if isinstance(result, list):
        return True
    text = f"{payload.get('message') or ''} {result or ''}".lower()
    return "no transactions" in text or "no records" in text


def etherscanCall(
    session: HttpSession,
    dataDir: str,
    params: dict[str, Any],
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> dict[str, Any]:
    key = etherscanCacheKey(params)
    host = "api.etherscan.io"
    before = session.stats.cacheHits.get(host, 0)
    query = {"chainid": etherscanChainId, **params, "apikey": apiKey}
    payload = session.getJson(etherscanApi, query, cacheKind="etherscan", cacheKey=key, refresh=refresh)
    if session.stats.cacheHits.get(host, 0) > before:
        stats.cached += 1
    else:
        stats.fetched += 1
    if not isinstance(payload, dict) or not payloadUsable(params, payload):
        path = cachePath(dataDir, "etherscan", key)
        path.unlink(missing_ok=True)
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("result") or "")
        if "invalid api key" in message.lower():
            raise RuntimeError("etherscan rejected the API key")
        raise RuntimeError(f"etherscan {params.get('action')} failed: {message[:160]}")
    return payload


def tokenRows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    return []


def isEoa(payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    if not isinstance(result, str) or not result.startswith("0x"):
        message = str(payload.get("message") or result or "")[:160]
        raise RuntimeError(f"getcode failed: {message}")
    body = result[2:]
    return body == "" or set(body) <= {"0"}


def tokenAmount(row: dict[str, Any]) -> float:
    raw = row.get("tokenDecimal")
    decimals = int(raw) if raw not in (None, "") else 6
    return int(row.get("value") or 0) / (10**decimals)


def parseCollateral(row: dict[str, Any], minFundingUsd: float) -> TransferRow | None:
    token = str(row.get("contractAddress") or "").lower()
    if token not in collateralTokens:
        return None
    src = str(row.get("from") or "").lower()
    dst = str(row.get("to") or "").lower()
    if not src or not dst or src == dst:
        return None
    if src in polymarketContracts or dst in polymarketContracts:
        return None
    amount = tokenAmount(row)
    if amount < minFundingUsd:
        return None
    return TransferRow(
        ts=int(row["timeStamp"]),
        fromAddr=src,
        toAddr=dst,
        amountUsd=amount,
        txHash=str(row.get("hash") or "").lower(),
    )


def collateralCounterparties(address: str, rows: list[dict[str, Any]]) -> int:
    # Spam airdrops come from many token contracts. Count stablecoin
    # counterparties only, or a normal wallet looks like a hub.
    address = address.lower()
    others: set[str] = set()
    for row in rows:
        token = str(row.get("contractAddress") or "").lower()
        if token not in collateralTokens:
            continue
        src = str(row.get("from") or "").lower()
        dst = str(row.get("to") or "").lower()
        if src == address and dst and dst != address:
            others.add(dst)
        elif dst == address and src and src != address:
            others.add(src)
    return len(others)


def hubAddresses(samples: dict[str, list[dict[str, Any]]], minimum: int) -> dict[str, int]:
    found: dict[str, int] = {}
    for address, rows in samples.items():
        count = collateralCounterparties(address, rows)
        if count >= minimum:
            found[address.lower()] = count
    return found


def hubFromSample(
    descCount: int,
    ascCount: int,
    pageFull: bool,
    isContract: bool,
    minimum: int,
    codeChars: int = 0,
) -> bool:
    # Newest-page counterparties miss routers whose recent flow sits on a few
    # pools. A full page plus real bytecode is a router; the ~125-byte funding
    # clones in this tape are not.
    if max(descCount, ascCount) >= minimum:
        return True
    return pageFull and isContract and codeChars > 1000


def judgeHub(
    address: str,
    descRows: list[dict[str, Any]],
    ascRows: list[dict[str, Any]],
    codeResult: dict[str, Any] | None,
    minimum: int,
    pageSize: int = etherscanPageSize,
) -> int | None:
    descCount = collateralCounterparties(address, descRows)
    pageFull = len(descRows) >= pageSize
    ascCount = collateralCounterparties(address, ascRows) if pageFull and descCount < minimum else 0
    if ascRows and len(ascRows) >= pageSize:
        pageFull = True
    isContract = False
    codeChars = 0
    if pageFull and max(descCount, ascCount) < minimum and codeResult is not None:
        isContract = not isEoa(codeResult)
        codeChars = len(str(codeResult.get("result") or ""))
    if not hubFromSample(descCount, ascCount, pageFull, isContract, minimum, codeChars):
        return None
    return max(descCount, ascCount)


def fetchTokenPage(
    session: HttpSession,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
    sort: str,
    page: int,
) -> list[dict[str, Any]]:
    payload = etherscanCall(
        session,
        dataDir,
        {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": page,
            "offset": etherscanPageSize,
            "sort": sort,
        },
        refresh,
        apiKey,
        stats,
    )
    return tokenRows(payload)


def fetchTokenHistory(
    session: HttpSession,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, etherscanMaxPages + 1):
        batch = fetchTokenPage(session, dataDir, address, refresh, apiKey, stats, "asc", page)
        rows.extend(batch)
        if len(batch) < etherscanPageSize:
            break
    return rows


def fetchProbe(
    session: HttpSession,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> list[dict[str, Any]]:
    return fetchTokenPage(session, dataDir, address, refresh, apiKey, stats, "desc", 1)


def codePayload(
    session: HttpSession,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> dict[str, Any]:
    return etherscanCall(
        session,
        dataDir,
        {"module": "proxy", "action": "eth_getCode", "address": address, "tag": "latest"},
        refresh,
        apiKey,
        stats,
    )


def classifyProbe(
    session: HttpSession,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
    descRows: list[dict[str, Any]],
    minimum: int,
) -> int | None:
    descCount = collateralCounterparties(address, descRows)
    ascRows: list[dict[str, Any]] = []
    if descCount < minimum and len(descRows) >= etherscanPageSize:
        ascRows = fetchTokenPage(session, dataDir, address, refresh, apiKey, stats, "asc", 1)
    code = None
    ascCount = collateralCounterparties(address, ascRows) if ascRows else 0
    if len(descRows) >= etherscanPageSize and max(descCount, ascCount) < minimum:
        code = codePayload(session, dataDir, address, refresh, apiKey, stats)
    return judgeHub(address, descRows, ascRows, code, minimum)


def polymarketHit(row: dict[str, Any]) -> bool:
    token = str(row.get("contractAddress") or "").lower()
    if token not in collateralTokens:
        return False
    src = str(row.get("from") or "").lower()
    dst = str(row.get("to") or "").lower()
    return src in polymarketContracts or dst in polymarketContracts


def noteOtherToken(row: dict[str, Any], account: str, minFundingUsd: float, counter: Counter[str]) -> None:
    token = str(row.get("contractAddress") or "").lower()
    if token in collateralTokens or token in polymarketContracts:
        return
    if str(row.get("to") or "").lower() != account:
        return
    if str(row.get("tokenDecimal") or "") != "6":
        return
    amount = tokenAmount(row)
    if amount < minFundingUsd or amount > 10_000_000:
        return
    symbol = str(row.get("tokenSymbol") or token[:10])
    counter[f"{symbol}:{token}"] += 1


def counterpartiesBeforeSplit(
    transfers: list[TransferRow],
    traced: set[str],
    splitTs: int,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    funders: dict[str, set[str]] = defaultdict(set)
    cashOuts: dict[str, set[str]] = defaultdict(set)
    for row in transfers:
        if row.ts >= splitTs:
            continue
        if row.toAddr in traced and row.fromAddr not in traced:
            funders[row.fromAddr].add(row.toAddr)
        if row.fromAddr in traced and row.toAddr not in traced:
            cashOuts[row.toAddr].add(row.fromAddr)
    return funders, cashOuts


def outgoingRecipients(address: str, rows: list[dict[str, Any]], minFundingUsd: float) -> set[str]:
    found: set[str] = set()
    for row in rows:
        parsed = parseCollateral(row, minFundingUsd)
        if parsed is not None and parsed.fromAddr == address:
            found.add(parsed.toAddr)
    return found


def incomingFunders(address: str, rows: list[dict[str, Any]], minFundingUsd: float) -> set[str]:
    found: set[str] = set()
    for row in rows:
        parsed = parseCollateral(row, minFundingUsd)
        if parsed is not None and parsed.toAddr == address:
            found.add(parsed.fromAddr)
    return found


def hopSources(
    funders: dict[str, set[str]],
    hubs: set[str],
    excluded: set[str],
    probes: dict[str, list[dict[str, Any]]],
    minFundingUsd: float,
    hubMinimum: int,
    codeFn: Callable[[str], dict[str, Any]],
    probeFn: Callable[[str], list[dict[str, Any]]],
    classifyFn: Callable[[str, list[dict[str, Any]]], int | None],
) -> tuple[set[str], dict[str, set[str]], dict[str, int]]:
    blocked = hubs | excluded
    eoaFunders: set[str] = set()
    grandparents: dict[str, set[str]] = {}
    reached: dict[str, set[str]] = defaultdict(set)
    candidates = sorted(addr for addr in funders if addr not in blocked)
    for index, funder in enumerate(candidates, start=1):
        if index == 1 or index % 25 == 0 or index == len(candidates):
            print(f"funder code {index}/{len(candidates)}", flush=True)
        payload = codeFn(funder)
        if not isEoa(payload):
            continue
        eoaFunders.add(funder)
        sources = incomingFunders(funder, probes.get(funder, []), minFundingUsd)
        grandparents[funder] = sources
        for source in sources:
            reached[source].update(funders[funder])
    extraSamples: dict[str, list[dict[str, Any]]] = {}
    for source, group in reached.items():
        if len(group) < 2 or source in probes or source in blocked:
            continue
        extraSamples[source] = probeFn(source)
    extraHubs: dict[str, int] = {}
    for source, rows in extraSamples.items():
        count = classifyFn(source, rows)
        if count is not None:
            extraHubs[source] = count
    if extraHubs:
        grandparents = {
            funder: {source for source in sources if source not in extraHubs and source not in blocked}
            for funder, sources in grandparents.items()
        }
    return eoaFunders, grandparents, extraHubs


def unixOf(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def alchemyToRow(item: dict[str, Any]) -> dict[str, Any] | None:
    raw = item.get("rawContract") if isinstance(item.get("rawContract"), dict) else {}
    decimalText = str(raw.get("decimal") or "0x6")
    try:
        decimals = int(decimalText, 16) if decimalText.startswith(("0x", "0X")) else int(decimalText)
    except ValueError:
        decimals = 6
    valueText = str(raw.get("value") or "")
    if valueText.startswith(("0x", "0X")):
        try:
            amount = int(valueText, 16)
        except ValueError:
            amount = 0
    else:
        try:
            amount = int(round(float(item.get("value") or 0) * (10**decimals)))
        except (TypeError, ValueError):
            amount = 0
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    ts = unixOf(meta.get("blockTimestamp"))
    if ts is None:
        return None
    return {
        "contractAddress": str(raw.get("address") or "").lower(),
        "from": str(item.get("from") or "").lower(),
        "to": str(item.get("to") or "").lower(),
        "tokenDecimal": str(decimals),
        "value": str(amount),
        "timeStamp": str(ts),
        "hash": str(item.get("hash") or "").lower(),
        "tokenSymbol": str(item.get("asset") or ""),
    }


def itemLimited(item: dict[str, Any]) -> bool:
    if rateLimitMessage(item):
        return True
    err = item.get("error")
    text = str(err.get("message") if isinstance(err, dict) else err or "").lower()
    return "rate limit" in text or "too many" in text


class AlchemyBook:
    def __init__(self, session: HttpSession, url: str, dataDir: str, refresh: bool) -> None:
        self.session = session
        self.url = url
        self.dataDir = dataDir
        self.refresh = refresh
        self.batchSize = alchemyBatchStart
        self.calls = 0
        self.cached = 0
        self.started = time.perf_counter()

    @property
    def seconds(self) -> float:
        return time.perf_counter() - self.started

    def _key(self, kind: str, address: str, tail: str) -> str:
        return f"{kind}_{address.lower()}_{tail or 'start'}"

    def read(self, kind: str, address: str, tail: str) -> Any | None:
        if self.refresh:
            return None
        path = cachePath(self.dataDir, "alchemy", self._key(kind, address, tail))
        if not path.exists():
            return None
        self.cached += 1
        return json.loads(path.read_text())

    def write(self, kind: str, address: str, tail: str, payload: Any) -> None:
        writeJson(cachePath(self.dataDir, "alchemy", self._key(kind, address, tail)), payload)

    def rpc(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        body = [
            {"jsonrpc": "2.0", "id": index, "method": call["method"], "params": call["params"]}
            for index, call in enumerate(calls)
        ]
        self.calls += 1
        started = time.perf_counter()
        payload = self.session.postJson(self.url, body)
        if self.calls <= 3 or self.calls % 10 == 0:
            print(f"alchemy batch {len(calls)} in {time.perf_counter() - started:.2f}s size {self.batchSize}", flush=True)
        if isinstance(payload, dict):
            message = str(payload.get("error") or payload)[:200]
            raise RuntimeError(redactSecrets(f"alchemy batch failed: {message}"))
        if not isinstance(payload, list):
            raise RuntimeError("alchemy batch was not a list")
        byId = {item.get("id"): item for item in payload if isinstance(item, dict)}
        return [byId.get(index, {"error": {"message": "missing rpc response"}}) for index in range(len(calls))]

    def runBatch(self, calls: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
        pending = list(range(len(calls)))
        out: list[dict[str, Any] | None] = [None] * len(calls)
        passes = 0
        while pending and passes < 8:
            passes += 1
            width = min(self.batchSize, len(pending))
            chunk = pending[:width]
            pending = pending[width:]
            items = self.rpc([calls[index] for index in chunk])
            again: list[int] = []
            for index, item in zip(chunk, items):
                if itemLimited(item):
                    again.append(index)
                else:
                    out[index] = item
            if again:
                self.batchSize = max(10, self.batchSize // 2)
                print(f"alchemy rate limit, next batch {self.batchSize}", flush=True)
                time.sleep(1.0)
                pending = again + pending
        return out


def transferParams(address: str, direction: str, order: str, pageKey: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "fromBlock": "0x0",
        "category": ["erc20"],
        "contractAddresses": collateralList,
        "order": order,
        "maxCount": "0x3e8",
        "withMetadata": True,
    }
    params["toAddress" if direction == "in" else "fromAddress"] = address
    if pageKey:
        params["pageKey"] = pageKey
    return params


def rowsFromResult(result: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    rows = []
    for item in result.get("transfers") or []:
        if isinstance(item, dict):
            parsed = alchemyToRow(item)
            if parsed is not None:
                rows.append(parsed)
    pageKey = result.get("pageKey") or None
    return rows, str(pageKey) if pageKey else None


def alchemyHistories(book: AlchemyBook, addresses: list[str]) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    found: dict[str, list[dict[str, Any]]] = {addr: [] for addr in addresses}
    failed: set[str] = set()
    for direction in ("in", "out"):
        queue: list[tuple[str, str | None]] = [(addr, None) for addr in addresses]
        seen: set[tuple[str, str | None]] = set()
        pages = 0
        while queue and pages < alchemyPageCap:
            pages += 1
            jobs = []
            for addr, pageKey in queue:
                if addr in failed or (addr, pageKey) in seen:
                    continue
                seen.add((addr, pageKey))
                tail = f"{direction}_asc_{pageKey or 'start'}"
                cached = book.read("xfer", addr, tail)
                if cached is not None:
                    found[addr].extend(cached.get("rows") or [])
                    nxt = cached.get("pageKey")
                    if nxt and nxt != pageKey:
                        jobs.append((addr, nxt, True))
                    continue
                jobs.append((addr, pageKey, False))
            queue = [(addr, pageKey) for addr, pageKey, cachedHit in jobs if cachedHit]
            need = [(addr, pageKey) for addr, pageKey, cachedHit in jobs if not cachedHit]
            if not need:
                continue
            calls = [
                {"method": "alchemy_getAssetTransfers", "params": [transferParams(addr, direction, "asc", pageKey)]}
                for addr, pageKey in need
            ]
            items = book.runBatch(calls)
            for (addr, pageKey), item in zip(need, items):
                if item is None or item.get("error") or not isinstance(item.get("result"), dict):
                    failed.add(addr)
                    continue
                result = item["result"]
                rows, nxt = rowsFromResult(result)
                book.write("xfer", addr, f"{direction}_asc_{pageKey or 'start'}", {"rows": rows, "pageKey": nxt})
                found[addr].extend(rows)
                if nxt and nxt != pageKey:
                    queue.append((addr, nxt))
    for addr in failed:
        found.pop(addr, None)
    return found, failed


def alchemyProbe(
    book: AlchemyBook,
    addresses: list[str],
    order: str,
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    found: dict[str, list[dict[str, Any]]] = {addr: [] for addr in addresses}
    failed: set[str] = set()
    for direction in ("in", "out"):
        need = []
        for addr in addresses:
            tail = f"{direction}_{order}_start"
            cached = book.read("probe", addr, tail)
            if cached is not None:
                found[addr].extend(cached.get("rows") or [])
                continue
            need.append(addr)
        if not need:
            continue
        calls = [
            {"method": "alchemy_getAssetTransfers", "params": [transferParams(addr, direction, order, None)]}
            for addr in need
        ]
        items = book.runBatch(calls)
        for addr, item in zip(need, items):
            if item is None or item.get("error") or not isinstance(item.get("result"), dict):
                failed.add(addr)
                continue
            rows, _page = rowsFromResult(item["result"])
            book.write("probe", addr, f"{direction}_{order}_start", {"rows": rows})
            found[addr].extend(rows)
    for addr in failed:
        found.pop(addr, None)
    return found, failed


def alchemyCodes(book: AlchemyBook, addresses: list[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    need: list[str] = []
    for addr in addresses:
        cached = book.read("code", addr, "latest")
        if isinstance(cached, dict) and isinstance(cached.get("result"), str):
            found[addr] = cached
        else:
            need.append(addr)
    if not need:
        return found
    calls = [{"method": "eth_getCode", "params": [addr, "latest"]} for addr in need]
    items = book.runBatch(calls)
    for addr, item in zip(need, items):
        result = item.get("result") if isinstance(item, dict) else None
        if not isinstance(result, str) or not result.startswith("0x"):
            continue
        payload = {"result": result}
        book.write("code", addr, "latest", payload)
        found[addr] = payload
    return found


def openAlchemy(session: HttpSession, dataDir: str, refresh: bool) -> AlchemyBook | None:
    key = loadApiKey("ALCHEMY_API_KEY")
    if not key:
        return None
    return AlchemyBook(session, alchemyUrl(key), dataDir, refresh)


def requireEtherscanKey() -> str:
    key = loadApiKey("ETHERSCAN_API_KEY")
    if not key:
        raise RuntimeError("ETHERSCAN_API_KEY is not set")
    return key
