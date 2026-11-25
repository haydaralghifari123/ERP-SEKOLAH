# `nti_edu_pegawai` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modul baru `nti_edu_pegawai`: profil kepegawaian guru & staf (sekali per orang, tampil di tiap unit), akun login guru, penempatan lintas unit, dan pencabutan akses saat keluar unit.

**Architecture:** Addon baru di `D:/odoo2/nti_edu_pegawai`, depends `nti_edu_base` + `hr`. Data per orang di `res.partner` (kontak kerja yang dibagi semua `hr.employee` milik satu user, perilaku standar Odoo 18); data per unit di `hr.employee`. Penulisan profil lewat `sudo()` di balik penjaga "memegang semua unit orang itu atau HRD". Tidak ada modul lain yang bergantung padanya.

**Tech Stack:** Odoo 18.0 Community (`hr`), Python 3, XML views, tour `web_tour` untuk uji asap browser.

**Spec:** `D:/odoo2/docs/superpowers/specs/2026-11-25-nti-edu-pegawai-design.md` (induk: `2026-11-24-nti-edu-arsitektur-design.md` §I.4).

## Global Constraints

- Odoo **18.0 Community** saja; tanpa Enterprise/OCA.
- `__manifest__.py`: `'depends': ['nti_edu_base', 'hr']`, `'version': '18.0.1.0.0'`, `'license': 'LGPL-3'`, `'category': 'Education'`, `'application': False`, tanpa `auto_install`. Tidak depend ke modul fitur NTI Edu lain.
- Field baru di model standar (`res.partner`, `hr.employee`, `res.users`) **selalu** berawalan `nti_edu_`; model baru `nti_edu.<nama>`; field base (`nti_edu_nik`, dll.) **tidak** didefinisikan ulang.
- Nama field/model/pesan/komentar Bahasa Indonesia; pesan galat lewat `_()`; pesan galat keunikan NUPTK/NIP tidak menyebut nama/unit pemilik.
- View Odoo 18: `<list>`, ekspresi `invisible=`/`readonly=`, kanban `t-name="card"` tanpa `kanban_image`/`user_context`.
- Tes: `@tagged('post_install', '-at_install')`, data dibuat sendiri (tidak bergantung demo, tetap lulus dengan demo).
- Commit tanpa `Co-Authored-By` dan tanpa menyebut Claude; pesan `nti_edu_pegawai: <ringkasan Bahasa Indonesia>`.
- Perintah tes (PowerShell, bukan Git Bash), DB tes **`nti_pegawai_tes`** (pertama `-i`, berikutnya `-u`):
  ```
  & "D:/Program Files/python/python.exe" "D:/Program Files/server/odoo-bin" --config=D:/odoo2/.odoo-test.conf -d nti_pegawai_tes -i nti_edu_pegawai --test-tags /nti_edu_pegawai --stop-after-init --http-port 8079 --db-filter=.* --log-level=test
  ```
  Lulus = `0 failed, 0 error(s)`. Akhir tiap task: suite `/nti_edu_pegawai` + `scripts/uji_tunggal.ps1 -Modul nti_edu_pegawai`.
- Jangan sentuh `odoo.conf`, DB `odoo2`, atau Odoo pengguna (debugger VS Code) / ngrok di port 8070.

## Review Focus

1. Guru di SMP dan SMA: NUPTK diubah dari record SMA → record SMP menampilkan nilai baru; TU yang hanya memegang SMA ditolak mengubahnya (Task 2).
2. TU satu unit tidak bisa menambah unit ke akun siapa pun — lewat `user_id`, Buat Akun Login, atau Tempatkan di Unit Lain (Task 2, 4, 5).
3. TU SMA membuka pegawai SMA yang kontaknya dulu milik SMP: field profil tampil tanpa `AccessError` (Task 5, kontak dikosongkan company-nya).
4. Arsip pegawai terakhir → akun nonaktif; arsip salah satu dari dua unit → hanya unit itu dicabut (Task 6).
5. Galat NUPTK/NIP ganda tidak membocorkan nama/unit pemegang lain (Task 1).

---

### Task 1: Kerangka modul, grup, dan model data

