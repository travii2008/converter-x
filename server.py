"""
Universal Converter - Flask API Backend
Deployed on Render.com
"""
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
import tempfile, subprocess, shutil, os, json, time

app = Flask(__name__)
CORS(app, origins=["https://converterx-all-in-one.web.app", "http://localhost:5000"])
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024

TEMP_DIR = Path(tempfile.gettempdir()) / "converter_api"
TEMP_DIR.mkdir(exist_ok=True)

HAS_FFMPEG=shutil.which("ffmpeg") is not None
HAS_PIL=False; HAS_PDFPLUMBER=False; HAS_DOCX=False
HAS_PDF2DOCX=False; HAS_OPENPYXL=False

try: from PIL import Image; HAS_PIL=True
except: pass
try: import pdfplumber; HAS_PDFPLUMBER=True
except: pass
try: from docx import Document; HAS_DOCX=True
except: pass
try: from pdf2docx import Converter; HAS_PDF2DOCX=True
except: pass
try: import openpyxl; HAS_OPENPYXL=True
except: pass

# ── Currency ──────────────────────────────────────────────────────────────────
CURRENCY_RATES = {}
_CACHE = Path(__file__).parent / "rates_cache.json"

def load_rates():
    global CURRENCY_RATES
    try:
        if _CACHE.exists():
            data = json.loads(_CACHE.read_text())
            if (time.time() - data.get("timestamp",0)) / 3600 < 6:
                CURRENCY_RATES = data["rates"]; return
    except: pass
    try:
        import urllib.request
        with urllib.request.urlopen(
            urllib.request.Request("https://open.er-api.com/v6/latest/USD",
            headers={"User-Agent":"ConverterX"}), timeout=10) as r:
            data = json.loads(r.read())
        if data.get("result") == "success":
            CURRENCY_RATES = data["rates"]; CURRENCY_RATES["USD"] = 1.0
            _CACHE.write_text(json.dumps({"timestamp":time.time(),"rates":CURRENCY_RATES}))
    except Exception as e:
        print(f"Currency fetch failed: {e}")

load_rates()

# ── Helpers ───────────────────────────────────────────────────────────────────
def tmp(suffix=""):
    import uuid
    return TEMP_DIR / (str(uuid.uuid4())[:8] + suffix)

def ffmpeg(args, timeout=300):
    if not HAS_FFMPEG: return False, "FFmpeg not found on server"
    try:
        r = subprocess.run(["ffmpeg","-y"]+args, capture_output=True, text=True, timeout=timeout)
        return (True,"OK") if r.returncode==0 else (False, r.stderr[-400:])
    except subprocess.TimeoutExpired: return False, "Timed out"
    except Exception as e: return False, str(e)

# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/pdf/to_word_pdf", methods=["POST"])
def word_to_pdf():
    f = request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src = tmp(Path(f.filename).suffix); out = tmp(".pdf")
    f.save(src)
    try:
        import subprocess
        result = subprocess.run(
            ["libreoffice","--headless","--convert-to","pdf","--outdir",str(TEMP_DIR),str(src)],
            capture_output=True, timeout=60)
        gen = TEMP_DIR / (src.stem + ".pdf")
        if gen.exists():
            return send_file(gen, as_attachment=True,
                             download_name=Path(f.filename).stem+".pdf")
        return jsonify({"error":"LibreOffice conversion failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf/to_excel_pdf", methods=["POST"])
def excel_to_pdf():
    return word_to_pdf()

@app.route("/api/pdf/to_ppt_pdf", methods=["POST"])
def ppt_to_pdf():
    return word_to_pdf()
    
@app.route("/")
def health():
    return jsonify({"status":"ok","ffmpeg":HAS_FFMPEG,"pillow":HAS_PIL,
                    "pdfplumber":HAS_PDFPLUMBER,"currencies":len(CURRENCY_RATES)})

@app.route("/api/currency")
def api_currency():
    return jsonify({"rates": CURRENCY_RATES})

# ── Audio ─────────────────────────────────────────────────────────────────────
@app.route("/api/audio/convert", methods=["POST"])
def audio_convert():
    f = request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    fmt=request.form.get("format","mp3"); br=request.form.get("bitrate","192k")
    sr=request.form.get("samplerate","44100"); ch=request.form.get("channels","2")
    src=tmp(Path(f.filename).suffix); out=tmp(f".{fmt}")
    f.save(src)
    ok,msg=ffmpeg(["-i",str(src),"-ar",sr,"-ac",ch,"-b:a",br,str(out)])
    src.unlink(missing_ok=True)
    if not ok: return jsonify({"error":msg}), 500
    return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+f".{fmt}")

