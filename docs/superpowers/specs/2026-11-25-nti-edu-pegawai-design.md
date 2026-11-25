# Rancangan: `nti_edu_pegawai` (Data Guru & Staf)

Tanggal: 2026-11-25 · Fase 1 · Induk: `docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md` (aturan §I.4
berlaku penuh; dokumen ini hanya menambah yang khusus modul pegawai).

## 1. Maksud dan alasan

Tata Usaha (TU) di tiap unit dan HRD Yayasan perlu satu tempat untuk data kepegawaian guru & staf — data yang biasa
diminta Dapodik dan dipakai untuk administrasi sertifikasi — serta cara membuatkan akun login bagi guru baru. Di
`nti_edu_base` saat ini guru hanyalah akun login (`res.users`) dengan grup Data Sekolah, tanpa data kepegawaian.

Modul ini juga menjadi fondasi `hr.employee` yang nanti dipakai `nti_edu_presensi_pegawai` dan `nti_edu_penggajian`
(keduanya memakai `hr.employee` standar, bukan modul ini).

Keputusan pengguna (2026-11-25): **setiap modul berdiri sendiri** — `nti_edu_pegawai` hanya bergantung pada
`nti_edu_base` + `hr`; tidak ada modul lain yang bergantung padanya; fitur yang butuh modul lain masuk jembatan.

## 2. Sasaran, bukan sasaran, anti-sasaran

**Sasaran**
- Profil kepegawaian per **orang** (NUPTK, NIP, status kepegawaian, pendidikan terakhir, sertifikasi) diisi sekali dan
  tampil di setiap unit tempat orang itu bekerja.
- Data per **penempatan** (unit) — jenis PTK dan tanggal mulai tugas di unit itu.
- Menu **Data Sekolah › Pegawai** untuk TU (unitnya sendiri) dan HRD Yayasan (semua unit dan staf yayasan).
- Staf **yayasan** (HRD, bendahara, pengurus) bisa punya data pegawai langsung di yayasan, dikelola hanya oleh HRD
  (keputusan pengguna 2026-11-25, pilihan B).
- Tombol **Buat Akun Login** untuk pegawai: akun internal dengan akses Data Sekolah di unit-unit tempat ia bekerja.
- Tombol **Tempatkan di Unit Lain** untuk guru yang mengajar di lebih dari satu unit (satu orang, satu akun, beberapa
  record pegawai).
- Lulus uji pasang tunggal (DB berisi hanya `nti_edu_base`, `nti_edu_pegawai`, dan dependensi standar).

**Bukan sasaran (di modul lain)**
- Beban mengajar → jembatan `nti_edu_pegawai_jadwal` (dirancang bersama `nti_edu_jadwal`; menghitung JP dari data
  jadwal dan membandingkan dengan syarat sertifikasi 24 JP).
- Presensi pegawai → `nti_edu_presensi_pegawai`; gaji → `nti_edu_penggajian`; impor massal/Dapodik → `nti_edu_import`.
- Kontrak, cuti, departemen, jabatan generik → fitur `hr` standar apa adanya (tidak diubah).

**Anti-sasaran (gagal walau berjalan)**
- Modul fitur lain bergantung pada `nti_edu_pegawai`, atau rujukan guru di modul lain berubah dari `res.users`.
- NUPTK/NIP/sertifikasi harus diketik ulang per unit atau bisa berbeda antar unit untuk orang yang sama.
- NIK/NIP pegawai terbaca semua staf (mis. lewat Kontak atau direktori pegawai).
- TU unit A melihat atau mengubah pegawai unit B.

## 3. Pendekatan yang dipertimbangkan

1. **Data orang di kontak bersama (DIPILIH).** Odoo 18: satu user hanya punya satu pegawai per company
   (`user_uniq (user_id, company_id)`), dan semua pegawai milik satu user berbagi `work_contact_id` = kontak user itu.
   Field profil disimpan di `res.partner` (kontak itu) dan ditampilkan di form pegawai sebagai field terkait. Satu
   sumber, tanpa sinkronisasi.
