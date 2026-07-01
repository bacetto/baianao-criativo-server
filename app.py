from flask import Flask, request, jsonify, send_file
import os, io, re, base64, requests as req_lib
from PIL import Image, ImageDraw, ImageFont
import replicate

app = Flask(__name__)

ASSETS_DIR    = os.path.join(os.path.dirname(__file__), 'assets')
TEMPLATE_PATH = os.path.join(ASSETS_DIR, 'template-oferta.png')

TW, TH    = 941, 1672
RODAPE_Y  = 1248
RODAPE_FIM = 1585  # deixa a faixa branca do rodapé do template visível

# Área interna do quadro branco (desceu FY1 para não cobrir o logo Baianão)
FX1, FY1, FX2, FY2 = 118, 382, 808, 1222
FW, FH = FX2-FX1, FY2-FY1
FRAME_ANGLE = -2.5  # inclinação do quadro (graus)

AZUL    = (3,   18,  173)
VERM    = (185,  22,   33)
VERM_S  = (100,  10,   15)
BRANCO  = (255, 255,  255)
VERDE   = (28,  155,   50)

ARIAL_BLACK = os.path.join(ASSETS_DIR, 'ArialBlack.ttf')
IMPACT      = os.path.join(ASSETS_DIR, 'Impact.ttf')

def fnt(path, size):
    try:    return ImageFont.truetype(path, size)
    except: return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split(); lines=[]; cur=[]
    for w in words:
        test = ' '.join(cur+[w])
        bb = draw.textbbox((0,0), test, font=font)
        if bb[2]-bb[0] > max_width and cur:
            lines.append(' '.join(cur)); cur=[w]
        else: cur.append(w)
    if cur: lines.append(' '.join(cur))
    return lines

def sep_specs(nome):
    nome = nome.upper(); specs=[]
    for p in [r'\d+\s*PORTA[S]?', r'\d+\s*GAVETA[S]?', r'\d+\s*LUGAR[ES]?']:
        m = re.search(p, nome, re.I)
        if m: specs.append(m.group().strip()); nome = re.sub(p,'',nome,flags=re.I)
    return ' '.join(nome.split()), ' '.join(specs)

