# Merapikan `nti_edu_base` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menutup temuan kecil yang tertunda dari review `nti_edu_base` dan menambah uji asap di browser sungguhan supaya galat tampilan (seperti `kanban_image` di Odoo 18) tertangkap tes.

**Architecture:** Tiga task di modul `nti_edu_base` yang sudah ada. Task 1 menambah tour web (`web_tour`, sudah tersedia lewat dependensi `mail`) yang membuka setiap layar Data Sekolah, dijalankan dari `HttpCase.start_tour`. Task 2 dan 3 adalah perbaikan model dan wizard kecil, masing-masing dengan tes ORM.

**Tech Stack:** Odoo 18.0 Community, Python 3, JavaScript (tour `@web/core/registry`, `web_tour.tours`), Chrome headless (`C:\Program Files\Google\Chrome\Application\chrome.exe`) untuk `HttpCase`.

**Spec:** `D:/odoo2/docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md` (Bagian II; §II.3 siklus data, §II.5 hak akses, §II.6 akun portal)

## Global Constraints

- Odoo **18.0 Community** saja; tidak memakai/menyalin kode Enterprise; tidak memakai OCA.
- `__manifest__.py` tetap `'depends': ['base', 'mail', 'portal']` (tour memakai `web_tour` yang sudah dibawa `mail`; jangan tambah dependensi).
- Nama field/model/pesan/komentar dalam Bahasa Indonesia; pesan error lewat `_()`.
- View Odoo 18: `<list>`, `invisible=`/`readonly=` berupa ekspresi; kanban bergaya `t-name="card"` tanpa helper lama (`kanban_image`, `user_context`).
- Tes: `@tagged('post_install', '-at_install')`, turunan `NtiEduCommon` (atau `HttpCase` yang membuat datanya sendiri); tidak bergantung pada data demo, tetap lulus saat demo terpasang.
- **Commit tanpa baris `Co-Authored-By`** dan tanpa menyebut Claude. Pesan commit: `nti_edu_base: <ringkasan Bahasa Indonesia>`.
- Perintah tes (PowerShell, bukan Git Bash), DB tes `nti_base_tes`:
  ```
  & "D:/Program Files/python/python.exe" "D:/Program Files/server/odoo-bin" --config=D:/odoo2/.odoo-test.conf -d nti_base_tes -u nti_edu_base --test-tags /nti_edu_base --stop-after-init --http-port 8079 --db-filter=.* --log-level=test
  ```
  Satu kelas: `--test-tags /nti_edu_base:NamaKelasTes`. Lulus = `0 failed, 0 error(s)`. Di akhir setiap task: suite penuh + `scripts/uji_tunggal.ps1 -Modul nti_edu_base`.
- Jangan sentuh `odoo.conf`, DB `odoo2`, atau server Odoo (debugger VS Code) / ngrok di port 8070.

## Review Focus

1. Galat klien (Owl/JS) di layar mana pun Data Sekolah — kanban, list, form, wizard — harus membuat tes gagal, bukan lolos diam-diam (Task 1, dibuktikan dengan RED terhadap `kanban_image`).
2. Tes browser tidak boleh "lulus" karena dilewati: bila Chrome tidak ditemukan, laporan harus menyebutnya (Task 1).
3. Siswa yang diarsipkan tidak lagi dihitung di rombel dan tidak ikut wizard kenaikan kelas (Task 2).
4. Wizard "Tambah ke Rombel" yang menerima id siswa yang tidak terbaca pemanggil harus menolak dengan pesan, bukan menambah sebagian diam-diam (Task 3).
5. Kenaikan kelas ke tahun ajaran yang lebih awal, atau `naik` ke tingkat yang tidak lebih tinggi, ditolak (Task 3).

---

### Task 1: Uji asap layar Data Sekolah di browser

**Files:**
- Create: `nti_edu_base/static/tests/tours/nti_edu_base_asap.js`
- Create: `nti_edu_base/tests/test_ui.py` (daftarkan di `tests/__init__.py`)
- Modify: `nti_edu_base/__manifest__.py` (`'assets': {'web.assets_tests': ['nti_edu_base/static/tests/tours/**/*']}`)

**Interfaces:**
- Produces: tour `nti_edu_base_asap` (registry `web_tour.tours`), kelas tes `TestUiDataSekolah(HttpCase)`.