**Files:**
- Create: `nti_edu_pegawai/__init__.py`, `__manifest__.py`, `models/__init__.py`, `models/res_partner.py`, `models/hr_employee.py`, `models/sertifikasi.py`, `security/nti_edu_pegawai_security.xml`, `security/ir.model.access.csv`, `tests/__init__.py`, `tests/common.py`, `tests/test_model.py`

**Interfaces:**
- Produces:
  - Kategori `nti_edu_pegawai.module_category_nti_edu_pegawai` ("NTI Edu / Pegawai"); grup `nti_edu_pegawai.group_pegawai_operator` (implies `nti_edu_base.group_base_pengguna`, `hr.group_hr_user`), `nti_edu_pegawai.group_pegawai_hrd` (implies operator).
  - `res.partner`: `nti_edu_nuptk`, `nti_edu_nip` (Char), `nti_edu_status_kepegawaian` (Selection `pns`,`pppk`,`gty`,`gtt`,`honorer`,`lainnya`), `nti_edu_pendidikan_terakhir` (Selection `sma`,`d1`,`d2`,`d3`,`d4`,`s1`,`s2`,`s3`), `nti_edu_bidang_studi` (Char), `nti_edu_sertifikasi_ids` (O2m), `nti_edu_is_pegawai` (Boolean compute stored: punya `hr.employee` aktif yang `work_contact_id` = partner). Semua kecuali `nti_edu_is_pegawai` ber-`groups='nti_edu_pegawai.group_pegawai_operator'`.
  - `nti_edu.pegawai.sertifikasi`: `partner_id` (M2o wajib, ondelete cascade), `jenis` (Selection `pendidik`,`lainnya`, default `pendidik`), `nomor` (Char), `tahun` (Integer), `bidang` (Char), `mapel_id` (M2o `nti_edu.mapel`), `lampiran` (Binary, attachment=True).
  - `hr.employee`: `nti_edu_jenis_ptk` (Selection `guru_mapel`,`guru_kelas`,`guru_bk`,`kepala_sekolah`,`wakil_kepala`,`tendik_admin`,`pustakawan`,`laboran`,`lainnya`), `nti_edu_tmt` (Date); constraint `company_id.nti_edu_jenis == 'unit'`.
  - `tests/common.py` `NtiPegawaiCommon(TransactionCase)` dengan `yayasan`, `unit_smp`, `unit_sma` (unit dengan `nti_edu_kode`), user `tu_smp` (operator pegawai, SMP), `tu_sma`, `tu_dua` (operator pegawai, SMP+SMA), `hrd` (HRD, SMP+SMA), `guru_smp` (`group_base_pengguna` saja), helper `_buat_pegawai(nama, unit, **vals)` sebagai superuser.

- [ ] **Step 1: Tes gagal** `TestModel`:
  - `test_instal_dan_grup`: modul terpasang; `group_pegawai_hrd` implies operator; operator implies `group_base_pengguna` dan `hr.group_hr_user`.
  - `test_nuptk_unik_tanpa_bocor`: dua orang beda unit dengan NUPTK sama → `ValidationError`; pesan tidak memuat nama orang pertama maupun nama unitnya. Sama untuk NIP; NUPTK kosong boleh berulang; berlaku juga terhadap kontak arsip.
  - `test_pegawai_wajib_unit`: pegawai dengan `company_id=yayasan` → `ValidationError`.
  - `test_guru_tidak_baca_profil`: `guru_smp` membaca `nti_edu_nuptk`/`nti_edu_nip` kontak pegawai → `AccessError`.
  - `test_penanda_pegawai`: kontak kerja pegawai aktif `nti_edu_is_pegawai` True; setelah pegawai diarsipkan False.
