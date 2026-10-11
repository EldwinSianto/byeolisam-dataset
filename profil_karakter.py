"""
profil_karakter.py — kartu profil otomatis untuk tiap tokoh dari data/dialog.csv.

  python profil_karakter.py            # -> profil/*.md, profil/gaya_bicara.csv, profil/honorifik.csv, profil/relasi.csv

Isi kartu: kemunculan, porsi tipe teks, gaya bicara (dibanding rata-rata), kata khas (Fightin' Words),
lawan bicara, honorifik (sopan/santai ke siapa), ucapan vs pikiran, contoh kutipan.
"""
import math, re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from kiwipiepy import Kiwi

OUT = Path("profil")
OUT.mkdir(exist_ok=True)
df = pd.read_csv("data/dialog.csv", encoding="utf-8-sig").sort_values("urutan")
df["teks"] = df.teks.astype(str)
tokoh = pd.read_csv("data/tokoh.csv", encoding="utf-8-sig")
NAMA = dict(zip(tokoh.pembicara, tokoh.pembicara_romawi))
BUKAN = {"Unknown", "Narration", "SFX"}
CHAPTERS = sorted(df.chapter.unique())
MIN_TEKS = 30                      # tokoh dengan teks lebih sedikit tidak dibuatkan kartu

# ---------- ciri gaya per kalimat ----------
SOPAN = re.compile(r"(?:요|니다|니까|세요|죠|시오)[.!?~…\s]*$")
MAKI = re.compile(r"ㅅㅂ|씨발|시발|ㅂㅅ|병신|붕신|새끼|새꺄|새키|존나|좆|ㅈㄴ")
FITUR = {
    "panjang": lambda t: len(t),
    "% sopan": lambda t: 100 * bool(SOPAN.search(t)),
    "% tanya": lambda t: 100 * ("?" in t),
    "% seru": lambda t: 100 * ("!" in t),
    "% ragu (...)": lambda t: 100 * bool(re.search(r"\.\.|…", t)),
    "% ㅋ/ㅎ": lambda t: 100 * bool(re.search(r"[ㅋㅎ]{2,}", t)),
    "% makian": lambda t: 100 * bool(MAKI.search(t)),
}
for k, f in FITUR.items():
    df[k] = df.teks.map(f)

# ---------- token (kata dasar) ----------
kiwi = Kiwi()
# nama tokoh & panggilan pendeknya jangan dipecah (설효 -> 설 + 효)
for w in set(tokoh.pembicara) - BUKAN | {"설효", "양진", "방동", "준현", "진수", "수원", "효림", "리나", "진경", "희준", "인섭", "철규"}:
    if not w.startswith("anon"):
        kiwi.add_user_word(w, "NNP")
AMBIL = {"NNG", "NNP", "VV", "VA", "MAG", "IC", "XR"}
def kata(t):
    return [x.form + ("다" if x.tag in ("VV", "VA") else "") for x in kiwi.tokenize(t) if x.tag in AMBIL and len(x.form) > 0]
df["kata"] = df.teks.map(kata)


def fightin_words(a, b, prior, top=15, min_n=4):
    """kata yang paling khas untuk a dibanding b (log-odds dengan prior Dirichlet, Monroe dkk. 2008) -> [(kata, z, n)]"""
    na, nb, a0 = sum(a.values()), sum(b.values()), sum(prior.values()) + 1
    out = []
    for w, ya in a.items():
        if ya < min_n:
            continue
        aw, yb = prior[w], b.get(w, 0)
        d = math.log((ya + aw) / (na + a0 - ya - aw)) - math.log((yb + aw) / (nb + a0 - yb - aw))
        out.append((w, d / math.sqrt(1 / (ya + aw) + 1 / (yb + aw)), ya))
    return sorted(out, key=lambda x: -x[1])[:top]


# ---------- percakapan: lawan bicara terdekat (perkiraan) ----------
u = df[(df.tipe == "ucapan") & ~df.pembicara.isin(BUKAN)].reset_index(drop=True)
lawan = [None] * len(u)
for i, r in u.iterrows():
    for j in (i + 1, i - 1):          # utamakan yang menjawab sesudahnya, lalu yang bicara sebelumnya
        if 0 <= j < len(u):
            s = u.loc[j]
            if s.chapter == r.chapter and abs(s.panel - r.panel) <= 1 and s.pembicara != r.pembicara:
                lawan[i] = s.pembicara
                break
