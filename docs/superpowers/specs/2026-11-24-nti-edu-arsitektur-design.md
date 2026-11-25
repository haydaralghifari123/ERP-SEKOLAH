# Rancangan: Arsitektur Produk NTI Edu (ERP Sekolah) + Fondasi `nti_edu_base`

Tanggal: 2026-11-24 · Odoo 18 Community · workspace `D:\odoo2` (addons_path: addons Odoo + `D:\odoo2`, database `odoo2`)

Dokumen ini punya dua bagian:
- **Bagian I** — arsitektur seluruh produk: aturan main, peta modul, pengguna, pola varian/jembatan, urutan fase.
  Berlaku untuk semua modul `nti_edu_*`.
- **Bagian II** — desain rinci `nti_edu_base`, modul pertama yang dibangun.

Setiap modul lain dirancang di dokumennya sendiri (diskusi → desain → rencana → bangun), satu per satu,
mengikuti urutan fase di §I.9, dan harus tunduk pada aturan di §I.4.

---

# BAGIAN I — ARSITEKTUR PRODUK

## I.1 Maksud dan alasan

Latihan membangun **produk** ERP sekolah di atas Odoo 18 Community — bukan pesanan satu sekolah. "Produk" berarti:
bisa dipasang di sekolah mana pun tanpa mengubah kode, perilaku disesuaikan lewat konfigurasi atau modul varian,
dan **setiap modul bisa dipasang/dijual sendiri-sendiri**, tetapi saling terhubung otomatis bila dipasang bersama.

Fitur yang di Odoo hanya ada di Enterprise (laporan akuntansi, penggajian, helpdesk, documents, sign, appointment)
**dibuat sendiri**, tidak memakai OCA.

Sudah ada dua modul sekolah buatan pengguna di `D:\odoo`: `nti_edu_ekskul` (+ `ekskul_tema`) dan `nti_edu_bk`
(+ `nti_edu_bk_tema`). Keduanya akan **disalin** ke produk ini dan dirampingkan (lihat §I.10).

## I.2 Sasaran, bukan sasaran, anti-sasaran

**Sasaran**
- Peta ±40 addon yang mencakup operasional sekolah Indonesia (akademik, kesiswaan, keuangan, SDM, operasional,
  portal), dibangun bertahap.
- Setiap modul fitur bisa dipasang hanya dengan `nti_edu_base` + modul standar Odoo.
- Satu data master bersama (siswa, rombel, tahun ajaran, dll.) dipakai semua modul.
- Mendukung struktur **yayasan dengan beberapa unit sekolah** (TK/SD/SMP/SMA/SMK) sejak awal.
- Perilaku yang berbeda antar sekolah diatur lewat **konfigurasi data**; yang butuh kode berbeda dibuat
  **modul varian** yang bisa dipilih per unit.

**Bukan sasaran**
- Memindahkan data dari database lama (`D:\odoo`) — produk dimulai dengan database baru.
- Aplikasi mobile native (portal web responsif sudah cukup).
- Terjemahan selain Bahasa Indonesia untuk saat ini (kode tetap memakai `_()`/teks yang bisa diterjemahkan).
- Integrasi langsung (API) ke Dapodik — cukup impor/ekspor berkas.

**Anti-sasaran** (gagal walau "jalan")
- Modul fitur diam-diam butuh modul fitur lain agar bisa dipasang atau berjalan.
- Data master yang sama disimpan di lebih dari satu tempat (tahun ajaran di ekskul *dan* di base, dsb.).
- Data pribadi siswa terbaca oleh orang tua siswa lain, siswa lain, atau internal user yang tidak berhak
  (mis. Mitra DU/DI). Ini juga menyangkut UU Pelindungan Data Pribadi.
- Menyalin kode sumber Odoo Enterprise (pelanggaran lisensi). Modul pengganti Enterprise ditulis sendiri.
- Konfigurasi begitu rumit sehingga admin sekolah tidak bisa menyiapkan sistem tanpa developer.

## I.3 Pendekatan arsitektur

| Pendekatan | Ringkas | Dipilih? |
|---|---|---|
| **A. Inti + Varian + Modul Jembatan** | Tiap tema punya modul inti; perbedaan berbasis kode jadi modul varian; integrasi antar fitur lewat modul jembatan `auto_install`. Banyak addon kecil. | **Ya**, ditambah sedikit B |
| B. Inti tebal + mesin aturan | Hampir semua perilaku (termasuk rumus) diatur lewat data; varian hanya untuk integrasi luar. Paling dinamis, tapi konfigurasi rumit dan sulit dites. | Hanya untuk komponen gaji, aturan poin BK, bobot nilai |
| C. Modul besar per domain | ±8 addon besar, varian dinyalakan lewat pengaturan. Cepat dimulai, tapi tiap sekolah memasang semuanya. | Tidak — bertentangan dengan "dijual sendiri-sendiri" |

Pengguna memilih A karena tujuan utamanya: **tiap modul bisa dipasang/dijual sendiri** tanpa menduplikasi data master.

