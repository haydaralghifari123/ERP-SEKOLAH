# Rancangan: `nti_edu_tagihan` (Tagihan & Pembayaran Siswa)

Tanggal: 2026-11-26 · Fase 1 · Induk: `docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md` (aturan §I.4
berlaku penuh; dokumen ini hanya menambah yang khusus modul tagihan).

## 1. Maksud dan alasan

Bendahara di tiap unit perlu menagih biaya sekolah (SPP, uang pangkal, kegiatan, dll.), menerima pembayaran, dan
mengetahui tunggakan; orang tua perlu melihat tagihan anaknya dan melaporkan transfer tanpa harus datang atau
mengirim foto lewat WA. Yayasan perlu satu pembukuan yang rapi (yayasan = root company, unit = branch, §I.5.4).

NTI Edu adalah produk yang dijual ke banyak sekolah, jadi **semua skema biaya dan aturan tagihan diatur admin lewat
data konfigurasi**, tanpa angka atau aturan yang tertanam di kode (keputusan pengguna 2026-11-26: "jadikan dinamis,
diatur admin" — berlaku untuk semua fitur yang skemanya bisa berbeda antar sekolah). Batasan §I.4.6 tetap berlaku:
tidak ada rumus Python bebas di modul ini; "dinamis" = record konfigurasi dengan pilihan terstruktur.

## 2. Sasaran, bukan sasaran, anti-sasaran

**Sasaran**
- Admin Keuangan mengatur komponen biaya, skema biaya per unit + tahun ajaran (nominal bisa beda per tingkat/jurusan),
  jenis potongan, aturan cicilan, aturan denda, dan pengaturan pembuatan/pengingat tagihan.
- Tagihan dibuat otomatis (jadwal harian) dan manual (tombol per periode/rombel), tanpa tagihan ganda.
- Orang tua (portal) melihat tagihan & riwayat anaknya, mengunggah bukti transfer; bendahara memverifikasi.
- Bendahara mencatat pembayaran tunai/langsung, memecah tagihan menjadi cicilan, mengelola denda.
- Kartu SPP (PDF) per siswa per tahun ajaran; daftar tunggakan per unit/rombel/siswa.
- Pembukuan benar otomatis: tagihan = invoice Odoo, pembayaran = payment Odoo yang direkonsiliasi.
- Lulus uji pasang tunggal (DB berisi hanya `nti_edu_base`, `nti_edu_tagihan`, dan dependensi standar).

**Bukan sasaran (di modul lain / nanti)**
- Payment gateway / VA otomatis → varian `nti_edu_payment_*`.
- Notifikasi WhatsApp/SMS → `nti_edu_notifikasi` + jembatan; modul ini hanya email (templat Odoo).
- Laporan keuangan yayasan, RKAS, BOS → `nti_edu_akuntansi`.
- Iuran ekskul, denda perpustakaan, biaya pendaftaran PPDB → jembatan masing-masing (memanggil API pembuatan
  tagihan modul ini, §4.6).
- Tabungan siswa/kantin, koperasi → modul opsional.
- Pengembalian dana (refund) → nota kredit standar Odoo apa adanya.

**Anti-sasaran (gagal walau berjalan)**
- Wali melihat tagihan siswa yang bukan anaknya; siswa melihat tagihan siswa lain.
- Bendahara unit A melihat/mengubah tagihan atau pembayaran unit B.
- Siswa tertagih dua kali untuk komponen + periode yang sama.
- Mengubah skema/potongan diam-diam mengubah tagihan yang sudah terbit.
- Bukti transfer diterima tetapi invoice tidak tercatat lunas (atau sebaliknya) — status tagihan dan pembukuan berbeda.
- Bendahara butuh menu/konfigurasi Akuntansi penuh untuk pekerjaan sehari-hari.
- Konfigurasi begitu rumit sehingga admin sekolah butuh developer.

## 3. Pendekatan yang dipertimbangkan

1. **Tagihan = invoice Odoo (`account.move` out_invoice) yang diperluas (DIPILIH pengguna).** Field sekolah
   (siswa, komponen, periode, tahun ajaran, rombel saat terbit) ditambahkan ke invoice. Potongan = baris minus;
   cicilan = termin pembayaran Odoo; bukti transfer = model sendiri yang saat diterima membuat payment Odoo dan
   merekonsiliasinya. Satu sumber kebenaran; status lunas, umur piutang, pembukuan langsung benar; `nti_edu_akuntansi`
   tinggal melanjutkan. Risiko: invoice Odoo rumit, hak akses harus dijaga.
2. Lapisan "Tagihan Siswa" sendiri yang membuat invoice di belakangnya — kartu SPP & cegah ganda lebih mudah, tetapi dua
   data yang harus sinkron (invoice dibatalkan di Akuntansi → tidak cocok). Ditolak.
3. Tagihan tanpa invoice (pembukuan menyusul) — bertentangan dengan peta modul (basis `account`) dan menggandakan
   pekerjaan akuntansi. Ditolak.

## 4. Rancangan

### 4.1 Manifest
`'depends': ['nti_edu_base', 'account', 'portal']`, kategori Education, LGPL-3, `18.0.1.0.0`, `application: True`
(app **Keuangan Sekolah**). Tanpa `auto_install`.

### 4.2 Konfigurasi (data master diatur Admin Keuangan; pengaturan kebijakan oleh Admin Sistem)

Prinsip (keputusan pengguna 2026-11-26): setiap pilihan yang bisa berbeda antar sekolah adalah **data master** yang
dibuat/diubah/diarsipkan admin di menu Konfigurasi, bukan daftar tetap di kode. Yang tetap di kode hanya **jenis
perilaku** yang butuh logika program (mis. denda tetap vs persen); admin bebas membuat aturan sebanyak apa pun dari
jenis-jenis itu. Semua master punya `name`, `company_id` opsional (kosong = semua unit), `active`, urutan; data awal
menyediakan contoh yang langsung bisa dipakai. Mengubah master hanya berpengaruh pada tagihan/denda/cicilan yang
dibuat sesudahnya.

**Periode tagihan — `nti_edu.tagihan.periode.jenis`**
- `dasar`: `bulan` (kelipatan bulan dihitung dari awal tahun ajaran) / `semester` (mengikuti semester base) /
  `tahun_ajaran` / `sekali`; `jumlah_bulan` untuk dasar `bulan` (1 = bulanan, 3 = triwulan, …).
- `hari_terbit` (tanggal terbit dalam bulan pertama periode) dan `hari_jatuh_tempo` (tanggal jatuh tempo dalam bulan
  pertama periode; untuk `sekali`: jumlah hari setelah terbit).
- `bulan_libur_ids` (dasar `bulan`: bulan yang tidak ditagih, mis. Juni) — m2m ke 12 record bulan (data awal).
- Data awal: Bulanan, Semester, Tahunan, Sekali.

**Aturan denda — `nti_edu.tagihan.aturan.denda`**
- `tipe` (`tetap` / `persen` dari sisa tagihan atau sisa cicilan), `nilai`, `berulang` (`sekali` / `per_bulan`
  keterlambatan), `tenggang_hari`, `maks` (nominal maksimum total per tagihan; 0 = tanpa batas), `komponen_denda_id`
  (komponen jenis `denda` yang dipakai untuk menagih). Satu aturan bisa dipakai banyak komponen.
- Data awal: contoh "Denda Rp10.000 per bulan, tenggang 7 hari" (tidak terpasang ke komponen mana pun).

**Aturan cicilan — `nti_edu.tagihan.aturan.cicilan`**
- `maks_kali`, `jarak` + `jarak_satuan` (`hari` / `bulan`), `uang_muka_persen` (0 = tanpa uang muka; bila diisi,
  cicilan pertama minimal sebesar itu).
- Data awal: "Cicil 4× bulanan", "Cicil 2× per 6 bulan".

**Aturan siswa masuk tengah — `nti_edu.tagihan.aturan.masuk`**
- `cara`: `penuh` / `berikutnya` (mulai periode berikutnya) / `prorata` (dibagi per bulan tersisa dalam periode,
  dibulatkan ke rupiah). Tidak relevan untuk periode 1 bulan (selalu mulai bulan masuk).
- Data awal: "Tagih penuh" (bawaan komponen baru), "Mulai periode berikutnya", "Prorata per bulan".

**Rekening pembayaran — `nti_edu.tagihan.rekening`**
- bank, nomor rekening, atas nama, `company_ids` (unit yang memakai; kosong = semua), `journal_id` (jurnal bank/kas
  Odoo tempat payment dicatat), instruksi transfer (HTML). Ditampilkan di portal dan dipilih saat konfirmasi transfer
  & Terima Pembayaran.

**Alasan penolakan transfer — `nti_edu.tagihan.alasan.tolak`** dan **alasan penghapusan denda —
`nti_edu.tagihan.alasan.hapus`**
- name, `perlu_catatan` (catatan bebas wajib bila dicentang). Dipilih bendahara saat menolak konfirmasi / menghapus
  denda; alasan tampil di portal (tolak) dan chatter.
- Data awal: "Bukti tidak terbaca", "Nominal tidak sesuai", "Transfer tidak ditemukan di rekening", "Lainnya"
  (perlu catatan); "Kebijakan sekolah", "Kesalahan sistem", "Lainnya" (perlu catatan).

**Komponen biaya — `nti_edu.tagihan.komponen`**
- name, kode, company_id (opsional), urutan, aktif.
- `jenis`: `biaya` (biasa) / `denda` (dipakai aturan denda; tidak masuk skema).
- `periode_jenis_id`, `aturan_masuk_id` (bawaan "Tagih penuh"), `aturan_cicilan_id` (kosong = tidak boleh dicicil),
  `aturan_denda_id` (kosong = tanpa denda) — semuanya memilih dari master di atas.
- Akun pendapatan (produk layanan dibuat otomatis di belakang komponen, tidak terlihat bendahara).

**Skema biaya — `nti_edu.tagihan.skema`**
- company_id (unit, wajib), tahun_ajaran_id, state (`draft`/`aktif`/`arsip`), baris_ids.
- Satu skema aktif per (unit, tahun ajaran).
- **Baris skema** `nti_edu.tagihan.skema.baris`: komponen_id, tingkat_id (opsional), jurusan_id (opsional), nominal.
  Pencocokan siswa → baris paling spesifik: tingkat+jurusan > tingkat > jurusan > umum. Constraint: tidak ada dua
  baris dengan komponen + tingkat + jurusan yang sama.
- Skema yang sudah aktif tetap boleh diubah, tetapi perubahan **hanya berlaku untuk tagihan yang terbit sesudahnya**;
  tagihan lama tidak disentuh (anti-sasaran 4). Ada tombol "Salin ke tahun ajaran berikutnya".

**Jenis potongan — `nti_edu.tagihan.potongan.jenis`**
- name, company_id (opsional), tipe (`persen`/`nominal`), nilai_bawaan, komponen_ids (berlaku untuk komponen apa),
  `dapat_digabung` (bool), `perlu_persetujuan` (bool: potongan siswa jenis ini aktif hanya setelah disetujui Admin
  Keuangan).

**Potongan siswa — `nti_edu.tagihan.potongan`**
- siswa_id, jenis_id, nilai (bawaan dari jenis, boleh diubah), tanggal_mulai, tanggal_selesai, alasan, lampiran,
  state (`draft`/`menunggu`/`aktif`/`berakhir`/`ditolak`), company_id (= unit siswa).
- Potongan yang disetujui/dimulai mundur **tidak mengubah tagihan yang sudah terbit secara diam-diam**. Form potongan
  punya tombol eksplisit **Terapkan ke Tagihan Terbit**: untuk tagihan belum lunas dalam rentang tanggal potongan,
  dibuat nota kredit sebesar selisih potongan (tercatat di chatter tagihan dan potongan). Tagihan yang sudah lunas
  tidak disentuh (kelebihan ditangani manual lewat nota kredit standar).
- Penerapan saat tagihan terbit: potongan aktif pada tanggal periode untuk komponen itu. Jika ada lebih dari satu:
  semua yang `dapat_digabung` dijumlah, yang tidak dapat digabung → diambil yang terbesar, lalu dibandingkan dan
  dipakai yang menghasilkan potongan terbesar (keputusan Claude). Total potongan tidak melebihi nominal komponen.
- Potongan tampil sebagai **baris minus** di invoice ("Potongan Beasiswa Prestasi").

**Pengaturan per unit** (Keuangan Sekolah › Konfigurasi › Pengaturan; field di `res.company`, diatur per unit lewat
pemilih company). **Pengaturan kebijakan ini hanya bisa diubah Admin Sistem** (`base.group_system`, admin seluruh
sistem — keputusan pengguna 2026-11-26); Admin Keuangan bisa melihatnya. Setiap pilihan punya nilai bawaan yang aman
sehingga sistem langsung jalan tanpa diatur.
- `akses_pembukuan` — cakupan yang dilihat Bendahara Unit dan Pemantau Keuangan di unit itu:
  `dokumen_sekolah` (bawaan: hanya tagihan siswa dan pembayaran/payment yang dibuat modul ini) atau `semua` (seluruh
  invoice, tagihan vendor, payment, dan jurnal unit itu, mis. bila bendahara unit juga mengurus belanja). Grup
  Akuntansi Odoo (akuntan yayasan) dan Admin Sistem tidak terpengaruh dan selalu melihat semuanya.
- `tagihan_otomatis` (jadwal harian pembuatan tagihan on/off).
- `tagihan_mulai` (tanggal, wajib sebelum `tagihan_otomatis` bisa dinyalakan): jadwal dan wizard tidak pernah
  menerbitkan tagihan untuk periode yang dimulai sebelum tanggal ini, dan komponen `sekali` tidak ditagihkan ke siswa
  yang masuk rombel sebelum tanggal ini. Ini untuk sekolah yang mulai memakai sistem di tengah tahun ajaran.
- `denda_saldo_awal` (bool, bawaan mati): apakah tunggakan saldo awal (lihat §4.3) ikut dikenai denda.
- `tagihan_jurnal_id` (jurnal penjualan untuk tagihan; bawaan jurnal penjualan yayasan).
- `pengingat_hari` (kirim email pengingat N hari sebelum jatuh tempo; 0 = mati) dan `pengingat_tunggakan` (kirim
  ringkasan tunggakan tiap N hari; 0 = mati).
- `denda_hapus_perlu_admin` (penghapusan denda hanya Admin Keuangan; bila mati, bendahara boleh dengan alasan).
- `wali_kelas_lihat_tunggakan` (wali kelas boleh melihat daftar tunggakan rombelnya; bawaan mati).
- `bukti_ukuran_maks_mb` (batas ukuran unggahan bukti; bawaan 5).
- Templat email (terbit, pengingat, konfirmasi diterima/ditolak) memakai `mail.template` yang bisa diedit admin.

### 4.3 Tagihan (perluasan `account.move`)
Field baru di invoice: `nti_edu_siswa_id` (= partner invoice, siswa), `nti_edu_komponen_id`, `nti_edu_periode`
(tanggal awal periode: bulan / awal semester / awal tahun ajaran; kosong untuk `sekali`), `nti_edu_tahun_ajaran_id`,
`nti_edu_semester_id`, `nti_edu_rombel_id` (rombel saat terbit — snapshot), `nti_edu_tagihan_asal_id` (untuk denda:
tagihan yang terlambat), `nti_edu_denda_ke` (urutan denda per tagihan asal).

- **Satu invoice = satu siswa + satu komponen + satu periode.** Partner invoice = **siswa**, sehingga riwayat dan
  kartu SPP melekat ke anak dan tidak rusak bila penanggung biaya berganti. Company invoice = unit siswa.
- **Cegah ganda di database**: indeks unik parsial pada (siswa, komponen, periode) untuk invoice yang tidak
  dibatalkan; `sekali` → (siswa, komponen) sekali seumur hidup; denda → (tagihan asal, denda_ke).
- Tagihan terbit dalam status **posted** (langsung menjadi piutang).
- **Pembuatan** — mesin yang sama dipakai jadwal dan tombol manual:
  - Siswa yang ditagih: `nti_edu_status = aktif` dan menjadi anggota rombel di unit itu pada tanggal periode
    (`_nti_edu_rombel_pada`); tingkat/jurusan diambil dari rombel itu. Siswa pindah/keluar/lulus tidak dibuatkan
    tagihan baru; tunggakan lama tetap.
  - Periode mengikuti master periode komponen: dasar `bulan` → setiap `jumlah_bulan` bulan dalam tahun ajaran
    (kecuali bulan libur), dasar `semester` → per semester base, `tahun_ajaran` → per tahun ajaran, `sekali` → sekali,
    saat siswa pertama kali cocok dengan baris skema yang memuat komponen itu (mis. uang pangkal hanya diisi untuk
    tingkat awal). Siswa yang masuk rombel di tengah periode diperlakukan menurut aturan masuk komponen.
  - Jadwal harian (`ir.cron`): untuk unit dengan `tagihan_otomatis`, terbitkan tagihan periode yang `hari_terbit`-nya
    sudah lewat dan belum ada. Aman dijalankan berulang (indeks unik).
  - Wizard **Buat Tagihan** (bendahara): pilih komponen, periode, rombel (opsional, bawaan semua), tampilkan pratinjau
    jumlah siswa & total, lalu terbitkan. Siswa yang sudah punya tagihan itu dilewati dan dilaporkan.
- **Batal/koreksi**: bendahara membatalkan tagihan yang belum dibayar (tombol batal Odoo, wajib alasan di chatter);
  yang sudah dibayar → nota kredit standar.
- **Saldo awal tunggakan**: wizard **Tunggakan Awal** (Admin Keuangan/bendahara) untuk memasukkan tunggakan dari
  sebelum `tagihan_mulai` — per baris: siswa, komponen, periode, sisa. Menjadi tagihan biasa bertanda
  `nti_edu_saldo_awal` (ikut indeks unik, kartu SPP, portal, tunggakan); denda hanya bila `denda_saldo_awal`.
  Bisa diisi juga lewat impor standar Odoo dari berkas (impor Dapodik/Excel lanjutan → `nti_edu_import`).
- **API untuk jembatan**: `env['account.move']._nti_edu_buat_tagihan(siswa, komponen, nominal, sumber,
  keterangan=None)` → invoice, dengan `sumber` = record asal (mis. pendaftaran ekskul, peminjaman buku) disimpan di
  field `nti_edu_sumber` (referensi `model,id`). Tagihan jembatan **tidak** memakai skema dan potongan; denda tetap
  mengikuti pengaturan komponen yang dipilih jembatan. Kunci cegah ganda tagihan jembatan = `nti_edu_sumber`
  (unik bila diisi); indeks (siswa, komponen, periode) hanya berlaku untuk tagihan tanpa sumber. Partner wajib siswa
  (`nti_edu_is_siswa`); kebutuhan menagih pendaftar PPDB yang belum menjadi siswa diputuskan di desain PPDB.

### 4.4 Cicilan
- Tombol **Atur Cicilan** di tagihan yang komponennya punya `aturan_cicilan_id` dan belum ada pembayaran: pilih
  jumlah kali (≤ `maks_kali` aturan); jatuh tempo berjarak `jarak` `jarak_satuan`; bila ada `uang_muka_persen`,
  cicilan pertama sebesar itu dan sisanya dibagi rata, selain itu semua dibagi rata (sisa pembulatan di cicilan
  terakhir). Tagihan dikembalikan ke draft, diberi termin pembayaran Odoo yang sesuai (dibuat/dipakai ulang
  otomatis), lalu di-post lagi. Riwayat di chatter.
- Status per cicilan mengikuti baris piutang (`date_maturity`, sisa) — dipakai mesin denda dan kartu SPP.

### 4.5 Denda keterlambatan
- Jadwal harian: untuk tagihan posted dengan sisa > 0 yang komponennya punya `aturan_denda_id`, bila jatuh tempo
  (per cicilan, bila dicicil) + `tenggang_hari` sudah lewat → terbitkan tagihan denda (komponen `komponen_denda_id`
  aturan, `tagihan_asal_id`, `denda_ke`). `sekali` → satu denda; `per_bulan` → satu denda per tiap bulan
  keterlambatan penuh. Nominal tetap atau persen dari sisa pada saat itu; berhenti bila total denda mencapai `maks`.
  Aturan yang dipakai = aturan komponen pada saat denda dibuat.
- **Tagihan bercicilan**: denda dihitung **per cicilan yang terlambat** — persen dari sisa cicilan itu; `sekali` =
  sekali per cicilan; `per_bulan` = per bulan keterlambatan cicilan itu. `denda_ke` dinomori berurutan per tagihan
  asal (lintas cicilan); kunci cegah ganda = (tagihan asal, jatuh tempo cicilan, ke-n bulan). `maks` tetap satu
  total per tagihan asal.
- Tagihan yang terbit untuk periode sebelum `tagihan_mulai` tidak ada; denda hanya untuk jatuh tempo setelah
  `tagihan_mulai` (dan saldo awal hanya bila `denda_saldo_awal`).
- Denda tidak dikenai denda lagi.
- **Hapus denda**: tombol pada tagihan denda (batal bila belum dibayar), wajib memilih alasan dari master alasan
  penghapusan (+ catatan bila alasan mewajibkannya); dibatasi Admin Keuangan bila `denda_hapus_perlu_admin`.

### 4.6 Pembayaran

**Konfirmasi transfer dari portal — `nti_edu.tagihan.konfirmasi`**
- pengirim (partner user portal/internal yang mengunggah), company_id (unit), tagihan_ids (m2m invoice), siswa_ids
  (compute), tanggal_transfer, nominal, rekening_id (master rekening pembayaran yang berlaku untuk unit itu),
  nama_pengirim rekening, bukti (lampiran: jpg/png/pdf, ≤ batas ukuran), catatan, state
  (`menunggu`/`diterima`/`ditolak`), alasan_tolak_id (master) + catatan_tolak, payment_ids, diverifikasi_oleh,
  tanggal_verifikasi. Chatter.
- Satu konfirmasi boleh mencakup beberapa tagihan dan beberapa anak, **tetapi hanya dari satu unit** (bendahara unit
  memverifikasi unitnya sendiri). Portal mengelompokkan pilihan per unit; wali dengan anak di dua unit mengunggah dua
  kali (berkas boleh sama). Keputusan Claude.
- **Terima** (bendahara unit): nominal diterima boleh dikoreksi bendahara (bawaan = nominal laporan); dialokasikan
  ke tagihan terpilih mulai jatuh tempo paling lama; dibuat satu payment Odoo per siswa pada jurnal rekening
  dan direkonsiliasi dengan tagihan-tagihan siswa itu. **Kelebihan** bayar menjadi saldo kredit siswa (outstanding
  credit Odoo) yang ditampilkan di form siswa & portal; bendahara menerapkannya ke tagihan berikut secara manual
  (keputusan Claude). Email "diterima" ke pengirim.
- **Tolak**: alasan wajib (pilih dari master alasan penolakan, + catatan bila alasan mewajibkannya), tampil di
  portal, email "ditolak". Konfirmasi ditolak tidak bisa diubah; wali membuat
  konfirmasi baru.
- Tagihan yang sedang ada di konfirmasi `menunggu` ditandai "Menunggu Verifikasi" di portal dan backend, tetapi tetap
  bisa dibayar tunai; saat diverifikasi, alokasi hanya ke sisa yang masih ada (kelebihan → saldo kredit).
- Antrean verifikasi: Keuangan Sekolah › Konfirmasi Transfer (bawaan filter `menunggu`), pratinjau bukti di form.

**Pembayaran langsung (tunai/transfer yang diterima bendahara)** — wizard **Terima Pembayaran** dari form siswa atau
daftar tagihan: pilih tagihan (bawaan semua yang terbuka, urut jatuh tempo), nominal, jurnal (kas/bank), tanggal →
payment + rekonsiliasi dengan alokasi yang sama. Cetak kuitansi = laporan tanda terima pembayaran Odoo
(`account.report_payment_receipt`) dengan judul/kop unit.

### 4.7 Kartu SPP dan tunggakan
- **Kartu SPP** (QWeb PDF) per siswa per tahun ajaran: tabel komponen bulanan × bulan (nominal, potongan, tanggal
  lunas / sisa / belum terbit), lalu daftar komponen non-bulanan & denda, total tagihan, total dibayar, sisa, saldo
  kredit. Dari form siswa (tab **Keuangan**) dan portal.
- **Tunggakan**: menu daftar tagihan terbuka yang lewat jatuh tempo, list + pivot, kelompok per unit/rombel/siswa/
  komponen, kolom umur (0–30, 31–60, 61–90, >90 hari). Tombol "Kirim Pengingat" massal (email ke wali penanggung
  biaya).
- Tab **Keuangan** di form siswa (field ber-`groups` grup tagihan): ringkasan sisa, tunggakan, saldo kredit,
  potongan aktif, daftar tagihan, tombol Kartu SPP / Terima Pembayaran.
- Wali kelas (bila `wali_kelas_lihat_tunggakan`): menu **Tunggakan Rombel Saya** — daftar baca-saja (dibaca lewat
  `sudo` setelah memastikan user adalah wali kelas rombel itu), hanya nama siswa, komponen, sisa, jatuh tempo.

### 4.8 Portal
- Kartu **Tagihan** di `/my` dan halaman `/my/tagihan` (pakai pemilih anak aktif base): tagihan belum lunas (dengan
  status "Menunggu Verifikasi" / cicilan), riwayat lunas, total tunggakan, saldo kredit, rekening tujuan + instruksi
  unit, unduh invoice PDF dan Kartu SPP.
- Form **Konfirmasi Transfer**: pilih tagihan (satu unit), nominal, tanggal, rekening tujuan, nama pemilik rekening,
  unggah bukti, catatan. Daftar konfirmasi + status + alasan tolak.
- Semua data dibaca lewat `sudo` setelah siswa dipastikan ada di helper akses anak base (§II.5). Konfirmasi hanya
  boleh memuat tagihan milik anak-anak itu (dicek ulang di server).
- Anak yang **tidak lagi aktif** (lulus/pindah/keluar) tetapi masih punya tagihan terbuka tetap tampil di halaman
  tagihan. Untuk itu helper base `_nti_edu_siswa_portal()` diberi parameter opsional (`termasuk_nonaktif=False`);
  perilaku bawaan tidak berubah (perubahan kecil di `nti_edu_base`, keputusan Claude).
- Siswa yang punya akun portal sendiri melihat tagihannya (baca saja) dan boleh mengirim konfirmasi.
- Halaman bawaan Odoo `/my/invoices` tidak diubah (wali tidak melihat apa-apa di sana karena invoice atas nama siswa;
  siswa melihat invoice sendiri — wajar).

### 4.9 Notifikasi (email)
- Tagihan terbit (opsional per unit, ringkas per wali: satu email berisi semua tagihan baru anak-anaknya dalam satu
  jalan pembuatan), pengingat sebelum jatuh tempo, ringkasan tunggakan berkala, konfirmasi diterima/ditolak.
- Penerima: wali dengan `is_penanggung_biaya` yang punya email; bila tidak ada, wali kontak utama; bila tidak ada,
  tidak dikirim (tercatat di chatter).

### 4.10 Menu (app "Keuangan Sekolah")
```
Keuangan Sekolah
├─ Tagihan            (semua tagihan sekolah; list/form invoice dengan tampilan sendiri)
├─ Konfirmasi Transfer (antrean verifikasi)
├─ Pembayaran          (payment yang dibuat modul ini)
├─ Tunggakan           (list/pivot + umur)
├─ Tunggakan Rombel Saya (wali kelas; hanya bila pengaturan menyala)
├─ Potongan Siswa
├─ Proses
│   └─ Buat Tagihan    (wizard)
└─ Konfigurasi         (Admin Keuangan; Pengaturan diubah Admin Sistem)
    ├─ Komponen Biaya
    ├─ Skema Biaya
    ├─ Jenis Potongan
    ├─ Periode Tagihan
    ├─ Aturan Denda
    ├─ Aturan Cicilan
    ├─ Aturan Siswa Masuk Tengah
    ├─ Rekening Pembayaran
    ├─ Alasan Penolakan Transfer
    ├─ Alasan Penghapusan Denda
    └─ Pengaturan
```
Tampilan invoice untuk app ini memakai view list/form sendiri (field sekolah di depan, tanpa tab akuntansi lanjutan);
form invoice standar Akuntansi tetap ada untuk akuntan.

### 4.11 Grup dan hak akses (kategori "NTI Edu / Tagihan")
| Grup | Implies | Hak |
|---|---|---|
| `group_tagihan_pemantau` (Pemantau Keuangan, mis. kepala sekolah/pengurus) | `nti_edu_base.group_base_pengguna`, `account.group_account_readonly` | Baca tagihan, pembayaran, tunggakan, kartu SPP, potongan di unit yang diizinkan. Tanpa ubah. |
| `group_tagihan_bendahara` (Bendahara Unit) | pemantau, `account.group_account_invoice` | Buat tagihan (wizard), batalkan tagihan belum dibayar, atur cicilan, terima pembayaran, verifikasi konfirmasi, ajukan/kelola potongan siswa (yang `perlu_persetujuan` menunggu admin), hapus denda bila diizinkan pengaturan. Baca konfigurasi. |
| `group_tagihan_admin` (Admin Keuangan Yayasan) | bendahara | Kelola komponen, skema, jenis potongan; setujui potongan; hapus data konfigurasi; baca pengaturan kebijakan; semua unit yang diizinkan. |

- **Admin Sistem** (`base.group_system`) otomatis mendapat `group_tagihan_admin` dan satu-satunya yang mengubah
  pengaturan kebijakan (§4.2).
- Isolasi unit: aturan multi-company standar `account.move`/`account.payment` + rule baru untuk model modul ini
  (`company_id in company_ids`). Bendahara diberi hanya unitnya di *allowed companies*; Admin Keuangan diberi yayasan
  dan semua unit.
- **Cakupan pembukuan** (`akses_pembukuan`): rule grup pada `account.move`, `account.move.line`, `account.payment`
  untuk grup Pemantau/Bendahara: dokumen modul ini (punya `nti_edu_komponen_id`, atau payment yang dibuat modul ini)
  **atau** company dokumen ber-`akses_pembukuan = semua`. Karena rule grup digabung OR, grup akuntan Odoo
  (`account.group_account_user` ke atas) dan Admin Sistem diberi rule terbuka `[(1, '=', 1)]` agar akuntan yang juga
  bendahara tidak ikut terbatasi. Tes wajib: bendahara tidak melihat tagihan vendor/jurnal lain pada mode bawaan,
  melihatnya pada mode `semua`, akuntan selalu melihat.
- Menu Akuntansi Odoo disembunyikan dari grup tagihan yang bukan akuntan (menu Keuangan Sekolah cukup); grup akuntan
  Odoo tetap bekerja seperti biasa.
- Wali kelas & portal tidak diberi ACL ke model tagihan; mereka membaca lewat `sudo` di balik pemeriksaan akses (pola
  base).
- Penjaga tulis: field sekolah di invoice (`nti_edu_*`) hanya ditulis mesin modul/oleh bendahara saat draft;
  konfirmasi hanya dapat diubah state-nya lewat tombol Terima/Tolak oleh bendahara unit itu.

### 4.12 Data awal & demo
- **Data awal** (`noupdate`, bisa diubah/diarsipkan admin): 12 record bulan, kategori produk "Biaya Sekolah",
  templat email, cron (pembuatan tagihan, denda, pengingat), komponen jenis `denda` bawaan "Denda Keterlambatan",
  dan contoh master dari §4.2 (periode, aturan denda/cicilan/masuk, alasan tolak/hapus).
- **Demo**: komponen SPP (Bulanan, tanpa cicilan, aturan denda Rp10.000/bulan tenggang 7 hari), Uang Pangkal (Sekali,
  aturan "Cicil 4× bulanan"), Kegiatan (Semester, aturan masuk "Prorata per bulan"); skema aktif SMP & SMA tahun
  ajaran berjalan dengan nominal beda per tingkat;
  jenis potongan Saudara Kandung 10% SPP (dapat digabung) dan Beasiswa Prestasi 100% SPP (perlu persetujuan);
  tagihan bulan-bulan berjalan untuk siswa demo, beberapa lunas, satu dicicil, satu tunggakan berdenda, satu
  konfirmasi transfer `menunggu` dari akun portal wali demo; user demo Bendahara SMP dan Admin Keuangan.
- Rekening demo: master rekening "Bank Yayasan" (jurnal bank yayasan) untuk kedua unit.

### 4.13 Tes (`post_install`, tanpa bergantung demo)
- Skema: baris paling spesifik terpilih; constraint baris ganda; satu skema aktif per unit+TA; perubahan skema tidak
  mengubah tagihan terbit.
- Pembuatan: bulanan sesuai tahun ajaran & bulan libur, mulai bulan masuk; semester/tahunan/sekali; siswa
  nonaktif dilewati; jalan ulang tidak menggandakan (indeks unik, juga lewat create langsung); wizard melaporkan
  yang dilewati.
- Potongan: persen/nominal, gabung vs terbesar, batas nominal, rentang tanggal, perlu persetujuan.
- Cicilan: pembagian & jatuh tempo, ditolak bila sudah ada pembayaran / melebihi maks / komponen tidak boleh cicil.
- Denda: sekali vs per bulan, tenggang, persen dari sisa, batas maks, per cicilan, tidak denda atas denda, hapus denda
  sesuai pengaturan.
- Konfirmasi: terima → payment per siswa, invoice lunas/sebagian, alokasi jatuh tempo terlama, kelebihan jadi kredit;
  tolak wajib alasan; satu unit per konfirmasi; tagihan anak orang lain ditolak di server.
- Terima Pembayaran tunai: alokasi & rekonsiliasi.
- Hak akses: bendahara SMP tidak melihat tagihan/konfirmasi SMA; pemantau tidak bisa mengubah; bendahara tidak bisa
  mengubah konfigurasi; wali portal hanya tagihan anaknya (termasuk anak lintas unit & anak nonaktif bertunggakan);
  wali kelas hanya rombelnya dan hanya bila pengaturan menyala.
- Portal (HTTP): halaman tagihan, unggah konfirmasi, tolak berkas terlalu besar/jenis salah.
- Kartu SPP: render PDF tanpa galat dengan cicilan, potongan, denda, kredit.
- Uji asap browser (tour) menu Keuangan Sekolah: tagihan, konfirmasi (terima/tolak), wizard buat tagihan, konfigurasi.
- Uji pasang tunggal: `scripts/uji_tunggal.ps1 -Modul nti_edu_tagihan`.

### 4.14 Keputusan Claude (silakan dicek pengguna)
1. Invoice atas nama **siswa**; wali penanggung biaya menerima email; semua wali anak itu melihat tagihan di portal.
2. Satu invoice per siswa + komponen + periode (bukan satu invoice bulanan berisi banyak komponen) — membuat cegah
   ganda, cicilan, denda, dan kartu SPP sederhana; konsekuensinya orang tua melihat beberapa baris per bulan.
3. Tagihan terbit langsung posted.
4. Konfirmasi transfer dibatasi satu unit; kelebihan bayar menjadi saldo kredit yang diterapkan manual.
5. Potongan bertumpuk: yang dapat digabung dijumlah, yang tidak → terbesar.
6. Parameter `termasuk_nonaktif` ditambahkan ke helper portal base.
7. Grup Pemantau Keuangan baca-saja (kepala sekolah/pengurus) ditambahkan.
8. Mulai di tengah tahun: pengaturan `tagihan_mulai` per unit + wizard Tunggakan Awal; saldo awal tidak didenda
   kecuali dinyalakan.
9. Tagihan jembatan memakai kunci `nti_edu_sumber`, tanpa skema/potongan, partner wajib siswa.
10. Denda bercicilan dihitung per cicilan terlambat.
11. Siswa masuk di tengah semester/tahun: master aturan masuk (`penuh`/`berikutnya`/`prorata`) dipilih per
    komponen, bawaan "Tagih penuh".
12. Potongan mundur hanya mengubah tagihan terbit lewat tombol eksplisit yang membuat nota kredit.
13. *(Diputuskan pengguna)* Cakupan pembukuan bendahara/pemantau adalah pengaturan per unit (bawaan: hanya dokumen
    sekolah), dan semua pengaturan kebijakan modul diubah oleh Admin Sistem. Konfigurasi biaya (komponen, skema,
    jenis potongan, master aturan) tetap oleh Admin Keuangan (+ Admin Sistem).
14. *(Diputuskan pengguna)* Pilihan yang bisa berbeda antar sekolah = data master (periode, aturan denda, aturan
    cicilan, aturan masuk tengah, rekening, alasan tolak/hapus), bukan daftar tetap di kode (§4.2).

## 5. Perubahan di dokumen induk
- §I.6 baris `nti_edu_tagihan`: tambahkan "Rancangan: `2026-11-26-nti-edu-tagihan-design.md`"; basis `account, portal`.
- §II.2 helper: `_nti_edu_siswa_portal(termasuk_nonaktif=False)`.

## 6. Diserahkan ke pembangun
- Cara teknis produk di belakang komponen, akun pendapatan bawaan, dan penyiapan bagan akun di DB uji/demo
  (mis. `l10n_generic_coa` lewat helper tes akuntansi Odoo).
- Bentuk indeks unik parsial dan cara menangani galat pelanggarannya menjadi pesan yang ramah.
- Pembuatan/penggunaan ulang termin pembayaran cicilan.
- Tata letak form/list/portal, ikon app, nama xmlid sesuai §I.4.11, teks templat email.
- Cara menyembunyikan menu Akuntansi dari grup tagihan.
