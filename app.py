"""
傾青景觀設計 — Facebook 貼文自動產生器
使用 Groq API（免費）+ Pollinations AI（免費）
.env 需要：GROQ_API_KEY=你的金鑰
"""

import os, io, re, base64, textwrap, urllib.parse
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
from groq import Groq
from PIL import Image, ImageDraw, ImageFont

load_dotenv()
app = Flask(__name__)
OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

BRAND_SYSTEM = """你是傾青景觀設計的社群媒體文案編輯。
傾青是一家台灣的景觀設計公司，風格融合植栽美學與人文藝術，語氣自然、專業但親切，
像一位懂植物的朋友在分享生活。
寫 Facebook 貼文時請遵守：
- 繁體中文，語氣輕鬆但有質感
- 150～220 字之間
- 適當使用 1～3 個表情符號（不要過多）
- 結尾加上 3～5 個 hashtag（以 #傾青景觀設計 開頭）
- 不要用過度行銷的語氣"""

TONE_MAP = {
    "自然親切": "語氣自然、像朋友聊天，輕鬆但有質感",
    "專業知識": "語氣專業、有條理，像專家在分享知識",
    "文藝詩意": "語氣偏文藝、帶點詩意和意境，像散文一樣有畫面感",
    "活潑有趣": "語氣活潑、帶點幽默，容易引起互動和分享",
    "溫暖故事": "語氣溫暖、帶有情感，像在說一個小故事，引起共鳴",
}

FONT_MAP = {
    "正黑體": [
        r"C:\Windows\Fonts\msjhbd.ttc", r"C:\Windows\Fonts\msjh.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
    ],
    "標楷體": [
        r"C:\Windows\Fonts\kaiu.ttf",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ],
    "細明體": [
        r"C:\Windows\Fonts\mingliu.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ],
    "新細明體": [
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ],
}


def get_groq_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("找不到 GROQ_API_KEY，請確認 .env 檔案")
    return Groq(api_key=key)


def hex_to_rgba(h, a=255):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def load_font(style, size):
    for fp in FONT_MAP.get(style, FONT_MAP["正黑體"]):
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate-script", methods=["POST"])
def generate_script():
    try:
        data = request.get_json()
        topic = data.get("topic", "").strip()
        post_type = data.get("post_type", "植栽分享")
        tone = data.get("tone", "自然親切")
        if not topic:
            return jsonify({"error": "請輸入主題"}), 400
        tone_desc = TONE_MAP.get(tone, TONE_MAP["自然親切"])
        client = get_groq_client()
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": BRAND_SYSTEM},
                {"role": "user", "content": f"貼文類型：{post_type}\n語氣風格：{tone_desc}\n主題：{topic}"},
            ],
            max_tokens=1024,
        )
        return jsonify({"script": resp.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": f"文案產生失敗：{str(e)}"}), 500


@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.get_json()
        topic = data.get("topic", "").strip()
        if not topic:
            return jsonify({"error": "請輸入主題"}), 400
        client = get_groq_client()
        pr = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": (
                f"Write an English image generation prompt in 50 words or less. "
                f"Style: Taiwan landscape design, natural light photography, plant aesthetics, "
                f"muted natural colors, professional photography, no text. Topic: {topic}. "
                f"Output only the prompt."
            )}],
            max_tokens=100,
        )
       image_prompt = pr.choices[0].message.content.strip()
        encoded = urllib.parse.quote(image_prompt)
        import requests as _req, time as _time
        img_bytes = None
        for attempt in range(3):
            try:
                url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&seed={attempt*7}"
                img_resp = _req.get(url, timeout=90)
                if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                    img_bytes = img_resp.content
                    break
            except Exception:
                pass
            if attempt < 2:
                _time.sleep(3)
        if not img_bytes:
            return jsonify({"error": "圖片生成失敗，請再試一次（Pollinations 服務不穩定）"}), 500
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (OUTPUT_DIR / f"generated_{timestamp}.png").write_bytes(img_bytes)
        return jsonify({
            "image_b64": "data:image/png;base64," + base64.b64encode(img_bytes).decode(),
            "image_prompt": image_prompt,
        })
    except Exception as e:
        return jsonify({"error": f"圖片產生失敗：{str(e)}"}), 500


