# Dataset Dialog Manhwa *Byeolisam* (ch006–ch060)

Transkripsi teks (bahasa Korea) dari 55 chapter webtoon, dengan label **siapa yang berbicara** dan **jenis teksnya**.
Dibuat untuk proyek kuliah text mining & profil karakter.

> ⚠️ **Hak cipta.** Teks dialog adalah milik penulis/penerbit *Byeolisam*. Dataset ini hanya untuk keperluan akademik
> dan **tidak boleh dipublikasikan** (repo harus tetap *private*, jangan diunggah ulang ke tempat publik).
> Gambar panel sengaja tidak disertakan.

## Isi folder

| File | Isi |
|---|---|
| `dataset_final/dialog_final.csv` | **Dataset utama.** 7.282 teks, satu baris per teks, sudah urut baca |
| `dataset_final/tokoh.csv` | Daftar pembicara: romanisasi nama, jenis, jumlah teks per tipe, rentang chapter |
| `dataset_final/ringkasan.txt` | Statistik singkat per pembicara & tipe |
| `dataset_final/dibuang.csv` | 617 teks yang dikeluarkan + alasannya (duplikat, kredit penerjemah/penulis, belum dilabel) |
| `annotations/manual_labels.csv` | Label manual mentah (pembicara + tipe) per bubble, sebelum dibakukan |
| `annotations/koreksi_teks.csv` | Koreksi OCR untuk 254 teks berskor rendah (dicek visual) |
| `annotations/koreksi_urutan.csv` | Perbaikan urutan baca di 165 potongan panel |
| `annotations/koreksi_tipe.csv` | Kotak narasi yang tipenya dikoreksi (mis. menjadi `ingatan`) |
| `annotations/kandidat_ingatan.csv` | Kandidat kutipan ingatan hasil pencarian otomatis (tidak diterapkan) |
| `output_speaker_vf/chNNN.json` | Hasil deteksi mentah per chapter: kotak bubble, teks OCR, skor OCR |
| `output/pass2/names.json` | Peta cluster wajah → nama tokoh |
| `build_final_dataset.py`, `prepare_finetune.py` | Skrip yang membangun `dataset_final/` dari semua file di atas |
| `find_memories.py` | Skrip pencari kandidat ingatan |

## Kolom `dialog_final.csv`

| Kolom | Arti |
|---|---|
| `urutan` | Nomor urut baca global (1 … 7282), lintas chapter |
| `chapter` | `ch006` … `ch060` |
| `panel` | Indeks potongan gambar dalam chapter (gambar webtoon dipotong per ±1600 px, atas → bawah) |
| `urut_panel` | Urutan teks di dalam potongan itu |
| `bubble_id` | ID unik teks, `chNNN_panel_PPP_BB` |
| `jenis_kotak` | `dialog_bubble` (balon bicara, 5.471) atau `narration_box` (kotak narasi/pikiran, 1.811) |
| `pembicara` | Nama tokoh (Hangul), `anon_cNNN`, `Unknown`, `Narration`, atau `SFX` — lihat di bawah |
| `tipe` | Jenis teks — lihat di bawah |
| `teks` | **Teks final** (sudah dikoreksi bila ada koreksi OCR), satu baris |
| `layar` | `1` = teks yang tampil di layar HP/komputer (chat, komentar, notifikasi); 52 baris |
| `label_asli` | Label mentah dari anotator sebelum dibakukan |
| `teks_ocr_asli` | Teks OCR sebelum dikoreksi |
| `teks_dikoreksi` | `1` = teks OCR sudah diperbaiki (154 baris) |
| `teks_ragu` | `1` = koreksi teks masih ragu karena gambar kurang jelas (14 baris) |
| `catatan` | Catatan anotator |

### Nilai `pembicara`
- **Nama Hangul** (mis. 지수원 = Ji Suwon, 박동 = Park Dong): 22 tokoh bernama. Romanisasi ada di `tokoh.csv`.
- **`anon_cNNN`**: tokoh tanpa nama tapi wajahnya konsisten (dikenali dari cluster wajah), jadi bisa dianalisis sebagai satu orang.
- **`Unknown`**: figuran / pembicara yang tidak bisa ditentukan.
- **`Narration`**: narator, keterangan, teks sistem.
- **`SFX`**: efek suara yang tertulis di balon.

### Nilai `tipe`
| Tipe | Arti | Jumlah |
|---|---|---|
| `ucapan` | Diucapkan dengan suara | 5.469 |
| `pikiran` | Monolog batin tokoh | 1.301 |
| `narasi` | Narasi / keterangan (pembicara `Narration` atau `Unknown`) | 429 |
| `tulisan` | Teks yang **ditulis** tokoh: pesan chat, surat, komentar | 30 |
| `efek_suara` | Efek suara | 38 |
| `ingatan` | Kutipan ucapan masa lalu yang terngiang. Pembicara = **orang yang dulu mengucapkannya** | 15 |

## Cara membaca data (Python)

```python
import pandas as pd
df = pd.read_csv("dataset_final/dialog_final.csv", encoding="utf-8-sig")
tokoh = df[~df.pembicara.isin(["Unknown", "Narration", "SFX"])]
tokoh[tokoh.tipe == "ucapan"].groupby("pembicara").teks.count().sort_values()
```

Untuk profil gaya bicara biasanya pakai `tipe in ("ucapan", "tulisan")`; untuk sisi batin pakai `pikiran`.
Tokenisasi Korea: `kiwipiepy` atau `konlpy` (Okt/Mecab).

## Bagaimana data dibuat

1. Deteksi bubble & OCR otomatis (Magi + model OCR Korea) → `output_speaker_vf/`.
2. **Pembicara dan tipe dilabel manual** untuk semua chapter ch006–ch060.
   Anotator dibantu foto referensi wajah tiap tokoh. Semua label manual dianggap keyakinan tinggi.
3. Koreksi OCR untuk teks berskor OCR < 0,85 (dicek terhadap gambar).
4. Urutan baca dibakukan atas → bawah, kiri → kanan; bubble yang terbelah batas potongan atau terdeteksi ganda digabung.

Membangun ulang `dataset_final/` dari bahan mentah:

```bash
python -X utf8 build_final_dataset.py
```

## Keterbatasan yang perlu diketahui

- **Urutan bubble yang sejajar** (setinggi sama, berdampingan) mengikuti aturan *kiri dulu*; kasus ketika penulis
  meletakkan jawaban di kiri belum dicek satu per satu. Tidak berpengaruh untuk analisis per tokoh, tapi perlu hati-hati
  untuk analisis giliran bicara (siapa menjawab siapa).
- Teks dengan skor OCR ≥ 0,85 tidak dicek ulang; kemungkinan masih ada salah ketik kecil.
- 12 kotak narasi yang mungkin berupa ingatan dibiarkan sebagai `ucapan` karena ragu (lihat `annotations/koreksi_tipe.csv`).
- Slang/singkatan internet (ㅅㅂ, ㅋㅋ, ㅂㅅ) sengaja dipertahankan apa adanya.
- ch001–ch005 tidak termasuk.