u["lawan"] = lawan
relasi = u.dropna(subset=["lawan"]).groupby(["pembicara", "lawan"]).size().rename("jumlah").reset_index()
hono = (u.dropna(subset=["lawan"]).groupby(["pembicara", "lawan"])["% sopan"].agg(["mean", "size"])
        .rename(columns={"mean": "% sopan", "size": "n"}).reset_index())
hono = hono[hono.n >= 8]
for d, f in ((relasi, "relasi.csv"), (hono, "honorifik.csv")):
    d.assign(pembicara_romawi=d.pembicara.map(NAMA), lawan_romawi=d.lawan.map(NAMA)).to_csv(
        OUT / f, index=False, encoding="utf-8-sig", float_format="%.1f")

# ---------- tabel gaya bicara ----------
bicara = df[df.tipe.isin(["ucapan", "tulisan"])]
rata = bicara[list(FITUR)].mean()
gaya = bicara[~bicara.pembicara.isin(BUKAN)].groupby("pembicara")[list(FITUR)].mean()
gaya["n"] = bicara.groupby("pembicara").size()
gaya = gaya[gaya.n >= MIN_TEKS].sort_values("n", ascending=False)
gaya.assign(pembicara_romawi=gaya.index.map(NAMA)).to_csv(OUT / "gaya_bicara.csv", encoding="utf-8-sig", float_format="%.1f")

semua_kata = Counter(w for ws in df.kata for w in ws)
prior = defaultdict(lambda: 0.01, {w: 0.01 * n for w, n in semua_kata.items()})
BAR = "▁▂▃▄▅▆▇█"


def spark(counts):
    m = max(counts) or 1
    return "".join(" " if c == 0 else BAR[min(7, int(7 * c / m))] for c in counts)


def kutipan(d, kunci, k):
    """contoh kalimat yang memuat kata khas, panjang sedang, dari chapter berbeda"""
    d = d[d.teks.str.len().between(8, 60)]
    skor = d.kata.map(lambda ws: len(set(ws) & kunci))
    d = d.assign(skor=skor).sort_values(["skor", "urutan"], ascending=[False, True]).drop_duplicates("chapter")
    return d.head(k).sort_values("urutan")


