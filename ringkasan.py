"""
ringkasan.py — ringkasan otomatis per chapter dan per arc dari data/dialog.csv (tanpa LLM generatif besar).

  python ringkasan.py --ch ch001-ch016                          # semua metode
  python ringkasan.py --ch ch001-ch016 --metode emb,kobart
  python ringkasan.py --ch ch001-ch016 --metode mmr --k 8

Metode ekstraktif (memilih kalimat asli, tidak menulis kalimat baru):
  awal      baseline: k kalimat pertama chapter
  acak      baseline: k kalimat acak (seed tetap)
  textrank  graf kemiripan antar-kalimat (TF-IDF morfem Kiwi), skor PageRank, ambil k teratas
  mmr       TextRank + Maximal Marginal Relevance: penting tapi tidak saling mengulang
  mmr_kw    seperti mmr, relevansi = 0,5 TextRank + 0,5 skor kata kunci khas chapter (TF-IDF tingkat chapter)
  emb       seperti mmr_kw, tetapi kemiripan antar-kalimat dari sentence embedding Korea (--emb), bukan TF-IDF
Metode abstraktif (menulis kalimat baru):
  kobart    KoBART (transformer kecil ~124M, --kobart) bertingkat: dialog chapter dipotong per ~--max_in token
            ("Nama: teks" per baris), tiap potongan diringkas jadi satu kalimat; arc = ringkasan dari ringkasan chapter.
Kata sangat umum (STOP: 80 morfem tersering + kata fungsi) dibuang sebelum menghitung kemiripan TF-IDF.
Arc ekstraktif: kandidat = gabungan ringkasan chapter dalam arc (batas arc dari arc.csv), lalu dipilih lagi.

Metrik tanpa ringkasan acuan (dihitung terhadap teks chapter/arc):
  js         Jensen-Shannon divergence sebaran morfem ringkasan vs sumber (kecil = lebih mewakili)
  cakupan    rata-rata kemiripan maksimum (TF-IDF) tiap kalimat sumber ke ringkasan (besar = lebih tercakup)
  cak_emb    sama, tetapi dengan embedding evaluasi (--emb_eval, model berbeda dari --emb agar tidak memihak)
  ulang      rata-rata kemiripan embedding evaluasi antar-kalimat ringkasan (kecil = sedikit pengulangan)
  nama_asing proporsi nama tokoh di ringkasan yang tidak muncul di sumber (indikasi halusinasi; 0 = baik)
Dengan ringkasan acuan (acuan/ringkasan_acuan.csv, bila ada untuk chapter/arc itu):
  rouge1/2/L ROUGE F1 pada morfem isi Kiwi;  sim_acuan  F1 kemiripan embedding evaluasi per kalimat
Keluaran: ringkasan/<metode>/chNNN.md, ringkasan/<metode>/arc_*.md, ringkasan/metrik.csv
"""
import argparse, csv, random, re, time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from kiwipiepy import Kiwi
from sklearn.feature_extraction.text import TfidfVectorizer

ap = argparse.ArgumentParser()
ap.add_argument("--ch", default="ch001-ch016", help="rentang chapter, mis. ch001-ch016")
ap.add_argument("--metode", default="awal,acak,textrank,mmr,mmr_kw,emb,kobart")
ap.add_argument("--k", type=int, default=0, help="jumlah kalimat per chapter (0 = otomatis ~8%%, min 6, maks 12)")
ap.add_argument("--k_arc", type=int, default=15)
ap.add_argument("--lam", type=float, default=0.7, help="bobot relevansi pada MMR")
ap.add_argument("--emb", default="jhgan/ko-sroberta-multitask", help="embedding untuk memilih kalimat (metode emb)")
ap.add_argument("--emb_eval", default="snunlp/KR-SBERT-V40K-klueNLI-augSTS", help="embedding untuk metrik")
ap.add_argument("--kobart", default="EbanLee/kobart-summary-v3", help="KoBART ringkasan (dipilih dari 4 kandidat, lihat README)")
ap.add_argument("--max_in", type=int, default=400, help="panjang maksimum satu potongan input KoBART (token)")
ap.add_argument("--out", default="ringkasan")
a = ap.parse_args()

