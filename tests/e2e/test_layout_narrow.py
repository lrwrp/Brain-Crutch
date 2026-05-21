"""End-to-end: narrow viewport doesn't hide the clock.

Regression for the clock-disappears-on-horizontal-scroll bug. With viewport
< layout-min-width the body scrolls horizontally; the topbar is
``position: fixed`` and must stay anchored to the viewport's top-left.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_clock_stays_anchored_when_page_scrolls_horizontally(page, live_server):
    # 600 px is narrower than the layout's minimum (420 + 320 + gaps + padding
    # ≈ 800 px), forcing a horizontal scrollbar.
    page.set_viewport_size({"width": 600, "height": 800})
    page.goto(live_server.url)

    # Clock starts at viewport (24, 18). getBoundingClientRect returns
    # viewport-relative coordinates, which is exactly what we want here.
    initial = page.evaluate(
        "document.getElementById('clock').getBoundingClientRect().toJSON()"
    )
    assert initial["x"] == pytest.approx(24, abs=1)
    assert initial["y"] == pytest.approx(18, abs=1)

    # Scroll horizontally 200 px.
    page.evaluate("window.scrollTo(200, 0)")
    page.wait_for_function("window.scrollX > 100")

    # Topbar is position: fixed → clock remains at the same viewport coords.
    after = page.evaluate(
        "document.getElementById('clock').getBoundingClientRect().toJSON()"
    )
    assert after["x"] == pytest.approx(24, abs=1), (
        f"clock x drifted to {after['x']} after horizontal scroll"
    )
    assert after["y"] == pytest.approx(18, abs=1)