- [ ] **Step 2: Jalankan** dengan `-i nti_edu_pegawai` (DB baru) → gagal karena modul/field belum ada.
- [ ] **Step 3: Implementasi** sesuai Interfaces. Keunikan dicek dengan `sudo().with_context(active_test=False)`. ACL sertifikasi: operator baca/tulis/buat, hapus hanya HRD.
- [ ] **Step 4: Suite + `uji_tunggal.ps1 -Modul nti_edu_pegawai`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_pegawai: kerangka modul, grup, profil kepegawaian dan sertifikasi`

### Task 2: Penjaga tulis profil, user_id, dan hapus

**Files:**
- Modify: `nti_edu_pegawai/models/res_partner.py`, `models/hr_employee.py`, `models/sertifikasi.py`
- Test: `nti_edu_pegawai/tests/test_penjaga.py`

**Interfaces:**
- Produces:
  - `FIELD_PROFIL = {'nti_edu_nuptk','nti_edu_nip','nti_edu_status_kepegawaian','nti_edu_pendidikan_terakhir','nti_edu_bidang_studi','nti_edu_sertifikasi_ids'}`.
  - `res.partner._nti_edu_boleh_ubah_profil_pegawai(self) -> bool` (satu kontak; benar bila `env.su`, user di `group_pegawai_hrd` dan memegang semua unit pegawai aktif orang itu, atau user di `group_pegawai_operator` dan **semua** unit pegawai aktif orang itu ⊆ `env.user.company_ids`; kontak tanpa pegawai aktif → hanya HRD/su).
  - `hr.employee`: field profil terkait yang **dapat diedit** dari form pegawai (nama sama dengan field partner, ber-`groups` operator, compute dari `work_contact_id.sudo()`, inverse menulis lewat `sudo()` setelah penjaga); `nti_edu_nik` (Char, groups operator pegawai) proxy ke `work_contact_id.nti_edu_nik` milik base dengan penjaga yang sama.
- Consumes: Task 1.

- [ ] **Step 1: Tes gagal** `TestPenjaga` (pegawai `budi` di SMP+SMA, kontak sama):
  - `test_tu_dua_unit_ubah_profil_terlihat_di_keduanya`: `tu_dua` menulis `nti_edu_nuptk` di record SMA → record SMP membaca nilai yang sama.
  - `test_tu_satu_unit_ditolak`: `tu_sma` menulis `nti_edu_nuptk` budi → `AccessError`; nilai tidak berubah. Sama lewat membuat/mengubah `nti_edu.pegawai.sertifikasi` budi.
  - `test_tu_satu_unit_boleh_untuk_pegawai_unitnya`: pegawai `sari` hanya di SMP; `tu_smp` mengubah profil & menambah sertifikasi → berhasil.
  - `test_nik_satu_per_orang`: `tu_dua` mengisi `nti_edu_nik` di record SMP → `work_contact_id.nti_edu_nik` (base) terisi; terbaca dari record SMA.
  - `test_tu_tidak_isi_user_id`: `tu_smp` menulis `user_id` pada pegawai → `AccessError`; HRD boleh.
  - `test_hapus_hanya_hrd`: `tu_smp` unlink pegawai/sertifikasi → `AccessError`; `hrd` boleh.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi** penjaga di `res.partner.write` (bila `FIELD_PROFIL & vals` dan bukan su) dan di create/write/unlink sertifikasi (cek `partner_id`); field profil di `hr.employee` sesuai Interfaces; tolak `user_id` di `hr.employee.create/write` bagi non-HRD non-su; unlink pegawai hanya HRD (ACL `perm_unlink` operator = 0 untuk `hr.employee` lewat rule/override, karena `hr.group_hr_user` punya hapus — gunakan override `unlink`). Pesan: `_("Profil kepegawaian hanya boleh diubah HRD atau TU yang memegang semua unit tempat pegawai ini bekerja.")`.
- [ ] **Step 4: Suite + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_pegawai: penjaga profil lintas unit, user_id hanya HRD, hapus hanya HRD`

### Task 3: Menu dan tampilan

**Files:**
- Create: `nti_edu_pegawai/views/hr_employee_views.xml`, `views/sertifikasi_views.xml`, `views/menu.xml`, `tests/test_tampilan.py`
- Modify: `__manifest__.py` (`data`)

**Interfaces:**
- Produces: action `nti_edu_pegawai.action_pegawai` (`hr.employee`, `view_mode` `kanban,list,form`, view sendiri `view_pegawai_kanban`/`view_pegawai_list`/`view_pegawai_form`), menu `nti_edu_pegawai.menu_pegawai` di bawah `nti_edu_base.menu_data_sekolah` (groups operator pegawai); tab "Kepegawaian" (`page_kepegawaian`) berisi field profil (Task 2), `nti_edu_nik`, sertifikasi (list editable), `nti_edu_jenis_ptk`, `nti_edu_tmt`.
- Consumes: Task 1–2.

