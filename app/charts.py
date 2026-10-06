"""Hand-rolled inline SVG chart helpers - no JS charting library, no
external assets, so the dashboard stays fast and works fully offline."""


def bar_chart_svg(labels: list[str], values: list[float], width: int = 640, height: int = 220, unit: str = "") -> str:
    if not labels:
        return '<div class="empty-state"><p>No data yet for this period.</p></div>'

    padding_left = 46
    padding_bottom = 28
    padding_top = 14
    padding_right = 14
    chart_w = width - padding_left - padding_right
    chart_h = height - padding_top - padding_bottom

    max_val = max(values) if max(values) > 0 else 1
    n = len(values)
    gap = 10
    bar_w = max((chart_w - gap * (n - 1)) / n, 4) if n else 0

    bars = []
    for i, (label, val) in enumerate(zip(labels, values)):
        bar_h = (val / max_val) * chart_h if max_val else 0
        x = padding_left + i * (bar_w + gap)
        y = padding_top + (chart_h - bar_h)
        bars.append(
            f'<rect class="chart-bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="2">'
            f"<title>{label}: {val:g} {unit}</title></rect>"
        )
        bars.append(
            f'<text class="chart-label" x="{x + bar_w / 2:.1f}" y="{height - padding_bottom + 14}" text-anchor="middle">{label}</text>'
        )
        bars.append(
            f'<text class="chart-label" x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle">{val:g}</text>'
        )

    axis = (
        f'<line class="chart-axis" x1="{padding_left}" y1="{padding_top + chart_h}" '
        f'x2="{padding_left + chart_w}" y2="{padding_top + chart_h}" />'
    )

    return (
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img">'
        f"{axis}{''.join(bars)}</svg>"
    )


def horizontal_bar_svg(labels: list[str], values: list[float], width: int = 640, unit: str = "") -> str:
    if not labels:
        return '<div class="empty-state"><p>No data yet.</p></div>'

    row_h = 26
    padding_left = 4
    label_w = 150
    height = row_h * len(labels) + 10
    max_val = max(values) if max(values) > 0 else 1
    bar_area = width - label_w - 70

    rows = []
    for i, (label, val) in enumerate(zip(labels, values)):
        y = i * row_h + 6
        bar_w = (val / max_val) * bar_area if max_val else 0
        short_label = (label[:20] + "...") if len(label) > 22 else label
        rows.append(
            f'<text class="chart-label" x="{padding_left}" y="{y + 14}" font-size="12" fill="#1a2433">{short_label}</text>'
            f'<rect class="chart-bar" x="{label_w}" y="{y}" width="{bar_w:.1f}" height="16" rx="2">'
            f"<title>{label}: {val:g} {unit}</title></rect>"
            f'<text class="chart-label" x="{label_w + bar_w + 6:.1f}" y="{y + 13}">{val:g}</text>'
        )

    return (
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img">'
        f"{''.join(rows)}</svg>"
    )
