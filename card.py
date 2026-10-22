"""Create a deterministic 1080x1350 Korean information card; no image API."""
import io
from PIL import Image, ImageDraw, ImageFont


def wrap(text, font, width):
    lines, line = [], ''
    for char in str(text):
        if char == '\n' or (line and font.getlength(line + char) > width):
            lines.append(line)
            line = '' if char == '\n' else char
        else:
            line += char
    if line:
        lines.append(line)
    return lines


def render_card(draft, font_path):
    image = Image.new('RGB', (1080, 1350), '#FAF5E9')
    draw = ImageDraw.Draw(image)
    def block(text, size, y, color='#323D2E', max_lines=3):
        font = ImageFont.truetype(font_path, size)
        lines = wrap(text, font, 900)
        if len(lines) > max_lines:
            raise ValueError('Card text too long; shorten before publishing')
        for line in lines:
            draw.text((90, y), line, font=font, fill=color)
            y += size + 18
        return y
    draw.rounded_rectangle((72, 65, 1008, 142), radius=34, fill='#E77937')
    draw.text((110, 77), draft.get('headline', '이번 주말 · 아이들과 하루 한 곳'), font=ImageFont.truetype(font_path, 33), fill='white')
    if draft.get('card_title'):
        block(draft.get('fee', ''), 52, 174, '#C2532A', 1)
        y = block(draft['card_title'], 72, 270, max_lines=3)
    else:
        y = block(draft['event'], 69, 192, max_lines=2)
    y = block(draft['dates'], 31, y + 23, '#686F58', 2)
    y = block(draft['place'], 31, y + 8, '#686F58', 2)
    draw.line((90, y + 28, 990, y + 28), fill='#D6CEBB', width=2)
    y = block('함께 해볼 활동', 36, y + 48)
    for i, item in enumerate(draft['activities'], 1):
        y = block(f'{i:02d}  {item}', 31, y + 14, max_lines=2)
    if y > 1170:
        raise ValueError('Card layout overflow')
    draw.line((90, 1214, 990, 1214), fill='#D6CEBB', width=2)
    block('@sglide_h', 30, 1240)
    draw.text((650, 1250), '행사 정보 디자인 카드', font=ImageFont.truetype(font_path, 23), fill='#777766')
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def render_slide(title, body, label, page, font_path, accent=False):
    image = Image.new("RGB", (1080, 1350), "#173F36" if accent else "#FAF5E9")
    draw = ImageDraw.Draw(image)
    fg = "#FAF5E9" if accent else "#173F36"
    muted = "#C7DAD0" if accent else "#5F7066"
    def text_block(text, top, size, bottom, color):
        while size >= 24:
            font = ImageFont.truetype(font_path, size)
            lines = wrap(text, font, 896)
            if top + len(lines)*(size+18) <= bottom:
                for line in lines:
                    draw.text((92, top), line, font=font, fill=color)
                    top += size+18
                return top
            size -= 2
        raise ValueError("Carousel slide overflow")
    draw.rounded_rectangle((90, 80, 990, 148), radius=25, fill="#E77937")
    draw.text((118, 92), label, font=ImageFont.truetype(font_path, 30), fill="white")
    text_block(title, 225, 78 if accent else 64, 710, fg)
    draw.line((92, 755, 988, 755), fill="#E77937", width=5)
    text_block(body, 805, 38, 1195, muted)
    draw.text((92, 1250), "@sglide_h", font=ImageFont.truetype(font_path, 27), fill=fg)
    draw.text((880, 1250), f"{page}/5", font=ImageFont.truetype(font_path, 27), fill=fg)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
