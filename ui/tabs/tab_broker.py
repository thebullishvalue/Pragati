"""
PRAGYAM — Curated units, written into broker order templates.

The natural final step of the flow: curate -> sync -> execute. Reads the LIVE
portfolio, so what is written is what is held.

Author: @thebullishvalue
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from ui.components import (
    render_empty_state,
    render_interpretation_card,
    render_section_header,
    render_table_panel,
)
from ui.shared import NCO_STYLES, REGIME_FACTOR_ORDER, STYLE_LABELS, num, style_spec
import html as html_module

from logger_config import get_console

log = get_console()


def _sync_broker_json(json_data, quantity_map: Dict[str, int]) -> Tuple[list, int, int]:
    """Map curated per-symbol units into a broker order-template JSON.

    Walks each instrument in the template, and where its
    ``instrument.tradingsymbol`` matches a curated holding WITH units > 0,
    writes the holding's unit count into ``params.quantity``. A match with
    units == 0 is left untouched rather than zeroing out the template's
    existing quantity — the method card promises non-matching instruments
    are "untouched", and a matched-but-zero-unit holding silently
    zeroing a possibly-intentional manual quantity was a third, undocumented
    case (see AUDIT_DIRECTIVES.md B8). Returns (mutated JSON, instruments
    updated, instruments matched-but-skipped-for-zero-units).
    """
    updated = 0
    skipped_zero = 0
    for item in json_data:
        try:
            symbol = item.get("instrument", {}).get("tradingsymbol")
            if symbol and symbol in quantity_map and "params" in item:
                qty = quantity_map[symbol]
                if qty > 0:
                    item["params"]["quantity"] = qty
                    updated += 1
                else:
                    skipped_zero += 1
        except Exception:
            continue
    return json_data, updated, skipped_zero


def _render_broker_sync_tab(portfolio: pd.DataFrame):
    """Tab — Broker JSON Sync: write curated units into broker order templates.

    Reads the LIVE curated portfolio (no CSV re-upload) and maps each holding's
    unit count onto the matching instrument's ``params.quantity`` in every
    uploaded broker template (e.g. Kite ETF.json), producing ready-to-import
    order files. The natural final step of the flow: curate → sync → execute.
    """
    import json as _json

    render_section_header(
        "Broker JSON Sync",
        "Write curated units into broker order templates · curate → sync → execute",
        icon="download",
        accent="cyan",
    )

    # Guard: nothing to sync until a portfolio has been curated.
    if portfolio is None or portfolio.empty or "symbol" not in portfolio.columns or "units" not in portfolio.columns:
        render_interpretation_card(
            title="NO CURATED PORTFOLIO",
            body=(
                "Run an analysis first — the sync uses the live curated portfolio "
                "directly, so there is nothing to map onto your broker templates yet."
            ),
            color="warning",
        )
        return

    # Build the symbol → units map from the live portfolio (units ≥ 0, integer).
    qty_map: Dict[str, int] = {
        str(sym): int(u)
        for sym, u in zip(portfolio["symbol"], portfolio["units"].fillna(0))
    }
    tradable = sum(1 for u in qty_map.values() if u > 0)

    # ── Balanced two-column layout, mirroring the Intelligence tab exactly ─────
    #    col1 = status card + template uploader
    #    col2 = results table + totals line + per-file downloads
    col1, col2 = st.columns([1, 1])

    # Process uploaded templates once, up front, so both columns read the same
    # deterministic result set (status card, results table, download buttons).
    json_files = st.session_state.get("broker_sync_json_uploader")
    # (fname, payload_or_None, updated_count, skipped_zero_count, error_or_None)
    results: List[Tuple[str, Optional[str], int, int, Optional[str]]] = []
    if json_files:
        for j_file in json_files:
            try:
                j_file.seek(0)
                content = _json.load(j_file)
                updated_json, count, skipped_zero = _sync_broker_json(content, qty_map)
                results.append((j_file.name, _json.dumps(updated_json, indent=4), count, skipped_zero, None))
            except Exception as e:
                results.append((j_file.name, None, 0, 0, str(e)))
    n_templates = len(results)
    ok = sum(1 for _, p, _, _, _ in results if p is not None)
    total_updated = sum(c for _, p, c, _, _ in results if p is not None)
    total_skipped_zero = sum(s for _, p, _, s, _ in results if p is not None)

    # This tab re-runs on every widget interaction, and re-logging an unchanged
    # result on each one would drown the run trace it sits under. The fingerprint
    # makes the log fire on a CHANGE — a new upload, a different book — which is
    # the only time there is something new to say.
    if results:
        _sync_print = (tuple(sorted((f, c, s, e is not None) for f, _, c, s, e in results)),
                       tradable)
        if st.session_state.get("_broker_sync_logged") != _sync_print:
            st.session_state["_broker_sync_logged"] = _sync_print
            with log.task("Broker sync",
                          f"{n_templates} template(s) · {tradable} tradable holding(s)") as _t:
                for _fname, _payload, _count, _skipped, _err in results:
                    if _err is not None:
                        _t.item(_fname, f"FAILED — {_err}")
                    else:
                        _t.item(_fname, f"{_count} instrument(s) updated"
                                        + (f" · {_skipped} matched at zero units, left untouched"
                                           if _skipped else ""))
                if ok == n_templates:
                    _t.ok(f"{total_updated} instrument(s) written across {ok} template(s)"
                          + (f" · {total_skipped_zero} skipped at zero units"
                             if total_skipped_zero else ""))
                else:
                    _t.warn(f"{ok} of {n_templates} template(s) synced · "
                            f"{n_templates - ok} failed")

    with col1:
        if n_templates == 0:
            render_interpretation_card(
                title="AWAITING TEMPLATES",
                body=(
                    f"Curated book holds <strong>{tradable}</strong> tradable holding(s). "
                    "Upload one or more broker order-template JSONs (e.g. Kite "
                    "<strong>ETF.json</strong>) to sync their quantities."
                ),
                color="info",
            )
        elif ok == 0:
            render_interpretation_card(
                title="NO FILES SYNCED",
                body=(
                    f"None of the <strong>{n_templates}</strong> uploaded template(s) could be "
                    "processed. Check that each is a valid broker order JSON."
                ),
                color="danger",
            )
        else:
            _skip_note = (
                f" <strong>{total_skipped_zero}</strong> matched instrument(s) left untouched "
                "(curated at 0 units)."
                if total_skipped_zero > 0 else ""
            )
            render_interpretation_card(
                title="READY TO EXPORT",
                body=(
                    f"Synced <strong>{ok}/{n_templates}</strong> template(s) · "
                    f"<strong>{total_updated}</strong> instrument(s) updated from "
                    f"<strong>{tradable}</strong> tradable holding(s).{_skip_note} "
                    "Download the import-ready files on the right."
                ),
                color="success",
            )

        st.file_uploader(
            "Upload broker JSON templates",
            type=["json"],
            accept_multiple_files=True,
            help="Your original broker order files (e.g. ETF.json). Each instrument's "
                 "quantity is set from the curated units for its trading symbol.",
            key="broker_sync_json_uploader",
            label_visibility="collapsed",
        )

    with col2:
        # The same table primitive as the holdings book. This was a third
        # hand-rolled <table> with its own column widths and per-cell inline
        # colours — the app's third table system, on the one page whose output
        # goes to a broker.
        if n_templates == 0:
            render_empty_state(
                "No templates uploaded",
                "Upload one or more broker order-template JSONs to map curated units "
                "onto their instruments.",
                action_label="Kite exports one file per basket, e.g. ETF.json",
            )
        else:
            _rows = []
            for fname, payload, count, skipped_zero, err in results:
                if err is not None:
                    _rows.append({"Template": fname, "Updated": np.nan, "Status": "ERROR"})
                    continue
                # Distinguish "matched nothing at all" from "matched, but every
                # match was a 0-unit holding left untouched" — the old NO MATCH
                # label conflated both (see AUDIT_DIRECTIVES.md B8).
                if count > 0:
                    status = "SYNCED"
                elif skipped_zero > 0:
                    status = f"SKIPPED · {skipped_zero} @ 0 units"
                else:
                    status = "NO MATCH"
                _rows.append({"Template": fname, "Updated": float(count), "Status": status})
            render_table_panel(
                pd.DataFrame(_rows), "sync-results",
                context=f"{ok} of {n_templates} template(s) synced",
                show_index=False, label_col="Template",
                col_precision={"Updated": 0},
                max_height=360,
            )

            for fname, payload, count, skipped_zero, err in results:
                if payload is not None:
                    st.download_button(
                        label=f"Download updated {fname}",
                        data=payload,
                        file_name=f"updated_{fname}",
                        mime="application/json",
                        use_container_width=True,
                        key=f"broker_sync_dl_{fname}",
                    )

    # ── Full-width METHOD card (Obsidian Quant fidelity) — mirrors the
    #    Intelligence tab's method card: header + pill + lede + tile grid.
    method_html = (
        '<div class="intel-method-card">'
            '<div class="intel-method-header">'
                '<div class="intel-method-title">How the Sync Works</div>'
                '<div class="intel-method-pill">'
                'symbol → units → params.quantity'
                '</div>'
            '</div>'
            '<div class="intel-method-lede">'
                'The Broker Sync closes the loop from a curated book to broker execution. '
                'It reads the <strong>live curated portfolio</strong> directly — no CSV '
                're-upload — and writes each holding\'s unit count into the matching '
                'instrument of every broker order template you upload.'
            '</div>'
            '<div class="intel-method-grid">'

                '<div class="intel-method-tile tile-learns">'
                    '<div class="tile-label">Source</div>'
                    '<div class="tile-body">'
                        'The live curated portfolio in memory — its <code>symbol</code> and '
                        '<code>units</code> columns, exactly as shown in the Portfolio tab. '
                        'Nothing to export or re-import.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-how">'
                    '<div class="tile-label">Mapping</div>'
                    '<div class="tile-body">'
                        'For each instrument in a template, if its '
                        '<code>instrument.tradingsymbol</code> matches a curated holding, '
                        'that holding\'s units are written to <code>params.quantity</code>.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-obj">'
                    '<div class="tile-label">Templates</div>'
                    '<div class="tile-body">'
                        'Standard broker order JSONs (e.g. Kite <code>ETF.json</code>). '
                        'Upload as many as you like; each is synced and offered as a '
                        'separate <code>updated_*</code> download.'
                    '</div>'
                '</div>'

                '<div class="intel-method-tile tile-safety">'
                    '<div class="tile-label">Safety</div>'
                    '<div class="tile-body">'
                        'Non-destructive: instruments with no matching holding, or matching a '
                        'holding curated at <strong>0 units</strong>, are left '
                        '<strong>untouched</strong> rather than zeroed out — and the original '
                        'files are never modified, you download fresh copies.'
                    '</div>'
                '</div>'

            '</div>'
        '</div>'
    )
    st.markdown(method_html, unsafe_allow_html=True)