OUT = Path(a.out)
df = pd.read_csv("data/dialog.csv", encoding="utf-8-sig").sort_values("urutan").reset_index(drop=True)
df["teks"] = df.teks.astype(str).str.replace("\n", " ")
df["gi"] = df.index
tokoh = pd.read_csv("data/tokoh.csv", encoding="utf-8-sig")
ROM = dict(zip(tokoh.pembicara, tokoh.pembicara_romawi))
lo, _, hi = a.ch.partition("-")
hi = hi or lo
dev = None

# ---------- kandidat kalimat ----------
BUANG_SP = {"SFX", "Komik dalam komik"}
norm = lambda t: re.sub(r"[\s.,!?~…;:\-'\"ㅋㅎㅠㅜ]", "", t)
kiwi = Kiwi()
KEEP = ("NNG", "NNP", "VV", "VA", "XR", "MAG", "SL")


def morf(t):
    return [tok.form + ("다" if tok.tag in ("VV", "VA") else "") for tok in kiwi.tokenize(t) if tok.tag.startswith(KEEP)]


df["isi"] = df.tipe.isin(["ucapan", "pikiran", "narasi", "tulisan"]) & ~df.pembicara.isin(BUANG_SP)
df["kandidat"] = df.isi & (df.teks.map(lambda t: len(norm(t))) >= 6)
df["morf"] = df.teks.map(morf)
_frek = Counter(w for m in df.morf for w in m)
STOP = {w for w, _ in _frek.most_common(80)} | {"하다", "되다", "있다", "없다", "같다", "보다", "가다", "오다", "개", "걔", "얘",
                                               "그냥", "진짜", "좀", "너무", "이제", "그렇다", "이렇다", "아니다", "알다", "모르다"}
saring = lambda m: [w for w in m if w not in STOP]
df["morf"] = df.morf.map(saring)
df.loc[df.morf.map(len) < 2, "kandidat"] = False
# kata kunci khas tiap chapter: TF-IDF dengan satu chapter = satu dokumen
_cv = TfidfVectorizer(analyzer=lambda x: x, sublinear_tf=True, min_df=1)
_chs = sorted(df.chapter.unique())
_K = _cv.fit_transform([sum(df.morf[df.chapter == c], []) for c in _chs])
_voc = _cv.get_feature_names_out()
KW = {c: dict(zip(_voc, _K[i].toarray()[0])) for i, c in enumerate(_chs)}
# IDF dari seluruh dataset (satu baris = satu dokumen)
vec = TfidfVectorizer(analyzer=lambda x: x, sublinear_tf=True, min_df=2)
vec.fit(df.morf)

# nama tokoh (lengkap dan nama depan) untuk metrik nama_asing
NAMA = {}
for s in tokoh[tokoh.jenis == "tokoh bernama"].pembicara:
    if re.fullmatch(r"[가-힣]{2,4}", s):
        NAMA[s] = s
        if len(s) == 3:
            NAMA[s[1:]] = s
POLA_NAMA = re.compile("|".join(sorted(NAMA, key=len, reverse=True)))


def unit(X):
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.where(n == 0, 1, n)


def tfidf(morfs):
    return unit(vec.transform(list(morfs)).toarray())


# ---------- embedding (sentence-transformers), dimuat bila perlu ----------
_ST = {}


def embed(model, teks):
    global dev
    if model not in _ST:
        import torch
        from sentence_transformers import SentenceTransformer
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _ST[model] = SentenceTransformer(model, device=dev)
    return _ST[model].encode(list(teks), batch_size=128, normalize_embeddings=True, show_progress_bar=False)


