"""End-to-end: narrow viewport doesn't hide the clock; date stacks.

Regression for the clock-disappears-on-horizontal-scroll bug. With viewport
< layout-min-width the body scrolls horizontally; the topbar is
``position: fixed`` and must stay anchored to the viewport's top-left.

Also covers Tier 2 #14: the date in the topbar renders as two stacked
lines — weekday on top, month + day below.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_clock_stays_anchored_when_page_scrolls_horizontally(page, live_server):
    # 760 px sits just above the 720 px mobile breakpoint, so the two-column
    # layout is still in effect — and 760 is narrower than that layout's
    # minimum (420 + 320 + gaps + padding ≈ 800 px), forcing a horizontal
    # scrollbar. (At ≤720 the layout collapses to a single column with no
    # horizontal overflow; that path is covered by test_mobile_layout.py.)
    page.set_viewport_size({"width": 760, "height": 800})
    page.goto(live_server.url)

    # Clock starts at viewport (24, 18). getBoundingClientRect returns
    # viewport-relative coordinates, which is exactly what we want here.
    initial = page.evaluate(
        "document.getElementById('clock').getBoundingClientRect().toJSON()"
    )
    assert initial["x"] == pytest.approx(24, abs=1)
    assert initial["y"] == pytest.approx(18, abs=1)

    # Scroll horizontally as far as the overflow allows (the two-column band
    # between the 720 px breakpoint and the ~806 px layout min is narrow, so
    # the request clamps to whatever overflow exists — any non-zero scroll
    # exercises the regression).
    page.evaluate("window.scrollTo(400, 0)")
    page.wait_for_function("window.scrollX > 0")

    # Topbar is position: fixed → clock remains at the same viewport coords.
    after = page.evaluate(
        "document.getElementById('clock').getBoundingClientRect().toJSON()"
    )
    assert after["x"] == pytest.approx(24, abs=1), (
        f"clock x drifted to {after['x']} after horizontal scroll"
    )
    assert after["y"] == pytest.approx(18, abs=1)


@pytest.mark.e2e
def test_topbar_date_stacks_weekday_above_month_day(page, live_server):
    """Both #date-weekday and #date-monthday exist, both render non-empty
    text, and the weekday's top edge sits above the month-day's top edge."""
    page.goto(live_server.url)

    weekday = page.locator("#date-weekday")
    monthday = page.locator("#date-monthday")
    expect(weekday).to_be_visible()
    expect(monthday).to_be_visible()
    # Both populated by main.js#tickClock on boot; the em-dash placeholder
    # in the HTML is replaced before the first paint settles.
    assert (weekday.text_content() or "").strip() not in ("", "—")
    assert (monthday.text_content() or "").strip() not in ("", "—")

    w_box = weekday.bounding_box()
    m_box = monthday.bounding_box()
    assert w_box is not None and m_box is not None
    # Weekday is the upper line; month-day sits below it.
    assert w_box["y"] < m_box["y"], (
        f"expected weekday above month-day; got weekday.y={w_box['y']}, "
        f"month-day.y={m_box['y']}"
    )