2. Data di setiap `hr.employee` — sederhana tetapi dobel per unit dan bisa tidak konsisten. Ditolak (anti-sasaran 2).
3. Beban mengajar di modul ini dengan model penugasan sendiri — modul jadwal/penilaian tidak boleh memakainya (aturan
   §I.4.1), sehingga data penugasan akan dobel. Ditolak; dipindah ke jembatan (keputusan pengguna).
4. Modul pegawai tanpa `nti_edu_base` (bisa untuk perusahaan non-sekolah) — kehilangan unit, menu Data Sekolah, dan
   akses guru. Ditolak pengguna ("Arti 1").

## 4. Rancangan

### 4.1 Manifest
`'depends': ['nti_edu_base', 'hr']`, kategori Education, LGPL-3, `18.0.1.0.0`, `application: False` (menu masuk app
Data Sekolah). Tanpa `auto_install`.

### 4.2 Data per orang — di `res.partner` (kontak kerja pegawai)
Field baru, semua berawalan `nti_edu_` dan **hanya** didefinisikan di modul ini:
- `nti_edu_nuptk` (char, unik global bila diisi), `nti_edu_nip` (char, unik global bila diisi)
- `nti_edu_status_kepegawaian` (selection: PNS, PPPK, GTY/PTY, GTT/PTT, Honorer, Lainnya)
- `nti_edu_pendidikan_terakhir` (selection: SMA/sederajat, D1–D4, S1, S2, S3), `nti_edu_bidang_studi` (char)
- `nti_edu_sertifikasi_ids` (o2m `nti_edu.pegawai.sertifikasi`)
- `nti_edu_is_pegawai` (bool, compute stored: punya minimal satu `hr.employee` aktif) — penanda kontak pegawai.

Semua field profil di atas diberi `groups='nti_edu_pegawai.group_pegawai_operator'` (kontak terbaca semua internal
user; lihat §II.2/§II.5 induk). NIK memakai field `nti_edu_nik` milik `nti_edu_base` (satu NIK per orang, tidak
didefinisikan ulang); cara menampilkannya ke grup pegawai diserahkan ke pembangun (lihat §6).

### 4.3 Sertifikasi — `nti_edu.pegawai.sertifikasi`
`partner_id` (m2o kontak pegawai, wajib), `jenis` (selection: Sertifikat Pendidik, Lainnya), `nomor` (char),
`tahun` (int), `bidang` (char, mis. nama mapel sertifikasi), `mapel_id` (m2o `nti_edu.mapel`, opsional),
`lampiran` (binary/attachment, opsional). Hanya grup pegawai yang membaca/menulis.

### 4.4 Data per penempatan — di `hr.employee`
- `nti_edu_jenis_ptk` (selection: Guru Mapel, Guru Kelas, Guru BK, Kepala Sekolah, Wakil Kepala, Tenaga
  Administrasi, Pustakawan, Laboran, Staf Yayasan, Lainnya), `nti_edu_tmt` (date, tanggal mulai tugas di unit ini).
- Field terkait (related ke `work_contact_id`) untuk menampilkan profil per orang di form pegawai.
- `company_id` pegawai wajib unit **atau yayasan** (`nti_edu_jenis in ('unit', 'yayasan')`). Pegawai di yayasan =
  staf yayasan (keputusan pengguna 2026-11-25, pilihan B: biaya gaji, presensi, dan laporan per unit tetap bersih;
  staf yayasan tidak perlu "dititipkan" di unit). Pegawai yayasan — membuat, mengubah, mengarsipkan, menempatkan ke
  atau dari yayasan, dan profil orang yang punya penempatan yayasan — hanya oleh HRD (atau superuser); TU tidak pernah.
- Company yang masih punya pegawai aktif tidak bisa diubah jenisnya (unit ↔ yayasan).

