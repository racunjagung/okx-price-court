#!/usr/bin/env python3
"""Build the OKX Price Court demo video (<=45s) from evidence/demo_result.json.

Renders 6 captioned slides (1280x720) with PIL — title with the three
official logos (Internet Court, GenLayer, OKX), the dispute, the validator
jury fetching OKX evidence, both verdicts, and a reproduce-it card — then
assembles them with ffmpeg (slow zoom + crossfades).

Usage: python3 build_video.py   (writes okx-price-court-demo.mp4 next to it)
"""
import json, os, subprocess, textwrap

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = "/tmp/court_video"
os.makedirs(TMP, exist_ok=True)
os.makedirs(os.path.join(TMP, "logos"), exist_ok=True)

W, H = 1280, 720
BG = (11, 14, 26)
CARD = (20, 24, 48)
BORDER = (48, 56, 102)
TEXT = (232, 235, 245)
MUTED = (154, 163, 192)
ACCENT = (139, 124, 255)
GREEN = (61, 220, 151)
RED = (255, 107, 129)
MONO_BG = (7, 9, 18)

SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def rasterize_logo(svg, name, height=92):
    out = os.path.join(TMP, "logos", name + ".png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i",
                    os.path.join(ROOT, "assets", svg),
                    "-vf", f"scale=-1:{height}", out], check=True)
    return Image.open(out).convert("RGBA")


LOGOS = {
    "tic": rasterize_logo("tic-logo-red.svg", "tic"),
    "genlayer": rasterize_logo("genlayer-logo-white-cropped.svg", "genlayer"),
    "okx": rasterize_logo("okx-mark-white.svg", "okx", height=92),
}