# ── Video ─────────────────────────────────────────────────────────────────────
@app.route("/api/video/convert", methods=["POST"])
def video_convert():
    f = request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    fmt=request.form.get("format","mp4"); crf=request.form.get("crf","23")
    res=request.form.get("resolution",""); fps=request.form.get("fps","")
    src=tmp(Path(f.filename).suffix); out=tmp(f".{fmt}")
    f.save(src)
    args=["-i",str(src),"-crf",crf]
    if res: args+=["-vf",f"scale={res}"]
    if fps: args+=["-r",fps]
    args.append(str(out))
    ok,msg=ffmpeg(args)
    src.unlink(missing_ok=True)
    if not ok: return jsonify({"error":msg}), 500
    return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+f".{fmt}")

@app.route("/api/video/extract_audio", methods=["POST"])
def video_extract():
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(Path(f.filename).suffix); out=tmp(".mp3")
    f.save(src)
    ok,msg=ffmpeg(["-i",str(src),"-vn","-ab","192k",str(out)])
    src.unlink(missing_ok=True)
    if not ok: return jsonify({"error":msg}), 500
    return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".mp3")

# ── Image ─────────────────────────────────────────────────────────────────────
@app.route("/api/image/convert", methods=["POST"])
def image_convert():
    if not HAS_PIL: return jsonify({"error":"Pillow not on server"}), 500
    files=request.files.getlist("files"); fmt=request.form.get("format","png")
    scale=int(request.form.get("scale",100))/100
    if not files: return jsonify({"error":"No files"}), 400
    if len(files)==1:
        f=files[0]; src=tmp(Path(f.filename).suffix); out=tmp(f".{fmt}")
        f.save(src)
        img=Image.open(src)
        if scale!=1.0: img=img.resize((max(1,int(img.width*scale)),max(1,int(img.height*scale))),Image.LANCZOS)
        if fmt in("pdf","jpg","jpeg") and img.mode in("RGBA","P","LA"): img=img.convert("RGB")
        img.save(out); src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+f".{fmt}")
    import zipfile, io
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as zf:
        for f in files:
            src=tmp(Path(f.filename).suffix); out=tmp(f".{fmt}")
            f.save(src); img=Image.open(src)
            if scale!=1.0: img=img.resize((max(1,int(img.width*scale)),max(1,int(img.height*scale))),Image.LANCZOS)
            if fmt in("pdf","jpg","jpeg") and img.mode in("RGBA","P","LA"): img=img.convert("RGB")
            img.save(out); zf.write(out,Path(f.filename).stem+f".{fmt}"); src.unlink(missing_ok=True)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="converted.zip")

