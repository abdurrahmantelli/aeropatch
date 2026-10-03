"""wsl/ dizinindeki .sh dosyalarindaki CRLF'u temizler."""
import glob
import os

d = os.path.dirname(os.path.abspath(__file__))
for p in glob.glob(os.path.join(d, "*.sh")):
    with open(p, "rb") as f:
        data = f.read()
    if b"\r" in data:
        # Saglamlastirildi: cift CR (\r\r\n) tuzuagi — tek gecis yetmez,
        # tum CR'leri temizle (lone \r dahil); .sh icin guvenli.
        data = data.replace(b"\r\r\n", b"\n")
        data = data.replace(b"\r\n", b"\n")
        data = data.replace(b"\r", b"\n")
        with open(p, "wb") as f:
            f.write(data)
        print("fixed:", os.path.basename(p))
    else:
        print("ok:", os.path.basename(p))
