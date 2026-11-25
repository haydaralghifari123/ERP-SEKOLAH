# Pelengkap `nti_edu_base` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menutup celah antara `nti_edu_base` dan spec Bagian II: helper bernama sesuai spec, master tingkat yayasan bisa dipakai unit, siswa wajib milik unit, dan wizard "Tambah ke Rombel".

**Architecture:** Perubahan kecil di modul `nti_edu_base` yang sudah ada (branch `nti-edu-base`). Helper spec ditambahkan di `res.company` sebagai pintu resmi untuk modul lain (helper lama `_get_aktif()` tetap). Wizard baru mengikuti pola wizard kenaikan kelas (TransientModel, ACL operator, validasi semua baris dulu).

**Tech Stack:** Odoo 18.0 Community, Python 3, PostgreSQL, tes `odoo.tests` (`TransactionCase`, `Form`).

**Spec:** `D:/odoo2/docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md` (Bagian II; §I.5.4 untuk master bersama)

## Global Constraints

- Odoo **18.0 Community** saja; tidak memakai/menyalin kode Enterprise; tidak memakai OCA.
- `__manifest__.py` tetap `'depends': ['base', 'mail', 'portal']`; tidak depend ke `hr`, `account`, `website`.
- Model baru bernama `nti_edu.<nama>`; field baru di model standar berawalan `nti_edu_`.
- Nama field/model/pesan/komentar dalam Bahasa Indonesia; pesan error lewat `_()`.
- View Odoo 18: `<list>` (bukan `<tree>`), `invisible=`/`readonly=` berupa ekspresi.
- Tes: `@tagged('post_install', '-at_install')`, turunan `NtiEduCommon` (`tests/common.py`); tidak bergantung pada data demo dan tetap lulus saat demo terpasang.
- **Commit tanpa baris `Co-Authored-By`** dan tanpa menyebut Claude; identitas git laptop apa adanya. Pesan commit: `nti_edu_base: <ringkasan Bahasa Indonesia>`.
- Perintah tes (PowerShell, bukan Git Bash), DB tes `nti_base_tes` (modul sudah terpasang → `-u`):
  ```
  & "D:/Program Files/python/python.exe" "D:/Program Files/server/odoo-bin" --config=D:/odoo2/.odoo-test.conf -d nti_base_tes -u nti_edu_base --test-tags /nti_edu_base --stop-after-init --http-port 8079 --db-filter=.* --log-level=test
  ```
  Satu kelas: `--test-tags /nti_edu_base:NamaKelasTes`. Lulus = log memuat `0 failed, 0 error(s)`.
  Di akhir tiap task jalankan suite penuh; di Task 4 juga `scripts/uji_tunggal.ps1`.
- Jangan sentuh `odoo.conf`, DB `odoo2`, atau server Odoo/ngrok yang sedang berjalan di port 8070.

## Review Focus

1. Operator multi-unit memilih jurusan di rombel: harus melihat jurusan global, jurusan yayasan, dan jurusan unit rombel itu — **tidak** jurusan unit lain (tes di Task 2).
2. "Tambah ke Rombel" dipanggil dengan pilihan yang memuat siswa unit lain, siswa non-aktif, atau partner bukan siswa: ditolak seluruhnya dengan pesan yang menyebut namanya, tanpa penambahan sebagian (tes di Task 4).
3. "Tambah ke Rombel" untuk rombel tahun ajaran mendatang: `tanggal_masuk` bawaan = tanggal mulai tahun ajaran itu, bukan hari ini (tes di Task 4).
4. `_nti_edu_hari_efektif(tanggal)` dipanggil tanpa `company` dari `self.env['res.company']` kosong: memakai `self.env.company`, bukan error (tes di Task 1).
5. Guru (bukan operator) tidak bisa memakai wizard "Tambah ke Rombel" dan tidak melihat tombolnya (tes di Task 4).

---

### Task 1: Helper dengan nama spec di `res.company`

**Files:**
- Modify: `nti_edu_base/models/res_company.py` (method `_nti_edu_hari_efektif`, tambah dua helper)
- Test: `nti_edu_base/tests/test_kalender.py`

