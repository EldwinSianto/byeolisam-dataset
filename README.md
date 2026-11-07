# Dataset Dialog Manhwa *Byeolisam* (ch001–ch217)

Transkripsi teks (bahasa Korea) dari 216 chapter webtoon *별이삼샵* (ch001–ch217, tanpa ch200), dengan label **siapa yang berbicara** dan **jenis teksnya**.
Dibuat untuk proyek kuliah text mining & profil karakter.

> ⚠️ **Hak cipta.** Teks dialog adalah milik penulis/penerbit *Byeolisam*. Dataset ini hanya untuk keperluan akademik
> dan **tidak boleh dipublikasikan** (repo harus tetap *private*, jangan diunggah ulang ke tempat publik).

## Isi

| File | Isi |
|---|---|
| `data/dialog.csv` | **Dataset utama.** 27.563 teks, satu baris per teks, sudah urut baca |
| `data/tokoh.csv` | Daftar 68 pembicara: romanisasi nama, jenis, jumlah teks per tipe, rentang chapter |
| `data/dibuang.csv` | 4.824 teks yang dikeluarkan + alasannya (duplikat, kredit penerjemah/penulis, belum dilabel) |
| `panels/chNNN/panel_PPP.jpg` | Gambar webtoon (16.822 potongan, ±1600 px tinggi, urut atas → bawah) untuk mengecek teks |
| `profil_karakter.py` → `profil/` | Kartu profil otomatis per tokoh (kemunculan, gaya bicara, kata khas, lawan bicara, honorifik, ucapan vs pikiran) + `gaya_bicara.csv`, `relasi.csv`, `honorifik.csv` |
| `analisis.ipynb` | Notebook awal: kemunculan tokoh, bicara vs. berpikir, gaya bicara, kata khas, siapa bicara dengan siapa, pencarian teks, `lihat()` untuk menampilkan gambar |

## Mulai

```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate
```
```bash
pip install -r requirements.txt
```
```bash
jupyter lab analisis.ipynb
```

Atau buka `data/dialog.csv` langsung di Excel / Google Sheets (encoding UTF-8).

**Mengecek teks ke gambarnya:** di notebook, `lihat("ch006_panel_037_02")` menampilkan panelnya dengan kotak merah pada
teks itu dan label pembicara untuk teks lain di panel yang sama. Tanpa notebook: buka file di kolom `gambar`, lalu cari
kotak di koordinat kolom `kotak`.

## Kolom `data/dialog.csv`

| Kolom | Arti |
|---|---|
| `urutan` | Nomor urut baca global (1 … 27563), lintas chapter |
| `chapter` | `ch001` … `ch217` (ch200, chapter spesial QnA, tidak termasuk) |
| `panel` | Indeks potongan gambar dalam chapter (gambar webtoon dipotong per ±1600 px, atas → bawah) |
| `urut_panel` | Urutan teks di dalam potongan itu |
| `bubble_id` | ID unik teks, `chNNN_panel_PPP_BB` |
| `jenis_kotak` | `dialog_bubble` (balon bicara, 22.475) atau `narration_box` (kotak narasi/pikiran, 5.088) |
| `pembicara` | Nama tokoh (Hangul), `anon_cNNN`, `Unknown`, `Narration`, atau `SFX` — lihat di bawah |
| `pembicara_romawi` | Nama pembicara dalam huruf Latin (지수원 → Ji Suwon) |
| `tipe` | Jenis teks — lihat di bawah |
| `teks` | **Teks final** (sudah dikoreksi bila ada koreksi OCR), satu baris |
| `layar` | `1` = teks yang tampil di layar HP/komputer (chat, komentar, notifikasi); 61 baris |
| `gambar` | File panel tempat teks berada, mis. `panels/ch006/panel_002.jpg` |
| `kotak` | Letak teks di gambar itu: `x1,y1,x2,y2` (piksel) |
| `posisi_persen` | Posisi teks dalam chapter (0 = awal, 100 = akhir) — berguna kalau mencocokkan dengan webtoon resmi |
| `teks_ocr_asli` | Teks hasil OCR sebelum dikoreksi |
| `teks_dikoreksi` | `1` = teks OCR sudah diperbaiki (4.184 baris) |
| `teks_ragu` | `1` = koreksi teks masih ragu karena gambar kurang jelas (48 baris) |
| `catatan` | Catatan anotator |