def kartu(p):
    nama, semua = NAMA.get(p, p), df[df.pembicara == p]
    ucap, pikir = semua[semua.tipe.isin(["ucapan", "tulisan"])], semua[semua.tipe == "pikiran"]
    per_ch = semua.groupby("chapter").size().reindex(CHAPTERS, fill_value=0)
    L = [f"# {nama} ({p})", ""]
    L += ["## Kemunculan", f"- Total **{len(semua)} teks** di **{(per_ch > 0).sum()} chapter** "
          f"({per_ch[per_ch > 0].index.min()} – {per_ch[per_ch > 0].index.max()})",
          f"- Per chapter (ch006 → ch060): `{spark(per_ch.tolist())}`",
          f"- Chapter tersibuk: " + ", ".join(f"{c} ({n})" for c, n in per_ch.nlargest(3).items()), ""]
    tp = semua.tipe.value_counts()
    L += ["## Porsi tipe teks", "| ucapan | pikiran | tulisan | ingatan* |", "|---|---|---|---|",
          f"| {tp.get('ucapan', 0)} | {tp.get('pikiran', 0)} | {tp.get('tulisan', 0)} | {tp.get('ingatan', 0)} |",
          "", f"Porsi pikiran **{100 * len(pikir) / max(1, len(semua)):.0f}%** "
          + ("→ kemungkinan tokoh sudut pandang (POV)." if len(pikir) / max(1, len(semua)) > 0.15 else "→ jarang terlihat isi pikirannya."),
          "*ingatan = kalimatnya yang terngiang di kepala tokoh lain.", ""]
    if len(ucap) >= MIN_TEKS:
        g = ucap[list(FITUR)].mean()
        L += ["## Gaya bicara (ucapan + tulisan)", "| ciri | tokoh ini | rata-rata semua | |", "|---|---|---|---|"]
        for k in FITUR:
            rasio = g[k] / rata[k] if rata[k] else 1
            tanda = "⬆ jauh lebih tinggi" if rasio >= 1.5 else "⬇ jauh lebih rendah" if rasio <= 0.6 else ""
            L.append(f"| {k} | {g[k]:.1f} | {rata[k]:.1f} | {tanda} |")
        L.append("")
        lain = Counter(w for ws in bicara[bicara.pembicara != p].kata for w in ws)
        fw = fightin_words(Counter(w for ws in ucap.kata for w in ws), lain, prior)
        L += ["## Kata khas (dibanding tokoh lain)", "", ", ".join(f"**{w}** ({n}×)" for w, z, n in fw if z > 1.5) or "-", ""]
        kunci = {w for w, z, n in fw}
        L += ["Contoh ucapan:", ""] + [f"- {r.chapter}: {r.teks}  `{r.bubble_id}`" for r in kutipan(ucap, kunci, 5).itertuples()] + [""]
    rl = relasi[relasi.pembicara == p].nlargest(6, "jumlah")
    if len(rl):
        L += ["## Lawan bicara tersering", "| lawan | pertukaran | % sopan ke dia |", "|---|---|---|"]
        for r in rl.itertuples():
            h = hono[(hono.pembicara == p) & (hono.lawan == r.lawan)]
            L.append(f"| {NAMA.get(r.lawan, r.lawan)} | {r.jumlah} | {f'{h.iloc[0][chr(37) + ' sopan']:.0f}%' if len(h) else '–'} |")
        dari = hono[hono.lawan == p].assign(nm=lambda d: d.pembicara.map(NAMA)).sort_values("% sopan", ascending=False)
        if len(dari):
            L += ["", "Yang bicara sopan kepadanya: " + ", ".join(f"{r.nm} {r[3]:.0f}%" for r in dari.head(5).itertuples())]
        L += ["", "_Lawan bicara = pembicara tepat sesudah/sebelumnya di panel yang sama atau berdekatan (perkiraan)._", ""]
    if len(pikir) >= 20 and len(ucap) >= 20:
        gp = pikir[list(FITUR)].mean(); gu = ucap[list(FITUR)].mean()
        L += ["## Ucapan vs pikiran", "| ciri | diucapkan | dipikirkan |", "|---|---|---|"]
        L += [f"| {k} | {gu[k]:.1f} | {gp[k]:.1f} |" for k in FITUR]
        cu, cp = Counter(w for ws in ucap.kata for w in ws), Counter(w for ws in pikir.kata for w in ws)
        L += ["", "Kata yang muncul di **pikiran** tapi jarang diucapkan: "
              + ", ".join(f"**{w}** ({n}×)" for w, z, n in fightin_words(cp, cu, prior, top=12, min_n=3) if z > 1.0),
              "", "Kata yang **diucapkan** tapi jarang dipikirkan: "
              + ", ".join(f"**{w}** ({n}×)" for w, z, n in fightin_words(cu, cp, prior, top=12, min_n=3) if z > 1.0), ""]
        kp = {w for w, z, n in fightin_words(cp, cu, prior, top=25, min_n=3)}
        L += ["Contoh pikiran:", ""] + [f"- {r.chapter}: {r.teks}  `{r.bubble_id}`" for r in kutipan(pikir, kp, 5).itertuples()] + [""]
    return "\n".join(L)


daftar = [p for p in tokoh.pembicara if p not in BUKAN and (df.pembicara == p).sum() >= MIN_TEKS]
for p in daftar:
    (OUT / f"{NAMA.get(p, p).replace(' ', '_')}.md").write_text(kartu(p), encoding="utf-8")
idx = ["# Profil tokoh", "", "| tokoh | teks | pikiran | chapter | file |", "|---|---|---|---|---|"]
for p in daftar:
    s = df[df.pembicara == p]
    f = NAMA.get(p, p).replace(" ", "_") + ".md"
    idx.append(f"| {NAMA.get(p, p)} ({p}) | {len(s)} | {(s.tipe == 'pikiran').sum()} | {s.chapter.nunique()} | [{f}]({f}) |")
idx += ["", "Tabel pendukung: `gaya_bicara.csv`, `relasi.csv`, `honorifik.csv`."]
(OUT / "README.md").write_text("\n".join(idx), encoding="utf-8")
print(f"{len(daftar)} kartu profil -> {OUT}/")
