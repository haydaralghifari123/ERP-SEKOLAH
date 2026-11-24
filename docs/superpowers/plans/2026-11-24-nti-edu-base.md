# `nti_edu_base` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun modul fondasi `nti_edu_base`: master bersama (unit, kalender akademik, rombel, mapel, ruang), data
siswa & wali di `res.partner`, grup dasar, akun portal, kerangka portal "Anak Saya", wizard kenaikan kelas, app
"Data Sekolah", dan data demo.

**Architecture:** Satu addon Odoo 18 Community di `D:\odoo2\nti_edu_base`, depends `base`, `mail`, `portal`. Yayasan =
root `res.company`, unit = branch. Siswa = `res.partner` dengan field berawalan `nti_edu_`. Akses data anak untuk
portal/wali selalu lewat satu helper `res.users._nti_edu_siswa_portal()` + `sudo()`.

**Tech Stack:** Odoo 18 Community (Python 3.12, PostgreSQL), QWeb, tes `odoo.tests` (`TransactionCase`, `HttpCase`).

**Spec:** `docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md` — Bagian II (dan aturan §I.4). Baca keduanya.

## Global Constraints

- Odoo **18.0 Community** saja; tidak boleh memakai/menyalin kode Enterprise; tidak memakai OCA.
- `__manifest__.py`: `'depends': ['base', 'mail', 'portal']`, `'version': '18.0.1.0.0'`, `'license': 'LGPL-3'`,
  `'category': 'Education'`, `'application': True`. **Tidak** depend ke `hr`, `account`, `website`.
- Model baru bernama `nti_edu.<nama>`; field yang ditambahkan ke model standar (`res.partner`, `res.company`,
  `res.users`) **selalu** berawalan `nti_edu_` (supaya tidak bentrok dengan field `nis`/`kelas` modul lama).
- Nama field/model/pesan/komentar dalam Bahasa Indonesia; pesan error lewat `_()`.
- View Odoo 18: `<list>` (bukan `<tree>`), atribut `invisible=`/`readonly=` berupa ekspresi (bukan `attrs`).
- Tes: `@tagged('post_install', '-at_install')`. Tes tidak boleh bergantung pada data demo, dan harus tetap lulus
  saat demo terpasang (lihat `tests/common.py` di Task 1).
- **Commit tanpa baris `Co-Authored-By`** dan tanpa menyebut Claude; pakai identitas git laptop apa adanya.
- Perintah tes (PowerShell), DB tes `nti_base_tes`:
  ```
  & "D:/Program Files/python/python.exe" "D:/Program Files/server/odoo-bin" --config=D:/odoo2/odoo.conf -d nti_base_tes -i nti_edu_base --test-tags /nti_edu_base --stop-after-init --http-port 8079 --db-filter=.* --log-level=test
  ```
  Pemasangan pertama pakai `-i`; berikutnya ganti `-i` dengan `-u`. Untuk satu kelas tes:
  `--test-tags /nti_edu_base:NamaKelasTes`. Lulus = log memuat `0 failed, 0 error(s)`.
  `--db-filter=.*` wajib karena `odoo.conf` berisi `dbfilter = ^odoo2$`.

## Review Focus

1. **Siswa dibuat tanpa unit** (mis. dari app Kontak, `company_id` kosong) → harus ditolak dengan pesan jelas, bukan
   lolos lalu terlihat semua unit. Tes: Task 3 `test_siswa_wajib_unit`.
2. **Login portal bentrok** (NISN sudah jadi login user lain, atau email wali sudah dipakai) → `UserError` yang
   menyebut login-nya, bukan error SQL. Tes: Task 6 `test_login_bentrok_pesan_jelas`.
3. **Siswa pindah unit** padahal masih anggota rombel unit lama → anggota rombel harus satu unit dengan siswa;
   menambah siswa unit A ke rombel unit B ditolak. Tes: Task 4 `test_anggota_beda_unit_ditolak`.
4. **Menghapus tahun ajaran yang sudah punya rombel/semester** → ditolak (`ondelete='restrict'`), riwayat kelas tidak
   hilang. Tes: Task 4 `test_hapus_tahun_ajaran_berrombel_ditolak`.
5. **Hari libur satu hari** (`tanggal_selesai` kosong) → dianggap hanya tanggal mulai. Tes: Task 2
   `test_libur_satu_hari`.

---

## Struktur berkas

```
nti_edu_base/
├─ __init__.py, __manifest__.py
├─ models/
│  ├─ __init__.py
│  ├─ res_company.py        # field unit + _nti_edu_hari_efektif
│  ├─ jenjang.py            # nti_edu.jenjang, nti_edu.tingkat
│  ├─ jurusan.py            # nti_edu.jurusan
│  ├─ tahun_ajaran.py       # nti_edu.tahun.ajaran, nti_edu.semester
│  ├─ hari_libur.py         # nti_edu.hari.libur
│  ├─ mapel.py              # nti_edu.mapel
│  ├─ ruang.py              # nti_edu.ruang
│  ├─ rombel.py             # nti_edu.rombel, nti_edu.rombel.anggota
│  ├─ res_partner.py        # field siswa/wali + penjaga tulis
│  ├─ siswa_wali.py         # nti_edu.siswa.wali
│  └─ res_users.py          # _nti_edu_siswa_portal
├─ wizard/
│  ├─ akun_portal_wizard.py (+ _views.xml)
│  └─ kenaikan_kelas_wizard.py (+ _views.xml)
├─ controllers/portal.py
├─ security/nti_edu_security.xml, nti_edu_rules.xml, ir.model.access.csv
├─ data/jenjang_data.xml
├─ demo/nti_edu_demo.xml
├─ views/  (satu file per model + menu.xml + portal_templates.xml)
└─ tests/  (common.py + satu file per task)
scripts/uji_tunggal.ps1      # di root repo D:\odoo2, dipakai semua modul
```

