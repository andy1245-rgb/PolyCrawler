"""Discovery engine package.

The runtime engine lives in `polycrawler.discovery.engine` (suspicious
flagging, funding trace, origin linking, the cluster build itself); the
focused helpers live beside it: activity, flagging, funding, links and
mergeScores. The package root re-exports the engine's public names so
`from polycrawler.discovery import runDiscover` keeps working for the CLI,
backtest and research scripts.
"""

from polycrawler.discovery.engine import *  # noqa: F401,F403
