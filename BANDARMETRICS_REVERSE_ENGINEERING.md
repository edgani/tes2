# Bandarmetrics.com — Reverse-Engineering Analysis

Tujuan: nurunin formula tiap panel di bandarmetrics.com (ref: chart HUMI) supaya bisa direplikasi.
Gw jujur soal **tingkat keyakinan** tiap formula dan **data apa yang gw butuh** buat bikin EXACT.

## Yang kebaca dari chart HUMI (titik kalibrasi)
```
O 146 · H 149 · L 136 · C 136 · Volume 59,896,200
LPM (Liquidity Pressure Model) = -371,489,575.45   (garis teal)
Foreign Flow                   = -34,209,819,300    (garis biru)
Corr F = 0.642 · Par F = 13.05%
```
Turnover harian ≈ C×Vol ≈ 136 × 59.9jt ≈ **Rp 8.1 T/hari**.
→ LPM (-371jt) ≈ **4.6% dari turnover harian** → LPM itu **net-flow window pendek / oscillator**, BUKAN kumulatif all-time (kalau kumulatif pasti triliunan).
→ Foreign Flow (-34.2 M lot? atau -34.2 T?) jauh lebih gede → ini **kumulatif foreign net value**.

---

## 1. LPM — Liquidity Pressure Model  ⚠️ butuh kalibrasi
**Konsep:** tekanan beli-jual bersih dalam satuan uang. Garis teal yang naik = tekanan beli akumulatif, turun = tekanan jual.

**Formula turunan (paling mungkin):**
```
money_flow_bar = ((C - L) - (H - C)) / (H - L) × Volume × C      # CLV × Vol × harga (signed money flow)
LPM            = EMA_n( Σ money_flow_bar )                         # akumulasi, lalu smoothing
```
- CLV (Close Location Value) = `((C-L)-(H-C))/(H-L)` ∈ [-1,+1]: +1 close di high (beli kuat), -1 close di low (jual kuat).
- Skala -371jt yang kecil relatif turnover → kemungkinan **window** (mis. Σ 20-60 hari) ATAU **net** (beli−jual saling cancel, sisa kecil). Gw default ke kumulatif+EMA tapi **butuh data buat mastiin apakah windowed**.

**Keyakinan: 60%** (struktur yakin: signed money-flow akumulasi; skala/window perlu fit).

---

## 2. Foreign Flow  ❌ TIDAK BISA tanpa data Type-F
**Konsep:** akumulasi net beli asing (Rupiah). -34.2 → asing net jual besar.
**Formula:** `Foreign Flow = Σ (Foreign_Buy_Value − Foreign_Sell_Value)` per hari.
**Masalah:** butuh **data Type-F IDX** (volume/value beli-jual asing per hari). **Ini GAK ADA di yfinance.** Sumbernya: broker summary IDX, Invezgo, GOAPI, RapidAPI IDX, atau scrape Stockbit/RTI.
→ **Tanpa data ini, Foreign Flow mustahil direplikasi.** Ini bukan soal formula, tapi soal sumber data.

**Yang gw butuh dari lu:** export/feed harian `(tanggal, foreign_buy_value, foreign_sell_value)` per ticker. Kalau ada, langsung gw masukin (interface-nya udah gw siapin di engine: `foreign_flow_metrics`).

---

## 3. Intensity  ✅ bisa dari OHLCV
**Konsep:** lonjakan aktivitas gak wajar — bar ungu nongol pas ada volume/pergerakan anomali (spike Jan di HUMI).
**Formula turunan:**
```
effort      = Volume × |C − C_prev| / C_prev          # effort = volume × magnitude gerak
intensity_z = (effort − mean_20(effort)) / std_20(effort)
Intensity   = intensity_z  jika > ambang (≈1.5), else 0
```
Ini nangkep "effort" (usaha) — volume gede + gerak gede = intensitas tinggi. Cocok sama bar ungu yang cuma spike sesekali.

**Keyakinan: 70%** (volume×range z-score adalah standar buat "intensity/effort"; ambang perlu fit).

---

## 4. Vol Rotation  ✅ bisa dari OHLCV
**Konsep:** volume diklasifikasi — **ijo** = rotasi efisien/akumulasi (close naik di volume), **merah** = distribusi (close turun di volume), **kuning** = churning/netral (volume gede tapi gerak kecil = barang muter doang).
**Formula turunan:**
```
efficiency = |C − O| / (H − L)            # 0..1: gerak bersih vs range (efisien vs churn)
direction  = sign(C − O)
rot_score  = direction × efficiency × volume_z
warna      = ijo  kalau rot_score > +0.15
             merah kalau rot_score < −0.15
             kuning selainnya  (volume ada tapi gak efisien/netral = churn)
```
Spike merah di HUMI = distribusi (jual di volume tinggi). Kuning dominan = churning.

**Keyakinan: 65%** (logika warna yakin; threshold perlu fit).

---

## 5. Avg Cost  ✅ bisa dari OHLCV (proxy)
**Konsep:** harga modal rata-rata bandar (garis acuan).
**Formula:** `AvgCost = VWAP_window` atau `EMA_60(typical_price)`, typical = (H+L+C)/3.
**Keyakinan: 55%** (kalau mereka pakai broker-level avg price, beda; ini proxy VWAP).

---

## 6. Corr F & Par F  ❌ butuh data Type-F
- **Par F (Participation Foreign) = 13.05%** → `foreign_value / total_value` (window tertentu). Butuh Type-F.
- **Corr F = 0.642** → korelasi antara `Foreign Flow` dan `harga` (rolling, mis. 20-60 hari). Butuh Type-F.

---

## Kenapa gw GAK BISA klaim "formula EXACT" cuma dari screenshot
Reverse-engineer exact = gw butuh **pasangan data**: untuk N tanggal, gw butuh **nilai yang bandarmetrics tampilkan** (LPM, Intensity, VolRotation) DI tanggal itu, terus gw fit ke OHLCV yang gw fetch sendiri. Dari 1 screenshot gw cuma dapet 1 titik (nilai terkini) — gak cukup buat solve koefisien/window.

### Data yang gw butuh buat bikin EXACT (lu nawarin — ini list-nya):
1. **Buat 1-2 saham** (mis. HUMI + BBCA): nilai **LPM, Intensity, Vol Rotation** di **~20-30 tanggal** (hover di chart bandarmetrics, atau kalau ada export). Gw fetch OHLCV-nya sendiri terus fit formula + window-nya sampe match.
2. **Buat Foreign Flow / Corr F / Par F:** feed harian `(tanggal, foreign_buy_value, foreign_sell_value)` — atau sumber API Type-F yang lu mau gw colok.
3. Konfirmasi window default mereka (banyak tool IDX pakai **20D** atau **akumulasi sejak listing**).

Kasih salah satu aja udah cukup buat gw naikin keyakinan dari ~60% ke >90% + verifikasi numerik.