def textrank(S, d=0.85, it=60):
    W = np.clip(S, 0, None).copy(); np.fill_diagonal(W, 0)
    s = W.sum(1, keepdims=True); W = W / np.where(s == 0, 1, s)
    r = np.ones(len(W)) / len(W)
    for _ in range(it):
        r = (1 - d) / len(W) + d * W.T @ r
    return r


E_SEL = None


def pilih(rows, k, metode, seed=0):
    if len(rows) <= k:
        return list(range(len(rows)))
    if metode == "awal":
        return list(range(k))
    if metode == "acak":
        return sorted(random.Random(seed).sample(range(len(rows)), k))
    X = E_SEL[rows.gi.values] if metode == "emb" else tfidf(rows.morf)
    S = X @ X.T
    tr = textrank(S)
    if metode == "textrank":
        return sorted(np.argsort(-tr)[:k].tolist())
    rel = (tr - tr.min()) / (np.ptp(tr) or 1)
    if metode in ("mmr_kw", "emb"):
        kw = np.array([sum(KW[r.chapter].get(w, 0) for w in set(r.morf)) for r in rows.itertuples()])
        rel = 0.5 * rel + 0.5 * (kw - kw.min()) / (np.ptp(kw) or 1)
    sel = [int(np.argmax(rel))]
    while len(sel) < k:
        red = S[:, sel].max(1)
        sc = a.lam * rel - (1 - a.lam) * red
        sc[sel] = -1e9
        sel.append(int(np.argmax(sc)))
    return sorted(sel)


# ---------- KoBART abstraktif ----------
_KB = {}


def kobart(potongan):
    """potongan: daftar string input; keluaran: satu kalimat ringkasan per potongan."""
    import torch
    if not _KB:
        from huggingface_hub import hf_hub_download
        from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
        # tokenizer.json dimuat langsung: AutoTokenizer di transformers 5 salah mengenali tokenizer KoBART (jadi byte-level)
        _KB["tok"] = PreTrainedTokenizerFast(tokenizer_file=hf_hub_download(a.kobart, "tokenizer.json"))
        _KB["mdl"] = BartForConditionalGeneration.from_pretrained(a.kobart).to(
            "cuda" if torch.cuda.is_available() else "cpu").eval()
    tok, mdl = _KB["tok"], _KB["mdl"]
    bos, eos, pad = mdl.config.bos_token_id, mdl.config.eos_token_id, mdl.config.pad_token_id
    out = []
    for i in range(0, len(potongan), 8):
        ids = [[bos] + tok(p)["input_ids"][:1020] + [eos] for p in potongan[i:i + 8]]
        n = max(map(len, ids))
        x = torch.tensor([s + [pad] * (n - len(s)) for s in ids], device=mdl.device)
        m = torch.tensor([[1] * len(s) + [0] * (n - len(s)) for s in ids], device=mdl.device)
        with torch.no_grad():
            g = mdl.generate(input_ids=x, attention_mask=m, num_beams=4, max_length=96, no_repeat_ngram_size=3,
                             early_stopping=True)
        out += [t.strip() for t in tok.batch_decode(g, skip_special_tokens=True)]
    return out


def potong(baris_list):
    tok = _KB["tok"] if _KB else None
    if tok is None:
        kobart(["."])  # memuat model
        tok = _KB["tok"]
    hasil, cur, n = [], [], 0
    for b in baris_list:
        l = len(tok.tokenize(b)) + 1
        if cur and n + l > a.max_in:
            hasil.append("\n".join(cur)); cur, n = [], 0
        cur.append(b); n += l
    if cur:
        hasil.append("\n".join(cur))
    return hasil


def nama_kr(sp):
    return sp if re.fullmatch(r"[가-힣]{2,4}", str(sp)) else {"Narration": "내레이션"}.get(sp, "누군가")