### 4.5 Tindakan
- **Buat Akun Login** (form pegawai, grup pegawai operator): membuat `res.users` internal yang memakai kontak kerja
  pegawai sebagai partner-nya, grup `base.group_user` + `nti_edu_base.group_base_pengguna`, `company_ids` = semua unit
  tempat orang itu punya record pegawai, lalu menautkan `user_id` di setiap record pegawainya. Login = email kerja;
  undangan dikirim lewat email (pola sama dengan wizard akun portal di base: kata sandi awal ditampilkan sekali bila
  email tidak ada). Ditolak bila orang itu sudah punya akun.
- **Tempatkan di Unit Lain** (wizard): memilih unit lain → membuat record `hr.employee` baru untuk orang yang sama
  (kontak dan user sama), lalu menambahkan unit itu ke `company_ids` user-nya bila ada. Hanya unit yang diizinkan bagi
  pemanggil. HRD juga bisa memilih **yayasan** (yayasan yang sama dengan unit asal) sebagai tujuan.

### 4.6 Menu dan tampilan
`Data Sekolah › Pegawai` (list/kanban/form `hr.employee`) dengan filter unit lewat aturan multi-company standar; tab
"Kepegawaian" di form pegawai berisi profil per orang + sertifikasi + data penempatan. App Karyawan (`hr`) bawaan
tetap ada dan tidak diubah. Kanban memakai gaya `card` Odoo 18 (tanpa `kanban_image`).

### 4.7 Grup dan hak akses (kategori "NTI Edu / Pegawai")
| Grup | Implies | Hak |
|---|---|---|
| `group_pegawai_operator` (TU Pegawai) | `nti_edu_base.group_base_pengguna`, `hr.group_hr_user` | Buat/ubah pegawai, profil, sertifikasi di unit yang diizinkan baginya; buat akun login; tempatkan di unit lain (unit yang ia pegang). |
| `group_pegawai_hrd` (HRD Yayasan) | `group_pegawai_operator` | Sama, untuk semua unit yang diizinkan (HRD diberi semua unit dan yayasan); kelola staf yayasan; hapus data pegawai. |

- Isolasi unit memakai aturan multi-company `hr.employee` standar (company ∈ company_ids).
- Guru/staf biasa: hanya direktori pegawai standar (`hr.employee.public`); field profil kepegawaian tersembunyi
  oleh `groups=`.
- Profil per orang (di kontak) boleh diubah oleh operator pegawai yang memegang **semua** unit tempat orang itu
  bekerja, atau HRD — pola sama dengan kunci kontak wali di base, supaya TU satu unit tidak mengubah data orang yang
  juga bekerja di unit lain tanpa hak.

### 4.8 Data demo
Pegawai untuk user demo base (operator + 3 guru): satu guru ditempatkan di SMP **dan** SMA; satu kepala sekolah;
beberapa sertifikasi; satu tenaga administrasi tanpa akun login.

### 4.9 Tes (`post_install`, tanpa bergantung demo)
- Profil per orang: guru di dua unit punya dua record pegawai dengan NUPTK/sertifikasi yang sama (ubah sekali, tampil
  di keduanya).
- NUPTK/NIP unik antar orang (termasuk arsip).
- TU SMP tidak melihat pegawai SMA; guru tidak membaca NIP/NIK/NUPTK.
- Buat Akun Login: user internal dengan `group_base_pengguna`, `company_ids` = unit penempatan, partner = kontak
  kerja; ditolak bila sudah punya akun.
- Tempatkan di Unit Lain: record baru di unit lain, kontak/user sama, `company_ids` user bertambah; TU tanpa unit
  tujuan ditolak.