- [ ] **Step 1: Tulis tour + tes.** `TestUiDataSekolah.setUpClass` membuat datanya sendiri (unit, tahun ajaran aktif, rombel, ≥1 siswa dengan wali, hari libur) dan user admin Data Sekolah (`group_base_admin` + `base.group_user`, akses ke unit itu). Tour (mulai dari `/odoo`): buka app Data Sekolah; untuk setiap menu Siswa, Rombel, Wali Murid, Kalender › Tahun Ajaran & Semester, Kalender › Hari Libur, Konfigurasi › (Unit Sekolah, Jenjang & Tingkat, Jurusan, Mata Pelajaran, Ruang): buka, tunggu view tampil, ganti ke setiap view type yang tersedia di switcher (kanban/list), buka record pertama (form), kembali. Tambahan: dari list Siswa centang satu siswa → klik "Tambah ke Rombel" → wizard tampil → batal; dari form Rombel klik "Kenaikan Kelas" → wizard tampil → batal. Tes: `self.start_tour('/odoo', 'nti_edu_base_asap', login=<admin>)`; tes kedua `test_operator` menjalankan tour versi operator (tanpa Konfigurasi) — boleh tour terpisah `nti_edu_base_asap_operator` atau satu tour dengan langkah bersyarat.
- [ ] **Step 2: Buktikan RED.** Sementara (jangan di-commit) kembalikan kanban siswa ke `<img t-att-src="kanban_image('res.partner', 'avatar_128', record.id.raw_value)"/>`, jalankan `--test-tags /nti_edu_base:TestUiDataSekolah` → gagal dengan `kanban_image is not a function`. Kembalikan perubahan (`git checkout -- nti_edu_base/views/siswa_views.xml`).
- [ ] **Step 3: GREEN** kelas itu, lalu suite penuh + `uji_tunggal.ps1`. Pastikan log memperlihatkan tour benar-benar berjalan (bukan `skip`/"Chrome not found").
- [ ] **Step 4: Commit** `nti_edu_base: uji asap layar Data Sekolah di browser (tour)`

### Task 2: Perbaikan kecil model

**Files:**
- Modify: `nti_edu_base/models/jurusan.py`, `nti_edu_base/models/mapel.py`, `nti_edu_base/models/res_company.py`, `nti_edu_base/models/res_partner.py`, `nti_edu_base/models/rombel.py` (bila perlu untuk `jumlah_siswa`)
- Test: `nti_edu_base/tests/test_rombel.py`, `nti_edu_base/tests/test_kalender.py`, `nti_edu_base/tests/test_siswa.py`

**Interfaces:**
- Produces: perilaku `_check_company_domain` jurusan/mapel tidak berubah (tes Task 2 rencana sebelumnya tetap hijau); `res.company._nti_edu_tahun_ajaran_aktif()` / `_nti_edu_semester_aktif()` bisa dipanggil oleh user portal.

- [ ] **Step 1: Tes gagal:**
  - `test_mapel_yayasan_dipakai_unit` (test_rombel): domain `self.env['nti_edu.mapel']._check_company_domain(self.unit_sma)` memuat mapel global + yayasan + SMA, tidak memuat mapel SMP.
  - `test_jurusan_unit_ikut_terhapus` (test_rombel): unit baru tanpa data lain + jurusan & mapel milik unit itu; `unlink()` unit → keduanya tidak ada lagi.
  - `test_helper_aktif_untuk_portal` (test_kalender): user portal (`base.group_portal`) memanggil `env['res.company'].with_user(portal)._nti_edu_tahun_ajaran_aktif()` dan `_nti_edu_semester_aktif()` → mengembalikan record aktif, tanpa `AccessError`.
  - `test_arsip_siswa_menutup_keanggotaan` (test_siswa): siswa anggota rombel aktif; operator `write({'active': False})` → keanggotaan terbuka mendapat `tanggal_keluar`; `rombel.jumlah_siswa` turun.