- [ ] **Step 1: Tes gagal** `TestTampilan`: menu terlihat untuk `tu_smp`/`hrd`, tidak untuk `guru_smp`; `get_views` action untuk `tu_smp` memuat kanban/list/form; arch form memuat `page[@name="page_kepegawaian"]` dengan `nti_edu_nuptk`; kanban tanpa `kanban_image`.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi** view & menu (kanban `card`: foto `avatar_128` widget image, nama, unit, jenis PTK).
- [ ] **Step 4: Suite + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_pegawai: menu Data Sekolah > Pegawai dan tab Kepegawaian`

### Task 4: Wizard Buat Akun Login

**Files:**
- Create: `nti_edu_pegawai/wizard/__init__.py`, `wizard/akun_login_wizard.py`, `wizard/akun_login_wizard_views.xml`, `tests/test_akun_login.py`
- Modify: `__init__.py`, `__manifest__.py`, `security/ir.model.access.csv`, `views/hr_employee_views.xml` (tombol header "Buat Akun Login", invisible bila `user_id`)

**Interfaces:**
- Produces: `nti_edu.pegawai.akun.wizard` (`employee_id`, `login` (bawaan email kerja), `password_awal` readonly, `state`), `action_buat() -> dict`, `action_tutup() -> dict`; rule global `create_uid = user`, `_transient_max_hours = 0.1` (pola `nti_edu_base` akun portal wizard); `hr.employee.action_nti_edu_buat_akun_login() -> dict`.

- [ ] **Step 1: Tes gagal** `TestAkunLogin`:
  - `test_buat_akun_dengan_email`: pegawai SMP+SMA dengan email kerja; `tu_dua` → user internal: `share` False, grup `group_base_pengguna`, `company_ids` = SMP+SMA, `partner_id` = kontak kerja; `user_id` terisi di kedua record pegawai; `password_awal` kosong.
  - `test_tanpa_email_isi_login`: email kosong, login diketik → `password_awal` terisi; `action_tutup` mengosongkannya.
  - `test_sudah_punya_akun_ditolak`; `test_login_dipakai_ditolak` (`UserError`).
  - `test_tu_satu_unit_untuk_pegawai_dua_unit_ditolak`: `tu_smp` untuk pegawai SMP+SMA → `AccessError`, tidak ada user dibuat.
  - `test_guru_tidak_bisa`: `guru_smp` membuat wizard → `AccessError`.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi**: cek penjaga `_nti_edu_boleh_ubah_profil_pegawai()` pada kontak kerja sebelum `sudo()`; buat user lewat `sudo()` dengan `partner_id` = kontak kerja; undangan via `action_reset_password` dengan `create_user` context bila ada email, selain itu kata sandi acak (`secrets`) ditampilkan sekali.
- [ ] **Step 4: Suite + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_pegawai: wizard Buat Akun Login untuk pegawai`

### Task 5: Wizard Tempatkan di Unit Lain

**Files:**
- Create: `nti_edu_pegawai/wizard/penempatan_wizard.py`, `wizard/penempatan_wizard_views.xml`, `tests/test_penempatan.py`
- Modify: `wizard/__init__.py`, `__manifest__.py`, `security/ir.model.access.csv`, `views/hr_employee_views.xml` (tombol "Tempatkan di Unit Lain")

**Interfaces:**
- Produces: `nti_edu.pegawai.penempatan.wizard` (`employee_id`, `company_id` domain unit lain yang dipegang pemanggil, `nti_edu_jenis_ptk`, `nti_edu_tmt`), `action_tempatkan() -> dict` (membuka form pegawai baru).
- Consumes: Task 2 penjaga.

