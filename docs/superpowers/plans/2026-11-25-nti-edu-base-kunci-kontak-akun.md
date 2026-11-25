# nti_edu_base — Kunci Kontak Akun Internal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operator Data Sekolah tidak bisa lagi mengubah email/telepon kontak milik akun internal orang lain (jalur ambil alih akun lewat reset kata sandi).

**Architecture:** `nti_edu_base.group_base_operator` mengimplikasikan `base.group_partner_manager`, jadi operator unit bisa menulis `res.partner` mana pun di unitnya, termasuk kontak akun TU/HRD/guru. Email kontak = email akun = tujuan reset kata sandi. Tambah penjaga di `res.partner.write` (pola sama dengan kunci kontak wali `FIELD_KONTAK_WALI` yang sudah ada).

**Tech Stack:** Odoo 18 Community, modul `nti_edu_base`.

**Spec:** docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md §II.5 (grup & hak akses). Temuan berasal dari review akhir `nti_edu_pegawai` (2026-11-25); pengguna menyetujui perbaikan ("ok kerjakan juga setelah task 8").

## Global Constraints

- Odoo **18.0 Community**; hanya modul `nti_edu_base` yang diubah; `nti_edu_base` tidak boleh bergantung pada modul NTI lain (tidak menyebut `hr` atau `nti_edu_pegawai`).
- Pesan galat Bahasa Indonesia via `_()`, tidak menyebut nama orang lain.
- Tes `@tagged('post_install', '-at_install')`, data sendiri.
- Perintah tes (PowerShell, bukan Git Bash): DB `nti_base_tes`, `-u nti_edu_base --test-tags /nti_edu_base`, `--config=D:/odoo2/.odoo-test.conf --http-port 8079 --db-filter=.* --log-level=test --stop-after-init`; lalu DB `nti_pegawai_tes` `-u nti_edu_base,nti_edu_pegawai --test-tags /nti_edu_base,/nti_edu_pegawai` (modul pegawai tetap hijau); lalu `scripts/uji_tunggal.ps1 -Modul nti_edu_base`. Lulus = `0 failed, 0 error(s)`.
- Commit `nti_edu_base: <ringkasan>`, tanpa `Co-Authored-By`, tanpa menyebut Claude.
- Jangan sentuh DB `odoo2`, `odoo.conf`, port 8070.

## Review Focus

- Pengguna mengubah email/telepon **akunnya sendiri** (preferensi, `/my/account` portal) harus tetap bisa.
- Administrator (`base.group_erp_manager`) dan superuser tetap bisa mengubah kontak akun siapa pun.
- Jalur sudo modul lain (mis. `nti_edu_pegawai` mengubah email kerja guru setelah penjaganya sendiri) tidak terpengaruh.
- Kontak tanpa akun internal (siswa, wali tanpa akun, kontak biasa) tetap mengikuti aturan lama (kunci wali tetap berlaku).
- Akun yang diarsipkan tetap dilindungi (`active_test=False`).

---

### Task 1: Kunci email/telepon kontak akun internal

**Files:**
- Modify: `nti_edu_base/models/res_partner.py` (`write`)
- Test: `nti_edu_base/tests/test_kontak_akun.py` (baru), `tests/__init__.py`

**Interfaces:**
- Produces: `res.partner._nti_edu_boleh_ubah_kontak_akun(self) -> bool` (satu kontak): benar bila `env.su`, user di `base.group_erp_manager`, kontak tidak punya user internal (`user_ids` dengan `share=False`, `active_test=False`), atau semua user internalnya = `env.user`.
- Penjaga di `write`: bila bukan su dan `FIELD_KONTAK_WALI & vals` (email, phone, mobile), untuk tiap record (sudo) yang punya user internal, panggil helper dengan env pemanggil; bila salah → `AccessError(_("Email dan telepon akun pengguna hanya bisa diubah oleh pemilik akun atau administrator."))`. Nilai yang sama dengan nilai lama tidak dianggap perubahan.

- [ ] **Step 1: Tes gagal** `TestKontakAkun`:
  - `test_operator_tak_bisa_ubah_email_akun_lain`: operator unit SMP menulis `email` pada kontak user internal (pengguna biasa, company SMP) → `AccessError`; email tidak berubah. Sama untuk `phone`, `mobile`, dan untuk akun yang diarsipkan.
  - `test_operator_tak_bisa_ubah_email_akun_operator_lain`: kontak user operator lain di unit yang sama → `AccessError`.
  - `test_pemilik_boleh_ubah_kontaknya`: user internal (pengguna biasa) menulis email kontaknya sendiri lewat `env.user.partner_id` → berhasil (bila hak tulis partner miliknya ada; bila tidak, uji lewat `res.users.write({'email': ...})` pada dirinya — jalur preferensi Odoo).
  - `test_admin_boleh`: user `base.group_erp_manager` mengubah email kontak operator → berhasil.
  - `test_kontak_tanpa_akun_tetap_bisa`: operator mengubah email kontak biasa / siswa di unitnya → berhasil (aturan lama tidak berubah).
  - `test_nilai_sama_tidak_ditolak`: operator menulis email yang sama dengan nilai lama pada kontak akun → tidak galat.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi** helper + penjaga sesuai Interfaces (letakkan setelah penjaga kontak wali yang ada; pakai pola `self.sudo()` untuk membaca `user_ids`).
- [ ] **Step 4: Suite** `/nti_edu_base` (nti_base_tes), `/nti_edu_base,/nti_edu_pegawai` (nti_pegawai_tes, tour ikut jalan), `uji_tunggal.ps1 -Modul nti_edu_base` → semua `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_base: email dan telepon akun internal hanya diubah pemilik atau administrator`