def logo_row(img, y, scale=1.0, cx=W // 2):
    parts = []
    for key in ("tic", "genlayer", "okx"):
        lg = LOGOS[key]
        if scale != 1.0:
            lg = lg.resize((int(lg.width * scale), int(lg.height * scale)))
        parts.append(lg)
    gap = 46
    total = sum(p.width for p in parts) + gap * (len(parts) - 1)
    x = cx - total // 2
    for p in parts:
        img.paste(p, (x, y + (92 - p.height) // 2), p)
        x += p.width + gap


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def text_block(draw, xy, text, fnt, fill, max_w, leading=1.28, align="left"):
    x, y = xy
    for line in wrap(draw, text, fnt, max_w):
        lx = x if align == "left" else x + (max_w - draw.textlength(line, font=fnt)) / 2
        draw.text((lx, y), line, font=fnt, fill=fill)
        y += fnt.size * leading
    return y


def slide_base():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def card(draw, box, fill=CARD):
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=BORDER, width=2)


def save(img, name):
    p = os.path.join(TMP, name)
    img.save(p)
    return p


def main():
    data = json.load(open(os.path.join(ROOT, "evidence", "demo_result.json")))
    c1, c2 = data["cases"]
    contract = data["contract"]["contractAddress"]
    slides = []

    # 1 — title
    img, d = slide_base()
    logo_row(img, 120)
    d.text((W // 2, 300), "OKX PRICE COURT", font=font(SANS_B, 74),
           fill=TEXT, anchor="ma")
    d.text((W // 2, 392), "An Internet Court demo on GenLayer",
           font=font(SANS, 33), fill=ACCENT, anchor="ma")
    text_block(d, (190, 452),
               "Two agents dispute a market fact. A jury of validators fetches "
               "the evidence from OKX and rules by consensus — on-chain.",
               font(SANS, 27), MUTED, 900, align="center")
    d.text((W // 2, 640), "GenLayer Studio Next testnet  ·  chainId 61997",
           font=font(MONO, 21), fill=MUTED, anchor="ma")
    slides.append(save(img, "s1.png"))

    # 2 — the dispute
    img, d = slide_base()
    d.text((70, 54), "THE DISPUTE", font=font(SANS_B, 40), fill=ACCENT)
    card(d, (70, 130, 1210, 400))
    y = text_block(d, (105, 158), c1["claim"], font(SANS, 28), TEXT, 1040)
    d.text((105, y + 18), "Agent A: “It paid out.”   Agent B: “Prove it.”",
           font=font(SANS_B, 28), fill=(255, 209, 102))
    card(d, (70, 430, 1210, 560), fill=MONO_BG)
    d.text((105, 458), "DEAL TERM  ·  BTC-USDT daily close (OKX)  ·  2026-11-19  ·  ≥ 59,000 USDT",
           font=font(MONO_B, 24), fill=TEXT)
    d.text((105, 502), "A normal smart contract cannot check this. The fact lives off-chain.",
           font=font(SANS, 24), fill=MUTED)
    d.text((70, 610), "So the case goes to the Internet Court — GenLayer validators are the jury.",
           font=font(SANS, 27), fill=TEXT)
    slides.append(save(img, "s2.png"))

    # 3 — the jury fetches OKX evidence
    img, d = slide_base()
    d.text((70, 54), "THE JURY CONVENES", font=font(SANS_B, 40), fill=ACCENT)
    for i in range(5):
        x = 70 + i * 232
        card(d, (x, 140, x + 200, 236))
        d.text((x + 100, 160), f"VALIDATOR {i + 1}", font=font(SANS_B, 21),
               fill=TEXT, anchor="ma")
        d.text((x + 100, 196), "fetch + judge", font=font(SANS, 19),
               fill=MUTED, anchor="ma")
    card(d, (70, 280, 1210, 420), fill=MONO_BG)
    d.text((100, 306), "GET okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1Dutc",
           font=font(MONO, 22), fill=(126, 231, 135))
    d.text((100, 348), 'candle 2026-11-19 (UTC) →  close 61,984.8 USDT  ·  confirm = "1"',
           font=font(MONO, 22), fill=TEXT)
    text_block(d, (70, 462),
               "Every validator renders the OKX API independently. The Equivalence "
               "Principle: the closing price and the verdict must match exactly — "
               "only the ruling's wording may differ.",
               font(SANS, 27), TEXT, 1140)
    d.text((70, 620), "No single oracle. Consensus is the judge.",
           font=font(SANS_B, 28), fill=ACCENT)
    slides.append(save(img, "s3.png"))

    # 4 — verdict case 1
    img, d = slide_base()
    d.text((70, 54), "VERDICT — CASE 001", font=font(SANS_B, 40), fill=ACCENT)
    d.text((70, 130), "CLAIM UPHELD", font=font(SANS_B, 64), fill=GREEN)
    card(d, (70, 240, 1210, 430))
    text_block(d, (105, 268), "“" + c1["final"]["ruling"] + "”",
               font(SANS, 29), TEXT, 1040)
    d.text((70, 480), "Stored on-chain · resolve tx", font=font(SANS, 24), fill=MUTED)
    d.text((70, 522), c1["resolveTx"], font=font(MONO, 21), fill=MUTED)
    d.text((70, 600), "OKX close 61,984.8 ≥ 59,000 threshold — the note pays out.",
           font=font(SANS_B, 27), fill=TEXT)
    slides.append(save(img, "s4.png"))

    # 5 — verdict case 2
    img, d = slide_base()
    d.text((70, 54), "VERDICT — CASE 002", font=font(SANS_B, 40), fill=ACCENT)
    d.text((70, 130), "CLAIM DISMISSED", font=font(SANS_B, 64), fill=RED)
    card(d, (70, 240, 1210, 430))
    text_block(d, (105, 268), "“" + c2["final"]["ruling"] + "”",
               font(SANS, 29), TEXT, 1040)
    d.text((70, 480), "Stored on-chain · resolve tx", font=font(SANS, 24), fill=MUTED)
    d.text((70, 522), c2["resolveTx"], font=font(MONO, 21), fill=MUTED)
    d.text((70, 600), "OKX close 63,070.6 < 65,000 threshold — the escrow does not settle.",
           font=font(SANS_B, 27), fill=TEXT)
    slides.append(save(img, "s5.png"))

    # 6 — reproduce
    img, d = slide_base()
    logo_row(img, 84, scale=0.8)
    d.text((W // 2, 236), "REPRODUCE IT YOURSELF", font=font(SANS_B, 42),
           fill=TEXT, anchor="ma")
    card(d, (140, 320, 1140, 470), fill=MONO_BG)
    d.text((W // 2, 348), "Contract on GenLayer Studio Next", font=font(SANS, 23),
           fill=MUTED, anchor="ma")
    d.text((W // 2, 388), contract, font=font(MONO_B, 25), fill=TEXT, anchor="ma")
    d.text((W // 2, 428), "explorer-studio-dev.genlayer.com", font=font(MONO, 21),
           fill=MUTED, anchor="ma")
    text_block(d, (190, 510),
               "Clean, documented code + a step-by-step SKILL.md in the public "
               "repository. File a case, let the validators fetch OKX evidence, "
               "read the verdict on-chain.",
               font(SANS, 26), TEXT, 900, align="center")
    d.text((W // 2, 664), "Internet Court  ×  GenLayer  ×  OKX",
           font=font(SANS_B, 24), fill=ACCENT, anchor="ma")
    slides.append(save(img, "s6.png"))

    # assemble: crossfades between slides. 6 x 7.5s - 5 x 0.5s = 42.5s.
    # (No zoompan: with -loop inputs it multiplies frames per input frame and
    # explodes the runtime — static slides + fades stay tight and clean.)
    dur, fade, fps = 7.5, 0.5, 25
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for s in slides:
        cmd += ["-loop", "1", "-t", str(dur), "-i", s]
    filt = []
    for i in range(len(slides)):
        filt.append(f"[{i}:v]fps={fps},format=yuv420p[v{i}]")
    prev = "v0"
    for i in range(1, len(slides)):
        off = dur * i - fade * i
        filt.append(f"[{prev}][v{i}]xfade=transition=fade:duration={fade}:"
                    f"offset={off:.2f}[x{i}]")
        prev = f"x{i}"
    cmd += ["-filter_complex", ";".join(filt), "-map", f"[{prev}]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            os.path.join(HERE, "okx-price-court-demo.mp4")]
    subprocess.run(cmd, check=True)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0",
                          os.path.join(HERE, "okx-price-court-demo.mp4")],
                         capture_output=True, text=True)
    print("video duration:", out.stdout.strip(), "s")


if __name__ == "__main__":
    main()