- [ ] **Step 1: Tes gagal** `TestPenempatan`:
  - `test_tempatkan_dengan_akun`: pegawai SMP punya user; `tu_dua` menempatkan di SMA → record baru di SMA dengan `user_id` & `work_contact_id` sama; `company_ids` user += SMA; kontak kerja `company_id` jadi kosong; `tu_sma` membaca `nti_edu_nuptk` record SMA tanpa galat.
  - `test_tempatkan_tanpa_akun`: tanpa user → record baru memakai `work_contact_id` yang sama.
  - `test_tu_tanpa_unit_tujuan_ditolak`: `tu_smp` memilih SMA → `AccessError`; tidak ada record dibuat.
  - `test_sudah_di_unit_itu_ditolak` (`UserError`).
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi** (create pegawai dengan `sudo()` setelah cek: pemanggil memegang unit asal & tujuan, unit tujuan berjenis unit; set `work_contact_id` eksplisit bila tanpa user).
- [ ] **Step 4: Suite + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_pegawai: wizard Tempatkan di Unit Lain`

### Task 6: Keluar unit mencabut akses

**Files:**
- Modify: `nti_edu_pegawai/models/hr_employee.py`
- Test: `nti_edu_pegawai/tests/test_keluar.py`

**Interfaces:**
- Produces: `hr.employee._nti_edu_sinkron_akses_akun()` dipanggil setelah `write({'active': False})` (dan `toggle_active`/`action_archive`): cabut unit dari `user_id.company_ids` bila tak ada pegawai aktif lain milik user itu di unit tsb; bila tak tersisa pegawai aktif, `user_id.active = False`. Semua lewat `sudo()`. Tidak mengaktifkan ulang akun saat pegawai diaktifkan.

- [ ] **Step 1: Tes gagal** `TestKeluar`: (a) user SMP+SMA, arsip record SMA → `company_ids` = SMP, user aktif, `company_id` user pindah ke SMP bila tadinya SMA; (b) arsip record terakhir → user `active` False; (c) aktifkan lagi pegawai → user tetap nonaktif; (d) pegawai tanpa user diarsipkan → tanpa galat.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi** sesuai Interfaces (jaga `company_id` user tetap di dalam `company_ids`).
- [ ] **Step 4: Suite + `uji_tunggal.ps1`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_pegawai: arsip pegawai mencabut unit dan menonaktifkan akun terakhir`

### Task 7: Data demo dan uji asap browser

**Files:**
- Create: `nti_edu_pegawai/demo/nti_edu_pegawai_demo.xml`, `static/tests/tours/nti_edu_pegawai_asap.js`, `tests/test_demo.py`, `tests/test_ui.py`
- Modify: `__manifest__.py` (`demo`, `assets` `web.assets_tests`, `description` berisi akun demo)

**Interfaces:**
- Consumes: semua task; xmlid demo base (`nti_edu_base` demo: unit SMP/SMA, user `operator.demo`, `guru1.demo`..`guru3.demo`) — cek nama persis di `nti_edu_base/demo/nti_edu_demo.xml`.

- [ ] **Step 1: Demo**: pegawai untuk operator & 3 guru demo (tertaut ke user mereka), satu guru di SMP **dan** SMA, satu kepala sekolah, satu tenaga administrasi tanpa akun, beberapa sertifikasi; user HRD demo `hrd.demo` (password = login) dengan SMP+SMA; `operator.demo` diberi `group_pegawai_operator`.
- [ ] **Step 2: Tes** `TestDemo` (lewati diri bila demo tidak ada): guru dua unit punya 2 record dengan kontak sama; `hrd.demo` ada. `TestUiPegawai(HttpCase)` dengan data sendiri: tour `nti_edu_pegawai_asap` sebagai TU dua unit — Data Sekolah › Pegawai, kanban → list → form (tab Kepegawaian), buka & batal wizard Buat Akun Login dan Tempatkan di Unit Lain; tiap langkah menunggu remah roti layar baru dan modal tertutup (pelajaran tour base); `start_tour(..., timeout=120)`. Buktikan RED dengan sementara merusak satu view (jangan di-commit).
- [ ] **Step 3: Suite `/nti_edu_pegawai`**, lalu jalankan juga `--test-tags /nti_edu_base,/nti_edu_pegawai` di `nti_pegawai_tes` (base tetap hijau dengan `hr` + pegawai terpasang), dan `uji_tunggal.ps1 -Modul nti_edu_pegawai` → semua `0 failed, 0 error(s)`.
- [ ] **Step 4: Commit** `nti_edu_pegawai: data demo dan uji asap browser`
