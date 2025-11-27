def mmss(ms):
    s = int((ms or 0) / 1000)
    return f"{s//60:02d}:{s%60:02d}"