---

### Task 0: Kerangka modul + skrip uji pasang tunggal

**Files:**
- Create: `nti_edu_base/__init__.py`, `nti_edu_base/__manifest__.py`, `nti_edu_base/models/__init__.py`,
  `nti_edu_base/tests/__init__.py`, `nti_edu_base/tests/test_instal.py`, `scripts/uji_tunggal.ps1`

**Interfaces:**
- Produces: `scripts/uji_tunggal.ps1 -Modul <nama>`: membuang DB `uji_<nama>` bila ada, lalu memasang modul itu saja
  dengan tes (`-i <nama> --test-tags /<nama>`) di DB baru. Keluar dengan kode ≠ 0 bila log tidak memuat
  `0 failed, 0 error(s)`.

- [ ] **Step 1: Cek lingkungan.** `Test-Path "D:/Program Files/python/python.exe"` dan
  `& "D:/Program Files/PostgreSQL/bin/psql.exe" --version` → keduanya ada.
- [ ] **Step 2: Tes gagal.** `tests/test_instal.py`, kelas `TestInstal(TransactionCase)`:
  `test_modul_terpasang`: `self.assertEqual(self.env['ir.module.module'].search([('name','=','nti_edu_base')]).state, 'installed')`.
  Jalankan perintah tes → gagal karena modul belum ada (`module nti_edu_base: not installable` / tidak ditemukan).