## I.4 Aturan arsitektur (wajib untuk semua modul)

1. **Modul fitur hanya boleh depend ke `nti_edu_base` dan modul standar Odoo Community.** Tidak boleh depend ke
   modul fitur lain.
2. **`nti_edu_base` tipis dan selalu ikut** bersama modul mana pun yang didistribusikan/dijual. Isinya hanya master
   bersama, hak akses dasar, portal dasar, dan app "Data Sekolah".
3. **Integrasi antar fitur hanya lewat modul jembatan**: `depends` = dua modul yang dihubungkan, `auto_install: True`,
   nama `nti_edu_<a>_<b>` (mis. `nti_edu_ekskul_tagihan`). Jembatan tidak menambah fitur yang berdiri sendiri.
4. **Pengecualian: varian dan paket boleh depend ke inti temanya** (mis. `nti_edu_kurikulum_merdeka` → `nti_edu_penilaian`).
   Varian dijual sebagai tambahan modul intinya.
5. **Data dulu, kode belakangan.** Perbedaan yang hanya berupa nilai/aturan/skala/template/label dibuat sebagai record
   konfigurasi di modul yang sama. Modul varian hanya jika butuh model/field/view/logika berbeda, dependensi luar
   (library, API, perangkat), atau besar dan jarang dipakai.
6. **Rumus (ekspresi Python lewat `safe_eval`) hanya** untuk komponen gaji, aturan poin BK, dan bobot nilai.
7. **Master bersama di app "Data Sekolah"** (dari `nti_edu_base`); master khusus modul di menu **Konfigurasi** modul itu.
8. **Ortu, siswa, pendaftar, alumni = portal user.** Hanya pegawai sekolah dan Mitra DU/DI yang internal user;
   Mitra DU/DI memakai grup khusus yang dibatasi ketat (hanya ada bila paket SMK terpasang).
   **Pegawai yang juga orang tua** tetap satu akun internal (Odoo melarang satu user internal sekaligus portal), jadi
   halaman "Anak Saya" dan aturan akses wali→anak harus berlaku juga untuk internal user, bukan hanya `base.group_portal`.
9. **Uji pasang tunggal**: setiap modul fitur harus lulus instal + seluruh tesnya di database kosong yang hanya berisi
   modul itu, `nti_edu_base`, dan dependensi standar Odoo-nya.
10. **Data demo**: master demo (unit, tahun ajaran, rombel, beberapa siswa & wali, beberapa guru) ada di
    `nti_edu_base`; tiap modul menambah demo miliknya sendiri, sehingga modul yang dipasang sendirian langsung bisa dicoba.
11. **Penamaan**: addon `nti_edu_<nama>`, model `nti_edu.<nama>`, xmlid grup `group_<modul>_<peran>`.
    Nama field/model/pesan/komentar dalam Bahasa Indonesia, mengikuti gaya `nti_edu_ekskul`.
12. **Tema tampilan** (sidebar/warna) selalu modul terpisah `nti_edu_<modul>_tema` yang depend ke modulnya, tidak
    mengubah warna app lain.

### I.4.1 Satuan distribusi

Satu modul yang dicoba/dijual = folder modul itu + folder `nti_edu_base` (+ varian/tema bila diinginkan).
Modul standar Odoo sudah ada di instalasi mana pun. Modul jembatan hanya disertakan bila pembeli punya kedua modulnya.

## I.5 Pola teknis

### I.5.1 Modul jembatan
```python
# nti_edu_ekskul_tagihan/__manifest__.py
{'depends': ['nti_edu_ekskul', 'nti_edu_tagihan'], 'auto_install': True, ...}
```
Contoh: iuran ekskul dibuat sebagai tagihan siswa di modul tagihan; denda perpustakaan masuk tagihan; BK melihat
riwayat absensi ekskul (`nti_edu_bk_ekskul`).

### I.5.2 Varian yang dipilih per unit
Inti mendefinisikan "kontrak": field pilihan mesin yang **kosong di inti** dan metode yang dipanggil lewat nama mesin.
```python
# di modul inti, mis. nti_edu_penilaian
class ResCompany(models.Model):
    _inherit = 'res.company'
    nti_edu_kurikulum = fields.Selection([], string='Kurikulum')

class Rapor(models.Model):
    _name = 'nti_edu.rapor'
    def _hitung(self):
        mesin = self.company_id.nti_edu_kurikulum
        if not mesin:
            raise UserError(_('Kurikulum unit ini belum dipilih.'))
        return getattr(self, f'_hitung_{mesin}')()

# di modul varian, mis. nti_edu_kurikulum_merdeka
class ResCompany(models.Model):
    _inherit = 'res.company'
    nti_edu_kurikulum = fields.Selection(selection_add=[('merdeka', 'Kurikulum Merdeka')],
                                         ondelete={'merdeka': 'set null'})

class Rapor(models.Model):
    _inherit = 'nti_edu.rapor'
    def _hitung_merdeka(self): ...
```
Beberapa varian bisa terpasang sekaligus; tiap unit (company) memilih satu. Letak field pilihan (company, jenjang,
atau tingkat) ditentukan di desain modul intinya masing-masing.

