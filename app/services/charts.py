from __future__ import annotations

from io import BytesIO
from decimal import Decimal

from app.domain.schemas import PriceHistoryContext

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None
    ImageFont = None


def build_price_history_chart(
    *,
    context: PriceHistoryContext,
    current_price: Decimal,
    currency: str,
) -> bytes | None:
    if Image is None or len(context.points) < 2:
        return None

    width, height = 920, 420
    padding_left, padding_top, padding_right, padding_bottom = 56, 68, 32, 52
    chart_width = width - padding_left - padding_right
    chart_height = height - padding_top - padding_bottom

    image = Image.new("RGB", (width, height), "#f7fafc")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(22)
    body_font = _load_font(14)
    supports_cyrillic = getattr(title_font, "supports_cyrillic", False)
    title_text = "История цены" if supports_cyrillic else "Price history"
    subtitle_text = "По истории наблюдений бота" if supports_cyrillic else "Bot observations"
    min_label = "Минимум" if supports_cyrillic else "Min"
    now_label = "Сейчас" if supports_cyrillic else "Now"

    prices = [float(point.price_amount) for point in context.points] + [float(current_price)]
    min_price = min(prices)
    max_price = max(prices)
    if max_price == min_price:
        max_price += 1.0

    draw.rounded_rectangle((18, 18, width - 18, height - 18), radius=22, fill="#ffffff", outline="#d9e2ec", width=2)
    draw.text((padding_left, 26), title_text, fill="#102a43", font=title_font)
    draw.text((padding_left, 52), subtitle_text, fill="#486581", font=body_font)

    for idx in range(4):
        y = padding_top + idx * (chart_height / 3)
        draw.line((padding_left, y, width - padding_right, y), fill="#e9eef5", width=1)

    def project_x(index: int) -> float:
        if len(context.points) == 1:
            return padding_left + chart_width / 2
        return padding_left + (chart_width * index / (len(context.points) - 1))

    def project_y(price: float) -> float:
        ratio = (price - min_price) / (max_price - min_price)
        return padding_top + chart_height - ratio * chart_height

    line_points = [(project_x(index), project_y(float(point.price_amount))) for index, point in enumerate(context.points)]
    draw.line(line_points, fill="#2f855a", width=4)

    for x, y in line_points:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#2f855a")

    current_x = line_points[-1][0]
    current_y = project_y(float(current_price))
    draw.line((padding_left, current_y, width - padding_right, current_y), fill="#ef476f", width=2)
    draw.ellipse((current_x - 5, current_y - 5, current_x + 5, current_y + 5), fill="#ef476f")

    min_point = min(line_points, key=lambda point: point[1])
    draw.ellipse((min_point[0] - 5, min_point[1] - 5, min_point[0] + 5, min_point[1] + 5), fill="#1f6feb")

    draw.text(
        (padding_left, height - 34),
        f"{min_label}: {_format_money(context.min_price)} {currency}",
        fill="#1f6feb",
        font=body_font,
    )
    draw.text(
        (width - 240, height - 34),
        f"{now_label}: {_format_money(current_price)} {currency}",
        fill="#ef476f",
        font=body_font,
    )

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _format_money(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def _load_font(size: int):
    if ImageFont is None:  # pragma: no cover
        return None

    font_candidates = ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    for candidate in font_candidates:
        try:
            font = ImageFont.truetype(candidate, size=size)
            setattr(font, "supports_cyrillic", True)
            return font
        except OSError:
            continue

    font = ImageFont.load_default()
    setattr(font, "supports_cyrillic", False)
    return font