**Interfaces:**
- Produces (dipakai modul fitur, kontrak spec §II.2):
  - `res.company._nti_edu_tahun_ajaran_aktif() -> nti_edu.tahun.ajaran` (recordset 0/1; `@api.model`)
  - `res.company._nti_edu_semester_aktif() -> nti_edu.semester` (recordset 0/1; `@api.model`)
  - `res.company._nti_edu_hari_efektif(tanggal: date, company=None) -> bool`; unit = `company` bila diberikan, selain itu `self` bila tidak kosong, selain itu `self.env.company`.
- Tetap ada (jangan dihapus): `nti_edu.tahun.ajaran._get_aktif()`, `nti_edu.semester._get_aktif()`.

- [ ] **Step 1: Tulis tes gagal** di `TestKalender`:
  - `test_helper_spec_tahun_semester_aktif`: buat tahun aktif + semester aktif; `self.env['res.company']._nti_edu_tahun_ajaran_aktif()` == tahun itu; `..._nti_edu_semester_aktif()` == semester itu; setelah tahun dinonaktifkan keduanya kosong (`assertFalse`).
  - `test_hari_efektif_parameter_company`: untuk Sabtu 2026-08-01 dan `unit_smp.nti_edu_hari_sekolah = '6'`, `unit_sma.nti_edu_hari_sekolah = '5'`: `self.env['res.company']._nti_edu_hari_efektif(date(2026, 8, 1), company=self.unit_smp)` is True; `company=self.unit_sma` is False; `self.unit_sma._nti_edu_hari_efektif(date(2026, 8, 1), company=self.unit_smp)` is True (parameter menang atas `self`).
  - `test_hari_efektif_tanpa_company_memakai_company_aktif`: `self.env['res.company'].with_company(self.unit_sma)._nti_edu_hari_efektif(date(2026, 8, 1))` is False dan untuk Senin 2026-08-03 is True.