### I.5.3 Modul menambah tab ke data master
Modul fitur memakai `_inherit` pada model master base (siswa = `res.partner`, rombel, dst.) untuk menambah
One2many/field **baru** dan tab di form siswa. Field yang sensitif diberi `groups=` milik modul itu. Field yang sudah
didefinisikan base tidak boleh didefinisikan ulang.

### I.5.4 Konfigurasi multi-unit
- **Yayasan = company induk (root), unit = branch** (`res.company.parent_id`, fitur branch Odoo 18). Konsekuensi
  yang disengaja: unit berbagi **satu pembukuan yayasan** (COA, mata uang, tahun fiskal dipaksa sama dengan root —
  `account/models/company.py`), laporan bisa dipilah per branch. Ini cocok dengan yayasan di Indonesia, yang menjadi
  badan hukumnya, bukan unit. Hierarki company tidak bisa diubah setelah dibuat, jadi wizard onboarding harus
  membuat yayasan dulu lalu unit.
- **Sekolah mandiri (tanpa yayasan)** = satu company root dengan `nti_edu_jenis = 'unit'`, tanpa branch.
- Company bawaan (id 1) di-rename menjadi yayasan atau sekolah mandiri saat onboarding.
- Semua model transaksi punya `company_id` (default company aktif) dan record rule multi-company standar.
- Master yang boleh dipakai lintas unit (mis. mapel) memakai `company_id` opsional (kosong = berlaku untuk semua unit).
- **Referensi ke guru/staf di semua modul memakai `res.users`** (mis. wali kelas, pembina, guru BK). Modul yang
  memang berbasis `hr` (presensi pegawai, penggajian) memakai `hr.employee` standar. `nti_edu_pegawai` adalah modul
  fitur biasa: tidak boleh dijadikan dependensi modul fitur lain; data tambahannya (NUPTK, dsb.) dipakai modul lain
  lewat jembatan.

## I.6 Peta modul

Jenis: **Inti** · **Varian** (depend ke inti temanya) · **Jembatan** (dibuat saat dua modul terkait sudah ada) ·
**Opsional**. Basis = modul standar Odoo yang dipakai (selain `nti_edu_base`).