# ── PDF ───────────────────────────────────────────────────────────────────────
@app.route("/api/pdf/image_to_pdf", methods=["POST"])
def image_to_pdf():
    if not HAS_PIL: return jsonify({"error":"Pillow not on server"}), 500
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(Path(f.filename).suffix); out=tmp(".pdf")
    f.save(src)
    try:
        img=Image.open(src)
        if img.mode in("RGBA","P","LA"): img=img.convert("RGB")
        img.save(out,"PDF"); src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".pdf")
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/pdf/text_to_pdf", methods=["POST"])
def text_to_pdf():
    if not HAS_PIL: return jsonify({"error":"Pillow not on server"}), 500
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(Path(f.filename).suffix); out=tmp(".pdf")
    f.save(src)
    try:
        from PIL import Image as PI, ImageDraw
        lines=src.read_text(encoding="utf-8",errors="replace").split("\n")
        W,H,margin,lh=794,1123,60,20; per_page=(H-2*margin)//lh; pages=[]
        for i in range(0,max(1,len(lines)),per_page):
            img=PI.new("RGB",(W,H),"white"); draw=ImageDraw.Draw(img)
            for j,line in enumerate(lines[i:i+per_page]):
                draw.text((margin,margin+j*lh),line,fill="black")
            pages.append(img)
        pages[0].save(out,save_all=True,append_images=pages[1:]); src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".pdf")
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/pdf/to_word", methods=["POST"])
def pdf_to_word():
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(".pdf"); out=tmp(".docx"); f.save(src)
    try:
        if HAS_PDF2DOCX:
            from pdf2docx import Converter as CV
            cv=CV(str(src)); cv.convert(str(out)); cv.close()
        elif HAS_PDFPLUMBER and HAS_DOCX:
            import pdfplumber; from docx import Document as Doc
            doc=Doc()
            with pdfplumber.open(str(src)) as pdf:
                for page in pdf.pages:
                    for line in (page.extract_text() or "").split("\n"): doc.add_paragraph(line)
                    doc.add_page_break()
            doc.save(str(out))
        else: return jsonify({"error":"pdf2docx not on server"}), 500
        src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".docx")
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/pdf/to_text", methods=["POST"])
def pdf_to_text():
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(".pdf"); out=tmp(".txt"); f.save(src)
    try:
        import pdfplumber
        with pdfplumber.open(str(src)) as pdf:
            text="\n\n--- Page Break ---\n\n".join(p.extract_text() or "" for p in pdf.pages)
        out.write_text(text,encoding="utf-8"); src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".txt")
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/pdf/to_excel", methods=["POST"])
def pdf_to_excel():
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(".pdf"); out=tmp(".xlsx"); f.save(src)
    try:
        import pdfplumber, openpyxl
        wb=openpyxl.Workbook(); wb.remove(wb.active)
        with pdfplumber.open(str(src)) as pdf:
            tc=0
            for pn,page in enumerate(pdf.pages,1):
                for tn,table in enumerate(page.extract_tables(),1):
                    tc+=1; ws=wb.create_sheet(f"P{pn}_T{tn}")
                    for row in table: ws.append(row)
        if tc==0:
            ws=wb.create_sheet("Text")
            with pdfplumber.open(str(src)) as pdf:
                for page in pdf.pages:
                    for line in (page.extract_text() or "").split("\n"): ws.append([line])
        wb.save(str(out)); src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".xlsx")
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/pdf/to_ppt", methods=["POST"])
def pdf_to_ppt():
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(".pdf"); out=tmp(".pptx"); f.save(src)
    try:
        import pdfplumber; from pptx import Presentation; import tempfile as tf, os
        prs=Presentation(); blank=prs.slide_layouts[6]; W,H=prs.slide_width,prs.slide_height
        with pdfplumber.open(str(src)) as pdf:
            for page in pdf.pages:
                img=page.to_image(resolution=150); t=tf.mktemp(suffix=".png")
                img.save(t); slide=prs.slides.add_slide(blank)
                slide.shapes.add_picture(t,0,0,W,H); os.remove(t)
        prs.save(str(out)); src.unlink(missing_ok=True)
        return send_file(out, as_attachment=True, download_name=Path(f.filename).stem+".pptx")
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/pdf/to_jpg", methods=["POST"])
def pdf_to_jpg():
    f=request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    src=tmp(".pdf"); f.save(src)
    try:
        import pdfplumber, zipfile, io
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as zf:
            with pdfplumber.open(str(src)) as pdf:
                for i,page in enumerate(pdf.pages):
                    img=page.to_image(resolution=150); t=tmp(f"_p{i+1}.jpg")
                    img.save(str(t)); zf.write(t,f"page_{i+1:04d}.jpg"); t.unlink(missing_ok=True)
        buf.seek(0); src.unlink(missing_ok=True)
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name=Path(f.filename).stem+"_pages.zip")
    except Exception as e: return jsonify({"error":str(e)}), 500

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0", port=port)