@app.route("/add-overlay", methods=["POST"])
def add_overlay():
    try:
        data = request.get_json()
        image_b64    = data.get("image_b64", "")
        overlay_text = data.get("overlay_text", "").strip()
        position     = data.get("position", "bottom")
        font_size_pct= int(data.get("font_size_pct", 50))   # 1~100
        font_style   = data.get("font_style", "正黑體")
        text_color   = data.get("text_color", "#FFFCEB")
        bg_style     = data.get("bg_style", "漸層")          # 漸層 / 半透明 / 無背景

        if not image_b64 or not overlay_text:
            return jsonify({"error": "缺少圖片或文字"}), 400

        _, encoded = image_b64.split(",", 1)
        img = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
        W, H = img.size

        # 清除 emoji
        clean = re.sub(r'[^ -　一-鿿㐀-䶿＀-￯　-〿\w\s，。！？、：；「」（）【】—…·\-]', '', overlay_text).strip()
        if not clean:
            clean = overlay_text

        font_size = max(20, int(W * (0.02 + 0.07 * font_size_pct / 100)))
        font = load_font(font_style, font_size)
        txt_color = hex_to_rgba(text_color)

        chars_per_line = max(5, int(W / (font_size * 1.1)))
        lines = "\n".join(textwrap.wrap(clean, width=chars_per_line)).split("\n")
        line_h = int(font_size * 1.4)
        block_h = line_h * len(lines) + 50
        grad_h = block_h + 100

        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)

        # 背景
        if bg_style == "漸層":
            if position == "top":
                for y in range(grad_h):
                    draw.line([(0,y),(W,y)], fill=(15,15,10, int(180*(1-y/grad_h))))
                ty = 30
            elif position == "center":
                cy = H // 2
                for y in range(grad_h):
                    draw.line([(0, cy-grad_h//2+y),(W, cy-grad_h//2+y)],
                              fill=(15,15,10, int(160*(1-abs(y-grad_h//2)/(grad_h//2+1)))))
                ty = cy - block_h//2
            else:
                for y in range(grad_h):
                    draw.line([(0, H-grad_h+y),(W, H-grad_h+y)], fill=(15,15,10, int(190*y/grad_h)))
                ty = H - block_h - 15
        elif bg_style == "半透明":
            pad = 24
            if position == "top":
                draw.rectangle([(0,0),(W,block_h+pad*2)], fill=(15,15,10,170))
                ty = pad
            elif position == "center":
                cy = H//2
                draw.rectangle([(0,cy-block_h//2-pad),(W,cy+block_h//2+pad)], fill=(15,15,10,170))
                ty = cy - block_h//2
            else:
                draw.rectangle([(0,H-block_h-pad*2),(W,H)], fill=(15,15,10,170))
                ty = H - block_h - pad
        else:  # 無背景
            ty = {"top":30,"center":H//2-block_h//2}.get(position, H-block_h-15)

        # 文字
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0,0), line, font=font)
            x = (W - (bbox[2]-bbox[0])) // 2
            y = ty + i * line_h
            for dx, dy in [(-2,-2),(2,-2),(-2,2),(2,2),(0,2),(2,0)]:
                draw.text((x+dx, y+dy), line, font=font, fill=(0,0,0,140))
            draw.text((x, y), line, font=font, fill=txt_color)

        result = Image.alpha_composite(img, layer).convert("RGB")
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (OUTPUT_DIR / f"overlay_{timestamp}.png").write_bytes(buf.getvalue())

        return jsonify({"image_b64": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()})
    except Exception as e:
        return jsonify({"error": f"疊加失敗：{str(e)}"}), 500


@app.route("/download/<filename>")
def download(filename):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return "找不到檔案", 404
    return send_file(str(path), as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_ENV") != "production"
    print("🌿 傾青 FB 貼文產生器啟動中...")
    if debug:
        print(f"   請開啟瀏覽器前往 http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