| Kelompok | Addon | Isi pokok | Basis | Jenis |
|---|---|---|---|---|
| Fondasi | `nti_edu_base` | Lihat Bagian II | base, mail, portal | Fondasi |
| SDM | `nti_edu_pegawai` | Data guru & staf (NUPTK, sertifikasi, kualifikasi) di atas `hr.employee`, tautan ke `res.users`. Bukan dependensi modul lain (§I.5.4) | hr | Inti |
| Penerimaan | `nti_edu_ppdb` | Daftar online, berkas, jalur & kuota, metode seleksi (konfigurasi), pengumuman, daftar ulang → jadi siswa | website, survey | Inti |
| | `nti_edu_ppdb_zonasi` | Seleksi berbasis jarak/peta | — | Varian |
| Akademik | `nti_edu_jadwal` | Struktur mapel per tingkat, jadwal, cek bentrok, guru pengganti | — | Inti |
| | `nti_edu_jurnal_mengajar` | Agenda kelas per jam pelajaran | — | Inti |
| | `nti_edu_presensi` | Presensi harian/per jam, izin/sakit, manual & QR, rekap | — | Inti |
| | `nti_edu_presensi_rfid` | RFID/fingerprint | — | Varian |
| | `nti_edu_penilaian` | Komponen nilai, skala (konfigurasi), leger, remedial, catatan wali, rapor PDF | — | Inti |
| | `nti_edu_kurikulum_merdeka` / `_k13` / `_internasional` | Struktur & rapor per kurikulum | — | Varian (`_internasional` opsional) |
| | `nti_edu_rapor_ai` | Asisten narasi deskripsi rapor | — | Varian, Opsional |
| | `nti_edu_bank_soal` | Bank soal, analisis butir, ujian/CBT | survey | Inti |
| | `nti_edu_elearning` | Materi, tugas, kuis | website_slides, survey | Inti |
| Kesiswaan | `nti_edu_bk` | (salinan dirampingkan) pengajuan, bimbingan rahasia, poin, janji temu | mail, calendar | Inti |
| | `nti_edu_ekskul` | (salinan dirampingkan) ekskul, pendaftaran, absensi, nilai, prestasi, proposal | mail, portal | Inti |
| | `nti_edu_piket` | Guru piket, izin keluar, buku tamu | — | Inti |
| | `nti_edu_peringatan_dini` | Skor risiko siswa (sumber data lewat jembatan) | — | Inti |
| | `nti_edu_uks` | Kesehatan siswa | — | Opsional |
| Keuangan | `nti_edu_tagihan` | Skema biaya (konfigurasi), beasiswa/potongan, tagihan berkala, tunggakan, kartu SPP, transfer manual | account | Inti |
| | `nti_edu_payment_midtrans` / `_xendit` / `_va_bank` | Penyedia pembayaran | payment | Varian |
| | `nti_edu_akuntansi` | COA yayasan, neraca, laporan aktivitas, arus kas, RKAS, laporan BOS (pengganti Enterprise) | account | Inti |
| | `nti_edu_pos` | Koperasi seragam/buku | point_of_sale | Opsional |
| | `nti_edu_tabungan` | Tabungan siswa, kantin cashless | — | Opsional |
| SDM | `nti_edu_presensi_pegawai` | Presensi guru & staf | hr_attendance | Inti |
| | `nti_edu_penggajian` | Komponen gaji (rumus), slip, jurnal (pengganti Enterprise) | hr, account | Inti |
| Operasional | `nti_edu_sarpras` | Aset, inventaris, pengadaan, perawatan | purchase, stock, maintenance | Inti |
| | `nti_edu_ruang` | Peminjaman ruang & fasilitas | calendar | Inti |
| | `nti_edu_perpustakaan` | Katalog, peminjaman, denda | — | Inti |
| | `nti_edu_persuratan` | Surat masuk/keluar, penomoran, disposisi, arsip, tanda tangan digital | mail | Inti |
| | `nti_edu_layanan` | Tiket pengaduan + SLA, permohonan surat lewat portal | mail, portal | Inti |
| | `nti_edu_transport` | Antar-jemput | fleet | Opsional |
| Paket jenis sekolah | `nti_edu_smk` | PKL/Prakerin, BKK, uji kompetensi, akses Mitra DU/DI | — | Varian/Paket |
| | `nti_edu_pesantren` | Tahfidz, mutaba'ah, infaq/wakaf | — | Varian/Paket |
| | `nti_edu_asrama` | Kamar, izin pulang, laundry, uang saku | — | Varian/Paket |
| Komunikasi | `nti_edu_notifikasi` | Template & kanal email | mail | Inti |
| | `nti_edu_wa_<gateway>` / `nti_edu_sms` | Kanal WhatsApp/SMS | sms | Varian |
| | `nti_edu_pengumuman` | Pengumuman & agenda sekolah | event, website | Inti |
| Produk & laporan | `nti_edu_onboarding` | Wizard sekolah baru | — | Inti |
| | `nti_edu_import` | Impor Excel/Dapodik, ekspor Dapodik | — | Inti |
| | `nti_edu_audit` | Log audit perubahan data penting | — | Inti |
| | `nti_edu_dashboard` | Dashboard kepsek & yayasan | — | Inti |
| Tema | `nti_edu_<modul>_tema` | Sidebar & warna per app | — | Opsional |

Catatan:
- Halaman portal ortu/siswa **dibangun oleh masing-masing modul** (nilai oleh penilaian, tagihan oleh tagihan, dst.);
  `nti_edu_base` menyediakan kerangka portal dan hak akses ortu→anak (§II.6). Karena itu modul `sekolah_portal` di
  daftar awal **dihapus** sebagai modul terpisah.
- `nti_edu_demo` di daftar awal **dihapus**: data demo melekat di tiap modul (aturan 10).
- Modul jembatan tidak dicantumkan di peta; masing-masing dirancang bersama modul kedua yang membutuhkannya.

## I.7 Pengguna dan peran

**Level yayasan (internal):** Admin Sistem, Pengurus/Ketua Yayasan (baca saja), Bendahara/Akuntan Yayasan, HRD Yayasan.

**Level unit (internal):** Kepala Sekolah, Wakasek Kurikulum, Wakasek Kesiswaan, Wakasek Sarpras, Tata Usaha/Operator,
Bendahara/Kasir, Panitia PPDB, Guru Mapel, Wali Kelas, Guru BK, Guru Piket, Pembina Ekskul, Pustakawan, Petugas UKS,
Kasir Koperasi; paket: Koordinator/Pembimbing PKL, Ustadz Tahfidz/Musyrif, Pembina Asrama.

**Portal:** Orang Tua/Wali, Siswa, Calon Siswa/Pendaftar, Alumni.

**Internal terbatas:** Mitra DU/DI (paket SMK).

**Publik:** pengunjung website. **Aktor otomatis:** cron, webhook payment gateway, perangkat RFID.

Prinsip hak akses:
- **Peran bertumpuk** lewat grup Odoo (satu orang bisa guru + wali kelas + pembina).
- **Akses berbasis penugasan berlaku untuk data milik modul** (nilai, presensi, bimbingan, dst.): guru → kelas yang
  diajar; wali kelas → rombelnya; pembina → ekskul binaannya. **Daftar siswa itu sendiri** (nama, NIS, rombel, foto)
  boleh dibaca semua staf di unitnya — guru piket, guru pengganti, dan pembina perlu mencari siswa. Catatan teknis:
  record rule antar grup digabung dengan OR (hanya rule global yang AND), jadi rule base untuk siswa tidak bisa
  dipersempit modul lain; pembatasan data sensitif siswa dilakukan dengan `groups=` per field, bukan record rule.
