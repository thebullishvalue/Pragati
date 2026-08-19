"""
PRAGYAM — Tab modules.

One module per tab of the results page. Each owns its own rendering and
nothing else: no data fetching, no curation, no session-state mutation beyond
its own widgets. The shell in app.py decides WHICH tab renders; a tab decides
only HOW.
"""

from ui.tabs.tab_analytics import _render_analytics_tab as render_analytics_tab
from ui.tabs.tab_broker import _render_broker_sync_tab as render_broker_sync_tab
from ui.tabs.tab_portfolio import _render_portfolio_tab as render_portfolio_tab
from ui.tabs.tab_regime import _render_regime_tab as render_regime_tab
from ui.tabs.tab_system import _render_system_tab as render_system_tab

__all__ = [
    "render_analytics_tab",
    "render_broker_sync_tab",
    "render_portfolio_tab",
    "render_regime_tab",
    "render_system_tab",
]