### Nilai `pembicara`
- **Nama Hangul**: 52 tokoh bernama (lihat `data/tokoh.csv`).
- **`anon_cNNN`**: tokoh tanpa nama tapi wajahnya konsisten di beberapa chapter, jadi bisa dianalisis sebagai satu orang.
- **`Unknown`**: figuran / pembicara yang tidak bisa ditentukan.
- **`Narration`**: narator, keterangan, teks sistem.
- **`SFX`**: efek suara yang tertulis di balon.
- **`Komik dalam komik`**: tokoh fiksi di dalam komik yang digambar tokoh cerita (ch009, ch010, ch017). Bukan pembicara sungguhan — keluarkan dari analisis tokoh.

### Nilai `tipe`
| Tipe | Arti | Jumlah |
|---|---|---|
| `ucapan` | Diucapkan dengan suara | 21.540 |
| `pikiran` | Monolog batin tokoh | 4.486 |
| `narasi` | Narasi / keterangan | 1.324 |
| `tulisan` | Teks yang **ditulis** tokoh: pesan chat, surat, komentar | 158 |
| `efek_suara` | Efek suara | 40 |
| `ingatan` | Kutipan ucapan masa lalu yang terngiang. Pembicara = **orang yang dulu mengucapkannya** | 15 |

Untuk profil gaya bicara biasanya pakai `tipe` `ucapan` + `tulisan`; untuk sisi batin pakai `pikiran`.

## Bagaimana data dibuat

1. Deteksi bubble & OCR otomatis (Magi + model OCR Korea).
2. **Pembicara dan tipe dilabel manual** untuk semua chapter ch001–ch217, dibantu foto referensi wajah tiap tokoh dan saran pembicara dari model/Claude; semua label diperiksa dan disimpan manual.
3. Koreksi OCR untuk teks berskor OCR < 0,85 (dicek terhadap gambar).
4. Urutan baca dibakukan atas → bawah, kiri → kanan.
5. Pembersihan (dicek visual): balon yang terbelah batas potongan gambar digabung, deteksi dobel dibuang, kredit/judul/antarmuka messenger dibuang (alasan per baris di `data/dibuang.csv`). Balon yang diucapkan dua tokoh bersamaan dicatat sebagai dua baris (`bubble_id` berakhiran `#2` untuk tokoh kedua).

## Keterbatasan

- **Urutan bubble yang sejajar** (setinggi sama, berdampingan) mengikuti aturan *kiri dulu*; kasus ketika penulis
  meletakkan jawaban di kiri belum dicek satu per satu. Tidak berpengaruh untuk analisis per tokoh, tapi perlu hati-hati
  untuk analisis giliran bicara (siapa menjawab siapa).
- Teks dengan skor OCR ≥ 0,85 tidak dicek ulang; kemungkinan masih ada salah ketik kecil.
- 12 kotak narasi yang mungkin berupa ingatan dibiarkan sebagai `ucapan` karena ragu.
- Slang/singkatan internet (ㅅㅂ, ㅋㅋ, 붕신, 새꺄) sengaja dipertahankan apa adanya. Tokenizer Korea (kiwipiepy)
  kadang memecah slang menjadi potongan aneh (붕신 → 붕 + 신), jadi hasil "kata khas" perlu dibaca dengan hati-hati.
- ch200 (chapter spesial QnA, bukan cerita) tidak termasuk.
- Sumber: versi beku `dataset_beku/v2026-11-07` di repo pipeline (MANIFEST berisi SHA-256 tiap file).