- **Lintas unit** lewat *allowed companies*.
- **Data rahasia**: catatan konseling hanya BK (+kepsek bila diatur); gaji hanya HRD/bendahara; nilai hanya diubah
  guru pengampu sebelum rapor final.
- Setiap modul mendefinisikan grup perannya sendiri di kategori "NTI Edu / <Nama Modul>". `nti_edu_base` hanya
  mendefinisikan grup dasar (§II.5).

## I.8 Konfigurasi vs varian (patokan)

Jadikan **modul varian** bila memenuhi salah satu: (1) butuh model/field/view/logika Python berbeda; (2) butuh
dependensi luar; (3) besar dan jarang dipakai. Selain itu jadikan **record konfigurasi**.

Hasil penerapan: skema tagihan, komponen gaji, skala nilai, presensi manual/QR, metode seleksi PPDB → konfigurasi.
Struktur kurikulum, RFID, penyedia pembayaran, gateway WA, zonasi, paket SMK/pesantren/asrama → varian.

## I.9 Urutan fase

| Fase | Modul |
|---|---|
| 1 | `nti_edu_base`, `nti_edu_pegawai`, `nti_edu_tagihan`, `nti_edu_presensi`, `nti_edu_import`, `nti_edu_onboarding` (versi awal) |
| 2 | `nti_edu_ekskul` & `nti_edu_bk` (salin + rampingkan), `nti_edu_jadwal`, `nti_edu_jurnal_mengajar`, `nti_edu_penilaian` + `nti_edu_kurikulum_merdeka`, `nti_edu_notifikasi` |
| 3 | `nti_edu_ppdb`, `nti_edu_penggajian`, `nti_edu_akuntansi`, `nti_edu_persuratan`, `nti_edu_perpustakaan` |
| 4 | Sisanya, termasuk paket SMK/pesantren/asrama, varian pembayaran/WA, opsional |

Urutan di dalam fase dan perpindahan antar fase boleh disesuaikan saat modul dirancang. Ekskul & BK masuk fase 2
(bukan 1) karena butuh `nti_edu_base` stabil dan menjadi uji nyata pertama aturan "dipasang sendiri".

## I.10 Penyalinan `nti_edu_ekskul` dan `nti_edu_bk`

- Disalin dari `D:\odoo` ke `D:\odoo2`; versi asli di `D:\odoo` **tidak diubah**.
- Dibuang/dipindah: field siswa di `res.partner`, `ekskul.tahun.ajaran`, `bk.wali.kelas`, sinkronisasi kelas
  berbasis teks, wizard "buat akun" per modul (diganti mekanisme akun di base), dan fitur lain yang tumpang tindih.
  **Daftar yang akan dibuang ditunjukkan ke pengguna sebelum dihapus.**
- Akun siswa diubah dari internal user menjadi **portal user**; fitur siswa di backend BK (halaman Home siswa,
  pengajuan oleh siswa) dipindah ke portal. Ini pekerjaan terbesar penyalinan.
- Iuran ekskul dipindah ke jembatan `nti_edu_ekskul_tagihan`; `nti_edu_ekskul` tidak lagi depend ke `account`.
- Nama model boleh diganti ke konvensi `nti_edu.*` karena tidak ada data lama yang dipindah. Diputuskan di desain
  penyalinan masing-masing.

## I.11 Kriteria berhasil produk (per modul)

- Lulus uji pasang tunggal (aturan 9) dan tesnya hijau.
- Bila dipasang bersama modul lain, memakai siswa/rombel/tahun ajaran yang sama dari base tanpa sinkronisasi.
- Hak akses diuji: user peran lain, ortu lain, dan siswa lain tidak bisa membaca data yang bukan haknya.
- Data demo membuat modul langsung bisa dicoba.

---

# BAGIAN II — DESAIN `nti_edu_base`

## II.1 Tanggung jawab

Hanya yang dibutuhkan oleh **lebih dari satu** modul fitur:
struktur yayasan/unit, kalender akademik, struktur kelas, mapel, ruang, data siswa & wali, grup dasar, akun portal
siswa/ortu, kerangka portal "Anak Saya", helper untuk modul lain, app "Data Sekolah", data demo master.

Yang **tidak** masuk base: data pegawai lengkap (→ `nti_edu_pegawai`, butuh `hr`), mutasi/kelulusan/alumni lanjutan
(→ modul tersendiri nanti), impor massal (→ `nti_edu_import`), wizard onboarding (→ `nti_edu_onboarding`).

**Depends:** `base`, `mail`, `portal`. Tidak depend ke `hr`, `account`, atau `website`.

## II.2 Model