- [ ] **Step 2: Jalankan** `--test-tags /nti_edu_base:TestKalender` → gagal (`AttributeError`/`TypeError` unexpected keyword `company`).
- [ ] **Step 3: Implementasi** di `res_company.py`: dua helper `@api.model` yang mendelegasikan ke `_get_aktif()`; ubah tanda tangan `_nti_edu_hari_efektif(self, tanggal, company=None)`, tentukan unit sesuai Interfaces lalu `ensure_one()`; logika libur/akhir pekan tidak berubah (tetap `sudo()` untuk libur). Perbarui docstring.
- [ ] **Step 4: Jalankan** `TestKalender` lalu suite penuh → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_base: helper tahun ajaran, semester, dan hari efektif sesuai nama spec`

### Task 2: Master tingkat yayasan bisa dipakai unit

**Files:**
- Modify: `nti_edu_base/models/jurusan.py`, `nti_edu_base/models/mapel.py` (override `_check_company_domain`)
- Modify: `nti_edu_base/models/hari_libur.py` (`company_id` → `ondelete='cascade'`)
- Test: `nti_edu_base/tests/test_rombel.py` (jurusan di rombel), `nti_edu_base/tests/test_kalender.py` (libur)

**Interfaces:**
- Produces: `nti_edu.jurusan` dan `nti_edu.mapel` menerima record ber-`company_id` kosong **atau** induk (yayasan) dari company pemakai, pada pengecekan `check_company` dan domain dropdown. Modul fitur yang punya `Many2one('nti_edu.mapel', check_company=True)` otomatis ikut.

- [ ] **Step 1: Tulis tes gagal** di `TestRombel`:
  - `test_jurusan_yayasan_dipakai_rombel_unit`: buat jurusan `company_id=self.yayasan` dan rombel SMA dengan `jurusan_id` itu → tersimpan tanpa error.
  - `test_jurusan_unit_lain_ditolak`: jurusan `company_id=self.unit_smp` dipakai rombel SMA → `UserError` (pesan check_company Odoo).
  - `test_domain_jurusan_rombel`: `domain = self.env['nti_edu.jurusan']._check_company_domain(self.unit_sma)`; `search(domain)` memuat jurusan global (company kosong), jurusan yayasan, jurusan SMA; tidak memuat jurusan SMP.
  - di `TestKalender`: `test_libur_ikut_terhapus_bersama_unit`: buat company unit baru tanpa data lain + libur milik unit itu; `unlink()` company (sebagai superuser) → libur tidak ada lagi (`exists()` kosong).
- [ ] **Step 2: Jalankan** `TestRombel` dan `TestKalender` → tiga tes jurusan dan tes libur gagal.
- [ ] **Step 3: Implementasi** `_check_company_domain(self, companies)` di jurusan dan mapel. Tanpa `companies` → `[('company_id', '=', False)]`; selain itu `['|', ('company_id', '=', False), ('company_id', 'parent_of', <ids>)]`, dengan `<ids>` = `unquote(companies)` bila `companies` bertipe `odoo.tools.unquote` (dipakai domain view) atau `models.to_company_ids(companies)`. Ubah `hari_libur.company_id` ke `ondelete='cascade'`.
- [ ] **Step 4: Jalankan** dua kelas lalu suite penuh → `0 failed, 0 error(s)`. Pastikan form rombel masih terbuka di `test_tampilan` (domain view memakai `parent_of`).
- [ ] **Step 5: Commit** `nti_edu_base: jurusan dan mapel tingkat yayasan bisa dipakai unit; libur ikut terhapus bersama unit`

### Task 3: Siswa wajib milik unit sekolah

**Files:**
- Modify: `nti_edu_base/models/res_partner.py` (`_check_nti_edu_siswa_unit`)
- Modify: `nti_edu_base/views/siswa_views.xml` (domain `company_id` di form siswa)
- Test: `nti_edu_base/tests/test_siswa.py`

**Interfaces:**
- Produces: setiap partner `nti_edu_is_siswa` punya `company_id.nti_edu_jenis == 'unit'` (sekolah mandiri = company root berjenis `unit`, §I.5.4, tetap sah).

- [ ] **Step 1: Tulis tes gagal** di kelas tes siswa yang ada:
  - `test_siswa_di_yayasan_ditolak`: `_buat_siswa('X', self.yayasan, 'Y001')` → `ValidationError`.
  - `test_siswa_sekolah_mandiri_boleh`: company root baru `nti_edu_jenis='unit'` tanpa parent; buat siswa di sana → berhasil.
  - `test_form_siswa_domain_unit`: arch form `nti_edu_base.view_siswa_form` (parsing seperti `test_tampilan`) — field `company_id` punya domain yang memuat `nti_edu_jenis`.
- [ ] **Step 2: Jalankan** kelas itu → tiga tes gagal.
- [ ] **Step 3: Implementasi**: perluas `_check_nti_edu_siswa_unit` agar juga menolak company yang `nti_edu_jenis != 'unit'` (pesan `_('Siswa harus terdaftar pada unit sekolah, bukan yayasan.')`); tambah `domain="[('nti_edu_jenis', '=', 'unit')]"` di field `company_id` form siswa.
- [ ] **Step 4: Jalankan** suite penuh → `0 failed, 0 error(s)` (demo dan tes lain sudah memakai unit; perbaiki bila ada yang memakai yayasan).
- [ ] **Step 5: Commit** `nti_edu_base: siswa wajib terdaftar di unit sekolah`

### Task 4: Wizard "Tambah ke Rombel" + catatan spec

**Files:**
- Create: `nti_edu_base/wizard/tambah_rombel_wizard.py`, `nti_edu_base/wizard/tambah_rombel_wizard_views.xml`
- Create: `nti_edu_base/tests/test_tambah_rombel.py` (daftarkan di `tests/__init__.py`)
- Modify: `nti_edu_base/wizard/__init__.py`, `nti_edu_base/__manifest__.py` (`data`: views wizard sebelum `views/siswa_views.xml`), `nti_edu_base/security/ir.model.access.csv`, `nti_edu_base/views/siswa_views.xml` (tombol header list siswa)
- Modify: `docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md` (§II.4, §II.5)

**Interfaces:**
- Consumes: `nti_edu.rombel.anggota` (`rombel_id`, `siswa_id`, `tanggal_masuk`) beserta constraint yang ada (satu rombel per tahun, siswa satu unit dengan rombel).
- Produces:
  - Model `nti_edu.tambah.rombel.wizard` (TransientModel): `rombel_id` (m2o `nti_edu.rombel`, required), `siswa_ids` (m2m `res.partner`, domain `[('nti_edu_is_siswa', '=', True)]`, default dari context `active_ids` bila `active_model == 'res.partner'`), `tanggal_masuk` (Date, required).
  - `action_tambah(self) -> dict` (aksi tutup jendela `{'type': 'ir.actions.act_window_close'}`).
  - Form view xmlid `nti_edu_base.view_tambah_rombel_wizard_form` (field `rombel_id`, `tanggal_masuk`, `siswa_ids` sebagai list; tombol `action_tambah` dan Batal).
  - Action xmlid `nti_edu_base.action_tambah_rombel_wizard` (target `new`), dipanggil tombol header list siswa (`groups="nti_edu_base.group_base_operator"`).

- [ ] **Step 1: Tulis tes gagal** `TestTambahRombel(NtiEduCommon)` (setUpClass: tahun aktif berjalan mencakup hari ini, tahun depan; rombel SMP tahun aktif, rombel SMP tahun depan, rombel SMA; siswa SMP `a`, `b`, siswa SMA `c`). Semua sebagai `user_operator_smp` kecuali disebut lain:
  - `test_tambah_dua_siswa`: wizard dengan context `active_model='res.partner', active_ids=[a, b]`, `rombel_id` = rombel SMP aktif → `action_tambah()`; keduanya punya anggota di rombel itu dengan `tanggal_masuk` = hari ini.
  - `test_tanggal_masuk_tahun_depan`: `Form` wizard, set `rombel_id` = rombel tahun depan → `tanggal_masuk` == `tanggal_mulai` tahun depan.
  - `test_siswa_unit_lain_ditolak_tanpa_sebagian`: `siswa_ids=[a, c]`, rombel SMP (jalankan sebagai superuser agar `c` terbaca) → `UserError` yang pesannya memuat nama `c`; `a` tidak punya anggota baru.
  - `test_siswa_sudah_di_rombel_tahun_sama_ditolak`: `a` sudah anggota rombel SMP aktif lain → `UserError` memuat nama `a`.
  - `test_siswa_tidak_aktif_ditolak`: `b.nti_edu_status = 'lulus'` → `UserError` memuat nama `b`.
  - `test_bukan_siswa_ditolak`: partner biasa di `siswa_ids` (lewat `(6, 0, ids)`, superuser) → `UserError`.
  - `test_guru_tidak_bisa`: `with_user(self.user_guru_smp)` create wizard → `AccessError`.
  - `test_tombol_di_list_siswa`: arch list `nti_edu_base.view_siswa_list` memuat `<button>` dengan `name` = id action `action_tambah_rombel_wizard` dan `groups` operator (pola parsing arch seperti `test_tampilan.py`).
- [ ] **Step 2: Jalankan** `--test-tags /nti_edu_base:TestTambahRombel` → gagal (model belum ada).
- [ ] **Step 3: Implementasi wizard.** `tanggal_masuk`: compute stored `readonly=False` dari `rombel_id` = hari ini bila hari ini di dalam rentang tahun ajaran rombel, selain itu `tanggal_mulai` tahun ajaran itu (fallback hari ini bila rombel kosong). `action_tambah`: validasi **semua** siswa dulu dan kumpulkan masalah — bukan siswa, `nti_edu_status != 'aktif'` atau tidak `active`, `company_id != rombel_id.company_id`, sudah punya anggota terbuka (`tanggal_keluar` kosong) di tahun ajaran rombel (cari dengan `sudo()`); bila ada masalah raise satu `UserError` berisi daftar nama + alasan. Setelah lolos, buat anggota sebagai user pemanggil (bukan sudo) supaya ACL/rule berlaku. ACL: operator `1,1,1,1`. Tidak ada compute yang membaca data siswa dengan sudo (`compute_sudo=False` pada `tanggal_masuk`).
- [ ] **Step 4: Tambah tombol** di `<list>` siswa: `<header><button name="%(nti_edu_base.action_tambah_rombel_wizard)d" type="action" string="Tambah ke Rombel" groups="nti_edu_base.group_base_operator"/></header>`.
- [ ] **Step 5: Jalankan** `TestTambahRombel`, suite penuh, lalu `scripts/uji_tunggal.ps1` → semuanya `0 failed, 0 error(s)`.
- [ ] **Step 6: Perbarui spec**: §II.4 baris "Wali Murid" → `(kontak yang terhubung sebagai wali; hanya Operator, terbatas unit anaknya — data wali sensitif §II.5)`; §II.5 baris `group_base_operator` → tambahkan "tanpa hapus; hapus data hanya Admin" agar sesuai keputusan perbaikan review akhir.
- [ ] **Step 7: Commit** (kode dan spec terpisah):
  `nti_edu_base: wizard Tambah ke Rombel dari daftar siswa`
  `docs: catat menu Wali Murid khusus operator dan hak hapus admin`
