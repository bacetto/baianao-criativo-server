from flask import Flask, request, jsonify, send_file
import os, io, base64, requests as req_lib
from PIL import Image, ImageDraw, ImageFont
import replicate

app = Flask(__name__)

ASSETS_DIR    = os.path.join(os.path.dirname(__file__), 'assets')
TEMPLATE_PATH = os.path.join(ASSETS_DIR, 'template-oferta.png')

TW, TH    = 941, 1672
RODAPE_Y  = 1248
FOTO_X1, FOTO_Y1, FOTO_X2, FOTO_Y2 = 100, 314, 827, 1239
FW, FH    = FOTO_X2 - FOTO_X1, FOTO_Y2 - FOTO_Y1

AZUL    = (3,   18,  173)
VERM    = (185,  22,   33)
VERM_S  = (100,  10,   15)
BRANCO  = (255, 255,  255)
VERDE   = (28,  155,   50)

IMPACT         = '/usr/share/fonts/truetype/msttcorefonts/Impact.ttf'
HELVETICA_BOLD = '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'
if not os.path.exists(IMPACT):
    IMPACT         = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
if not os.path.exists(HELVETICA_BOLD):
    HELVETICA_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def fnt(path, size):
    try:    return ImageFont.truetype(path, size)
    except: return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    """Quebra texto em linhas que cabem em max_width."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = ' '.join(current + [word])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] > max_width and current:
            lines.append(' '.join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(' '.join(current))
    return lines

def gerar_criativo(foto_bytes, dados):
    t = Image.open(TEMPLATE_PATH).convert('RGBA')

    # Foto crop-to-fill — preenche o frame sem deixar espaço em branco
    foto = Image.open(io.BytesIO(foto_bytes)).convert('RGBA')
    ratio = max(FW / foto.width, FH / foto.height)
    nw, nh = int(foto.width * ratio), int(foto.height * ratio)
    foto = foto.resize((nw, nh), Image.LANCZOS)
    cx, cy = (nw - FW) // 2, (nh - FH) // 2
    foto = foto.crop((cx, cy, cx + FW, cy + FH))
    t.paste(foto, (FOTO_X1, FOTO_Y1), foto)

    ov = Image.new('RGBA', t.size, (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    d.rectangle([0, RODAPE_Y, TW, TH], fill=(*AZUL, 255))

    COLW = 440   # largura da coluna esquerda
    m    = 18    # margem esquerda
    y    = RODAPE_Y + 14

    # ── NOME — word-wrap em linhas grandes (Impact 54px) ─────────────
    nome = dados.get('nomeProduto', '').upper()
    f_nome = fnt(IMPACT, 54)
    lines  = wrap_text(d, nome, f_nome, COLW - m)
    if len(lines) > 3:          # se não couber em 3 linhas, reduz fonte
        f_nome = fnt(IMPACT, 40)
        lines  = wrap_text(d, nome, f_nome, COLW - m)

    for line in lines[:3]:
        d.text((m + 2, y + 2), line, font=f_nome, fill=(0, 0, 80))
        d.text((m,     y),     line, font=f_nome, fill=BRANCO)
        bb = d.textbbox((0, 0), line, font=f_nome)
        y += (bb[3] - bb[1]) + 2
    y += 6

    # ── MODELO — Impact 30px ─────────────────────────────────────────
    modelo = dados.get('modelo', '')
    if modelo:
        f_mod = fnt(IMPACT, 30)
        d.text((m, y), modelo.upper(), font=f_mod, fill=BRANCO)
        bb = d.textbbox((0, 0), modelo.upper(), font=f_mod)
        y += (bb[3] - bb[1]) + 8

    y += 4

    # ── BADGES — pills verdes ─────────────────────────────────────────
    badges = dados.get('badges', [])
    bx = m
    f_b = fnt(HELVETICA_BOLD, 20)
    for b in badges[:4]:
        bb = d.textbbox((0, 0), b, font=f_b)
        bw = bb[2] - bb[0] + 18
        if bx + bw > COLW:
            bx = m; y += 34
        d.rounded_rectangle([bx, y, bx + bw, y + 30], radius=6, fill=VERDE)
        d.text((bx + 9, y + 5), b, font=f_b, fill=BRANCO)
        bx += bw + 8

    # ── OVAL VERMELHO ─────────────────────────────────────────────────
    OX1, OY1 = 455, RODAPE_Y + 8
    OX2, OY2 = 926, RODAPE_Y + 156
    RAIO = 52
    OCX  = (OX1 + OX2) // 2
    OCY  = (OY1 + OY2) // 2

    d.rounded_rectangle([OX1 + 8, OY1 + 8, OX2 + 8, OY2 + 8], radius=RAIO, fill=VERM_S)
    d.rounded_rectangle([OX1,     OY1,      OX2,     OY2     ], radius=RAIO, fill=VERM)

    # "12X" — topo esquerda do oval
    parcelas_str = dados.get('parcelas', '12X SEM JUROS')
    num_parc     = parcelas_str.split('X')[0].strip()
    f_12x        = fnt(IMPACT, 26)
    d.text((OX1 + 14, OY1 + 10), num_parc + 'X', font=f_12x, fill=BRANCO)

    # "RS" — esquerda, alinhado com o número grande
    f_rs = fnt(IMPACT, 28)
    d.text((OX1 + 12, OCY - 12), 'RS', font=f_rs, fill=BRANCO)

    # Número grande — Impact 100px
    f_big   = fnt(IMPACT, 100)
    inteiro = dados.get('preco', '0')
    bb_i    = d.textbbox((0, 0), inteiro, font=f_big)
    iw      = bb_i[2] - bb_i[0]
    ix, iy  = OX1 + 78, OY1 - 4
    d.text((ix + 3, iy + 3), inteiro, font=f_big, fill=VERM_S)
    d.text((ix,     iy),     inteiro, font=f_big, fill=BRANCO)

    # Centavos — Impact 50px
    cents = f",{dados.get('centavos','00')}"
    f_c   = fnt(IMPACT, 50)
    d.text((ix + iw + 2, OY1 + 8), cents, font=f_c, fill=VERM_S)
    d.text((ix + iw,     OY1 + 6), cents, font=f_c, fill=BRANCO)

    # "SEM JUROS" — rodapé direita do oval, branco
    f_sj  = fnt(IMPACT, 24)
    bb_sj = d.textbbox((0, 0), 'SEM JUROS', font=f_sj)
    d.text((OX2 - (bb_sj[2] - bb_sj[0]) - 14, OY2 - 32), 'SEM JUROS', font=f_sj, fill=BRANCO)

    # ── ABAIXO DO OVAL — preço NO PIX ─────────────────────────────────
    preco_pix = dados.get('precoOriginal', '')
    if preco_pix:
        f_pix   = fnt(IMPACT, 30)
        txt_pix = f'R$ {preco_pix} NO PIX'
        bb_pix  = d.textbbox((0, 0), txt_pix, font=f_pix)
        d.text((OCX - (bb_pix[2] - bb_pix[0]) // 2, OY2 + 14), txt_pix, font=f_pix, fill=BRANCO)

    res = Image.alpha_composite(t, ov)
    buf = io.BytesIO()
    res.convert('RGB').save(buf, 'JPEG', quality=95)
    buf.seek(0)
    return buf

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/gerar', methods=['POST'])
def gerar():
    try:
        foto_file = request.files.get('foto')
        if not foto_file:
            return jsonify({'erro': 'foto ausente'}), 400

        foto_bytes = foto_file.read()

        # Suporta precoParcela (form novo) OU preco/centavos (n8n)
        preco_parc_raw = request.form.get('precoParcela', '')
        if preco_parc_raw:
            pp       = preco_parc_raw.replace('R$', '').replace('.', '').strip().split(',')
            preco    = pp[0] or '0'
            centavos = (pp[1] if len(pp) > 1 else '00').ljust(2, '0')[:2]
        else:
            preco    = request.form.get('preco', '0')
            centavos = request.form.get('centavos', '00')

        # Preço PIX / à vista
        preco_pix = (request.form.get('precoVista', '') or
                     request.form.get('precoOriginal', '')).replace('R$', '').strip()

        # Parcelas
        num_parc = (request.form.get('numParcelas', '') or
                    request.form.get('parcelas', '12X SEM JUROS').split('X')[0]).strip()

        dados = {
            'nomeProduto':   request.form.get('nomeProduto', ''),
            'subtitulo':     request.form.get('subtitulo', ''),
            'modelo':        request.form.get('modelo', ''),
            'preco':         preco,
            'centavos':      centavos,
            'precoOriginal': preco_pix,
            'parcelas':      num_parc + 'X SEM JUROS',
            'badges':        request.form.getlist('badges'),
        }
        if not dados['badges'] and request.form.get('badgesStr'):
            dados['badges'] = [b.strip() for b in request.form.get('badgesStr', '').split(',') if b.strip()]

        buf = gerar_criativo(foto_bytes, dados)
        return send_file(buf, mimetype='image/jpeg', download_name='criativo.jpg')

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/gerar-video', methods=['POST'])
def gerar_video():
    try:
        foto_file = request.files.get('foto')
        if not foto_file:
            return jsonify({'erro': 'foto ausente'}), 400

        prompt     = request.form.get('prompt', 'Product showcase video, smooth camera movement')
        foto_bytes = foto_file.read()
        ext        = foto_file.filename.rsplit('.', 1)[-1].lower() if foto_file.filename else 'jpg'
        mime       = 'image/png' if ext == 'png' else 'image/jpeg'
        data_url   = f"data:{mime};base64,{base64.b64encode(foto_bytes).decode()}"

        output = replicate.run(
            "wavespeedai/wan-2.1-i2v-480p",
            input={"image": data_url, "prompt": prompt, "num_frames": 81,
                   "sample_steps": 20, "frames_per_second": 16, "aspect_ratio": "9:16"}
        )
        video_url = str(output) if isinstance(output, str) else (output[0] if output else None)
        if not video_url:
            return jsonify({'erro': 'Replicate não retornou vídeo'}), 500

        r = req_lib.get(video_url, timeout=120); r.raise_for_status()
        buf = io.BytesIO(r.content); buf.seek(0)
        return send_file(buf, mimetype='video/mp4', download_name='video.mp4')

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