### Unit & struktur
- **Yayasan & unit = `res.company`.** Yayasan adalah company induk; unit adalah child company (`parent_id`).
  Field tambahan di `res.company`:
  `nti_edu_jenis` (selection: `yayasan`/`unit`), `nti_edu_jenjang_id` (m2o jenjang, untuk unit),
  `nti_edu_npsn` (char), `nti_edu_kode` (char unik, mis. `smp1`, dipakai di login siswa),
  `nti_edu_kepala_id` (m2o `res.users`, kepala sekolah), `nti_edu_hari_sekolah` (5/6 hari).
- **`nti_edu.jenjang`** — name (TK, SD, SMP, SMA, SMK, …), kode, urutan. Data awal disediakan; bisa ditambah.
- **`nti_edu.tingkat`** — name (mis. "Kelas X"), jenjang_id, urutan (angka untuk kenaikan kelas).
- **`nti_edu.jurusan`** — name, kode, jenjang_id, company_id (opsional).

### Kalender akademik
- **`nti_edu.tahun.ajaran`** — name ("2026/2027"), tanggal_mulai, tanggal_selesai, is_aktif. **Satu untuk seluruh
  database (yayasan), tanpa `company_id`** — kalender akademik nasional sama untuk semua jenjang; satu database =
  satu yayasan/sekolah. Constraint: tanggal valid; maksimal satu aktif. Perbedaan antar unit cukup lewat hari libur.
- **`nti_edu.semester`** — tahun_ajaran_id, jenis (`ganjil`/`genap`), tanggal_mulai, tanggal_selesai, is_aktif.
  Constraint: berada di dalam rentang tahun ajaran; satu aktif per tahun ajaran.
- **`nti_edu.hari.libur`** — name, tanggal_mulai, tanggal_selesai, company_id (opsional), jenis
  (`nasional`/`sekolah`/`ujian`/`lainnya`). Dipakai presensi & jadwal untuk menentukan hari efektif.

### Kelas, mapel, ruang
- **`nti_edu.rombel`** — name ("X IPA 1"), tahun_ajaran_id, tingkat_id, jurusan_id, company_id (wajib),
  wali_kelas_id (m2o `res.users`), ruang_id, anggota_ids (o2m `nti_edu.rombel.anggota`), jumlah_siswa (compute).
  Constraint: nama unik per (tahun ajaran, company).
- **`nti_edu.rombel.anggota`** — rombel_id, siswa_id, tahun_ajaran_id (related, stored), no_absen,
  tanggal_masuk, tanggal_keluar. Constraint: satu siswa hanya di satu rombel per tahun ajaran (yang belum keluar).
  Inilah **riwayat kelas** siswa.
- **`nti_edu.mapel`** — name, kode, kelompok (mis. umum/kejuruan/muatan lokal — selection yang bisa diperluas),
  company_id (opsional).
- **`nti_edu.ruang`** — name, kode, jenis (kelas/lab/aula/lapangan/lainnya), kapasitas, company_id.

### Siswa & wali
- **Siswa = `res.partner` langsung** (keputusan pengguna, sama seperti `nti_edu_ekskul`/`nti_edu_bk` lama), ditandai
  `nti_edu_is_siswa`. Field tambahan di `res.partner`:
  nis (unik per company), nisn (unik global bila diisi), nik, jenis_kelamin, tempat_lahir, tanggal_lahir, agama,
  nti_edu_status (`aktif`/`lulus`/`pindah`/`keluar`), tanggal_masuk, rombel_aktif_id (compute stored dari keanggotaan
  di tahun ajaran aktif), anggota_ids, wali_ids (o2m `nti_edu.siswa.wali`). Alamat memakai field alamat standar partner.
  `company_id` partner siswa = unit tempat ia bersekolah, sehingga rule multi-company bawaan (`res_partner_rule`)
  otomatis memisahkan siswa antar unit. Akun login siswa = `res.users` yang memakai partner yang sama (`user_ids`).
- Partner wali ditandai `nti_edu_is_wali` (compute stored dari baris wali), `company_id` **kosong** karena anaknya
  bisa di beberapa unit.
- **`nti_edu.siswa.wali`** — siswa_id (m2o `res.partner`, domain siswa), partner_id (kontak ortu/wali), hubungan
  (`ayah`/`ibu`/`wali`), is_kontak_utama, is_penanggung_biaya. Satu partner ortu bisa terhubung ke beberapa anak,
  termasuk lintas unit.
- Modul lain merujuk siswa dengan `fields.Many2one('res.partner', domain=[('nti_edu_is_siswa', '=', True)])`.

Konsekuensi yang diterima pengguna: `res.partner` bisa dibaca semua internal user (`access_res_partner_group_user`),
jadi field sensitif dijaga **per field** dengan `groups=` (§II.5), modul lain membaca field sensitif lewat pola proxy
seperti `nti_edu_bk`, dan setiap dropdown siswa wajib memakai domain `nti_edu_is_siswa`. Keuntungannya: sederhana,
langsung dipakai invoice/chatter/portal, dan penyalinan ekskul/BK lebih mudah karena modul lama sudah berbasis partner.
Field siswa **hanya didefinisikan di `nti_edu_base`**; modul lain tidak boleh mendefinisikan ulang field yang sama
(sumber masalah atribut `groups` saling menimpa di ekskul/BK lama).