def gerar_criativo(foto_bytes, dados):
    t = Image.open(TEMPLATE_PATH).convert('RGBA')

    # Foto: crop-to-fill + rotação para acompanhar inclinação do quadro
    foto = Image.open(io.BytesIO(foto_bytes)).convert('RGBA')
    ratio = max(FW/foto.width, FH/foto.height) * 1.08
    nw, nh = int(foto.width*ratio), int(foto.height*ratio)
    foto = foto.resize((nw, nh), Image.LANCZOS)
    foto = foto.rotate(FRAME_ANGLE, expand=False, fillcolor=(3,18,173,255))
    cx, cy = (nw-FW)//2, (nh-FH)//2
    foto = foto.crop((cx, cy, cx+FW, cy+FH))
    t.paste(foto, (FX1, FY1))

    ov = Image.new('RGBA', t.size, (0,0,0,0))
    d  = ImageDraw.Draw(ov)
    # Cobre só a área do rodapé, deixa faixa branca final do template
    d.rectangle([0, RODAPE_Y, TW, RODAPE_FIM], fill=(*AZUL, 255))

    COLW = 455; m = 18; y = RODAPE_Y + 16

    # Nome — Arial Black, word-wrap 2 linhas grandes
    nome_raw = dados.get('nomeProduto', '').upper()
    nome_limpo, specs = sep_specs(nome_raw)
    f_ab = fnt(ARIAL_BLACK, 58)
    lines = wrap_text(d, nome_limpo, f_ab, COLW-m)
    if len(lines) > 2:
        f_ab = fnt(ARIAL_BLACK, 44)
        lines = wrap_text(d, nome_limpo, f_ab, COLW-m)
    for line in lines[:2]:
        d.text((m, y), line, font=f_ab, fill=BRANCO)
        bb = d.textbbox((0,0), line, font=f_ab); y += bb[3]-bb[1]+2
    y += 4

    # Specs
    if specs:
        f_sp = fnt(ARIAL_BLACK, 30)
        d.text((m, y), specs, font=f_sp, fill=BRANCO)
        bb = d.textbbox((0,0), specs, font=f_sp); y += bb[3]-bb[1]+8

    # Modelo
    modelo = dados.get('modelo', '')
    if modelo and modelo.upper() not in nome_raw:
        f_mod = fnt(ARIAL_BLACK, 26)
        d.text((m, y), modelo.upper(), font=f_mod, fill=BRANCO)
        bb = d.textbbox((0,0), modelo.upper(), font=f_mod); y += bb[3]-bb[1]+6

    y += 4

    # Badges
    badges = dados.get('badges', [])
    bx = m; f_b = fnt(ARIAL_BLACK, 18)
    for b in badges[:4]:
        bb = d.textbbox((0,0), b, font=f_b); bw = bb[2]-bb[0]+18
        if bx+bw > COLW: bx=m; y+=30
        d.rounded_rectangle([bx,y,bx+bw,y+28], radius=6, fill=VERDE)
        d.text((bx+9,y+5), b, font=f_b, fill=BRANCO); bx += bw+8

    # Pílula vermelha
    OX1,OY1 = 462, RODAPE_Y+12
    OX2,OY2 = 928, RODAPE_Y+162
    RAIO = 50; OCX=(OX1+OX2)//2; OCY=(OY1+OY2)//2
    d.rounded_rectangle([OX1+8,OY1+8,OX2+8,OY2+8], radius=RAIO, fill=VERM_S)
    d.rounded_rectangle([OX1,OY1,OX2,OY2], radius=RAIO, fill=VERM)

    # "R$" esquerda da pílula
    f_rs = fnt(ARIAL_BLACK, 28)
    d.text((OX1+16, OCY-16), 'R$', font=f_rs, fill=BRANCO)

    # Número grande
    f_big = fnt(IMPACT, 108)
    inteiro = dados.get('preco', '0')
    bb_i = d.textbbox((0,0), inteiro, font=f_big); iw = bb_i[2]-bb_i[0]
    ix, iy = OX1+80, OY1-6
    d.text((ix+3,iy+3), inteiro, font=f_big, fill=VERM_S)
    d.text((ix,iy),     inteiro, font=f_big, fill=BRANCO)

    # Centavos
    f_c = fnt(IMPACT, 52); cents = f",{dados.get('centavos','00')}"
    d.text((ix+iw+2, OY1+8), cents, font=f_c, fill=VERM_S)
    d.text((ix+iw,   OY1+6), cents, font=f_c, fill=BRANCO)

    # "SEM JUROS" direita
    f_sj = fnt(ARIAL_BLACK, 22)
    bb_sj = d.textbbox((0,0), 'SEM JUROS', font=f_sj)
    d.text((OX2-(bb_sj[2]-bb_sj[0])-16, OY2-34), 'SEM JUROS', font=f_sj, fill=BRANCO)

    # Preço NO PIX abaixo da pílula
    preco_pix = dados.get('precoOriginal', '')
    if preco_pix:
        f_pix = fnt(ARIAL_BLACK, 26); txt = f'R$ {preco_pix} NO PIX'
        bb_p = d.textbbox((0,0), txt, font=f_pix)
        d.text((OCX-(bb_p[2]-bb_p[0])//2, OY2+16), txt, font=f_pix, fill=BRANCO)

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

        preco_parc_raw = request.form.get('precoParcela', '')
        if preco_parc_raw:
            pp = preco_parc_raw.replace('R$','').replace('.','').strip().split(',')
            preco    = pp[0] or '0'
            centavos = (pp[1] if len(pp)>1 else '00').ljust(2,'0')[:2]
        else:
            preco    = request.form.get('preco', '0')
            centavos = request.form.get('centavos', '00')

        preco_pix = (request.form.get('precoVista','') or
                     request.form.get('precoOriginal','')).replace('R$','').strip()
        num_parc  = (request.form.get('numParcelas','') or
                     request.form.get('parcelas','12X SEM JUROS').split('X')[0]).strip()

        dados = {
            'nomeProduto':   request.form.get('nomeProduto',''),
            'subtitulo':     request.form.get('subtitulo',''),
            'modelo':        request.form.get('modelo',''),
            'preco':         preco,
            'centavos':      centavos,
            'precoOriginal': preco_pix,
            'parcelas':      num_parc+'X SEM JUROS',
            'badges':        request.form.getlist('badges'),
        }
        if not dados['badges'] and request.form.get('badgesStr'):
            dados['badges'] = [b.strip() for b in request.form.get('badgesStr','').split(',') if b.strip()]

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

        prompt     = request.form.get('prompt','Product showcase video, smooth camera movement')
        foto_bytes = foto_file.read()
        ext        = foto_file.filename.rsplit('.',1)[-1].lower() if foto_file.filename else 'jpg'
        mime       = 'image/png' if ext=='png' else 'image/jpeg'
        data_url   = f"data:{mime};base64,{base64.b64encode(foto_bytes).decode()}"

        output = replicate.run("wavespeedai/wan-2.1-i2v-480p",
            input={"image":data_url,"prompt":prompt,"num_frames":81,
                   "sample_steps":20,"frames_per_second":16,"aspect_ratio":"9:16"})
        video_url = str(output) if isinstance(output,str) else (output[0] if output else None)
        if not video_url:
            return jsonify({'erro':'Replicate não retornou vídeo'}), 500

        r = req_lib.get(video_url,timeout=120); r.raise_for_status()
        buf = io.BytesIO(r.content); buf.seek(0)
        return send_file(buf, mimetype='video/mp4', download_name='video.mp4')

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',8080)))