# ---------- metrik ----------
def metrik(semua, teks, kunci=None):
    """semua: baris sumber (kandidat); teks: daftar kalimat ringkasan; kunci: nama di acuan/ringkasan_acuan.csv."""
    mr = [saring(morf(t)) for t in teks]
    ca = Counter(w for m in semua.morf for w in m); cs = Counter(w for m in mr for w in m)
    V = sorted(set(ca) | set(cs)); p = np.array([ca[w] for w in V], float); q = np.array([cs[w] for w in V], float)
    p /= p.sum(); q = q / q.sum() if q.sum() else q; m = (p + q) / 2
    kl = lambda x, y: float(np.sum(x[x > 0] * np.log2(x[x > 0] / y[x > 0])))
    js = (kl(p, m) + kl(q, m)) / 2
    cak = float((tfidf(semua.morf) @ tfidf(mr).T).max(1).mean())
    Ea = E_EVAL[semua.gi.values]; Es = embed(a.emb_eval, teks)
    cak_e = float((Ea @ Es.T).max(1).mean())
    Ss = Es @ Es.T; n = len(Ss)
    ul = float((Ss.sum() - np.trace(Ss)) / (n * (n - 1))) if n > 1 else 0.0
    sumber = " ".join(semua.teks) + " " + " ".join(semua.pembicara.astype(str))
    nm = [NAMA[x] for t in teks for x in POLA_NAMA.findall(t)]
    asing = sum(1 for x in nm if x not in sumber and x[1:] not in sumber) / len(nm) if nm else 0.0
    out = dict(js=round(js, 4), cakupan=round(cak, 4), cak_emb=round(cak_e, 4), ulang=round(ul, 4),
               nama_asing=round(asing, 3))
    if kunci in ACUAN:
        out.update(banding_acuan(teks, ACUAN[kunci]))
    return out


# ---------- perbandingan dengan ringkasan acuan (acuan/ringkasan_acuan.csv) ----------
ACUAN = {}
if Path("acuan/ringkasan_acuan.csv").exists():
    ACUAN = {r["nama"]: r["ringkasan_ko"] for r in csv.DictReader(open("acuan/ringkasan_acuan.csv", encoding="utf-8-sig"))}


def _f(p, r):
    return 2 * p * r / (p + r) if p + r else 0.0


def _lcs(x, y):
    d = [0] * (len(y) + 1)
    for a_ in x:
        prev = 0
        for j, b_ in enumerate(y):
            cur = d[j + 1]
            d[j + 1] = prev + 1 if a_ == b_ else max(d[j + 1], d[j])
            prev = cur
    return d[-1]


def banding_acuan(teks, acuan):
    """ROUGE-1/2/L (F1) pada morfem isi (Kiwi, tanpa STOP agar nama tokoh tetap dihitung) dan
    sim_acuan: F1 kemiripan embedding per kalimat (tiap kalimat acuan ↔ kalimat ringkasan terdekat, dan sebaliknya)."""
    s, r = morf(" ".join(teks)), morf(acuan)
    out = {}
    for n in (1, 2):
        cs_ = Counter(zip(*[s[i:] for i in range(n)])); cr = Counter(zip(*[r[i:] for i in range(n)]))
        ov = sum((cs_ & cr).values())
        out[f"rouge{n}"] = round(_f(ov / max(sum(cs_.values()), 1), ov / max(sum(cr.values()), 1)), 4)
    l = _lcs(s, r)
    out["rougeL"] = round(_f(l / max(len(s), 1), l / max(len(r), 1)), 4)
    ka = [k for k in re.split(r"(?<=[.!?다])\s+", acuan) if k.strip()]
    S = embed(a.emb_eval, teks) @ embed(a.emb_eval, ka).T
    out["sim_acuan"] = round(_f(float(S.max(1).mean()), float(S.max(0).mean())), 4)
    return out


def baris(r, ch=False):
    sp = ROM.get(r.pembicara, r.pembicara)
    return f"- {f'[{r.chapter}] ' if ch else ''}**{sp}** ({r.tipe}): {r.teks}  `{r.bubble_id}`"