### Helper untuk modul lain (di model abstrak atau `res.company`)
- `_nti_edu_tahun_ajaran_aktif()` → recordset tahun ajaran aktif (satu untuk seluruh yayasan).
- `_nti_edu_semester_aktif()`.
- `_nti_edu_hari_efektif(tanggal, company=None)` → bool (bukan Minggu/hari libur; hari kerja per unit
  diatur di field `nti_edu_hari_sekolah` pada company: 5 atau 6 hari).
- Di `res.partner` (siswa): `_nti_edu_rombel_pada(tanggal)`.
- Di `res.users`: `_nti_edu_siswa_portal()` → siswa yang boleh dilihat user portal ini (dirinya bila siswa,
  anak-anaknya bila wali).

## II.3 Siklus data utama

1. Admin membuat yayasan & unit (company), jenjang/tingkat (dari data awal), tahun ajaran + semester, rombel.
2. TU menambah siswa + wali (manual; impor massal datang dari `nti_edu_import`).
3. Siswa dimasukkan ke rombel lewat tab Anggota di rombel (atau wizard "Tambah ke rombel" dari daftar siswa).
4. Saat tahun ajaran berganti: rombel baru dibuat untuk tahun ajaran baru. **Wizard kenaikan kelas massal** di base:
   pilih rombel asal → rombel tujuan per siswa (default: rombel tujuan yang sama untuk semua), siswa tingkat akhir
   ditandai `lulus`. (Pembagian kelas otomatis dengan penyeimbangan → bukan sasaran base.)
5. Status `pindah`/`keluar` mengisi tanggal_keluar di keanggotaan aktif.

## II.4 App "Data Sekolah" (menu)

```
Data Sekolah
├─ Siswa            (kanban/list/form; tab Data Pribadi, Wali, Riwayat Kelas, + tab dari modul lain)
├─ Rombel           (list/form; tab Anggota)
├─ Wali Murid       (kontak yang terhubung sebagai wali; hanya Operator, terbatas unit anaknya — data wali sensitif §II.5)
├─ Kalender
│   ├─ Tahun Ajaran & Semester
│   └─ Hari Libur
└─ Konfigurasi      (hanya Admin)
    ├─ Unit Sekolah
    ├─ Jenjang & Tingkat
    ├─ Jurusan
    ├─ Mata Pelajaran
    └─ Ruang
```
Tampilan memakai view Odoo standar (tanpa tema). Tema base boleh dibuat nanti sebagai `nti_edu_base_tema`.

## II.5 Grup dan hak akses

Kategori: **NTI Edu / Data Sekolah**.

| Grup | Implies | Hak |
|---|---|---|
| `group_base_pengguna` (Pengguna Data Sekolah) | `base.group_user` | Baca master & data siswa **unit yang diizinkan**, tanpa NIK/data sensitif. Semua modul fitur meng-imply grup ini ke grup staf mereka. |
| `group_base_operator` (Operator/TU) | pengguna | Buat/ubah siswa, wali, rombel, keanggotaan, kalender, tanpa hapus; hapus data hanya Admin. Lihat NIK. |
| `group_base_admin` (Admin Data Sekolah) | operator | Konfigurasi unit, jenjang, tingkat, jurusan, mapel, ruang; hapus data. |

- Data dasar siswa (nama, foto, NIS, rombel) terbaca semua internal user di unitnya — bawaan `res.partner` +
  `res_partner_rule` multi-company. Ini sejalan dengan §I.7.
- Field sensitif (nik, nisn, tempat/tanggal_lahir, agama, data wali) diberi `groups='nti_edu_base.group_base_operator'`.
  Modul lain yang perlu membacanya (mis. BK) memakai pola field proxy (`compute` + `sudo`, `groups=` grup modul itu)
  seperti `nti_edu_bk`. Alamat memakai field standar partner sehingga **tidak** bisa diberi `groups=` — diterima.
- Penulisan data siswa dibatasi ke `group_base_operator` lewat override `write`/`create` di `res.partner` untuk record
  `nti_edu_is_siswa` (ACL partner bawaan memberi tulis ke banyak grup).
- **Wali → anak** (portal *dan* pegawai yang juga ortu): tidak lewat record rule partner (rule partner berdampak ke
  seluruh sistem). Halaman "Anak Saya" membaca data anak dengan `sudo()` di controller setelah memastikan ada baris
  `nti_edu.siswa.wali` yang menghubungkan partner user dengan siswa itu. Helper `_nti_edu_siswa_portal()` menjadi
  satu-satunya pintu yang dipakai semua modul. Siswa portal: hanya dirinya.