- [ ] **Step 2: Jalankan** → tes mapel lulus sudah (penjaga regresi), tiga lainnya gagal.
- [ ] **Step 3: Implementasi:** ganti override buatan sendiri di jurusan & mapel dengan `_check_company_domain = models.check_company_domain_parent_of` (bawaan Odoo 18, `odoo/models.py`); `company_id` jurusan & mapel `ondelete='cascade'`; kedua helper membaca dengan `sudo()` (data tahun ajaran tidak sensitif) dan mengembalikan record dalam env pemanggil (`.with_env(self.env)` tidak perlu — cukup kembalikan hasil sudo `.sudo(False)`); `res.partner.write` menutup keanggotaan bila `vals.get('active') is False` untuk siswa (pakai `_nti_edu_tutup_keanggotaan`).
- [ ] **Step 4: Suite penuh + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_base: master unit ikut terhapus, helper aktif untuk portal, arsip siswa menutup keanggotaan`

### Task 3: Pengerasan wizard

**Files:**
- Modify: `nti_edu_base/wizard/tambah_rombel_wizard.py`, `nti_edu_base/wizard/kenaikan_kelas_wizard.py`, `nti_edu_base/wizard/akun_portal_wizard.py`, `nti_edu_base/wizard/akun_portal_wizard_views.xml`
- Test: `nti_edu_base/tests/test_tambah_rombel.py`, `nti_edu_base/tests/test_kenaikan.py`, `nti_edu_base/tests/test_akun_portal.py`

**Interfaces:**
- Produces: `nti_edu.akun.portal.wizard.action_tutup(self) -> dict` (mengosongkan `password_awal`, mengembalikan `{'type': 'ir.actions.act_window_close'}`), dipakai tombol "Tutup" di footer menggantikan `special="cancel"`.

- [ ] **Step 1: Tes gagal:**
  - `test_id_tidak_terbaca_ditolak` (test_tambah_rombel): sebagai `user_operator_smp`, wizard dengan context `active_model='res.partner', active_ids=[siswa_smp.id, siswa_sma.id]` (SMA tidak terbaca) → `action_tambah()` raise `UserError` yang menyebut "tidak dapat diakses"; tidak ada keanggotaan baru.
  - `test_tujuan_tahun_lebih_awal_ditolak` (test_kenaikan): rombel tujuan di tahun ajaran yang mulai sebelum tahun ajaran asal → `UserError`.
  - `test_naik_ke_tingkat_tidak_lebih_tinggi_ditolak` (test_kenaikan): aksi `naik` ke rombel dengan `tingkat_id.urutan` ≤ tingkat asal → `UserError`; aksi `tinggal` ke tingkat yang sama tetap boleh.
  - `test_tutup_mengosongkan_password` (test_akun_portal): setelah `action_buat` menghasilkan `password_awal`, `action_tutup()` → `password_awal` kosong; arch form wizard punya `button[@name="action_tutup"]`.
- [ ] **Step 2: Jalankan** → keempatnya gagal.
- [ ] **Step 3: Implementasi:** Tambah ke Rombel — di `action_tambah`, bila `active_model == 'res.partner'`, bandingkan `active_ids` dengan `self.siswa_ids.ids`; id yang hilang → masuk daftar masalah dengan alasan `_('tidak dapat diakses atau bukan siswa')` (tampilkan jumlahnya, bukan nama — nama tidak terbaca). Kenaikan — di validasi `naik`/`tinggal`: `tujuan.tahun_ajaran_id.tanggal_mulai > asal.tahun_ajaran_id.tanggal_mulai`, dan untuk `naik` `tujuan.tingkat_id.urutan > asal.tingkat_id.urutan`; pesan `_()` menyebut nama siswa/rombel. Akun portal — `action_tutup` + tombol footer.
- [ ] **Step 4: Suite penuh + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_base: wizard menolak id tak terbaca, kenaikan ke tahun/tingkat salah, dan hapus kata sandi saat ditutup`

### Task 4: Kunci kontak wali (keputusan pengguna 2026-11-25)

Email wali adalah login dan kanal reset kata sandi akun portalnya; data wali sensitif (§II.5). Saat ini operator unit mana pun (dan siapa pun dengan `base.group_partner_manager`) bisa mengubah email wali dari unit lain lalu meminta reset kata sandi.

**Files:**
- Modify: `nti_edu_base/models/res_partner.py` (penjaga di `write`)
- Test: `nti_edu_base/tests/test_siswa.py`

**Interfaces:**
- Produces: `FIELD_KONTAK_WALI = {'email', 'phone', 'mobile'}` di `res_partner.py`; `res.partner._nti_edu_boleh_ubah_kontak_wali(self) -> bool` (self = satu partner wali, dievaluasi untuk `self.env.user`).

- [ ] **Step 1: Tes gagal** di `TestSiswa` (wali `w` dengan anak di SMP; buat juga `user_operator_sma` = operator SMA saja):
  - `test_operator_unit_anak_ubah_email_wali`: `user_operator_smp` menulis `email` wali → berhasil.
  - `test_operator_unit_lain_tidak_ubah_email_wali`: `user_operator_sma` menulis `email`/`phone`/`mobile` wali → `AccessError`; nilai tidak berubah.
  - `test_pengelola_kontak_non_sekolah_tidak_ubah_email_wali`: user internal dengan `base.group_partner_manager` saja → `AccessError`.
  - `test_wali_ubah_kontak_sendiri`: user portal milik wali menulis `email` partner-nya sendiri (lewat `with_user(portal).partner_id.write` dengan izin yang ada, atau `res.users` preferensi) → berhasil.
  - `test_field_lain_wali_tetap_bebas`: `user_operator_sma` menulis `comment` wali → berhasil (hanya kontak yang dikunci).
- [ ] **Step 2: Jalankan** `TestSiswa` → tes penolakan gagal.
- [ ] **Step 3: Implementasi:** di `write`, bila `FIELD_KONTAK_WALI & set(vals)` dan bukan `env.su`, untuk setiap record dengan `nti_edu_is_wali` (baca lewat `sudo()`) wajib `_nti_edu_boleh_ubah_kontak_wali()`: benar bila `self.env.user.partner_id == partner`, atau user punya `GRUP_OPERATOR` dan ada anak (`nti_edu_anak_ids.siswa_id`, baca sudo) dengan `company_id in self.env.user.company_ids`. Selain itu `AccessError(_("Kontak wali hanya boleh diubah oleh walinya sendiri atau Operator Data Sekolah di unit anaknya."))`.
- [ ] **Step 4: Suite penuh + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_base: kontak wali hanya diubah wali sendiri atau operator unit anaknya`
