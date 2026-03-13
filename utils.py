import subprocess
import shutil
import json
from pathlib import Path
import config

# ══════════════════════════════════════════════════════════════════════════════
#  UNIT CONVERSION LOGIC
# ══════════════════════════════════════════════════════════════════════════════
def fmt_num(n):
    if n is None: return "Error"
    if abs(n) < 1e-6 and n != 0 or abs(n) >= 1e13:
        return f"{n:.6e}"
    s = f"{n:,.10f}".rstrip("0").rstrip(".")
    return s

def cvt_temp(v, f, t):
    if f=="Celsius":      c=v
    elif f=="Fahrenheit": c=(v-32)*5/9
    elif f=="Kelvin":     c=v-273.15
    elif f=="Rankine":    c=(v-491.67)*5/9
    else: return None
    if t=="Celsius":    return c
    if t=="Fahrenheit": return c*9/5+32
    if t=="Kelvin":     return c+273.15
    if t=="Rankine":    return (c+273.15)*9/5

def cvt_unit(val, fu, tu, data):
    if "__temp__" in data:
        return cvt_temp(val, fu, tu)
    if fu not in data or tu not in data:
        return None
    return val * data[fu] / data[tu]

def cvt_currency(amt, fc, tc):
    if fc not in config.CURRENCY_RATES or tc not in config.CURRENCY_RATES:
        return None
    return amt / config.CURRENCY_RATES[fc] * config.CURRENCY_RATES[tc]

# ══════════════════════════════════════════════════════════════════════════════
#  FFMPEG HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _get_duration_seconds(src: str) -> float | None:
    """Use ffprobe to get file duration in seconds."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", src],
            capture_output=True, text=True, timeout=15
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def run_ffmpeg(args):
    """
    Simple FFmpeg run with no progress callback.
    Returns (Success: bool, Message: str).
    """
    if not config.HAS_FFMPEG:
        return False, "FFmpeg not found. Add to PATH."
    cmd = ["ffmpeg", "-y"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            return True, "OK"
        else:
            return False, r.stderr[-500:] if r.stderr else "Unknown Error"
    except subprocess.TimeoutExpired:
        return False, "Conversion timed out."
    except Exception as e:
        return False, str(e)


def run_ffmpeg_progress(args, progress_cb=None):
    """
    FFmpeg with real-time progress reporting.

    progress_cb(percent: float)  — called on the calling thread via a pipe;
    the caller is responsible for scheduling any UI update with .after().

    Returns (Success: bool, Message: str).

    How it works:
      • We inject  -progress pipe:1  so FFmpeg writes key=value lines to stdout.
      • We read  out_time_ms  (microseconds processed so far).
      • We get total duration via ffprobe first so we can calculate a true %.
      • progress_cb receives a float 0.0–100.0.
    """
    if not config.HAS_FFMPEG:
        return False, "FFmpeg not found. Add to PATH."

    # Try to find input file from args to get duration
    total_secs = None
    try:
        i_idx = args.index("-i")
        src   = args[i_idx + 1]
        total_secs = _get_duration_seconds(src)
    except (ValueError, IndexError):
        pass

    # Inject -progress pipe:1 right after -y
    cmd = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats"] + args

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        last_pct = 0.0
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()

            if line.startswith("out_time_ms=") and progress_cb:
                try:
                    out_us = int(line.split("=")[1])
                    out_s  = out_us / 1_000_000
                    if total_secs and total_secs > 0:
                        pct = min(99.0, (out_s / total_secs) * 100)
                    else:
                        # No duration info — pulse between 10–90
                        pct = min(90.0, last_pct + 2)
                    if pct != last_pct:
                        last_pct = pct
                        progress_cb(pct)
                except (ValueError, ZeroDivisionError):
                    pass

            if line == "progress=end" and progress_cb:
                progress_cb(100.0)
                break

        proc.wait(timeout=300)

        if proc.returncode == 0:
            return True, "OK"
        else:
            err = proc.stderr.read()[-500:] if proc.stderr else "Unknown Error"
            return False, err

    except subprocess.TimeoutExpired:
        try: proc.kill()
        except Exception: pass
        return False, "Conversion timed out."
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
#  OFFICE CONVERSION
# ══════════════════════════════════════════════════════════════════════════════
def run_office_conversion(src, out_fmt):
    """Convert Office docs to PDF. Returns (Success: bool, Message: str)"""
    src_path = Path(src)
    out_path = src_path.with_suffix(f'.{out_fmt}')

    # 1. Try Microsoft Office (Windows)
    if config.HAS_OFFICE:
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            ext = src_path.suffix.lower()
            if ext in ['.docx', '.doc']:
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                doc = word.Documents.Open(str(src_path.absolute()))
                doc.SaveAs(str(out_path.absolute()), FileFormat=17)
                doc.Close(); word.Quit()
            elif ext in ['.xlsx', '.xls']:
                excel = win32com.client.Dispatch("Excel.Application")
                excel.Visible = False; excel.DisplayAlerts = False
                wb = excel.Workbooks.Open(str(src_path.absolute()))
                wb.ExportAsFixedFormat(0, str(out_path.absolute()))
                wb.Close(False); excel.Quit()
            elif ext in ['.pptx', '.ppt']:
                ppt = win32com.client.Dispatch("PowerPoint.Application")
                prs = ppt.Presentations.Open(str(src_path.absolute()), WithWindow=False)
                prs.SaveAs(str(out_path.absolute()), 32)
                prs.Close(); ppt.Quit()
            return True, "OK"
        except Exception:
            pass
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # 2. Try LibreOffice (Cross-platform)
    if config.HAS_LIBREOFFICE:
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        out_dir = str(src_path.parent)
        cmd = [soffice, "--headless", "--convert-to", out_fmt, "--outdir", out_dir, src]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return r.returncode == 0, r.stderr if r.returncode != 0 else "OK"
        except subprocess.TimeoutExpired:
            return False, "Conversion timed out (60s limit)"
        except Exception as e:
            return False, str(e)

    return False, "Neither MS Office nor LibreOffice found."