- [ ] **Step 3: Buat manifest** sesuai Global Constraints (`name`: "Data Sekolah", `summary`: "Fondasi NTI Edu: unit,
  kalender akademik, rombel, siswa & wali, portal orang tua", `author`: diisi nama dari `git config user.name`).
  `data` dibiarkan kosong dulu; tiap task menambah berkasnya.
- [ ] **Step 4: Jalankan perintah tes** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Tulis `scripts/uji_tunggal.ps1`.** Baca `db_password` dari `D:\odoo2\odoo.conf` ke `$env:PGPASSWORD`,
  `dropdb.exe -h localhost -U odoo --if-exists uji_<modul>`, lalu odoo-bin dengan argumen perintah tes (DB
  `uji_<modul>`, port 8079). Jalankan `.\scripts\uji_tunggal.ps1 -Modul nti_edu_base` → lulus.
- [ ] **Step 6: Commit** `git add nti_edu_base scripts` → `git commit -m "nti_edu_base: kerangka modul dan skrip uji pasang tunggal"`.

---

### Task 1: Grup, unit sekolah, jenjang/tingkat/jurusan, data awal

**Files:**
- Create: `security/nti_edu_security.xml`, `security/ir.model.access.csv`, `models/res_company.py`, `models/jenjang.py`,
  `models/jurusan.py`, `data/jenjang_data.xml`, `tests/common.py`, `tests/test_struktur.py`
- Modify: `__manifest__.py` (data), `models/__init__.py`, `tests/__init__.py`

**Interfaces:**
- Produces grup (xmlid `nti_edu_base.`): `group_base_pengguna` (implies `base.group_user`), `group_base_operator`
  (implies pengguna **dan `base.group_partner_manager`** — hak tulis `res.partner` bawaan hanya untuk grup itu),
  `group_base_admin` (implies operator), `group_base_eksternal` (implies `base.group_user`). Kategori
  `module_category_nti_edu_data_sekolah` "NTI Edu / Data Sekolah".
- Produces `res.company`: `nti_edu_jenis` Selection `[('yayasan','Yayasan'),('unit','Unit Sekolah')]` default `'unit'`;
  `nti_edu_jenjang_id` M2o `nti_edu.jenjang`; `nti_edu_npsn` Char; `nti_edu_kode` Char (unik bila diisi);
  `nti_edu_kepala_id` M2o `res.users`; `nti_edu_hari_sekolah` Selection `[('5','5 hari'),('6','6 hari')]` default `'5'`.
- Produces `nti_edu.jenjang` (name, kode unik, urutan, tingkat_ids), `nti_edu.tingkat` (name, jenjang_id required,
  urutan Integer, `is_akhir` Boolean), `nti_edu.jurusan` (name, kode, jenjang_id, company_id opsional).
- Produces data xmlid `nti_edu_base.jenjang_tk|sd|smp|sma|smk` dan tingkat
  `tingkat_tk_a`, `tingkat_tk_b`, `tingkat_sd_1..6`, `tingkat_smp_7..9`, `tingkat_sma_10..12`, `tingkat_smk_10..12`
  (name "Kelas VII" dst., urutan = angka kelas; TK A=1, B=2; `is_akhir` True untuk TK B, SD 6, SMP 9, SMA 12, SMK 12).
- Produces `tests/common.py` kelas `NtiEduCommon(TransactionCase)`: di `setUpClass` menonaktifkan semua tahun ajaran
  aktif yang ada (demo), membuat `cls.yayasan` (root, `nti_edu_jenis='yayasan'`), `cls.unit_smp` dan `cls.unit_sma`
  (branch dari yayasan, jenjang SMP/SMA, kode `smpt`/`smat`), serta user tes:
  `cls.user_operator_smp` (operator, company_ids = [unit_smp]), `cls.user_guru_smp` (pengguna, [unit_smp]),
  `cls.user_guru_sma` (pengguna, [unit_sma]), `cls.user_eksternal` (eksternal, [unit_smp]).
  Tahun ajaran/rombel/siswa ditambahkan ke common oleh task berikutnya lewat helper
  `cls._buat_siswa(nama, unit, nis, **vals)`.

- [ ] **Step 1: Tes gagal** `tests/test_struktur.py` (`TestStruktur(NtiEduCommon)`):
  - `test_rantai_grup`: `user_operator_smp.has_group('nti_edu_base.group_base_pengguna')` True dan
    `has_group('base.group_partner_manager')` True; `user_guru_smp.has_group('nti_edu_base.group_base_operator')` False.
  - `test_data_jenjang`: `env.ref('nti_edu_base.jenjang_sma').tingkat_ids.mapped('urutan') == [10, 11, 12]`;
    `env.ref('nti_edu_base.tingkat_sma_12').is_akhir` True.
  - `test_unit_adalah_branch`: `unit_smp.parent_id == yayasan` dan `unit_smp.root_id == yayasan`.
  - `test_kode_unit_unik`: membuat company lain dengan `nti_edu_kode='smpt'` → `ValidationError` (constraint Python
    `@api.constrains('nti_edu_kode')`, kode kosong boleh berulang).
- [ ] **Step 2: Jalankan** `--test-tags /nti_edu_base:TestStruktur` → gagal (grup/model belum ada).
- [ ] **Step 3: Implementasi** model, grup, ACL (jenjang/tingkat/jurusan: baca `group_base_pengguna`, CRUD
  `group_base_admin`), data awal. `jenjang_data.xml` dengan `noupdate="1"`.
- [ ] **Step 4: Jalankan** dengan `-u` → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_base: grup dasar, unit sekolah, jenjang dan tingkat`.

---

### Task 2: Kalender akademik + helper hari efektif

**Files:**
- Create: `models/tahun_ajaran.py`, `models/hari_libur.py`, `tests/test_kalender.py`
- Modify: `models/res_company.py`, `security/ir.model.access.csv`, `models/__init__.py`, `tests/__init__.py`

**Interfaces:**
- Produces `nti_edu.tahun.ajaran`: name (required), tanggal_mulai, tanggal_selesai (required), is_aktif, semester_ids.
  `@api.model _get_aktif() -> recordset` (maks. 1, boleh kosong). Tanpa `company_id`.
- Produces `nti_edu.semester`: tahun_ajaran_id (required, `ondelete='restrict'`), jenis Selection
  `[('ganjil','Ganjil'),('genap','Genap')]`, tanggal_mulai, tanggal_selesai, is_aktif; name compute
  `"<tahun> - Ganjil"`. `@api.model _get_aktif() -> recordset`. SQL unique (tahun_ajaran_id, jenis).
- Produces `nti_edu.hari.libur`: name, tanggal_mulai (required), tanggal_selesai (opsional), company_id (opsional),
  jenis Selection `nasional|sekolah|ujian|lainnya`.
- Produces `res.company._nti_edu_hari_efektif(tanggal: date) -> bool` (self = satu company): False bila Minggu;
  False bila Sabtu dan `nti_edu_hari_sekolah == '5'`; False bila ada hari libur dengan
  `company_id in (False, self.id, self.parent_id.id)` yang mencakup tanggal (`tanggal_selesai` kosong = satu hari).

- [ ] **Step 1: Tes gagal** `tests/test_kalender.py` (`TestKalender(NtiEduCommon)`), pakai tahun 2026/2027
  (2026-07-13 s.d. 2027-06-30):
  - `test_tanggal_terbalik_ditolak`: tanggal_selesai < tanggal_mulai → `ValidationError`.
  - `test_satu_tahun_aktif`: dua tahun ajaran `is_aktif=True` → `ValidationError`; `_get_aktif()` mengembalikan yang aktif.
  - `test_semester_di_luar_tahun_ditolak` dan `test_satu_semester_aktif_per_tahun`.
  - `test_hari_efektif_akhir_pekan`: 2026-07-18 (Sabtu) → False untuk unit 5 hari, True untuk unit 6 hari;
    2026-07-19 (Minggu) → False untuk keduanya; 2026-07-20 (Senin) → True.
  - `test_libur_unit_dan_yayasan`: libur 2026-08-17 tanpa company → False untuk smp & sma; libur 2026-08-18
    `company_id=unit_smp` → False untuk smp, True untuk sma; libur `company_id=yayasan` 2026-08-19 → False untuk keduanya.
  - `test_libur_satu_hari` (Review Focus 5): libur 2026-08-20 tanpa tanggal_selesai → 2026-08-20 False, 2026-08-21 True.
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestKalender` → gagal.
- [ ] **Step 3: Implementasi.** ACL: baca `group_base_pengguna`, CRUD `group_base_operator`.
- [ ] **Step 4: Jalankan** → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: kalender akademik dan hari efektif`.

---

### Task 3: Siswa & wali di `res.partner` + penjaga tulis

**Files:**
- Create: `models/res_partner.py`, `models/siswa_wali.py`, `tests/test_siswa.py`
- Modify: `security/ir.model.access.csv`, `models/__init__.py`, `tests/common.py` (helper `_buat_siswa`), `tests/__init__.py`

**Interfaces:**
- Produces `res.partner` fields:
  `nti_edu_is_siswa` Boolean; `nti_edu_nis` Char; `nti_edu_nisn` Char; `nti_edu_nik` Char;
  `nti_edu_jenis_kelamin` Selection `[('l','Laki-laki'),('p','Perempuan')]`; `nti_edu_tempat_lahir` Char;
  `nti_edu_tanggal_lahir` Date; `nti_edu_agama` Selection
  `islam|kristen|katolik|hindu|buddha|konghucu|lainnya`; `nti_edu_status` Selection
  `[('aktif','Aktif'),('lulus','Lulus'),('pindah','Pindah'),('keluar','Keluar')]` default `'aktif'`;
  `nti_edu_tanggal_masuk` Date; `nti_edu_wali_ids` O2m `nti_edu.siswa.wali`/`siswa_id`;
  `nti_edu_anak_ids` O2m `nti_edu.siswa.wali`/`partner_id`; `nti_edu_is_wali` Boolean compute stored dari
  `nti_edu_anak_ids`.
  **`groups='nti_edu_base.group_base_operator'`** pada: `nti_edu_nisn`, `nti_edu_nik`, `nti_edu_tempat_lahir`,
  `nti_edu_tanggal_lahir`, `nti_edu_agama`, `nti_edu_wali_ids`.
- Produces konstanta modul `FIELD_SISWA` (set nama semua field `nti_edu_*` siswa di atas + `'name'`, `'company_id'`)
  di `models/res_partner.py`; dipakai penjaga tulis.
- Produces `nti_edu.siswa.wali`: siswa_id (M2o res.partner, required, `ondelete='cascade'`, domain siswa),
  partner_id (M2o res.partner, required, `ondelete='restrict'`), hubungan Selection `ayah|ibu|wali`,
  is_kontak_utama, is_penanggung_biaya. SQL unique (siswa_id, partner_id). Saat baris dibuat, bila partner wali
  bukan siswa dan tidak punya user internal, `company_id` partner itu dikosongkan (sudo) — wali dipakai lintas unit (§II.2).
- Produces `tests/common.py`: `cls._buat_siswa(nama: str, unit, nis: str, **vals) -> res.partner` (dibuat sebagai
  superuser, `nti_edu_is_siswa=True`, `company_id=unit.id`).

- [ ] **Step 1: Tes gagal** `tests/test_siswa.py` (`TestSiswa(NtiEduCommon)`):
  - `test_nis_unik_per_unit`: NIS `T001` di unit_smp dua kali → `ValidationError`; `T001` di unit_sma → boleh.
  - `test_nisn_unik_global`: NISN sama di dua unit → `ValidationError`; NISN kosong boleh berulang.
  - `test_siswa_wajib_unit` (Review Focus 1): membuat partner `nti_edu_is_siswa=True` tanpa company → `ValidationError`.
  - `test_wali_ditandai`: menambah baris wali → `partner.nti_edu_is_wali` True; menghapus baris → False.
  - `test_wali_tanpa_unit`: partner wali dibuat dengan `company_id=unit_smp`, lalu dijadikan wali →
    `company_id` kosong dan partner itu terbaca oleh `user_guru_sma`.
  - `test_guru_tidak_baca_nik`: `siswa.with_user(user_guru_smp).read(['nti_edu_nik'])` → `AccessError`;
    `with_user(user_operator_smp)` → terbaca.
  - `test_guru_tidak_bisa_ubah_siswa`: user `group_base_pengguna` + `base.group_partner_manager` (buat di tes)
    `write({'name': 'X'})` pada siswa → `AccessError`; write field yang sama pada partner non-siswa → boleh.
  - `test_operator_bisa_ubah_siswa`: `with_user(user_operator_smp).write({'nti_edu_nis': 'T009'})` → berhasil.
  - `test_buat_siswa_oleh_non_operator_ditolak`: `create({'name':..,'nti_edu_is_siswa': True, 'company_id': unit_smp.id})`
    oleh user pengguna+partner_manager → `AccessError`.
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestSiswa` → gagal.
- [ ] **Step 3: Implementasi.** Constraint NIS/NISN/unit dengan `@api.constrains` Python (unik per company tidak bisa
  dengan SQL unique karena company bisa NULL di partner lain). Penjaga di `res.partner.write`/`create`: bila
  `not self.env.su`, user bukan `group_base_operator`, dan (record yang ditulis `nti_edu_is_siswa` **dan** `vals`
  menyentuh `FIELD_SISWA`) atau (`create` dengan `nti_edu_is_siswa=True`) → `AccessError(_("Hanya Operator Data Sekolah yang boleh mengubah data siswa."))`.
  ACL `nti_edu.siswa.wali`: baca pengguna, CRUD operator.
- [ ] **Step 4: Jalankan** → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: data siswa dan wali di res.partner`.

---

### Task 4: Mapel, ruang, rombel & keanggotaan (riwayat kelas)

**Files:**
- Create: `models/mapel.py`, `models/ruang.py`, `models/rombel.py`, `tests/test_rombel.py`
- Modify: `models/res_partner.py`, `security/ir.model.access.csv`, `models/__init__.py`, `tests/__init__.py`

**Interfaces:**
- Consumes: `nti_edu.tahun.ajaran._get_aktif()` (Task 2), field siswa (Task 3).
- Produces `nti_edu.mapel`: name, kode, kelompok Selection `[('umum','Umum'),('kejuruan','Kejuruan'),('mulok','Muatan Lokal')]`,
  company_id opsional. `nti_edu.ruang`: name, kode, jenis Selection `kelas|lab|aula|lapangan|lainnya`, kapasitas,
  company_id (required, default company aktif).
- Produces `nti_edu.rombel`: name, tahun_ajaran_id (required, `ondelete='restrict'`), tingkat_id (required),
  jurusan_id, company_id (required, default `self.env.company`), wali_kelas_id M2o `res.users`, ruang_id,
  anggota_ids O2m, jumlah_siswa compute (anggota tanpa tanggal_keluar). SQL unique (name, tahun_ajaran_id, company_id).
  `_check_company_auto = True`.
- Produces `nti_edu.rombel.anggota`: rombel_id (required, `ondelete='cascade'`), siswa_id (required, domain siswa),
  tahun_ajaran_id related `rombel_id.tahun_ajaran_id` stored, company_id related `rombel_id.company_id` stored,
  no_absen Integer, tanggal_masuk Date, tanggal_keluar Date.
- Produces di `res.partner`: `nti_edu_anggota_ids` O2m `nti_edu.rombel.anggota`/`siswa_id`;
  `nti_edu_rombel_aktif_id` M2o `nti_edu.rombel` compute stored, depends
  `nti_edu_anggota_ids.rombel_id.tahun_ajaran_id.is_aktif`, `nti_edu_anggota_ids.tanggal_keluar`;
  method `_nti_edu_rombel_pada(tanggal: date) -> nti_edu.rombel` (anggota yang tahun ajarannya mencakup tanggal dan
  belum keluar pada tanggal itu; kosong bila tidak ada).

- [ ] **Step 1: Tes gagal** `tests/test_rombel.py` (`TestRombel(NtiEduCommon)`), siapkan tahun 2026/2027 aktif dan
  2025/2026 tidak aktif, rombel "VII A" (smp, 2025/26), "VIII A" (smp, 2026/27), "X IPA 1" (sma, 2026/27):
  - `test_satu_rombel_per_tahun`: siswa di dua rombel tahun yang sama (keduanya tanpa tanggal_keluar) → `ValidationError`;
    bila yang lama diberi tanggal_keluar → boleh.
  - `test_rombel_aktif_dan_riwayat`: siswa anggota VII A (2025/26) dan VIII A (2026/27) → `nti_edu_rombel_aktif_id ==
    VIII A`; `_nti_edu_rombel_pada(date(2025, 10, 1)) == VII A`.
  - `test_jumlah_siswa`: dua anggota, satu keluar → `jumlah_siswa == 1`.
  - `test_anggota_beda_unit_ditolak` (Review Focus 3): siswa unit_smp ke rombel "X IPA 1" (sma) → `ValidationError`.
  - `test_hapus_tahun_ajaran_berrombel_ditolak` (Review Focus 4): `unlink()` tahun 2026/27 → error
    (`UserError`/`IntegrityError`), rombel tetap ada.
  - `test_nama_rombel_unik`: "VIII A" kedua di smp 2026/27 → error; "VIII A" di sma → boleh.
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestRombel` → gagal.
- [ ] **Step 3: Implementasi.** Constraint satu-rombel: cari anggota lain dengan siswa & tahun ajaran sama, keduanya
  tanpa tanggal_keluar. Constraint unit: `anggota.siswa_id.company_id == anggota.company_id`. ACL: mapel/ruang baca
  pengguna, CRUD admin; rombel/anggota baca pengguna, CRUD operator.
- [ ] **Step 4: Jalankan** → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: mapel, ruang, rombel dan riwayat kelas`.

---

### Task 5: Aturan multi-unit dan grup eksternal

**Files:**
- Create: `security/nti_edu_rules.xml`, `tests/test_akses.py`
- Modify: `__manifest__.py`

**Interfaces:**
- Produces record rule global (tanpa `groups`) `['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`
  untuk `nti_edu.jurusan`, `nti_edu.hari.libur`, `nti_edu.mapel`, `nti_edu.ruang`, `nti_edu.rombel`,
  `nti_edu.rombel.anggota`. Siswa (partner) memakai `base.res_partner_rule` bawaan — tidak ditambah.
- Produces rule `rule_partner_eksternal` di `res.partner`, `groups = group_base_eksternal`, domain
  `[('nti_edu_is_siswa', '=', False), ('nti_edu_is_wali', '=', False)]`, semua perm.

- [ ] **Step 1: Tes gagal** `tests/test_akses.py` (`TestAkses(NtiEduCommon)`), satu siswa smp dengan satu wali,
  satu siswa sma, rombel di masing-masing unit:
  - `test_guru_unit_lain_tidak_lihat`: `env['res.partner'].with_user(user_guru_sma).search([('nti_edu_is_siswa','=',True)])`
    tidak memuat siswa smp; `env['nti_edu.rombel'].with_user(user_guru_sma).search([])` tidak memuat rombel smp.
  - `test_guru_unit_sama_lihat`: `user_guru_smp` menemukan siswa smp dan rombelnya.
  - `test_eksternal_tidak_lihat_siswa_wali`: `with_user(user_eksternal)` `search([('id','in',[siswa.id, wali.id])])`
    pada `res.partner` → kosong; `name_search(siswa.name)` → kosong; partner biasa tetap terlihat.
  - `test_eksternal_tanpa_akses_rombel`: `env['nti_edu.rombel'].with_user(user_eksternal).search([])` → `AccessError`
    (grup eksternal tidak meng-imply pengguna).
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestAkses` → gagal pada rombel lintas unit dan eksternal.
- [ ] **Step 3: Implementasi** `nti_edu_rules.xml` (tambahkan ke manifest setelah `ir.model.access.csv`).
- [ ] **Step 4: Jalankan** seluruh tes modul → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: aturan multi-unit dan grup eksternal`.

---

### Task 6: Wizard akun portal siswa & wali

**Files:**
- Create: `wizard/__init__.py`, `wizard/akun_portal_wizard.py`, `wizard/akun_portal_wizard_views.xml`, `tests/test_akun_portal.py`
- Modify: `__init__.py`, `security/ir.model.access.csv`, `__manifest__.py`, `models/res_partner.py`

**Interfaces:**
- Consumes: field siswa/wali (Task 3), `res.company.nti_edu_kode` (Task 1).
- Produces `nti_edu.akun.portal.wizard` (TransientModel): partner_id (required), login (compute dari partner,
  bisa diubah), `password_awal` Char readonly, `state` Selection `[('isi','Isi'),('selesai','Selesai')]`.
  `action_buat() -> dict` (action yang membuka ulang wizard dalam state `selesai`).
- Produces `res.partner._nti_edu_login_default() -> str`: siswa → NISN bila ada, selain itu
  `f"{company.nti_edu_kode}.{nis}"` (`UserError` bila kode unit atau NIS kosong); wali → email, bila kosong `phone`
  (`UserError` bila keduanya kosong).
- Produces `res.partner.action_nti_edu_buat_akun_portal() -> dict` (membuka wizard, hanya operator).
- Aturan `action_buat`: hanya `group_base_operator`; bila partner sudah punya user internal (`user_ids` dengan
  `share=False`) → `UserError(_("%s sudah punya akun internal; menu Anak Saya bisa dibuka dari akun itu."))`; bila
  sudah punya user portal → `UserError`; bila login sudah dipakai user lain → `UserError` yang menyebut login itu.
  Membuat user dengan `sudo()`: `groups_id = [(6, 0, [base.group_portal])]`, `partner_id`, `login`,
  `company_id`/`company_ids` = company partner (wali tanpa company → company aktif operator). Bila partner punya
  email → `user.action_reset_password()` (undangan); selain itu `password_awal = secrets.token_urlsafe(8)` diset ke
  user dan ditampilkan sekali di wizard.

- [ ] **Step 1: Tes gagal** `tests/test_akun_portal.py` (`TestAkunPortal(NtiEduCommon)`):
  - `test_login_nisn_diutamakan`: siswa NISN `0012345678` → login `0012345678`.
  - `test_login_kode_unit_nis`: siswa smp NIS `T001` tanpa NISN → `smpt.T001`; siswa sma NIS `T001` → `smat.T001`;
    keduanya bisa dibuat akunnya (tidak bentrok).
  - `test_akun_portal_dan_password_awal`: siswa tanpa email → user dibuat, `user.share` True,
    `has_group('base.group_portal')` True, `wizard.password_awal` terisi.
  - `test_wali_login_email`: wali dengan email → login = email, `password_awal` kosong.
  - `test_wali_pegawai_ditolak`: wali yang partner-nya milik `user_guru_smp` → `UserError`.
  - `test_login_bentrok_pesan_jelas` (Review Focus 2): user lain sudah ber-login `0012345678` → `UserError` dan
    pesannya memuat `0012345678`.
  - `test_hanya_operator`: wizard dijalankan `with_user(user_guru_smp)` → `AccessError`.
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestAkunPortal` → gagal.
- [ ] **Step 3: Implementasi** wizard + tombol "Buat Akun Portal" (view menyusul di Task 9; tombolnya dipasang di sana).
  ACL wizard: operator.
- [ ] **Step 4: Jalankan** → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: wizard akun portal siswa dan wali`.

---

### Task 7: Helper akses anak + portal "Anak Saya" / "Profil Saya"

**Files:**
- Create: `models/res_users.py`, `controllers/__init__.py`, `controllers/portal.py`, `views/portal_templates.xml`,
  `tests/test_portal.py`
- Modify: `__init__.py`, `models/__init__.py`, `__manifest__.py`

**Interfaces:**
- Produces `res.users._nti_edu_siswa_portal() -> res.partner` (self = satu user, hasil **sudo**): siswa aktif yang
  boleh dilihat user ini = partner user sendiri bila `nti_edu_is_siswa`, ditambah semua `siswa_id` dari baris
  `nti_edu.siswa.wali` dengan `partner_id = user.partner_id`. Berlaku untuk user portal **dan** internal.
- Produces controller `NtiEduPortal(CustomerPortal)`:
  - `_prepare_home_portal_values(counters)` menambah `nti_edu_anak_count` bila diminta.
  - `GET /my/anak` → daftar siswa dari helper (template `nti_edu_base.portal_my_anak`).
  - `GET /my/anak/<int:siswa_id>` → profil dasar (nama, NIS, unit, rombel aktif, tahun ajaran aktif); 404 bila
    `siswa_id` tidak ada di helper.
  - `GET /my/anak/<int:siswa_id>/pilih` → simpan `request.session['nti_edu_anak_id']`, redirect ke `/my`.
  - method `_nti_edu_anak_aktif() -> res.partner` (sudo): anak di session bila masih ada di helper, selain itu
    anak pertama. **Dipakai modul lain** untuk halaman portal mereka.
- Produces template `portal_my_home_nti_edu` (inherit `portal.portal_my_home`) yang menambah entri
  `portal.portal_docs_entry` "Anak Saya" (judul "Profil Saya" bila user sendiri siswa) dengan
  `placeholder_count="'nti_edu_anak_count'"`, url `/my/anak`.

- [ ] **Step 1: Tes gagal** `tests/test_portal.py`:
  - `TestHelperPortal(NtiEduCommon)`: wali dengan anak di smp **dan** sma → helper mengembalikan keduanya;
    siswa portal → hanya dirinya; user tanpa anak → kosong; `user_guru_smp` yang juga wali anak di sma → anak sma
    termasuk (pegawai-ortu).
  - `TestRutePortal(HttpCase)` (buat data sendiri di `setUp`, tanpa NtiEduCommon): login sebagai wali portal →
    `/my/anak` 200 dan memuat nama kedua anak; `/my/anak/<id anak orang lain>` → 404; login siswa →
    `/my/anak/<id dirinya>` 200; `/my/anak/<id>/pilih` lalu `_nti_edu_anak_aktif` → anak itu (uji lewat
    `/my/anak` yang menandai anak aktif).
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestHelperPortal,/nti_edu_base:TestRutePortal` → gagal.
- [ ] **Step 3: Implementasi.** Semua baca data di controller lewat `sudo()` **setelah** id dicek ada di helper.
- [ ] **Step 4: Jalankan** → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: portal Anak Saya dan helper akses anak`.

---

### Task 8: Wizard kenaikan kelas + status pindah/keluar

**Files:**
- Create: `wizard/kenaikan_kelas_wizard.py`, `wizard/kenaikan_kelas_wizard_views.xml`, `tests/test_kenaikan.py`
- Modify: `wizard/__init__.py`, `models/res_partner.py`, `security/ir.model.access.csv`, `__manifest__.py`

**Interfaces:**
- Consumes: rombel/anggota (Task 4).
- Produces `nti_edu.kenaikan.kelas.wizard`: rombel_asal_id (required), rombel_tujuan_id (default untuk semua baris),
  baris_ids O2m `nti_edu.kenaikan.kelas.baris` (siswa_id, rombel_tujuan_id, `aksi` Selection
  `[('naik','Naik/Pindah Rombel'),('tinggal','Tinggal Kelas'),('lulus','Lulus')]`). Baris terisi otomatis dari anggota
  aktif rombel asal; aksi default `lulus` bila `rombel_asal.tingkat_id.is_akhir`, selain itu `naik`.
  `action_proses() -> dict`.
- `action_proses`: untuk `naik`/`tinggal` membuat anggota baru di rombel tujuan baris (wajib diisi; tahun ajaran
  tujuan harus berbeda dari asal → `UserError`); untuk `lulus` set `nti_edu_status='lulus'` dan `tanggal_keluar`
  anggota asal = `rombel_asal.tahun_ajaran_id.tanggal_selesai`. Anggota lama tidak diubah selain itu.
- Produces di `res.partner`: saat `nti_edu_status` diubah ke `pindah`/`keluar`, anggota aktif (tanpa tanggal_keluar)
  diberi `tanggal_keluar = fields.Date.context_today(self)`.

- [ ] **Step 1: Tes gagal** `tests/test_kenaikan.py` (`TestKenaikan(NtiEduCommon)`):
  - `test_naik_kelas`: 3 siswa VII A (2025/26) → VIII A (2026/27): masing-masing punya 2 anggota, rombel aktif = VIII A,
    anggota VII A tetap ada.
  - `test_tingkat_akhir_lulus`: rombel IX (is_akhir) → semua baris default `lulus`; setelah proses status `lulus`,
    tanggal_keluar = 2026-06-30.
  - `test_tahun_tujuan_sama_ditolak`: rombel tujuan di tahun ajaran yang sama → `UserError`.
  - `test_status_pindah_tutup_anggota`: ubah status ke `pindah` → anggota aktif punya tanggal_keluar hari ini,
    `nti_edu_rombel_aktif_id` kosong.
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestKenaikan` → gagal.
- [ ] **Step 3: Implementasi.** ACL wizard & baris: operator.
- [ ] **Step 4: Jalankan** → lulus.
- [ ] **Step 5: Commit** `nti_edu_base: wizard kenaikan kelas dan penutupan keanggotaan`.

---

### Task 9: App "Data Sekolah" (view & menu)

**Files:**
- Create: `views/res_company_views.xml`, `views/jenjang_views.xml`, `views/jurusan_views.xml`,
  `views/tahun_ajaran_views.xml`, `views/hari_libur_views.xml`, `views/mapel_views.xml`, `views/ruang_views.xml`,
  `views/rombel_views.xml`, `views/siswa_views.xml`, `views/wali_views.xml`, `views/menu.xml`, `tests/test_tampilan.py`
- Modify: `__manifest__.py`

**Interfaces:**
- Produces action xmlid: `action_siswa` (res.partner, domain `[('nti_edu_is_siswa','=',True)]`, context
  `{'default_nti_edu_is_siswa': True}`, view kanban/list/form khusus), `action_rombel`, `action_wali`
  (domain `[('nti_edu_is_wali','=',True)]`), `action_tahun_ajaran`, `action_hari_libur`, `action_unit`
  (res.company), `action_jenjang`, `action_jurusan`, `action_mapel`, `action_ruang`.
- Produces menu root `menu_data_sekolah` "Data Sekolah" (groups pengguna) dengan struktur persis §II.4; submenu
  Konfigurasi groups `group_base_admin`.
- Form siswa: notebook dengan page `page_data_pribadi`, `page_wali`, `page_riwayat_kelas` (xmlid page dipakai modul
  lain untuk menambah tab sesudahnya); tombol header "Buat Akun Portal" (`action_nti_edu_buat_akun_portal`,
  groups operator, `invisible="user_ids"`). Form rombel: page `page_anggota`. Tombol "Kenaikan Kelas" di form rombel.

- [ ] **Step 1: Tes gagal** `tests/test_tampilan.py` (`TestTampilan(NtiEduCommon)`):
  - `test_semua_action_terbuka`: untuk setiap action di atas, `env[action.res_model].with_user(user_operator_smp).get_views(...)`
    untuk tiap `view_mode` tanpa error.
  - `test_menu_konfigurasi_khusus_admin`: menu Konfigurasi tidak ada di `env['ir.ui.menu'].with_user(user_operator_smp)._visible_menu_ids()`,
    ada untuk user admin.
  - `test_form_siswa_guru`: `Form(siswa.with_user(user_guru_smp), view='nti_edu_base.view_siswa_form')` terbuka tanpa
    `AccessError` (field sensitif tersembunyi, bukan error).
- [ ] **Step 2: Jalankan** `/nti_edu_base:TestTampilan` → gagal.
- [ ] **Step 3: Implementasi** view & menu (tata letak bebas, §II.10).
- [ ] **Step 4: Jalankan** seluruh tes modul → lulus. Buka `http://localhost:8070` di DB `odoo2` setelah
  `-u nti_edu_base` dan periksa menu secara visual.
- [ ] **Step 5: Commit** `nti_edu_base: app Data Sekolah`.

---

### Task 10: Data demo + uji pasang tunggal akhir

**Files:**
- Create: `demo/nti_edu_demo.xml`, `tests/test_demo.py`
- Modify: `__manifest__.py` (`'demo': ['demo/nti_edu_demo.xml']`)

**Interfaces:**
- Produces demo sesuai §II.7: yayasan "Yayasan Pendidikan Nusantara" (xmlid `demo_yayasan`), unit `demo_unit_smp`
  (kode `smp1`) & `demo_unit_sma` (kode `sma1`), tahun ajaran berjalan aktif + 2 semester, 4 rombel (2 per unit),
  20 siswa, wali (termasuk `demo_wali_bersaudara` dengan satu anak di SMP dan satu di SMA), 3 user guru
  (satu wali kelas), 1 operator, 1 user portal wali (`demo_wali_bersaudara`), 1 user portal siswa, 3 hari libur.
  Semua user demo berpassword sama dengan login dan disebut di `description` manifest.

- [ ] **Step 1: Tes gagal** `tests/test_demo.py` (`TestDemo(TransactionCase)`), dilewati (`self.skipTest`) bila
  `env.ref('nti_edu_base.demo_yayasan', raise_if_not_found=False)` kosong:
  - jumlah siswa demo 20; `demo_wali_bersaudara` punya user portal dan helper `_nti_edu_siswa_portal()` mengembalikan
    2 anak di dua unit berbeda; tahun ajaran aktif ada.
- [ ] **Step 2: Jalankan** di DB baru dengan demo → gagal.
- [ ] **Step 3: Implementasi** demo (`noupdate="1"`).
- [ ] **Step 4: Jalankan** `.\scripts\uji_tunggal.ps1 -Modul nti_edu_base` → `0 failed, 0 error(s)` (semua tes,
  termasuk dengan demo terpasang).
- [ ] **Step 5: Commit** `nti_edu_base: data demo` lalu `git push`.