arc = [r for r in csv.DictReader(open("arc.csv", encoding="utf-8-sig"))] if Path("arc.csv").exists() else []
chs = [c for c in sorted(df.chapter.unique()) if lo <= c <= hi]
metodes = a.metode.split(",")
pakai = df[df.chapter.isin(chs) & df.kandidat]
E_EVAL = np.zeros((len(df), 1), np.float32)
_e = embed(a.emb_eval, pakai.teks); E_EVAL = np.zeros((len(df), _e.shape[1]), np.float32); E_EVAL[pakai.gi.values] = _e
if "emb" in metodes:
    _e = embed(a.emb, pakai.teks); E_SEL = np.zeros((len(df), _e.shape[1]), np.float32); E_SEL[pakai.gi.values] = _e

hasil = []
for metode in metodes:
    t0 = time.time()
    D = OUT / metode; D.mkdir(parents=True, exist_ok=True)
    per_ch = {}
    for c in chs:
        semua = df[(df.chapter == c) & df.kandidat].reset_index(drop=True)
        if metode == "kobart":
            src = df[(df.chapter == c) & df.isi]
            pot = potong([f"{nama_kr(r.pembicara)}: {r.teks}" for r in src.itertuples()])
            teks = kobart(pot); per_ch[c] = teks
            isi = "\n".join(f"- {t}" for t in teks)
            judul = f"{len(teks)} kalimat dari {len(pot)} potongan dialog ({len(src)} baris)"
        else:
            k = a.k or max(6, min(12, round(0.08 * len(semua))))
            pil = semua.iloc[pilih(semua, k, metode, seed=int(c[2:]))]; per_ch[c] = pil
            teks = pil.teks.tolist(); isi = "\n".join(baris(r) for r in pil.itertuples())
            judul = f"{len(pil)} dari {len(semua)} kalimat"
        hasil.append({"tingkat": "chapter", "nama": c, "metode": metode, "k": len(teks), **metrik(semua, teks, c)})
        (D / f"{c}.md").write_text(f"# {c} — {metode} ({judul})\n\n{isi}\n", encoding="utf-8")
    for ar in arc:
        cs = [c for c in chs if ar["dari"] <= c <= ar["sampai"]]
        if len(cs) < 2:
            continue
        semua = df[df.chapter.isin(cs) & df.kandidat].reset_index(drop=True)
        if metode == "kobart":
            # tingkat 2: ringkasan chapter digabung, dipotong lagi, diringkas lagi
            pot = potong([f"[{c}] " + " ".join(per_ch[c]) for c in cs])
            teks = kobart(pot)
            isi = "\n".join(f"- {t}" for t in teks)
        else:
            kand = pd.concat([per_ch[c] for c in cs]).sort_values("urutan").reset_index(drop=True)
            pil = kand.iloc[pilih(kand, a.k_arc, metode, seed=1)]
            teks = pil.teks.tolist(); isi = "\n".join(baris(r, ch=True) for r in pil.itertuples())
        hasil.append({"tingkat": "arc", "nama": ar["arc"], "metode": metode, "k": len(teks),
                      **metrik(semua, teks, f"{ar['arc']} ({ar['dari']}-{ar['sampai']})")})
        (D / f"arc_{ar['dari']}-{ar['sampai']}.md").write_text(
            f"# Arc {ar['arc']} ({ar['dari']}–{ar['sampai']}) — {metode}\n\n{isi}\n", encoding="utf-8")
    print(f"{metode}: {time.time() - t0:.1f} dtk", flush=True)

M = pd.DataFrame(hasil)
M.to_csv(OUT / "metrik.csv", index=False, encoding="utf-8-sig")
kol = [k for k in ["k", "js", "cakupan", "cak_emb", "ulang", "nama_asing", "rouge1", "rouge2", "rougeL", "sim_acuan"] if k in M]
print(M.groupby(["tingkat", "metode"], sort=False)[kol].mean().round(3).to_string())