- Penjaga profil lintas unit (TU yang tidak memegang semua unit orang itu ditolak); TU tidak bisa mengisi `user_id`.
- Keluar dari unit: arsip pegawai mencabut unit dari akun; arsip pegawai terakhir menonaktifkan akun.
- Uji asap browser (tour) menu Pegawai: list, kanban, form, kedua tindakan.
- Uji pasang tunggal: `scripts/uji_tunggal.ps1 -Modul nti_edu_pegawai`.

### 4.10 Keputusan rinci (hasil pemeriksaan pembangun; keputusan Claude, silakan dicek pengguna)
1. **Jalur tulis profil.** `group_pegawai_operator` **tidak** di-imply `base.group_partner_manager`. Field profil
   per orang (§4.2) dan sertifikasi ditulis lewat `sudo()` di balik penjaga (pola penjaga siswa di base): hanya grup
   pegawai, dan hanya bila pemanggil memegang **semua** unit tempat orang itu bekerja (atau HRD). Penjaga yang sama
   berlaku untuk record sertifikasi dan untuk field terkait yang diedit dari form pegawai. Hapus pegawai/sertifikasi
   hanya HRD.
2. **Penempatan lintas unit** hanya oleh HRD atau TU yang memegang unit asal **dan** unit tujuan (TU satu unit tidak
   bisa melihat pegawai unit lain). Tidak ada pencarian pegawai unit lain lewat NUPTK/NIK. Pesan galat NUPTK/NIP ganda
   tidak menyebut nama atau unit pemiliknya.
3. **Kontak kerja bersama.** Saat orang ditempatkan di unit kedua, `company_id` kontak kerjanya dikosongkan (seperti
   wali di base) supaya terbaca di semua unitnya; field profil tetap terlindung `groups=`. Pegawai satu unit tetap
   memakai unitnya sebagai company kontak.
4. **Login tanpa email.** Wizard Buat Akun Login punya isian `login` (bawaan = email kerja). Bila email kosong,
   operator mengetik login dan kata sandi awal ditampilkan sekali (pola wizard akun portal). Email kerja memang
   per orang (kontak bersama).
5. **Akun yang sudah ada.** Mengisi `user_id` pada pegawai hanya boleh HRD (mencegah TU menautkan/mengambil akun
   orang lain lalu menambah unit ke akun itu). TU membuat akun hanya lewat tombol Buat Akun Login. Data demo
   menautkan pegawai ke user demo base. Tidak ada migrasi otomatis untuk instalasi lama.
6. **Keluar dari unit (keputusan pengguna 2026-11-25, pilihan A).** Saat record pegawai diarsipkan, unitnya dicabut
   dari `company_ids` akun orang itu (kecuali ia masih punya pegawai aktif lain di unit yang sama). Bila tidak tersisa
   pegawai aktif di unit mana pun, akunnya **dinonaktifkan** (`active=False`, tidak dihapus). Penempatan di yayasan
   diperlakukan sama (company yayasan dicabut/ditambahkan ke akun), dan hanya oleh HRD/superuser. Konsekuensi yang
   diterima: pegawai yang juga orang tua kehilangan akses "Anak Saya" setelah keluar. Mengaktifkan kembali record
   pegawai tidak otomatis mengaktifkan akun (dilakukan HRD/admin). `nti_edu_is_pegawai` mengikuti ada/tidaknya pegawai
   aktif.

## 5. Perubahan di dokumen induk
§I.6 baris `nti_edu_pegawai`: beban mengajar dipindah ke jembatan `nti_edu_pegawai_jadwal` (dirancang bersama
`nti_edu_jadwal`).

## 6. Diserahkan ke pembangun
- Cara grup pegawai membaca/menulis `nti_edu_nik` milik base (field ber-`groups` operator base) — mis. field proxy
  ber-`groups` pegawai — dengan syarat satu NIK per orang dan field base tidak didefinisikan ulang.
- Nilai persis selection (mengikuti istilah Dapodik), tata letak form/kanban, nama xmlid sesuai konvensi §I.4.11.
- Templat email undangan akun internal (templat standar Odoo boleh).
