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

AZUL   = (3,  18,  173)
VERM   = (185, 22,  33)
VERM_S = (100, 10,  15)
BRANCO = (255, 255, 255)
VERDE  = (28,  155,  50)
AMARELO = (255, 220, 0)

IMPACT         = '/usr/share/fonts/truetype/msttcorefonts/Impact.ttf'
HELVETICA      = '/usr/share/fonts/truetype/msttcorefonts/Arial.ttf'
HELVETICA_BOLD = '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'

if not os.path.exists(IMPACT):
    IMPACT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
if not os.path.exists(HELVETICA):
    HELVETICA = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
if not os.path.exists(HELVETICA_BOLD):
    HELVETICA_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def fnt(path, size):
    try:    return ImageFont.truetype(path, size)
    except: return ImageFont.load_default()

def gerar_criativo(foto_bytes, dados):
    t = Image.open(TEMPLATE_PATH).convert('RGBA')

    foto = Image.open(io.BytesIO(foto_bytes)).convert('RGBA')
    foto.thumbnail((FW, FH), Image.LANCZOS)
    c = Image.new('RGBA', (FW, FH), (0,0,0,0))
    c.paste(foto, ((FW-foto.width)//2, (FH-foto.height)//2), foto)
    t.paste(c, (FOTO_X1, FOTO_Y1), c)

    ov = Image.new('RGBA', t.size, (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    d.rectangle([0, RODAPE_Y, TW, TH], fill=(*AZUL, 255))

    m = 22; y = RODAPE_Y + 18

    # Nome do produto — mesmo estilo original (Impact 42px)
    nome = dados.get('nomeProduto', '').upper()
    d.text((m+2,y+2), nome, font=fnt(IMPACT,42), fill=(0,0,80))
    d.text((m,y),     nome, font=fnt(IMPACT,42), fill=BRANCO)
    y += 48

    sub = dados.get('subtitulo', '')
    if sub:
        d.text((m,y), sub.upper(), font=fnt(HELVETICA_BOLD,24), fill=BRANCO)
        y += 30

    modelo = dados.get('modelo', '')
    if modelo:
        d.text((m,y), modelo.upper(), font=fnt(HELVETICA_BOLD,24), fill=BRANCO)
        y += 30
    y += 4

    badges = dados.get('badges', [])
    bx = m
    for b in badges[:4]:
        f_b = fnt(HELVETICA_BOLD, 22)
        bb  = d.textbbox((0,0), b, font=f_b)
        bw  = bb[2]-bb[0]+16
        d.rounded_rectangle([bx,y,bx+bw,y+32], radius=6, fill=VERDE)
        d.text((bx+8, y+5), b, font=f_b, fill=BRANCO)
        bx += bw+8

    # ── OVAL VERMELHO — mesmas dimensões e posições originais ────────
    OX1,OY1 = 460, RODAPE_Y+8
    OX2,OY2 = 928, RODAPE_Y+152
    RAIO=50; OCX=(OX1+OX2)//2; OCY=(OY1+OY2)//2

    d.rounded_rectangle([OX1+10,OY1+10,OX2+10,OY2+10], radius=RAIO, fill=VERM_S)
    d.rounded_rectangle([OX1,OY1,OX2,OY2], radius=RAIO, fill=VERM)

    # "12X" no topo — mesmo tamanho do "NO PIX" original (Impact 28px), centralizado
    parcelas_str = dados.get('parcelas', '12X SEM JUROS')
    num_parc = parcelas_str.split('X')[0].strip()
    txt_12x = num_parc + 'X'
    f_12x = fnt(IMPACT, 28)
    bb_12x = d.textbbox((0,0), txt_12x, font=f_12x)
    d.text((OX2-(bb_12x[2]-bb_12x[0])-18, OY1+10), txt_12x, font=f_12x, fill=BRANCO)

    # "R$" pequeno — posição idêntica ao original
    d.text((OX1+18, OCY-18), 'R$', font=fnt(IMPACT,32), fill=BRANCO)

    # Preço da parcela grande — Impact 108px, mesma posição do original
    f_big   = fnt(IMPACT,108)
    inteiro = dados.get('preco','0')
    bb_i    = d.textbbox((0,0), inteiro, font=f_big)
    iw      = bb_i[2]-bb_i[0]
    ix = OX1+90; iy = OY1-8
    d.text((ix+3,iy+3), inteiro, font=f_big, fill=VERM_S)
    d.text((ix,iy),     inteiro, font=f_big, fill=BRANCO)

    # Centavos — Impact 54px, mesma posição original
    cents = f",{dados.get('centavos','00')}"
    f_c   = fnt(IMPACT,54)
    d.text((ix+iw+2, OY1+6), cents, font=f_c, fill=VERM_S)
    d.text((ix+iw,   OY1+4), cents, font=f_c, fill=BRANCO)

    # "SEM JUROS" no lugar do "NO PIX" — amarelo, mesmo tamanho
    f_sj   = fnt(IMPACT, 28)
    bb_sj  = d.textbbox((0,0), 'SEM JUROS', font=f_sj)
    d.text((OX1+18, OCY+6), 'SEM JUROS', font=f_sj, fill=AMARELO)

    # Abaixo do oval: preço à vista — mesmo estilo/posição do texto de parcelas original
    preco_vista = dados.get('precoOriginal', '')
    if preco_vista:
        txt_vista = f'R${preco_vista} À VISTA'
        f_12  = fnt(IMPACT, 34)
        bb12  = d.textbbox((0,0), txt_vista, font=f_12)
        d.text((OCX-(bb12[2]-bb12[0])//2, OY2+12), txt_vista, font=f_12, fill=BRANCO)

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
        dados = {
            'nomeProduto':   request.form.get('nomeProduto', ''),
            'subtitulo':     request.form.get('subtitulo', ''),
            'modelo':        request.form.get('modelo', ''),
            'preco':         request.form.get('preco', '0'),
            'centavos':      request.form.get('centavos', '00'),
            'precoOriginal': request.form.get('precoOriginal', ''),
            'parcelas':      request.form.get('parcelas', '12X SEM JUROS'),
            'badges':        request.form.getlist('badges'),
        }
        if not dados['badges'] and request.form.get('badgesStr'):
            dados['badges'] = [b.strip() for b in request.form.get('badgesStr','').split(',')]

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

        prompt     = request.form.get('prompt', 'Product showcase video, smooth camera movement, professional lighting')
        foto_bytes = foto_file.read()
        ext        = foto_file.filename.rsplit('.', 1)[-1].lower() if foto_file.filename else 'jpg'
        mime       = 'image/png' if ext == 'png' else 'image/jpeg'
        b64        = base64.b64encode(foto_bytes).decode()
        data_url   = f"data:{mime};base64,{b64}"

        output = replicate.run(
            "wavespeedai/wan-2.1-i2v-480p",
            input={
                "image":             data_url,
                "prompt":            prompt,
                "num_frames":        81,
                "sample_steps":      20,
                "frames_per_second": 16,
                "aspect_ratio":      "9:16"
            }
        )

        video_url = str(output) if isinstance(output, str) else (output[0] if output else None)
        if not video_url:
            return jsonify({'erro': 'Replicate não retornou vídeo'}), 500

        r = req_lib.get(video_url, timeout=120)
        r.raise_for_status()
        buf = io.BytesIO(r.content); buf.seek(0)
        return send_file(buf, mimetype='video/mp4', download_name='video.mp4')

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