- Portal tidak diberi ACL tambahan ke model base; nama rombel/tahun ajaran di portal dibaca lewat `sudo()` yang sama.
- Untuk internal user non-sekolah (Mitra DU/DI), `nti_edu_base` menyediakan **grup `group_base_eksternal`** dengan rule
  di `res.partner`: `[('nti_edu_is_siswa','=',False), ('nti_edu_is_wali','=',False)]`. Grup Mitra DU/DI (paket SMK)
  meng-imply grup ini. Karena `base.group_user` tidak punya rule partner, rule ini benar-benar membatasi anggotanya.
  (Akses Mitra ke siswa PKL-nya sendiri diberikan oleh paket SMK lewat `sudo`/rule tambahan.)

## II.6 Akun portal & kerangka portal

- Tombol "Buat Akun Portal" di form siswa (untuk siswa) dan di baris wali (untuk ortu): membuat `res.users` portal
  terhubung ke partner, kirim undangan reset password via email bila ada email; jika tidak, password awal
  ditampilkan sekali ke operator.
- **Login**: `res.users.login` unik se-database, sedangkan NIS hanya unik per unit. Login siswa = **NISN** bila ada,
  selain itu `<kode_unit>.<nis>` (kode unit = field `nti_edu_kode` baru di `res.company`, mis. `smp1`). Login wali =
  email; bila tidak ada email, nomor HP.
- Bila partner wali sudah punya user internal (pegawai yang juga ortu), tidak dibuat akun portal; akses "Anak Saya"
  datang dari helper `_nti_edu_siswa_portal()` (§II.5).
- Satu ortu dengan beberapa anak = satu akun.
- Portal `/my` mendapat kartu **"Anak Saya"** (untuk wali) / **"Profil Saya"** (untuk siswa): daftar anak, profil
  dasar, rombel aktif. Modul lain menambah kartu/halaman mereka sendiri dan memakai helper
  `_nti_edu_siswa_portal()` untuk membatasi data. Pemilihan anak aktif (bila lebih dari satu) disimpan di session.

## II.7 Data awal & demo

- **Data awal** (`data/`): jenjang TK/SD/SMP/SMA/SMK, tingkat untuk tiap jenjang, kelompok mapel.
- **Demo** (`demo/`): 1 yayasan dengan 2 unit (SMP & SMA), tahun ajaran berjalan + 2 semester, 4 rombel, ±20 siswa
  dengan wali (dua siswa bersaudara lintas unit), 3 user guru (salah satu wali kelas), 1 operator, 1 akun portal
  wali + 1 akun portal siswa, beberapa hari libur.

## II.8 Tes (`post_install`)

- Constraint: tanggal tahun ajaran/semester, satu aktif, NIS unik per unit, satu rombel per siswa per tahun ajaran.
- Login siswa: NISN dipakai bila ada; dua siswa beda unit dengan NIS sama tetap bisa dibuatkan akun.
- Pegawai yang juga wali: melihat anaknya di unit lain lewat `_nti_edu_siswa_portal()`.
- Mitra (grup `group_base_eksternal`): tidak menemukan partner siswa/wali di Kontak maupun dropdown.
- Helper: tahun ajaran/semester aktif, hari efektif (hari libur, akhir pekan 5/6 hari), `_rombel_pada`.
- Wizard kenaikan kelas: anggota baru tercipta, tingkat akhir jadi `lulus`, riwayat lama tetap.
- Hak akses: pengguna tidak melihat NIK; operator bisa; non-operator tidak bisa mengubah data siswa;
  user unit A tidak melihat siswa unit B; wali portal hanya melihat anaknya lewat `_nti_edu_siswa_portal()`
  (termasuk anak lintas unit); siswa portal hanya dirinya.
- Uji pasang tunggal: `odoo-bin -d <db_kosong> -i nti_edu_base --test-enable --stop-after-init`.

## II.9 Keputusan Claude (silakan dicek pengguna)

1. *(Diputuskan pengguna)* Siswa = `res.partner` langsung; field sensitif dijaga per field.
2. Semua staf di unit boleh melihat daftar siswa (data non-sensitif); pembatasan per penugasan hanya untuk data modul.
3. Pegawai yang juga ortu didukung (akses "Anak Saya" dengan akun internalnya).
4. Tahun ajaran & semester satu untuk seluruh yayasan; perbedaan per unit lewat hari libur.
5. Yayasan = root company, unit = branch → satu pembukuan yayasan. Sekolah mandiri = satu company.
6. Guru/staf direferensikan sebagai `res.users` di semua modul; `nti_edu_pegawai` bukan dependensi modul lain.
7. Login siswa = NISN, atau `<kode_unit>.<nis>`.
8. Grup `group_base_eksternal` menyembunyikan partner siswa/wali dari internal user non-sekolah (Mitra DU/DI).

## II.10 Diserahkan ke pembangun

- Tata letak form/kanban dan ikon app.
- Nama teknis persis field/xmlid selama mengikuti konvensi §I.4 aturan 11.
- Cara mengirim undangan portal (template email standar Odoo boleh dipakai).
- Skrip bantu uji pasang tunggal (PowerShell/bash) untuk dipakai semua modul.
